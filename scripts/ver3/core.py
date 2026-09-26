"""Canonical dimensional search and rigid-link kinematics. No CAD dependency."""

from __future__ import annotations

import csv
from functools import lru_cache
import hashlib
import itertools
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(__file__).with_name("design.json")
CONFIG = json.loads(CONFIG_PATH.read_text())
OUT = ROOT / "docs" / "ver3"
LINKS = {
    "L_AB": ("A", "B"),
    "L_AC": ("A", "C"),
    "L_PC": ("P", "C"),
    "L_PBD": ("P", "B", "D"),
    "L_DE": ("D", "E"),
    "L_CEF": ("C", "E", "F"),
}


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def circle_intersection(p, r, q, s, branch):
    p, q = np.asarray(p, dtype=float), np.asarray(q, dtype=float)
    delta = q - p
    distance = float(np.linalg.norm(delta))
    if not abs(r - s) < distance < r + s:
        raise ValueError(f"Non-closing linkage: {distance=} {r=} {s=}")
    along = (r * r - s * s + distance * distance) / (2 * distance)
    height = math.sqrt(r * r - along * along)
    midpoint = p + along * delta / distance
    normal = np.array([-delta[1], delta[0]]) / distance
    pair = [midpoint + height * normal, midpoint - height * normal]
    if branch == "top":
        return max(pair, key=lambda v: v[1])
    if branch == "bottom":
        return min(pair, key=lambda v: v[1])
    if branch == "left":
        return min(pair, key=lambda v: v[0])
    raise ValueError(branch)


@lru_cache(maxsize=16384)
def gait(theta, mirrored=False):
    if mirrored:
        return {name: value * np.array([-1, 1])
                for name, value in gait(math.pi - theta).items()}
    c = CONFIG["linkage"]
    k = c["scale"]
    lengths = {key: value * k for key, value in c.items()
               if key in ("QP", "OQ", "OA", "AB", "BP", "AC", "PC", "BD",
                          "PD", "CE", "DE", "CF", "EF")}
    p = np.array([-lengths["QP"], -lengths["OQ"]])
    a = lengths["OA"] * np.array([math.cos(theta), math.sin(theta)])
    b = circle_intersection(a, lengths["AB"], p, lengths["BP"], "top")
    c_point = circle_intersection(a, lengths["AC"], p, lengths["PC"], "bottom")
    d = circle_intersection(b, lengths["BD"], p, lengths["PD"], "left")
    e = circle_intersection(c_point, lengths["CE"], d, lengths["DE"], "bottom")
    f = circle_intersection(c_point, lengths["CF"], e, lengths["EF"], "bottom")
    return dict(O=np.zeros(2), P=p, A=a, B=b, C=c_point, D=d, E=e, F=f)


def local_link(part_id):
    names = LINKS[part_id.removesuffix("_R")]
    points = gait(0, part_id.endswith("_R"))
    origin = points[names[0]]
    vec = points[names[1]] - origin
    angle = math.atan2(vec[1], vec[0])
    co, si = math.cos(angle), math.sin(angle)
    matrix = np.array([[co, si], [-si, co]])
    return [(matrix @ (points[n] - origin)).tolist() for n in names]


def pose(x, yz=(0, 0), angle=0, flip=False):
    """Local XY = walking plane, local Z = shaft axis. Row-major transform."""
    co, si = math.cos(angle), math.sin(angle)
    z = CONFIG["linkage"]["crank_height"]
    # A flipped part keeps its local x direction but reverses y and z.
    sign = -1 if flip else 1
    return [[0, 0, sign, x],
            [co, -sign * si, 0, float(yz[0])],
            [si, sign * co, 0, float(yz[1]) + z],
            [0, 0, 0, 1]]


def link_pose(part_id, x, theta, mirrored=False):
    points = gait(theta, mirrored)
    a, b = [points[n] for n in LINKS[part_id.removesuffix("_R")][:2]]
    vector = b - a
    return pose(x, a, math.atan2(vector[1], vector[0]))


def animated_transform(instance, theta, design):
    """Animate the exact assembly instance, never reconstruct visualization parts."""
    original = np.array(instance["transform"], dtype=float)
    motion = instance.get("motion")
    if not motion:
        return original.tolist()
    kind = motion["type"]
    if kind == "link":
        layout = axial_layout(design["structure"]["plate_thickness_mm"], motion["mirrored"], design.get("foot_offset", 0))
        return link_pose(motion["part_id"], motion["bay"] + layout[motion["part_id"].removesuffix("_R")],
                         theta + motion["phase"], motion["mirrored"])
    if kind == "joint":
        initial = gait(motion["phase"], motion.get("mirrored", False))[motion["node"]]
        current = gait(motion["phase"] + theta, motion.get("mirrored", False))[motion["node"]]
        original[1:3, 3] += current - initial
        return original.tolist()
    if kind not in ("shaft", "crank"):
        raise ValueError(f"Unknown motion {kind}")
    center = motion.get("center", [0, 0])
    angle = theta * motion.get("speed", 1)
    co, si = math.cos(angle), math.sin(angle)
    rotation = np.eye(4)
    rotation[1:3, 1:3] = [[co, -si], [si, co]]
    point = np.array([0, center[0], center[1] + CONFIG["linkage"]["crank_height"]])
    rotation[:3, 3] = point - rotation[:3, :3] @ point
    return (rotation @ original).tolist()


