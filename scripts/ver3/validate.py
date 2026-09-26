"""Deterministic full-turn geometry, transmission and artifact checks."""

import argparse
from collections import Counter
import csv
import hashlib
import itertools
import json
import math

import numpy as np
from scipy.optimize import minimize_scalar
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
import trimesh

from core import (CONFIG, CONFIG_PATH, LINKS, ROOT, OUT, animated_transform,
                  axial_layout, axis_speeds, dump, foot_centers, gait,
                  gear_metrics, gear_outline)
from system_search import belt_length, stiffness_trial

parser = argparse.ArgumentParser()
parser.add_argument("--only", choices=["A", "B", "C"])
args = parser.parse_args()
L, H, P = CONFIG["linkage"], CONFIG["hardware"], CONFIG["system"]


def profile(part_id, points):
    names = LINKS[part_id]
    pairs = list(zip(names, names[1:]+names[:1])) if len(names) == 3 else [(names[0], names[1])]
    width = L["ac_link_width"] if part_id == "L_AC" else L["link_width"]
    shapes = [LineString([points[a], points[b]]).buffer(width/2, quad_segs=16) for a, b in pairs]
    shapes += [Point(points[n]).buffer(7 if n == "P" else 5 if n == "A" else 4, quad_segs=16) for n in names]
    result = unary_union(shapes)
    for name in names:
        radius = L["fixed_pivot_bore"]/2 if name == "P" else 3.1 if name == "A" else 2.1
        result = result.difference(Point(points[name]).buffer(radius, quad_segs=16))
    return result


def pivot_clearance(theta):
    points = gait(theta)
    return (LineString([points["A"], points["C"]]).distance(Point(points["P"]))
            -L["ac_link_width"]/2-(H["pivot_rod_diameter"]+2)/2)


closure_error = 0
for mirror in (False, True):
    for index in range(721):
        points = gait(math.radians(index/2), mirror)
        for pair in ("OA", "AB", "BP", "AC", "PC", "BD", "PD", "CE", "DE", "CF", "EF"):
            measured = float(np.linalg.norm(points[pair[0]]-points[pair[1]]))
            closure_error = max(closure_error, abs(measured-L[pair]*L["scale"]))
assert closure_error < 1e-8
minimum_index = min(range(720), key=lambda n: pivot_clearance(math.radians(n/2)))
minimum = minimize_scalar(pivot_clearance, bounds=(
    math.radians(minimum_index/2-1), math.radians(minimum_index/2+1)),
    method="bounded", options={"xatol": 1e-13})
assert minimum.fun >= 0.5
feet = np.array([gait(math.radians(i/2))["F"] for i in range(721)])

