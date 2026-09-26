"""Reproducible balanced-end drivetrain and constrained frame generation."""

from collections import Counter
import csv
import hashlib
import itertools
import json
import math

import numpy as np
from scipy.optimize import brentq
from scipy.spatial import Delaunay

from core import CONFIG, CONFIG_PATH, LINKS, OUT, dump, gait, gear_metrics

P, S, G = CONFIG["system"], CONFIG["structure"], CONFIG["gears"]


def intersections(first, radius, second, other_radius):
    first, second = np.asarray(first, float), np.asarray(second, float)
    delta = second-first
    distance = float(np.linalg.norm(delta))
    if distance < 1e-8 or distance > radius+other_radius or distance < abs(radius-other_radius):
        return []
    along = (radius*radius-other_radius*other_radius+distance*distance)/(2*distance)
    height = math.sqrt(max(0, radius*radius-along*along))
    middle = first+along*delta/distance
    normal = np.array([-delta[1], delta[0]])/distance
    return [(middle+sign*height*normal).tolist() for sign in (-1, 1)]


def belt_length(center, small, large):
    difference = large-small
    return (2*math.sqrt(center*center-difference*difference)+math.pi*(small+large)
            +2*difference*math.asin(difference/center))


def belt_stage():
    belt = P["belt"]
    radii = [teeth*belt["pitch"]/(2*math.pi) for teeth in belt["teeth"]]
    center = brentq(lambda c: belt_length(c, *radii)-belt["length"], 30, 500)
    small_wrap = math.pi-2*math.asin((radii[1]-radii[0])/center)
    return {
        "type": "belt", "ratio": 2.0, "pinion_teeth": 24, "wheel_teeth": 48,
        "center_distance_mm": center, "pitch_diameters_mm": [2*r for r in radii],
        "tip_diameters_mm": belt["flange_diameters"], "face_width_mm": 12,
        "volume_proxy_mm3": 23000/2.7+42000/1.2,
        "belt_pitch_length_mm": belt["length"], "belt_width_mm": belt["width"],
        "small_wrap_degrees": math.degrees(small_wrap),
        "engaged_small_teeth": small_wrap/(2*math.pi)*24,
        "belt_sku": belt["belt_sku"], "pulley_skus": belt["pulley_skus"],
        "mesh_efficiency_assumed": 0.95,
        "representation": "Purchased compatible HTD5M components; CAD envelopes, not manufacturing tooth profiles.",
    }


def belt_path(stage, axes, arc_samples=96):
    small = np.array(axes[stage["input_axis"]])
    large = np.array(axes[stage["output_axis"]])
    r, big_r = [d/2 for d in stage["pitch_diameters_mm"]]
    vector = large-small
    distance = float(np.linalg.norm(vector))
    direction = math.atan2(vector[1], vector[0])
    alpha = math.asin((big_r-r)/distance)
    high = direction+math.pi/2+alpha
    low = direction-math.pi/2-alpha
    unit = lambda angle: np.array([math.cos(angle), math.sin(angle)])
    p1, p2 = small+r*unit(high), large+big_r*unit(high)
    p3, p4 = large+big_r*unit(low), small+r*unit(low)
    points = [p1.tolist(), p2.tolist()]
    points += [(large+big_r*unit(a)).tolist() for a in np.linspace(high, low, arc_samples)[1:]]
    points += [p4.tolist()]
    points += [(small+r*unit(a)).tolist() for a in np.linspace(low, high-2*math.pi, arc_samples)[1:]]
    return points


def stage_bounds(stage, axes):
    points = [axes[stage["input_axis"]], axes[stage["output_axis"]]]
    radii = [d/2 for d in stage["tip_diameters_mm"]]
    margin = P["case_margin"]
    return [min(p[0]-r for p, r in zip(points, radii))-margin,
            max(p[0]+r for p, r in zip(points, radii))+margin,
            min(p[1]-r for p, r in zip(points, radii))-margin,
            max(p[1]+r for p, r in zip(points, radii))+margin]