def axis_speeds(design):
    result = {"O": 1.0}
    for stage in reversed(design["stages"]):
        direction = 1 if stage["type"] == "belt" else -1
        result[stage["input_axis"]] = direction * stage["ratio"] * result[stage["output_axis"]]
    return result


def foot_centers(design, theta):
    feet = []
    for bay, phase in enumerate(CONFIG["linkage"]["phases"]):
        for mirrored in (False, True):
            layout = axial_layout(design["structure"]["plate_thickness_mm"], mirrored, design.get("foot_offset", 0))
            point = gait(theta + math.radians(phase), mirrored)["F"]
            feet.append([bay * CONFIG["linkage"]["bay_pitch"] + layout["L_CEF"] + 1.5,
                         float(point[0]), float(point[1]) + CONFIG["linkage"]["crank_height"]])
    return np.array(feet)


def walking_transform(instance, frame, design):
    return (np.array(frame["body_matrix"]) @
            np.array(animated_transform(instance, frame["theta"], design))).tolist()


def axial_layout(plate_thickness, mirrored=False, foot_offset=0):
    h = CONFIG["hardware"]
    left_hub = plate_thickness / 2 + 1
    left_cheek = left_hub + h["hub_thickness"]
    gap = left_cheek + h["cheek_thickness"]
    right_cheek = gap + h["crank_gap"]
    right_hub = right_cheek + h["cheek_thickness"]
    return {
        "left_hub": left_hub,
        "left_cheek": left_cheek,
        "gap": gap,
        "right_cheek": right_cheek,
        "right_hub": right_hub,
        "L_PBD": left_hub + (8 if mirrored else 4),
        "L_PC": left_hub + (16 if mirrored else 12),
        "L_AB": gap + (8.0 if mirrored else 0.6),
        "L_AC": gap + (11.7 if mirrored else 4.3),
        "L_DE": right_hub + (5 if mirrored else 1),
        "L_CEF": right_hub + (14 if mirrored else 10) + foot_offset,
    }


def involute(value):
    return math.tan(value) - value


def gear_metrics(module, pinion, wheel):
    g = CONFIG["gears"]
    alpha = math.radians(g["pressure_angle"])
    radii = [module * n / 2 for n in (pinion, wheel)]
    base = [r * math.cos(alpha) for r in radii]
    tips = [r + module for r in radii]
    roots = [r - g["dedendum_factor"] * module for r in radii]
    center = sum(radii)
    path = sum(math.sqrt(ra * ra - rb * rb) for ra, rb in zip(tips, base))
    path -= center * math.sin(alpha)
    contact = path / (math.pi * module * math.cos(alpha))
    # Half the total backlash is removed from each member's pitch thickness.
    half_thickness = [(math.pi * module / 2 - g["total_tangential_backlash"] / 2)
                      / (2 * r) for r in radii]
    tip_thickness = [
        2 * ra * (half + involute(alpha) -
                  involute(math.acos(rb / ra)))
        for ra, rb, half in zip(tips, base, half_thickness)
    ]
    approach = math.sqrt(tips[1] ** 2 - base[1] ** 2) - radii[1] * math.sin(alpha)
    recess = math.sqrt(tips[0] ** 2 - base[0] ** 2) - radii[0] * math.sin(alpha)
    return {
        "module": module, "pinion_teeth": pinion, "wheel_teeth": wheel,
        "ratio": wheel / pinion, "center_distance_mm": center,
        "pitch_diameters_mm": [2 * r for r in radii],
        "tip_diameters_mm": [2 * r for r in tips],
        "root_diameters_mm": [2 * r for r in roots],
        "contact_ratio": contact, "tip_thickness_mm": min(tip_thickness),
        "root_web_mm": min(roots) - (math.sqrt(2) * 8 + 2.2),
        "involute_interference_margin_mm": min(
            radii[0] * math.sin(alpha) - approach,
            radii[1] * math.sin(alpha) - recess),
        "radial_tip_root_clearance_mm": 0.25 * module,
        "total_tangential_backlash_mm": g["total_tangential_backlash"],
        "face_width_mm": g["face_width"],
        "pressure_angle_deg": g["pressure_angle"],
        "volume_proxy_mm3": math.pi * sum(r * r for r in radii) * g["face_width"],
    }