for ident in [args.only] if args.only else ("A", "B", "C"):
    manifest = json.loads((OUT/f"assembly_{ident}.json").read_text())
    design = manifest["design"]
    if not isinstance(design["case"], dict) or "left" not in design["case"]:
        raise RuntimeError("Stale end-loaded assembly: regenerate the balanced design")
    angular_speeds = axis_speeds(design)
    assert abs(angular_speeds["I"]) == design["ratio"]
    spur_count = sum(stage["type"] == "spur" for stage in design["stages"])
    assert math.copysign(1, angular_speeds["I"]) == (-1)**spur_count
    assert design["rotor"]["handedness"] == (-1)**spur_count
    stage_reports = []
    for stage in design["stages"]:
        first = np.array(design["axes"][stage["input_axis"]])
        second = np.array(design["axes"][stage["output_axis"]])
        assert abs(np.linalg.norm(first-second)-stage["center_distance_mm"]) < 1e-7
        if stage["type"] == "belt":
            r, big_r = [d/2 for d in stage["pitch_diameters_mm"]]
            length_error = abs(belt_length(stage["center_distance_mm"], r, big_r)-stage["belt_pitch_length_mm"])
            assert length_error < 1e-7 and stage["engaged_small_teeth"] >= 8
            assert angular_speeds[stage["input_axis"]] == stage["ratio"]*angular_speeds[stage["output_axis"]]
            stage_reports.append(dict(stage=stage["id"], kind="purchased HTD5M",
                                      pitch_length_error_mm=length_error,
                                      small_wrap_deg=stage["small_wrap_degrees"],
                                      engaged_teeth=stage["engaged_small_teeth"]))
            continue
        metrics = gear_metrics(stage["module"], stage["pinion_teeth"], stage["wheel_teeth"])
        for key, value in metrics.items():
            assert stage[key] == value, (stage["id"], key)
        pinion_phase = math.atan2(second[1]-first[1], second[0]-first[0])-math.pi/stage["pinion_teeth"]
        wheel_phase = math.atan2(first[1]-second[1], first[0]-second[0])
        pinion = affinity.rotate(Polygon(gear_outline(stage["module"], stage["pinion_teeth"])),
                                  math.degrees(pinion_phase), origin=(0, 0))
        wheel = affinity.rotate(Polygon(gear_outline(stage["module"], stage["wheel_teeth"])),
                                math.degrees(wheel_phase), origin=(0, 0))
        maximum_overlap = 0
        # One complete tooth-mesh period, densely sampled independently of gear ratio.
        for step in range(721):
            angle = 360/stage["wheel_teeth"]*step/720
            p = affinity.translate(affinity.rotate(pinion, -stage["ratio"]*angle, origin=(0, 0)), *first)
            w = affinity.translate(affinity.rotate(wheel, angle, origin=(0, 0)), *second)
            maximum_overlap = max(maximum_overlap, p.intersection(w).area)
        assert maximum_overlap < 1e-7, (stage["id"], maximum_overlap)
        assert angular_speeds[stage["input_axis"]] == -stage["ratio"]*angular_speeds[stage["output_axis"]]
        stage_reports.append(dict(stage=stage["id"], kind="involute spur",
                                  contact_ratio=metrics["contact_ratio"], mesh_samples=721,
                                  overlap_max_mm2=maximum_overlap, root_web_mm=metrics["root_web_mm"],
                                  tip_thickness_mm=metrics["tip_thickness_mm"]))
    moving_overlap = 0
    minimum_tie = 1e9
    minimum_foreign_shaft = 1e9
    minimum_shoe_gap = 1e9
    for step in range(720):
        theta = math.radians(step/2)
        links = []
        for mirrored in (False, True):
            points = gait(theta, mirrored)
            layout = axial_layout(design["structure"]["plate_thickness_mm"], mirrored, design["foot_offset"])
            for part_id in LINKS:
                links.append((part_id, layout[part_id], profile(part_id, points)))
        for i, (part_id, x, shape) in enumerate(links):
            for _, other_x, other in links[i+1:]:
                if min(x+3, other_x+3) > max(x, other_x):
                    moving_overlap = max(moving_overlap, shape.intersection(other).area)
            for point in design["ties"]:
                minimum_tie = min(minimum_tie, shape.distance(Point(point))-5)
            for axis, point in design["axes"].items():
                if axis != "O":
                    minimum_foreign_shaft = min(minimum_foreign_shaft, shape.distance(Point(point))-4)
        foot_points = foot_centers(design, theta)
        # Whole-shoe AABBs conservatively include the lug and tie wrap.
        shoe_extent = np.array([design["foot_width"], P["foot_length"]+1, P["foot_pivot_to_ground"]+4])
        for first, second in itertools.combinations(foot_points, 2):
            minimum_shoe_gap = min(minimum_shoe_gap, float(max(np.abs(first-second)-shoe_extent)))
    assert moving_overlap < 1e-6, moving_overlap
    assert minimum_tie >= 0.5, minimum_tie
    assert minimum_foreign_shaft >= 0.5, minimum_foreign_shaft
    assert minimum_shoe_gap >= 0.5, minimum_shoe_gap
    rotary_sweep = min(math.dist(point, design["axes"]["I"])-design["rotor"]["radius"]-4
                       for axis, point in design["axes"].items() if axis != "I")
    assert rotary_sweep >= 3, rotary_sweep
    cycle_error = 0
    for instance in manifest["instances"]:
        initial = np.array(animated_transform(instance, 0, design))
        end = np.array(animated_transform(instance, 2*math.pi, design))
        cycle_error = max(cycle_error, float(np.abs(initial-end).max()))
    assert cycle_error < 1e-8, cycle_error
    counts = Counter(item["part_id"] for item in manifest["instances"])
    with (OUT/f"BOM_{ident}.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert sum(int(row["quantity"]) for row in rows) == len(manifest["instances"])
    assert all(counts[row["part_id"]] == int(row["quantity"]) for row in rows)
    stls = []
    for part_id, part in manifest["parts"].items():
        if part["category"] != "printed":
            continue
        mesh = trimesh.load_mesh(ROOT/"STL"/"Ver.3"/ident/(part_id+".stl"), process=True)
        volume_error = abs(abs(mesh.volume)-part["solid_volume_mm3"])/part["solid_volume_mm3"]
        assert mesh.is_watertight and mesh.is_winding_consistent and len(mesh.split()) == 1
        assert volume_error < 0.01, (part_id, volume_error)
        assert max(mesh.extents) <= 256.001, (part_id, mesh.extents)
        stls.append(dict(part=part_id, watertight=True, volume_relative_error=volume_error))
    structure = stiffness_trial(design, design["structure"]["plate_thickness_mm"], design["structure"]["rib_width_mm"])
    assert structure["feasible"]
    report = dict(prototype=ident, closure_samples_per_hand=721, link_closure_error_mm=closure_error,
                  ac_pivot_clearance_min_mm=float(minimum.fun), ac_closest_angle_deg=math.degrees(minimum.x)%360,
                  foot_stride_mm=float(np.ptp(feet[:, 0])), foot_lift_mm=float(np.ptp(feet[:, 1])),
                  stage_reports=stage_reports, axis_speed_per_crank=angular_speeds,
                  moving_link_overlap_mm2=moving_overlap, tie_rail_clearance_mm=minimum_tie,
                  continuous_foreign_shaft_clearance_mm=minimum_foreign_shaft,
                  shoe_separating_aabb_gap_mm=minimum_shoe_gap, rotor_foreign_shaft_clearance_mm=rotary_sweep,
                  transform_cycle_error=cycle_error, bom_count_consistent=True,
                  native_instance_count=len(manifest["instances"]), stl_results=stls,
                  structure_limits_pass=True, config_sha256=hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest())
    dump(OUT/f"validation_{ident}.json", report)
    print(ident, {key: value for key, value in report.items() if key != "stl_results"})