def side_case(axes, stages, indices, side):
    participating = sorted({name for i in indices for name in (stages[i]["input_axis"], stages[i]["output_axis"])})
    circles = [(axes[name], max(radius/2, 22)+6) for i in indices
               for name, radius in zip((stages[i]["input_axis"], stages[i]["output_axis"]), stages[i]["tip_diameters_mm"])]
    rows = [min(axes[n][1] for n in participating)-12, max(axes[n][1] for n in participating)]
    posts = []
    for z in rows:
        limits = [(point[0]-math.sqrt(max(0, radius*radius-(z-point[1])**2)),
                   point[0]+math.sqrt(max(0, radius*radius-(z-point[1])**2)))
                  for point, radius in circles if abs(z-point[1]) < radius]
        if not limits:
            raise RuntimeError("No stage support envelope at proposed row")
        posts += [[min(x[0] for x in limits)-4, z], [max(x[1] for x in limits)+4, z]]
    cases = {}
    offset = 0
    for ordinal, index in enumerate(indices):
        stage = stages[index]
        belt = stage["type"] == "belt"
        stage["side"] = side
        stage["side_index"] = ordinal
        stage["body_offset"] = 26 if belt else 20+P["stage_pitch"]*ordinal
        stage["guard_back_offset"] = 18 if belt else 10+P["stage_pitch"]*ordinal
        stage["guard_depth"] = 35 if belt else 31
        stage["window_aperture_mm"] = 13 if belt else 10
        stage["window_screw_length_mm"] = 40 if belt else 35
        if belt:
            stage["carriage_screw_window_bore_mm"] = P["belt"]["carriage_screw_window_bore_mm"]
            stage["carriage_screw_window_points"] = [
                [axes[stage["input_axis"]][0]+y, axes[stage["input_axis"]][1]+z]
                for y in (-18, 18) for z in (-18, 18)]
        offset = max(offset, 64 if belt else stage["body_offset"]+32)
        bounds = stage_bounds(stage, axes)
        possibilities = []
        for row in (0, 1):
            pair = posts[row*2:row*2+2]
            extent = [min(bounds[0], *(p[0]-6 for p in pair)),
                      max(bounds[1], *(p[0]+6 for p in pair)),
                      min(bounds[2], pair[0][1]-6), max(bounds[3], pair[0][1]+6)]
            if max(extent[1]-extent[0], extent[3]-extent[2]) <= P["maximum_print_span"]:
                possibilities.append((extent[3]-extent[2], row, extent))
        if not possibilities:
            return None
        _, row, extent = min(possibilities)
        corners = [[x, z] for x in (bounds[0]+5, bounds[1]-5) for z in (bounds[2]+5, bounds[3]-5)]
        if any(math.dist(corner, post) < 8 for corner in corners for post in posts[row*2:row*2+2]):
            return None
        cases[str(index)] = dict(bounds=bounds, print_bounds=extent, mount_row=row,
                                 mount_posts=posts[row*2:row*2+2], cover_corners=corners)
    return dict(axes=participating, stage_indices=indices, posts=posts, stages=cases, front_offset=offset)


def frame_network(design, kind, width):
    if "frame_networks" in design and width == design["structure"]["rib_width_mm"]:
        saved = design["frame_networks"][kind]
        return saved["nodes"], saved["radii"], [tuple(edge) for edge in saved["edges"]]
    axes = design["axes"]
    front = kind.startswith("front_")
    side = kind.removeprefix("front_") if front else kind
    nodes, radii = {}, {}
    if not front:
        pivot = gait(0)["P"].tolist()
        nodes.update(O=axes["O"], PL=pivot, PR=[-pivot[0], pivot[1]],
                     T0=design["ties"][0], T1=design["ties"][1])
        radii.update(O=22, PL=10, PR=10, T0=8, T1=8)
    if kind != "core":
        names = design["case"][side]["axes"] if front else list(axes)
        for name in names:
            nodes[name] = axes[name]
            radii[name] = 24 if design["id"] == "A" and name == "I" else 22
        posts = design["case"][side]["posts"]
        for i, point in enumerate(posts):
            nodes[f"K{i}"], radii[f"K{i}"] = point, 8
        for i in (0, 1):
            nodes[f"W{i}"] = ((np.array(posts[i])+posts[i+2])/2).tolist()
            radii[f"W{i}"] = width/2
        for row in (0, 1):
            point = ((np.array(posts[2*row])+posts[2*row+1])/2).tolist()
            if all(math.dist(point, old) > 1e-6 for old in nodes.values()):
                nodes[f"B{row}"], radii[f"B{row}"] = point, width/2
    def permitted(p, q):
        if kind != "core":
            return True
        center, vector = np.array(axes["I"]), q-p
        t = np.clip(np.dot(center-p, vector)/np.dot(vector, vector), 0, 1)
        return np.linalg.norm(center-p-t*vector) >= design["rotor"]["radius"]+width/2+3

    for refinement in range(4):
        names = list(nodes)
        coords = np.array(list(nodes.values()), float)
        edges = set()
        for simplex in Delaunay(coords).simplices:
            for i, j in itertools.combinations(simplex, 2):
                a, b = sorted((int(i), int(j)))
                if permitted(coords[a], coords[b]):
                    edges.add((names[a], names[b]))
        new_points = []
        for a, b in sorted(edges):
            p, q = np.array(nodes[a]), np.array(nodes[b])
            if np.linalg.norm(q-p)-radii[a]-radii[b] > S["maximum_free_rib_span"]:
                midpoint = ((p+q)/2).tolist()
                if all(math.dist(midpoint, old) > 1e-6 for old in list(nodes.values())+new_points):
                    new_points.append(midpoint)
        if not new_points:
            break
        if refinement == 3:
            raise RuntimeError("Rib-span refinement did not converge within its declared bound")
        for i, point in enumerate(new_points):
            name = f"G{refinement}_{i}"
            nodes[name], radii[name] = point, width/2
    return nodes, radii, sorted(edges)