def gear_outline(module, teeth, samples=10):
    """Polygonal sampling of the true involute, with radial root extensions."""
    g = CONFIG["gears"]
    alpha = math.radians(g["pressure_angle"])
    rp = module * teeth / 2
    rb = rp * math.cos(alpha)
    rr = rp - 1.25 * module
    ra = rp + module
    half = (math.pi * module / 2 - g["total_tangential_backlash"] / 2) / (2 * rp)
    lower = max(rr, rb)

    def flank(r):
        t = math.sqrt(max(0, (r / rb) ** 2 - 1))
        return half + involute(alpha) - (t - math.atan(t))

    points = []
    for tooth in range(teeth):
        center = 2 * math.pi * tooth / teeth
        root_angle = flank(lower)
        points.append((rr * math.cos(center - root_angle),
                       rr * math.sin(center - root_angle)))
        for r in np.linspace(lower, ra, samples):
            angle = center - flank(float(r))
            points.append((r * math.cos(angle), r * math.sin(angle)))
        for angle in np.linspace(center - flank(ra), center + flank(ra), 5)[1:]:
            points.append((ra * math.cos(angle), ra * math.sin(angle)))
        for r in np.linspace(ra, lower, samples)[1:]:
            angle = center + flank(float(r))
            points.append((r * math.cos(angle), r * math.sin(angle)))
        points.append((rr * math.cos(center + root_angle),
                       rr * math.sin(center + root_angle)))
        next_angle = center + 2 * math.pi / teeth - root_angle
        for angle in np.linspace(center + root_angle, next_angle, 6)[1:-1]:
            points.append((rr * math.cos(angle), rr * math.sin(angle)))
    return points


def structure_nodes(center, tower=True):
    p = gait(0)["P"].tolist()
    nodes = {"O": [0, 0], "P": p, "J": [-p[0], p[1]],
             "U": CONFIG["structure"]["tie_nodes"][0],
             "V": CONFIG["structure"]["tie_nodes"][1]}
    edges = [("O", "P"), ("O", "J"), ("O", "U"), ("O", "V"),
             ("P", "U"), ("P", "V"), ("J", "U"), ("J", "V"), ("P", "J")]
    if tower:
        nodes["I"] = [0, center]
        edges += [("I", "O"), ("I", "U"), ("I", "V")]
    return nodes, edges


def truss_result(center, thickness, width):
    """Linear pin-jointed axial network, NOT a continuum/printed-part FEA."""
    cfg = CONFIG["structure"]
    nodes, edges = structure_nodes(center)
    names = list(nodes)
    coords = np.array(list(nodes.values()), dtype=float)
    size = 2 * len(names)
    stiffness = np.zeros((size, size))
    element_data = []
    area = thickness * width
    for first, second in edges:
        i, j = names.index(first), names.index(second)
        v = coords[j] - coords[i]
        length = float(np.linalg.norm(v))
        c, s = v / length
        transform = np.array([-c, -s, c, s])
        dofs = [2 * i, 2 * i + 1, 2 * j, 2 * j + 1]
        stiffness[np.ix_(dofs, dofs)] += (
            cfg["elastic_modulus_mpa"] * area / length * np.outer(transform, transform))
        element_data.append((dofs, transform, length))
    loads = np.zeros(size)
    loads[2 * names.index("O") + 1] = -cfg["crank_load_n"]
    loads[2 * names.index("P") + 1] = -cfg["pivot_load_n"]
    loads[2 * names.index("J") + 1] = -cfg["pivot_load_n"]
    loads[2 * names.index("I")] = cfg["rotor_load_n"]
    fixed = [2 * names.index(n) + k for n in ("U", "V") for k in (0, 1)]
    free = [i for i in range(size) if i not in fixed]
    displacements = np.zeros(size)
    displacements[free] = np.linalg.solve(stiffness[np.ix_(free, free)], loads[free])
    stresses = [cfg["elastic_modulus_mpa"] / length * float(transform @ displacements[dofs])
                for dofs, transform, length in element_data]
    longest = max(item[2] for item in element_data)
    out_of_plane = (cfg["out_of_plane_load_n"] * longest ** 3 /
                    (3 * cfg["elastic_modulus_mpa"] * width * thickness ** 3 / 12))
    # Conservative additive rib volumes; overlaps and preserve bosses measured in CAD later.
    volume = sum(item[2] for item in element_data) * area
    return {
        "plate_thickness_mm": thickness, "rib_width_mm": width,
        "axial_truss_displacement_mm": float(np.linalg.norm(displacements.reshape(-1, 2), axis=1).max()),
        "axial_truss_stress_mpa": max(abs(s) for s in stresses),
        "out_of_plane_cantilever_proxy_mm": out_of_plane,
        "rib_volume_proxy_mm3": volume,
        "surrogate": "2D linear axial truss plus separate longest-rib 1 N out-of-plane cantilever; not solid FEA",
    }


