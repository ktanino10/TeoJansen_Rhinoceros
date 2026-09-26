"""Check explicit insertion/removal paths in the documented assembly states."""

import argparse
import json
import math
from pathlib import Path
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--freecad-lib", type=Path)
parser.add_argument("--only", choices=["A", "B", "C"])
args = parser.parse_args()
if args.freecad_lib:
    sys.path.insert(0, str(args.freecad_lib))
import FreeCAD as App
import Part

from core import CONFIG, LINKS, ROOT, OUT, dump, local_link


def run(ident):
    manifest = json.loads((OUT/f"assembly_{ident}.json").read_text())
    design = manifest["design"]
    doc = App.openDocument(str(ROOT/"FreeCAD"/"Ver.3"/ident/f"Ver3_{ident}.FCStd"))
    instances = manifest["instances"]
    records = []

    def local_solid(part_id):
        item = next(item for item in instances if item["part_id"] == part_id)
        obj = doc.getObject(item["name"])
        shape = obj.Shape.copy()
        shape.transformShape(obj.Placement.inverse().toMatrix())
        return shape

    def probe(name, part_id, point, expected_material):
        actual = local_solid(part_id).isInside(App.Vector(*point), 1e-7, True)
        records.append(dict(check=name, part=part_id, local_point_mm=list(point),
                            expected_material=expected_material, measured_material=actual,
                            passed=actual == expected_material))

    probe("REX hub has a real non-round torque flat", "H_REX_HUB", (0, 3.8, 4), True)
    probe("REX hub centre is bored through", "H_REX_HUB", (0, 0, 4), False)
    for x in (-8, 8):
        for y in (-8, 8):
            probe("Metal hub M4 flange hole", "H_REX_HUB", (x, y, 4), False)
    shaft_id = next(item["part_id"] for item in instances if item["part_id"].startswith("H_shaft_8_"))
    shaft = local_solid(shaft_id)
    middle = (shaft.BoundBox.ZMin+shaft.BoundBox.ZMax)/2
    clock = math.radians(CONFIG["hardware"]["rex_clocking_degrees"])
    probe("REX shaft flat removes round-bar material", shaft_id, (0, 3.8, middle), False)
    probe("REX shaft retains the supplier-clocked rounded corner", shaft_id,
          (3.8*math.cos(clock), 3.8*math.sin(clock), middle), True)
    probe("REX shaft bounded by8mm cylinder", shaft_id, (4.1, 0, middle), False)
    shaft_items = [item for item in instances if item["part_id"].startswith("H_shaft_8_")]
    for hub in [item for item in instances if item["part_id"] == "H_REX_HUB"]:
        shape = doc.getObject(hub["name"]).Shape
        matrix = hub["transform"]
        paired = []
        for item in shaft_items:
            transform = item["transform"]
            if max(abs(matrix[k][3]-transform[k][3]) for k in (1, 2)) > 1e-7:
                continue
            candidate = doc.getObject(item["name"]).Shape
            if min(shape.BoundBox.XMax, candidate.BoundBox.XMax) <= max(shape.BoundBox.XMin, candidate.BoundBox.XMin):
                continue
            paired.append((item["name"], shape.common(candidate).Volume))
        records.append(dict(check="All supplier-clocked hubs fit their connected REX shafts",
                            hub=hub["name"], shaft_pairs=paired,
                            passed=bool(paired) and all(value <= 1e-6 for _, value in paired),
                            interface_basis="Supplier hole-square angles45/135/225/315; flat normals45+60k. Axis corner15deg; reflected hub indexed90deg; bolt pattern unchanged."))
    for part_id in {item["part_id"] for item in instances if item["part_id"].removesuffix("_R") in LINKS}:
        for x, y in local_link(part_id):
            probe("Link journal hole is actual CAD void", part_id, (x, y, 1.5), False)
    probe("Crank pin through-hole", "P_CRANK_CHEEK", (21, 0, 4), False)
    probe("Crank pilot counterbore", "P_CRANK_CHEEK", (6.5, 0, 1), False)
    probe("Material behind pilot counterbore", "P_CRANK_CHEEK", (6.5, 0, 3), True)
    probe("Recessed shaft end-stop pocket", "P_CRANK_CHEEK", (6, 0, 6), False)
    probe("Bearing retainer clears inner ring", "P_BEARING_RETAINER", (0, 0, 1), False)
    probe("Bearing retainer outer-ring land", "P_BEARING_RETAINER", (10.5, 0, 1), True)
    for item in instances:
        part_id = item["part_id"]
        if part_id.startswith("P_S") and part_id.endswith(("PINION", "WHEEL")):
            probe("Printed gear central pilot bore", part_id, (0, 0, 4), False)
            for x in (-8, 8):
                for y in (-8, 8):
                    probe("Printed gear real M4 through-hole", part_id, (x, y, 4), False)
    cup = local_solid("P_ROTOR_CUP")
    middle = (cup.BoundBox.ZMin+cup.BoundBox.ZMax)/2
    for angle in range(0, 360, 30):
        theta = math.radians(angle)
        probe("Rotor clears an8mm shaft with radial margin", "P_ROTOR_CUP",
              (4.5*math.cos(theta), 4.5*math.sin(theta), middle), False)

    def check(name, movers, obstacles, direction, distances, state):
        moving = Part.makeCompound([doc.getObject(item["name"]).Shape for item in movers])
        maximum = 0.0
        for distance in distances:
            shape = moving.copy()
            shape.translate(App.Vector(direction*distance, 0, 0))
            for obstacle in obstacles:
                fixed = doc.getObject(obstacle["name"]).Shape
                if shape.BoundBox.intersect(fixed.BoundBox):
                    maximum = max(maximum, shape.common(fixed).Volume)
        record = dict(check=name, moving=[item["name"] for item in movers],
                      assembly_state=state, axis="X", direction=direction,
                      sample_distances_mm=distances, maximum_intersection_mm3=maximum,
                      pass_limit_mm3=0.05, passed=maximum <= 0.05)
        records.append(record)

    def at_point(item, yz, x=None):
        matrix = item["transform"]
        matched = abs(matrix[1][3]-yz[0]) < 1e-5 and abs(matrix[2][3]-yz[1]-CONFIG["linkage"]["crank_height"]) < 1e-5
        return matched and (x is None or abs(matrix[0][3]-x) < 1e-5)

    span = CONFIG["linkage"]["bay_count"]*CONFIG["linkage"]["bay_pitch"]
    for index, stage in enumerate(design["stages"]):
        direction = -1 if stage["side"] == "left" else 1
        origin = 0 if direction == -1 else span
        back = origin+direction*stage["guard_back_offset"]
        info = design["case"][stage["side"]]["stages"][str(index)]
        guard = next(item for item in instances if item["part_id"] == f"P_GUARD_{index+1}")
        window_id = f"S_WINDOW_{index+1}"
        expected_window = f"fourM3x{stage['window_screw_length_mm']},{stage['window_aperture_mm']}shaft apertures"
        records.append(dict(check="Window BOM description derives from this stage", part=window_id,
                            expected=expected_window,
                            passed=expected_window in manifest["parts"][window_id]["description"]))
        frame_offset = design["case"][stage["side"]]["front_offset"]
        frame_inner = frame_offset-design["structure"]["plate_thickness_mm"]/2
        removed = set()
        for item in instances:
            distance = direction*(item["transform"][0][3]-origin)
            if (distance >= frame_inner-5 and item["group"] not in
                    ("guard", "guard_lid", "drivetrain", "rotor", "crank", "legs", "feet")
                    and not item["part_id"].startswith(("H_shaft", "H_CASE_TIE"))):
                removed.add(item["name"])
        for outer_index, outer in enumerate(design["stages"]):
            if outer["side"] != stage["side"] or outer["side_index"] <= stage["side_index"]:
                continue
            for item in instances:
                distance = direction*(item["transform"][0][3]-origin)
                if item["part_id"] in (f"P_GUARD_{outer_index+1}", f"S_WINDOW_{outer_index+1}",
                                       f"P_{outer['id']}_PINION", f"P_{outer['id']}_WHEEL"):
                    removed.add(item["name"])
                if item["group"] == "drivetrain" and outer["body_offset"]-5 <= distance <= outer["body_offset"]+16.1:
                    removed.add(item["name"])
                if item["group"] in ("guard", "guard_lid") and outer["guard_back_offset"]-1 <= distance <= outer["guard_back_offset"]+outer["guard_depth"]+6:
                    removed.add(item["name"])
        for point in info["cover_corners"]:
            screw_x = back+direction*(stage["guard_depth"]+1.5)
            screw = next(item for item in instances if item["group"] == "guard_lid"
                         and item["part_id"].startswith("H_bolt_3_") and at_point(item, point, screw_x))
            radius = 2.5/math.sqrt(3)
            vertices = [App.Vector(radius*math.cos(i*math.pi/3), radius*math.sin(i*math.pi/3), -33) for i in range(6)]
            bit = Part.Face(Part.makePolygon(vertices+[vertices[0]])).extrude(App.Vector(0, 0, 29.99))
            bit.transformShape(App.Matrix(*[value for row in screw["transform"] for value in row]))
            hits = []
            for item in instances:
                if item["name"] == screw["name"] or item["name"] in removed:
                    continue
                obstacle = doc.getObject(item["name"]).Shape
                if bit.BoundBox.intersect(obstacle.BoundBox):
                    overlap = bit.common(obstacle).Volume
                    if overlap > 0.001:
                        hits.append(dict(part=item["name"], intersection_mm3=overlap))
            records.append(dict(check="Window screw straight-tool path after carrier-first disassembly",
                                screw=screw["name"], tool="2.5AF hex bit30mm outboard of actual socket",
                                removed_parts=sorted(removed), intersections=hits, passed=not hits,
                                assembly_state="Machine independently supported, shaft end stops and outboard carrier with its bearing/carriage/retainer fasteners removed. All farther-out stages on this side removed, with their windows and trays. Long shafts and main bearings remain."))
        for corner in info["cover_corners"]:
            nut = next(item for item in instances if item["part_id"] == "H_nut_3"
                       and item["group"] == "guard" and at_point(item, corner, back+direction*2.5))
            check(f"{stage['id']} cover nut rear access", [nut], [guard], -direction,
                  [0, 0.5, 1, 2, 3, 5, 8],
                  "Guard off machine; cover screw removed; insert nut from open rear hex pocket.")
        moving = []
        if stage["type"] == "belt":
            moving += [item for item in instances if item["part_id"] in ("H_PULLEY24", "H_PULLEY48", "H_BELT520")]
        else:
            moving += [item for item in instances if item["part_id"] in (f"P_{stage['id']}_PINION", f"P_{stage['id']}_WHEEL")]
        near = origin+direction*stage["body_offset"]
        hub_x = near-20 if stage["type"] == "belt" else near+direction*16
        for axis in (stage["input_axis"], stage["output_axis"]):
            hub = next(item for item in instances if item["part_id"] == "H_REX_HUB"
                       and item["group"] == "drivetrain" and at_point(item, design["axes"][axis], hub_x))
            moving.append(hub)
        check(f"{stage['id']} gear/pulley and hub withdrawal", moving, [guard], direction,
              [0, 1, 2, 4, 8, 16, 24, 40, 60],
              "Window, end stops and front bearing carrier removed; any outer-stage gears AND tray removed first. Only this stage's open tray remains. Belt/pulleys removed together.")

    rotor_prints = [item for item in instances if item["group"] == "rotor" and item["part_id"].startswith("P_ROTOR")]
    rotor_nuts = [item for item in instances if item["group"] == "rotor" and item["part_id"] in ("H_nut_3", "H_nut_4")]
    for nut in rotor_nuts:
        direction = 1 if nut["transform"][0][3] < span/2 else -1
        check("Rotor nut access from cup interior", [nut], rotor_prints, direction,
              [0, 0.5, 1, 2, 3, 5, 8, 12, 20],
              "Mating screw removed; move nut toward rotor interior. Other printed rotor parts remain; verifies pocket is not sealed by cup wall.")
    if ident == "A":
        belt = next(stage for stage in design["stages"] if stage["type"] == "belt")
        adjustment = CONFIG["system"]["belt"]["adjustment_each_way"]
        # Analytical radial clearance at the real guard/shaft and frame/collar apertures.
        clearances = {
            "window_input_shaft": belt["window_aperture_mm"]/2-8/2-adjustment,
            "guard_back_input_collar": 23/2-18/2-adjustment,
            "frame_input_window_collar": 28/2-18/2-adjustment,
            "window_carriage_screw": belt["carriage_screw_window_bore_mm"]/2-4/2-adjustment,
        }
        records.append(dict(check="A input adjustment swept radial clearances",
                            adjustment_each_way_mm=adjustment, clearances_mm=clearances,
                            passed=min(clearances.values()) >= 0.5,
                            assembly_state="All three input carriages translated together along belt-centre line; M1 remains fixed. Belt tension not physically tested."))
        def named(part, x, point):
            found = [item for item in instances if item["part_id"] == part and at_point(item, point, x)]
            if len(found) != 1:
                raise RuntimeError(f"Carrier member lookup was not unique: {part} at{x},{point}")
            return found[0]

        thickness = design["structure"]["plate_thickness_mm"]
        front = -design["case"]["left"]["front_offset"]
        outer = front-thickness/2
        members = [next(item for item in instances if item["part_id"] == "P_FRAME_FRONT_LEFT")]
        adjustable = set()
        for axis in design["case"]["left"]["axes"]:
            point = design["axes"][axis]
            carriage = axis == "I"
            bearing_outer = outer-(8 if carriage else 0)
            seat = 8 if carriage else thickness
            group = [named("H_608", bearing_outer+0.35, point),
                     named("P_BEARING_RETAINER", bearing_outer-2, point)]
            for y in (-16, 16):
                location = [point[0]+y, point[1]]
                group += [named(f"H_bolt_3_{int(seat+2)}", bearing_outer-2, location),
                          named("H_nut_3", bearing_outer+seat-2.5, location)]
            if carriage:
                group.append(named("P_INPUT_CARRIAGE_FLOAT", bearing_outer, point))
                inner = front+thickness/2
                for location in belt["carriage_screw_window_points"]:
                    group += [named("H_countersunk_4_30", bearing_outer, location),
                              named("H_washer_4_0p8", inner, location),
                              named("H_locknut_4", inner+0.8, location)]
                adjustable.update(item["name"] for item in group)
            members.extend(group)
        window = doc.getObject(next(item["name"] for item in instances if item["part_id"] == "S_WINDOW_1")).Shape
        input_axis, intermediate = design["axes"]["I"], design["axes"]["M1"]
        dy, dz = input_axis[0]-intermediate[0], input_axis[1]-intermediate[1]
        length = math.hypot(dy, dz)
        samples = []
        for setting in (-adjustment, 0, adjustment):
            for travel in (0, 1, 2, 4, 7.5, 8, 12, 24, 40, 60):
                maximum = 0.0
                for member in members:
                    shape = doc.getObject(member["name"]).Shape.copy()
                    offset = setting if member["name"] in adjustable else 0
                    shape.translate(App.Vector(-travel, offset*dy/length, offset*dz/length))
                    if shape.BoundBox.intersect(window.BoundBox):
                        maximum = max(maximum, shape.common(window).Volume)
                samples.append(dict(adjustment_mm=setting, withdrawal_mm=travel, maximum_intersection_mm3=maximum))
        records.append(dict(check="A complete left carrier unit versus retained window through withdrawal and tension adjustment",
                            unit_members=[item["name"] for item in members],
                            adjustable_members=sorted(adjustable), samples=samples,
                            passed=all(sample["maximum_intersection_mm3"] <= 0.001 for sample in samples),
                            assembly_state="External end stops/case nuts released; whole26-part carrier removed as a unit. Window remains installed. I carriage at nominal or +/-1.5mm setting; primary supports/shaft held independently."))
    passed = all(record["passed"] for record in records)
    report = dict(prototype=ident, passed=passed, checks=records,
                  limitations="Sampled native-solid paths in explicitly stated partial assemblies; not automated tool/hand ergonomics, a hardware trial, or a claim that parts pass through an assembled bearing carrier.")
    dump(OUT/f"assembly_access_{ident}.json", report)
    App.closeDocument(doc.Name)
    print(ident, "checks", len(records), "passed", passed)
    if not passed:
        raise RuntimeError(f"{ident} assembly path failure; see assembly_access_{ident}.json")


for ident in [args.only] if args.only else ("A", "B", "C"):
    run(ident)