def stiffness_trial(design, thickness, width):
    maximum_d = maximum_stress = longest = volume = 0
    cases = []
    for kind, quantity in (("core", 2), ("left", 1), ("right", 1), ("front_left", 1), ("front_right", 1)):
        nodes, radii, edges = frame_network(design, kind, width)
        names = list(nodes)
        coords = np.array(list(nodes.values()))
        size = 2*len(names)
        matrix = np.zeros((size, size))
        elements = []
        for a, b in edges:
            i, j = names.index(a), names.index(b)
            delta = coords[j]-coords[i]
            length = float(np.linalg.norm(delta))
            c, s = delta/length
            transform = np.array([-c, -s, c, s])
            dofs = [2*i, 2*i+1, 2*j, 2*j+1]
            matrix[np.ix_(dofs, dofs)] += S["elastic_modulus_mpa"]*thickness*width/length*np.outer(transform, transform)
            elements.append((dofs, transform, length))
            longest = max(longest, length-radii[a]-radii[b])
            volume += quantity*length*thickness*width
        volume += quantity*sum(math.pi*r*r*thickness for r in radii.values())
        fixed_names = [f"K{i}" for i in range(4)] if kind.startswith("front") else ["T0", "T1"]
        fixed = [2*names.index(n)+k for n in fixed_names for k in (0, 1)]
        free = [i for i in range(size) if i not in fixed]
        forces, displacement = np.zeros(size), np.zeros(size)
        for name in names:
            # Shared conservative radial load includes A's provisional belt pretension.
            force = 30 if name in design["axes"] else 10 if name in ("PL", "PR") else 0
            forces[2*names.index(name)+1] = -force
        try:
            displacement[free] = np.linalg.solve(matrix[np.ix_(free, free)], forces[free])
        except np.linalg.LinAlgError:
            return dict(feasible=False, failure="singular network", plate_thickness_mm=thickness, rib_width_mm=width)
        stress = max(abs(S["elastic_modulus_mpa"]/length*float(t@displacement[dofs])) for dofs, t, length in elements)
        peak = float(np.linalg.norm(displacement.reshape(-1, 2), axis=1).max())
        maximum_d, maximum_stress = max(maximum_d, peak), max(maximum_stress, stress)
        cases.append(dict(frame=kind, nodes=len(nodes), members=len(edges), maximum_displacement_mm=peak))
    out_of_plane = S["out_of_plane_load_n"]*longest**3/(3*S["elastic_modulus_mpa"]*width*thickness**3/12)
    return dict(plate_thickness_mm=thickness, rib_width_mm=width, volume_proxy_mm3=volume,
                axial_truss_displacement_mm=maximum_d, axial_truss_stress_mpa=maximum_stress,
                out_of_plane_cantilever_proxy_mm=out_of_plane, longest_free_rib_mm=longest,
                feasible=maximum_d <= S["maximum_truss_displacement"] and maximum_stress <= S["allowable_axial_stress_mpa"]
                and out_of_plane <= S["maximum_out_of_plane_proxy"], cases=cases,
                surrogate="Executed axial-member network plus longest free-rib cantilever; no continuum FEA, fatigue or topology optimization.")


def moving_segments():
    first, second = [], []
    for angle in np.linspace(0, 2*math.pi, 361):
        for mirrored in (False, True):
            points = gait(angle, mirrored)
            for names in LINKS.values():
                pairs = list(zip(names, names[1:]+names[:1])) if len(names) == 3 else [(names[0], names[1])]
                for a, b in pairs:
                    first.append(points[a])
                    second.append(points[b])
    first, second = np.array(first), np.array(second)
    return first, second-first