def selected_designs():
    return json.loads((OUT / "selected_designs.json").read_text())["designs"]


def _reference_search():
    g = CONFIG["gears"]
    s = CONFIG["structure"]
    states = [gait(math.radians(i / 2)) for i in range(721)]
    highest = max(float(p[n][1]) for p in states for n in ("A", "B", "C", "D", "E", "F"))
    rotor_min = highest + CONFIG["rotor"]["radius"] + CONFIG["rotor"]["sweep_clearance"]
    records = []
    feasible = []
    for module, pinion, wheel in itertools.product(
            g["modules"],
            range(g["pinion_bounds"][0], g["pinion_bounds"][1] + 1),
            range(g["wheel_bounds"][0], g["wheel_bounds"][1] + 1)):
        item = gear_metrics(module, pinion, wheel)
        failures = []
        criteria = {
            "ratio": 1 <= item["ratio"] <= 3.5,
            "rotor_sweep": item["center_distance_mm"] >= rotor_min,
            "envelope": item["center_distance_mm"] <= g["maximum_center_distance"],
            "contact": item["contact_ratio"] >= g["minimum_contact_ratio"],
            "tip": item["tip_thickness_mm"] >= g["minimum_tip_thickness"],
            "root_web": item["root_web_mm"] >= g["minimum_root_web"],
            "involute_interference": item["involute_interference_margin_mm"] >= 0,
            "guard_ground": CONFIG["linkage"]["crank_height"]
            - item["tip_diameters_mm"][1] / 2 - 6 >= g["minimum_guard_ground_clearance"],
        }
        failures = [key for key, ok in criteria.items() if not ok]
        row = {key: item[key] for key in
               ("module", "pinion_teeth", "wheel_teeth", "ratio",
                "center_distance_mm", "contact_ratio", "root_web_mm",
                "tip_thickness_mm", "volume_proxy_mm3")}
        row.update(feasible=not failures, rejected_by=";".join(failures))
        records.append(row)
        if not failures:
            feasible.append(item)
    selected = []
    for design_id, ratio, label in (
            ("A", g["baseline_ratio"], "Robust baseline"),
            ("B", g["low_input_torque_ratio"], "Lower required input torque")):
        subset = [x for x in feasible if abs(x["ratio"] - ratio) < 1e-10]
        if not subset:
            raise RuntimeError(f"No feasible gear pair at ratio {ratio}")
        best = min(subset, key=lambda x: (x["volume_proxy_mm3"],
                                         x["center_distance_mm"], x["module"]))
        selected.append(dict(id=design_id, name=label, gears=best,
                             structure=dict(style="solid",
                                            **truss_result(best["center_distance_mm"], 8, 14))))
    trials = []
    base = selected[0]["gears"]
    for thickness, width in itertools.product(s["thickness_bounds"], s["rib_width_bounds"]):
        trial = truss_result(base["center_distance_mm"], thickness, width)
        trial["feasible"] = (
            trial["axial_truss_displacement_mm"] <= s["maximum_truss_displacement"]
            and trial["axial_truss_stress_mpa"] <= s["allowable_axial_stress_mpa"]
            and trial["out_of_plane_cantilever_proxy_mm"] <= s["maximum_out_of_plane_proxy"])
        trials.append(trial)
    feasible_structures = [x for x in trials if x["feasible"]]
    if not feasible_structures:
        raise RuntimeError("No structure meets the declared surrogate constraints")
    light = min(feasible_structures, key=lambda x: x["rib_volume_proxy_mm3"])
    selected.append(dict(id="C", name="Parametrically generated rib structure",
                         gears=base, structure=dict(style="ribs", **light)))
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "gear_search.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    dump(OUT / "structure_search.json", trials)
    digest = hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest()
    result = {
        "config_sha256": digest, "gear_candidates": len(records),
        "feasible_gear_candidates": len(feasible),
        "structure_candidates": len(trials),
        "minimum_center_from_swept_linkage_mm": rotor_min,
        "objectives": {
            "A_B": "Minimize summed pitch-cylinder volume at the respective exact 2:1 / 3:1 ratios, subject to all recorded constraints.",
            "C": "Minimize additive rib volume over the stated width/thickness grid at A's gear geometry, subject to the recorded surrogate limits.",
        },
        "designs": selected,
    }
    dump(OUT / "selected_designs.json", result)
    print(json.dumps(result, indent=2))
    return result


def generate_search():
    from system_search import search
    return search()


if __name__ == "__main__":
    generate_search()