def assess(ident, axes, stages, segments):
    for first, second in itertools.combinations(axes.values(), 2):
        if math.dist(first, second) < P["minimum_axis_spacing"]:
            return None, "bearing_seat_spacing"
    starts, vectors = segments
    denominator = (vectors*vectors).sum(axis=1)
    radius = P["rotor_radii"][ident]
    for name, point in axes.items():
        if name in ("O", "I"):
            continue
        if math.dist(point, axes["I"]) < radius+7:
            return None, "shaft_in_rotor_sweep"
        if point[1] < 56:
            delta = np.array(point)-starts
            t = np.clip((delta*vectors).sum(axis=1)/denominator, 0, 1)
            if np.linalg.norm(delta-t[:, None]*vectors, axis=1).min() < 8.5:
                return None, "shaft_in_leg_sweep"
    for stage in stages:
        for name, diameter in zip((stage["input_axis"], stage["output_axis"]), stage["tip_diameters_mm"]):
            for other, point in axes.items():
                if other not in (stage["input_axis"], stage["output_axis"]) and math.dist(point, axes[name]) < diameter/2+5:
                    return None, "foreign_shaft_at_stage"
    ties = None
    for halfwidth in range(45, 116, 5):
        candidate = [[-halfwidth, 57], [halfwidth, 57]]
        extra = 1.5 if ident == "A" else 0
        if any(math.dist(p, axes["I"]) < radius+11+extra for p in candidate):
            continue
        if any(math.dist(p, axis) < 28 for p in candidate for axis in axes.values()):
            continue
        ties = candidate
        break
    if ties is None:
        return None, "tie_or_rotor_clearance"
    cases = {}
    for side in ("left", "right"):
        indices = [i for i, stage in enumerate(stages) if stage["side"] == side]
        case = side_case(axes, stages, indices, side)
        if case is None:
            return None, "guard_print_span"
        cases[side] = case
    all_posts = cases["left"]["posts"]+cases["right"]["posts"]
    bounds_y = [min(min(p[0]-22 for p in axes.values()), min(p[0]-8 for p in all_posts), -ties[1][0]-8),
                max(max(p[0]+22 for p in axes.values()), max(p[0]+8 for p in all_posts), ties[1][0]+8)]
    max_z = max(p[1]+(24 if ident == "A" and n == "I" else 22) for n, p in axes.items())
    min_z = min(-20.92, min(p[1]-8 for p in all_posts))
    if max(bounds_y[1]-bounds_y[0], max_z-min_z) > P["maximum_print_span"]:
        return None, "frame_print_span"
    return dict(case=cases, ties=ties), None


def search():
    options = {}
    for ratio in (2, 3, 4, 5):
        options[ratio] = []
        for pinion in range(P["pinion_bounds"][0], P["pinion_bounds"][1]+1):
            if pinion*ratio > P["maximum_wheel_teeth"]:
                continue
            gear = gear_metrics(P["module"], pinion, pinion*ratio)
            if (gear["root_web_mm"] >= G["minimum_root_web"] and gear["contact_ratio"] >= G["minimum_contact_ratio"]
                    and gear["tip_thickness_mm"] >= G["minimum_tip_thickness"] and gear["involute_interference_margin_mm"] >= 0):
                options[ratio].append(dict(gear, type="spur", mesh_efficiency_assumed=0.9))
    segments = moving_segments()
    records, selected, counts = [], [], {}
    for ident in ("A", "B", "C"):
        ratios = P["stage_ratios"][ident]
        groups = [[belt_stage()], options[3]] if ident == "A" else [options[r] for r in ratios]
        feasible, rejected, tested = [], Counter(), 0
        for height in range(102, int(P["maximum_primary_height"])+1, 2):
            if height < P["rotor_radii"][ident]+55:
                continue
            for input_y in P["input_y_options"][ident]:
                for values in itertools.product(*groups):
                    names = ["I"]+[f"M{i}" for i in range(1, len(values))]+["O"]
                    stages = [dict(v, id=f"S{i+1}", input_axis=names[i], output_axis=names[i+1],
                                   side=P["stage_sides"][ident][i]) for i, v in enumerate(values)]
                    base = {"O": [0.0, 0.0], "I": [float(input_y), float(height)]}
                    if len(stages) == 2:
                        layouts = [dict(base, M1=p) for p in intersections(base["O"], stages[1]["center_distance_mm"],
                                                                         base["I"], stages[0]["center_distance_mm"])]
                    else:
                        layouts = []
                        for degrees in range(35, 146, 5):
                            theta = math.radians(degrees)
                            length = stages[2]["center_distance_mm"]
                            m2 = [length*math.cos(theta), length*math.sin(theta)]
                            layouts += [dict(base, M1=m1, M2=m2) for m1 in intersections(
                                base["I"], stages[0]["center_distance_mm"], m2, stages[1]["center_distance_mm"])]
                    for axes in layouts:
                        tested += 1
                        arrangement, reason = assess(ident, axes, stages, segments)
                        if reason:
                            rejected[reason] += 1
                            continue
                        volume = sum(stage["volume_proxy_mm3"] for stage in stages)
                        lateral = abs(sum(axes[stage["output_axis"]][0]*stage["volume_proxy_mm3"] for stage in stages)
                                      +input_y*(P["rotor_radii"][ident]/45)**2*150000)/volume
                        score = volume+height*1000+lateral*3500
                        feasible.append((score, axes, [dict(s) for s in stages], arrangement))
        if not feasible:
            raise RuntimeError(f"{ident}: no balanced layout after{tested} candidates: {dict(rejected)}")
        feasible.sort(key=lambda item: (item[0], json.dumps(item[1], sort_keys=True)))
        radius = P["rotor_radii"][ident]
        design = None
        for score, axes, stages, arrangement in feasible[:100]:
            spur_count = sum(stage["type"] == "spur" for stage in stages)
            rotor = dict(CONFIG["rotor"], radius=radius, cup_radius=radius*24/45, cup_offset=radius*21/45,
                         wall=2.4 if ident == "A" else 2, spider=radius > 60, arm_thickness=8 if ident == "A" else 6,
                         arm_width=16 if ident == "A" else 14, handedness=(-1)**spur_count)
            candidate = dict(id=ident, name={"A": "Large rotor / belt and spur reduction", "B": "Small rotor / high reduction",
                                            "C": "Intermediate rotor / generative lightening"}[ident],
                             rotor=rotor, axes=axes, stages=stages, ratio=math.prod(ratios),
                             foot_width=P["foot_widths"][ident], foot_offset=P["foot_offsets"][ident],
                             layout_objective=score, **arrangement)
            robust = [stiffness_trial(candidate, t, 14) for t in (8, 10)]
            passing_robust = [trial for trial in robust if trial["feasible"]]
            if passing_robust:
                design = candidate
                baseline = passing_robust[0]
                break
            rejected["frame_stiffness"] += 1
        if design is None:
            raise RuntimeError(f"{ident}: none of the best100 geometric layouts meets the declared frame limits")
        axes, stages = design["axes"], design["stages"]
        for rank, (value, points, train, _) in enumerate(feasible[:100], 1):
            records.append([ident, rank, value, json.dumps(points, sort_keys=True),
                            ";".join(f"{s['type']}:{s['pinion_teeth']}:{s['wheel_teeth']}:{s['side']}" for s in train)])
        counts[ident] = dict(tested_layouts=tested, feasible_layouts=len(feasible), rejected=dict(rejected))
        for stage in stages:
            if stage["type"] == "belt":
                stage["pitch_path_mm"] = belt_path(stage, axes)
        trials = [stiffness_trial(design, t, w) for t, w in itertools.product(S["thickness_bounds"], S["rib_width_bounds"])]
        chosen = min((t for t in trials if t["feasible"]), key=lambda t: t["volume_proxy_mm3"]) if ident == "C" else baseline
        design["structure"] = dict(chosen, style="ribs", selection="generated minimum-volume grid" if ident == "C" else "first passing robust8/10 x14 size")
        networks = {}
        for kind in ("core", "left", "right", "front_left", "front_right"):
            nodes, radii, edges = frame_network(design, kind, chosen["rib_width_mm"])
            networks[kind] = dict(nodes=nodes, radii=radii, edges=edges)
        design["frame_networks"] = networks
        selected.append(design)
        dump(OUT/f"structure_search_{ident}.json", trials)
        print(ident, "ratio", design["ratio"], "axes", axes, "ties", design["ties"],
              "stages", [(s["type"], s["pinion_teeth"], s["wheel_teeth"], s["side"]) for s in stages], flush=True)
    with (OUT/"gear_search.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["prototype", "feasible_rank", "objective_proxy", "axes_mm", "stage_specification"])
        writer.writerows(records)
    result = dict(scope=P["scope"], config_sha256=hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest(),
                  bounds=P, search_counts=counts,
                  objectives="Gear volume proxy +1000*input height +3500*lateral mass-proxy eccentricity; stages distributed to balance axial COG. C minimizes constrained frame-rib volume.",
                  keepouts="Moving legs, whole rotor swept circle, foreign through shafts, bearing/collar/tool seats, chassis ties, printable guards and frames.",
                  designs=selected)
    dump(OUT/"selected_designs.json", result)
    return result


if __name__ == "__main__":
    search()
