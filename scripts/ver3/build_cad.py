"""Generate the three approved wind/drivetrain concepts with native FreeCAD."""

import argparse
import math
from pathlib import Path
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--freecad-lib", type=Path)
parser.add_argument("--only", choices=["A", "B", "C"])
parser.add_argument("--search", action="store_true")
args = parser.parse_args()
if args.freecad_lib:
    sys.path.insert(0, str(args.freecad_lib))

import FreeCAD as App
import Part
import numpy as np
from shapely.geometry import LineString

from core import CONFIG, LINKS, axial_layout, axis_speeds, gait, gear_outline, link_pose, pose, selected_designs
from system_search import frame_network, search
from cad_parts import (Assembly, V, bearing, bearing_screw_points, capsule, cheek,
                       collar, coupon, cylinder, disk, drilled, hexagon, hub, hub_pose,
                       joint_coupon, link_shape, polygon, retainer, square_holes)

L = CONFIG["linkage"]
H = CONFIG["hardware"]
P = CONFIG["system"]
S = CONFIG["structure"]


def motion(design, axis):
    return dict(type="shaft", speed=axis_speeds(design)[axis], center=design["axes"][axis])


def frame_shape(design, kind, reverse=False):
    thickness = design["structure"]["plate_thickness_mm"]
    width = design["structure"]["rib_width_mm"]
    nodes, radii, edges = frame_network(design, kind, width)
    points = {name: (point[0], -point[1] if reverse else point[1]) for name, point in nodes.items()}
    shapes = [capsule(points[a], points[b], width, thickness) for a, b in edges]
    for name, point in points.items():
        if design["id"] == "A" and name == "I":
            shapes.append(Part.makeBox(48, 48, thickness, V(point[0]-24, point[1]-24, 0)))
        else:
            shapes.append(cylinder(radii[name], thickness, *point))
    shape = shapes[0].multiFuse(shapes[1:]).removeSplitter()
    for name, point in points.items():
        if name in design["axes"]:
            if design["id"] == "A" and name == "I":
                shape = drilled(shape, [point], 28, thickness+2)
                direction = np.array(design["axes"]["I"])-design["axes"]["M1"]
                direction /= np.linalg.norm(direction)
                if reverse:
                    direction[1] *= -1
                for y, z in ((y, z) for y in (-18, 18) for z in (-18, 18)):
                    center = np.array(point)+[y, z]
                    slot = capsule(center-direction*1.5, center+direction*1.5, 4.4, thickness+2)
                    slot.translate(V(0, 0, -1))
                    shape = shape.cut(slot)
                continue
            locating = (kind == "left" and name == "O") or (kind == "right" and name != "O")
            depth = H["bearing_pocket_locating"] if locating else H["bearing_pocket_floating"]
            shape = drilled(shape, [point], H["bearing_shoulder_bore"], thickness + 2)
            shape = shape.cut(cylinder(H["bearing_seat_diameter"] / 2, depth, *point))
            for x, y in bearing_screw_points(point):
                shape = shape.cut(cylinder(1.65, thickness + 2, x, y, -1))
                shape = shape.cut(hexagon(5.8, 2.6, x, y, thickness - 2.6))
        elif name in ("PL", "PR"):
            shape = drilled(shape, [point], 6.2, thickness + 2)
        elif name.startswith(("K", "T")):
            shape = drilled(shape, [point], 4.4, thickness + 2)
    return shape.removeSplitter()


def gear_shape(design, stage, wheel=False):
    teeth = stage["wheel_teeth"] if wheel else stage["pinion_teeth"]
    start = design["axes"][stage["output_axis"] if wheel else stage["input_axis"]]
    end = design["axes"][stage["input_axis"] if wheel else stage["output_axis"]]
    physical_phase = math.atan2(end[1] - start[1], end[0] - start[0])
    if not wheel:
        physical_phase -= math.pi / teeth
    phase = -physical_phase if stage["side"] == "right" else physical_phase
    co, si = math.cos(phase), math.sin(phase)
    outline = [(co * x - si * y, si * x + co * y)
               for x, y in gear_outline(stage["module"], teeth)]
    shape = polygon(outline, 8).cut(cylinder(7.1, 10, z=-1))
    if wheel:
        root = stage["module"] * (teeth / 2 - 1.25)
        center = (22 + root - 6) / 2
        radius = min((root - 6 - 22) / 2, (center - 8) / 2)
        shape = drilled(shape, [(center * math.cos(i * math.pi / 3),
                                 center * math.sin(i * math.pi / 3)) for i in range(6)], 2 * radius, 10)
    return drilled(shape, square_holes(), 4.4, 10)


def rotor_points(rotor):
    radius = rotor["cup_radius"] * 0.75
    return [(rotor["cup_offset"] + radius * math.cos(math.radians(angle)),
             rotor["handedness"] * radius * math.sin(math.radians(angle))) for angle in (35, 70)]


def cup_shape(rotor):
    arm = rotor["arm_thickness"] if rotor["spider"] else 0
    length = rotor["span"] - 2 * (rotor["endplate_thickness"] + arm)
    outer, inner = [], []
    for angle in np.linspace(0, math.pi, 65):
        outer.append((rotor["cup_offset"] + rotor["cup_radius"] * math.cos(angle),
                      rotor["handedness"] * rotor["cup_radius"] * math.sin(angle)))
    for angle in np.linspace(math.pi, 0, 65):
        inner.append((rotor["cup_offset"] + (rotor["cup_radius"] - rotor["wall"]) * math.cos(angle),
                      rotor["handedness"] * (rotor["cup_radius"] - rotor["wall"]) * math.sin(angle)))
    shape = polygon(outer + inner, length)
    for point in rotor_points(rotor):
        # The hex nut clears the continuing curved wall along its insertion path.
        root = np.array([rotor["cup_offset"], 0])
        direction = (np.array(point) - root) / np.linalg.norm(np.array(point) - root)
        wall_point = root + direction * (rotor["cup_radius"] - rotor["wall"] / 2)
        for z in (0, length - 6):
            tab = capsule(point, wall_point, 12, 6)
            tab.translate(V(0, 0, z))
            shape = shape.fuse(tab)
            shape = shape.cut(cylinder(1.65, 8, *point, z - 1))
            pocket_z = 3.4 if z == 0 else length - 6
            shape = shape.cut(hexagon(5.8, 2.7, *point, pocket_z))
    shape = shape.common(cylinder(rotor["radius"], length))
    return shape.cut(cylinder(5, length + 2, z=-1)).removeSplitter()


def rotor_core(rotor, reverse=False):
    radius = 40 if rotor["spider"] else rotor["radius"]
    shape = disk(radius, 5, 8.2).cut(cylinder(7.1, 2.1, z=-0.05))
    shape = drilled(shape, square_holes(), 4.4, 7)
    holes = []
    points = yoke_roots(rotor) if rotor["spider"] else rotor_points(rotor)
    holes = points+[(-x, -y) for x, y in points]
    if reverse:
        holes = [(x, -y) for x, y in holes]
    return drilled(shape, holes, 4.4 if rotor["spider"] else 3.3, 7)


def yoke_roots(rotor):
    vector = np.array(rotor_points(rotor)).sum(axis=0)
    angle = math.atan2(vector[1], vector[0])
    return [(28*math.cos(angle+math.radians(d)), 28*math.sin(angle+math.radians(d))) for d in (-15, 15)]


def rotor_yoke(rotor, reverse=False):
    points = np.array(rotor_points(rotor))
    roots = np.array(yoke_roots(rotor))
    if reverse:
        points[:, 1] *= -1
        roots[:, 1] *= -1
    thickness = rotor["arm_thickness"]
    shape = capsule(roots[0], roots[1], rotor["arm_width"], thickness)
    for root, point in zip(roots, points):
        shape = shape.fuse(capsule(root, point, rotor["arm_width"], thickness))
    for x, y in roots:
        shape = shape.cut(cylinder(2.2, thickness+2, x, y, -1))
        shape = shape.cut(hexagon(7.4, 3.5, x, y, thickness-3.4))
    return drilled(shape, points, 3.3, thickness+2).removeSplitter()


def bearing_carriage(locating):
    shape = Part.makeBox(48, 48, 8, V(-24, -24, 0))
    shape = shape.cut(cylinder(10.1, 10, z=-1))
    depth = 7.2 if locating else 7.7
    shape = shape.cut(cylinder(11.1, depth))
    for x, y in bearing_screw_points():
        shape = shape.cut(cylinder(1.65, 10, x, y, -1))
        shape = shape.cut(hexagon(5.8, 2.6, x, y, 5.4))
    for x in (-18, 18):
        for y in (-18, 18):
            shape = shape.cut(cylinder(2.2, 10, x, y, -1))
            shape = shape.cut(Part.makeCone(4.2, 2.2, 2, V(x, y, 0)))
    return shape


def pulley(teeth):
    diameter = 38.9 if teeth == 24 else 78.7
    pitch = teeth*5/math.pi
    shape = disk(diameter/2, 1.375, 14)
    shape = shape.fuse(disk(pitch/2-0.57, 9.25, 14).translated(V(0, 0, 1.375)))
    shape = shape.fuse(disk(diameter/2, 1.375, 14).translated(V(0, 0, 10.625)))
    # Decorative pitch marks are not a claimed manufacturable HTD tooth profile.
    for i in range(teeth):
        angle = 2*math.pi*i/teeth
        radius = pitch/2-0.3
        shape = shape.cut(cylinder(0.65, 9.25, radius*math.cos(angle), radius*math.sin(angle), 1.375))
    shape = drilled(shape, square_holes(), 4, 14)
    if teeth == 24:
        for x, y in square_holes():
            shape = shape.cut(cylinder(3.6, 4, x, y, 8))
        alternate = [(16/math.sqrt(2)*math.cos(i*math.pi/2),
                      16/math.sqrt(2)*math.sin(i*math.pi/2)) for i in range(4)]
        shape = drilled(shape, alternate, 3.3, 14)
        shape = shape.cut(cylinder(8, 1)).cut(cylinder(8, 1, z=11))
    return shape.removeSplitter()


def belt_shape(stage):
    outline = LineString(stage["pitch_path_mm"]).buffer(1.9, quad_segs=16)
    outer = polygon(list(outline.exterior.coords)[:-1], 9)
    for ring in outline.interiors:
        outer = outer.cut(polygon(list(ring.coords)[:-1], 11).translated(V(0, 0, -1)))
    return outer


def guard(design, index):
    stage = design["stages"][index]
    info = design["case"][stage["side"]]["stages"][str(index)]
    reverse = stage["side"] == "left"
    transform = lambda point: [point[0], -point[1] if reverse else point[1]]
    y0, y1, z0, z1 = info["bounds"]
    if reverse:
        z0, z1 = -z1, -z0
    depth = stage["guard_depth"]
    tray = Part.makeBox(y1-y0, z1-z0, depth, V(y0, z0, 0))
    cavity = Part.makeBox(y1-y0-5, z1-z0-5, depth, V(y0+2.5, z0+2.5, 2))
    tray = tray.cut(cavity)
    for original in info["mount_posts"]:
        post = transform(original)
        anchor = [min(max(post[0], y0 + 5), y1 - 5),
                  min(max(post[1], z0 + 5), z1 - 5)]
        if math.dist(anchor, post) > 1e-7:
            tray = tray.fuse(capsule(anchor, post, 12, 2))
        tray = tray.fuse(cylinder(6, 2, *post))
        tray = drilled(tray, [post], 4.4, 4)
    for original in info["cover_corners"]:
        point = transform(original)
        tray = tray.fuse(cylinder(5, depth, *point))
        tray = drilled(tray, [point], 3.3, depth+2)
        tray = tray.cut(hexagon(5.8, 2.7, *point, -0.1))
    shaft_bores = [transform(point) for point in design["axes"].values()]
    tray = drilled(tray, shaft_bores, 23 if stage["type"] == "belt" else 20, depth+2)
    p = gait(0)["P"]
    tray = drilled(tray, [transform(p), transform((-p[0], p[1]))], 18, depth+2)
    tray = drilled(tray, [transform(point) for point in design["ties"]], 12, depth+2)
    for post_index, original in enumerate(design["case"][stage["side"]]["posts"]):
        point = transform(original)
        if post_index//2 == info["mount_row"]:
            tray = tray.cut(cylinder(5.2, depth, *point, 2))
        else:
            tray = drilled(tray, [point], 10.4, depth+2)
    window = Part.makeBox(y1 - y0, z1 - z0, 1, V(y0, z0, 0))
    window = drilled(window, shaft_bores, stage["window_aperture_mm"], 3)
    window = drilled(window, [transform(point) for point in info["cover_corners"]], 3.3, 3)
    window = drilled(window, [transform(point) for point in design["case"][stage["side"]]["posts"]], 10.4, 3)
    if stage["type"] == "belt":
        window = drilled(window, [transform(point) for point in stage["carriage_screw_window_points"]],
                         stage["carriage_screw_window_bore_mm"], 3)
    return tray.removeSplitter(), window


def shoe_shape(width):
    bottom = -7-P["foot_plate_thickness"]
    shape = Part.makeBox(width, P["foot_length"], P["foot_plate_thickness"],
                         V(-width / 2, -P["foot_length"] / 2, bottom))
    for x in (-5.2, 2.2):
        lug = Part.makeBox(3, 8, 7, V(x, -4, -7))
        lug = lug.fuse(Part.makeCylinder(4, 3, V(x, 0, 0), V(1, 0, 0)))
        lug = lug.cut(Part.makeCylinder(1.65, 5, V(x - 1, 0, 0), V(1, 0, 0)))
        shape = shape.fuse(lug)
    return shape.removeSplitter()


def shoe_pose(x, foot):
    result = np.eye(4)
    result[:3, 3] = [x, foot[0], foot[1] + L["crank_height"]]
    return result.tolist()


def add_frame(a, design, kind, x):
    thickness = design["structure"]["plate_thickness_mm"]
    reverse = kind in ("right", "front_right")
    a.add(f"P_FRAME_{kind.upper()}", pose(x + thickness / 2 if reverse else x - thickness / 2, flip=reverse))
    nodes, _, _ = frame_network(design, kind, design["structure"]["rib_width_mm"])
    for axis in nodes:
        if axis not in design["axes"]:
            continue
        center = design["axes"][axis]
        locating = (kind == "left" and axis == "O") or (kind == "right" and axis != "O")
        sign = -1 if reverse else 1
        outer = x + thickness / 2 if reverse else x - thickness / 2
        seat_thickness = thickness
        if design["id"] == "A" and axis == "I":
            frame_outer = outer
            outer -= sign*8
            seat_thickness = 8
            a.add("P_INPUT_CARRIAGE_LOC" if locating else "P_INPUT_CARRIAGE_FLOAT",
                  pose(outer, center, flip=reverse))
            for yy in (-18, 18):
                for zz in (-18, 18):
                    point = (center[0]+yy, center[1]+zz)
                    a.fastener("countersunk", outer, point, 30, 4, reverse)
                    inner = frame_outer+sign*thickness
                    a.fastener("washer", inner, point, 0.8, 4, reverse)
                    a.fastener("locknut", inner+sign*0.8, point, diameter=4, flip=reverse)
        depth = H["bearing_pocket_locating"] if locating else H["bearing_pocket_floating"]
        a.add("H_608", pose(outer + sign * (depth - 7) / 2, center, flip=reverse), assembly_group=f"bearing_{axis}")
        a.instances[-1]["axis"] = axis
        a.supports.setdefault(axis, []).append(dict(outer=outer, sign=sign, locating=locating, kind=kind))
        a.add("P_BEARING_RETAINER", pose(outer - sign * 2, center, flip=reverse))
        for point in bearing_screw_points(center):
            a.fastener("bolt", outer - sign * 2, point, seat_thickness + 2, flip=reverse)
            a.fastener("nut", outer + sign * (seat_thickness - 2.5), point, flip=reverse)


def add_legs(a, design):
    thickness = design["structure"]["plate_thickness_mm"]
    layout = axial_layout(thickness, False, design["foot_offset"])
    pitch = L["bay_pitch"]
    span = L["bay_count"] * pitch
    for index, phase_deg in enumerate(L["phases"]):
        bay = index * pitch
        phase = math.radians(phase_deg)
        rotating = dict(type="crank", bay=bay, phase=phase)
        first, second = bay + layout["left_cheek"], bay + layout["right_cheek"]
        a.add("P_CRANK_CHEEK", pose(first, angle=phase), rotating, "crank")
        a.add("P_CRANK_CHEEK", pose(second + 8, angle=phase, flip=True), rotating, "crank")
        a.add("H_REX_HUB", hub_pose(first - 8, angle=phase), rotating, "crank")
        a.add("H_REX_HUB", hub_pose(second + 16, angle=phase, flip=True), rotating, "crank")
        for face, flip in ((first, False), (second + 8, True)):
            sign = -1 if flip else 1
            for yy, zz in square_holes():
                point = (math.cos(phase) * yy - math.sin(phase) * zz,
                         math.sin(phase) * yy + math.cos(phase) * zz)
                a.fastener("countersunk", face + sign * 8, point, 16, 4, not flip, rotating, "crank")
        for face, flip in ((first + 4.5, False), (second + 3.5, True)):
            sign = -1 if flip else 1
            a.fastener("endwasher", face, (0, 0), diameter=4, flip=flip, motion=rotating, group="crank")
            a.fastener("button", face + sign * 0.8, (0, 0), 8, 4, not flip, rotating, "crank")
        for mirrored in (False, True):
            local = axial_layout(thickness, mirrored, design["foot_offset"])
            for original_id in LINKS:
                part_id = original_id + "_R" if mirrored and original_id in ("L_PBD", "L_CEF") else original_id
                a.add(part_id, link_pose(part_id, bay + local[original_id], phase, mirrored),
                      dict(type="link", part_id=part_id, bay=bay, phase=phase, mirrored=mirrored), "legs")
            for node in ("B", "C", "D", "E"):
                a.joint(node, bay, phase, local, mirrored)
            pivot = gait(0, mirrored)["P"]
            for part_id in ("L_PBD", "L_PC"):
                a.fastener("pivot_sleeve", bay + local[part_id] - 0.1, pivot, 3.2, group="pivot")
            intervals = [(bay + thickness / 2 + 0.2, bay + local["L_PBD"] - 0.1),
                         (bay + local["L_PBD"] + 3.1, bay + local["L_PC"] - 0.1),
                         (bay + local["L_PC"] + 3.1, (index + 1) * pitch - thickness / 2 - 0.2)]
            for low, high in intervals:
                a.fastener("pivot_sleeve", low, pivot, high - low, group="pivot")
            foot = gait(phase, mirrored)["F"]
            foot_x = bay + local["L_CEF"] + 1.5
            foot_motion = dict(type="joint", node="F", phase=phase, bay=bay, mirrored=mirrored)
            a.add("P_SHOE", shoe_pose(foot_x, foot), foot_motion, "feet")
            a.add("S_SOLE", shoe_pose(foot_x, foot), foot_motion, "feet")
            a.fastener("sleeve", foot_x - 1.6, foot, 3.2, motion=foot_motion, group="feet")
            for offset in (-2.2, 1.7, -5.7, 5.2):
                a.fastener("washer", foot_x + offset, foot, 0.5, motion=foot_motion, group="feet")
            a.fastener("bolt", foot_x - 5.7, foot, 20, motion=foot_motion, group="feet")
            a.fastener("locknut", foot_x + 5.7, foot, motion=foot_motion, group="feet")
            # Sole is mechanically tied around the plate; no load path depends on adhesive.
            for offset in (-design["foot_width"]/4, design["foot_width"]/4):
                a.add("H_SOLE_STRAP", shoe_pose(foot_x+offset, foot), foot_motion, "feet")
        crank_point = gait(phase)["A"]
        crank_motion = dict(type="joint", node="A", bay=bay, phase=phase)
        a.fastener("washer", first - 0.8, crank_point, 0.8, 4, motion=crank_motion, group="crank")
        a.fastener("bolt", first - 0.8, crank_point, 45, 4, motion=crank_motion, group="crank")
        a.fastener("washer", second + 8, crank_point, 0.8, 4, motion=crank_motion, group="crank")
        a.fastener("locknut", second + 8.8, crank_point, diameter=4, motion=crank_motion, group="crank")
        at = bay + layout["gap"]
        stack = ((0, "washer", 0.5), (0.5, "crank_sleeve", 3.2),
                 (3.7, "washer", 0.5), (4.2, "crank_sleeve", 3.2),
                 (7.4, "washer", 0.5), (7.9, "crank_sleeve", 3.2),
                 (11.1, "washer", 0.5), (11.6, "crank_sleeve", 3.2),
                 (14.8, "washer", 0.5), (15.3, "crank_sleeve", 4.7))
        for offset, kind, length in stack:
            a.fastener(kind, at + offset, crank_point, length, 4, motion=crank_motion, group="crank")
    left_end = layout["left_cheek"] + 4.5
    right_start = layout["right_cheek"] + 3.5
    shaft_low = min(s["outer"] for s in a.supports["O"])-16
    shaft_high = max(s["outer"] for s in a.supports["O"])+16
    segments = [(shaft_low, left_end)]
    segments += [(i * pitch + right_start, (i + 1) * pitch + left_end) for i in range(L["bay_count"] - 1)]
    segments += [((L["bay_count"] - 1) * pitch + right_start, shaft_high)]
    for start, end in segments:
        a.add(a.stock("shaft", end - start, 8), pose(start), motion(design, "O"), "crank")
    collar_start = -thickness / 2 - 11
    bearing_end = -thickness / 2 + 7.1
    a.add("H_COLLAR8", pose(collar_start), motion(design, "O"), "crank")
    a.fastener("inner_spacer", collar_start + 8, (0, 0), 3.1, motion=motion(design, "O"))
    a.fastener("inner_spacer", bearing_end, (0, 0), layout["left_hub"] - bearing_end - 0.2, motion=motion(design, "O"))
    for x, flip in ((shaft_low, True), (shaft_high, False)):
        a.fastener("endwasher", x, (0, 0), diameter=4, flip=flip, motion=motion(design, "O"))
        a.fastener("button", x + (-0.8 if flip else 0.8), (0, 0), 8, 4, not flip, motion(design, "O"))


def add_rotor(a, design):
    rotor = design["rotor"]
    center = design["axes"]["I"]
    rotating = motion(design, "I")
    span = L["bay_count"] * L["bay_pitch"]
    start = (span - rotor["span"]) / 2
    arm_t = rotor["arm_thickness"] if rotor["spider"] else 0
    points = rotor_points(rotor)
    for end, reverse in ((start, False), (start + rotor["span"], True)):
        sign = -1 if reverse else 1
        a.add("P_ROTOR_CORE_R" if reverse else "P_ROTOR_CORE", pose(end, center, flip=reverse), rotating, "rotor")
        a.add("H_REX_HUB", hub_pose(end - sign * 8, center, flip=reverse), rotating, "rotor")
        for y, z in square_holes():
            point = (center[0] + y, center[1] + z)
            a.fastener("washer", end + sign * 5, point, 0.8, 4, reverse, rotating, "rotor")
            a.fastener("bolt", end + sign * 5.8, point, 12, 4, not reverse, rotating, "rotor")
        if rotor["spider"]:
            for angle in (0, math.pi):
                a.add("P_ROTOR_YOKE_R" if reverse else "P_ROTOR_YOKE",
                      pose(end+sign*5, center, angle, reverse), rotating, "rotor")
            roots = yoke_roots(rotor)
            for point in roots+[(-x, -y) for x, y in roots]:
                yz = np.array(center)+point
                a.fastener("washer", end-sign*0.8, yz, 0.8, 4, reverse, rotating, "rotor")
                a.fastener("bolt", end-sign*0.8, yz, 16, 4, reverse, rotating, "rotor")
                a.fastener("nut", end+sign*(5+arm_t-3.3), yz, diameter=4, flip=reverse, motion=rotating, group="rotor")
        for point in points+[(-x, -y) for x, y in points]:
            yz = np.array(center) + point
            screw_face = end + sign * (5 if rotor["spider"] else 0)
            a.fastener("washer", screw_face - sign * 0.5, yz, 0.5, flip=reverse, motion=rotating, group="rotor")
            screw_length = 16 if rotor["spider"] else 12
            a.fastener("bolt", screw_face - sign * 0.5, yz, screw_length, flip=reverse, motion=rotating, group="rotor")
            a.fastener("nut", end + sign * (5 + arm_t + 3.5), yz, flip=reverse, motion=rotating, group="rotor")
    for angle in (0, math.pi):
        a.add("P_ROTOR_CUP", pose(start + 5 + arm_t, center, angle), rotating, "rotor")


def build(design):
    a = Assembly(design)
    a.supports = {}
    thickness = design["structure"]["plate_thickness_mm"]
    pitch = L["bay_pitch"]
    span = L["bay_count"] * pitch
    a.define("H_REX_HUB", hub(), "purchased",
             "goBILDA1309-0016-4008, REX8/7AF, 32ODx8 plus14pilotx2, 4xM4 on16square. REX corner datum15deg; reversed hub indexed90deg without moving bolt holes. Flexure and supplied clamp screws simplified.", 2.7, 14)
    a.define("H_608", bearing(), "purchased", "608-ZZ 8x22x7; ring/ shield envelopes, assumed12g, verify actual ring faces and starting drag.", mass=12)
    a.define("H_COLLAR8", collar(8), "purchased", "Split collar8 ID, envelope18ODx8, M3 clamp. Axial retention only; procurement and tightening spec pending.")
    a.define("H_COLLAR6", collar(6), "purchased", "Split collar6 ID, envelope16ODx8, M3 clamp; stationary pivot retention.")
    for part_id in list(LINKS) + ["L_PBD_R", "L_CEF_R"]:
        a.define(part_id, link_shape(part_id), "printed",
                 f"PETG Jansen {part_id}; thickness3, web{'7.5' if part_id == 'L_AC' else '8'}; P bore8.2, A bore6.2, other joints4.2; mirrored triangles have_R suffix.")
    a.define("P_CRANK_CHEEK", cheek(), "printed", "8 thick, crank21; metal flange4M4x16 countersunk; recessed M4 shaft end stops; M4 shared crank pin.")
    for kind in ("core", "left", "right", "front_left", "front_right"):
        a.define(f"P_FRAME_{kind.upper()}", frame_shape(design, kind, kind in ("right", "front_right")), "printed",
                 f"PETG {thickness:g} thick x{design['structure']['rib_width_mm']:g} ribs; actual preserve seats/bolt holes; {kind}; 22.2 bearing seats, 20.2 outer-ring shoulders.")
    if design["id"] == "A":
        for locating in (False, True):
            a.define("P_INPUT_CARRIAGE_LOC" if locating else "P_INPUT_CARRIAGE_FLOAT",
                     bearing_carriage(locating), "printed",
                     "48x48x8 input bearing carriage, fourM4 countersunk mounts in real +/-1.5mm frame slots; align all3 carriages together before tensioning.")
    a.define("P_BEARING_RETAINER", retainer(), "printed", "44ODx2,20.2aperture,twoM3 on32PCD; outer ring only.")
    for stage in design["stages"]:
        if stage["type"] == "belt":
            a.define("H_PULLEY24", pulley(24), "purchased",
                     "goBILDA3411-0014-0024;24T HTD5M,14bore,38.9flanges,12width,9.25belt channel; use unthreaded/counterbored16-square pattern (clocked45deg from threaded pattern); tooth envelope only.", 2.7, 23)
            a.define("H_PULLEY48", pulley(48), "purchased",
                     "goBILDA3415-0014-0048;48T HTD5M,14bore,78.7flanges,12width,9.3channel;4mm clearance grid; simplified purchased tooth envelope.", 1.2, 42)
            a.define("H_BELT520", belt_shape(stage), "purchased",
                     "goBILDA3412-0009-0520, HTD5M,104teeth,520pitch length,9width; neoprene/fiberglass; CAD envelope excludes meshing-tooth detail.", 1.2)
        else:
            for wheel, suffix in ((False, "PINION"), (True, "WHEEL")):
                teeth = stage["wheel_teeth"] if wheel else stage["pinion_teeth"]
                a.define(f"P_{stage['id']}_{suffix}", gear_shape(design, stage, wheel), "printed",
                         f"Involute20deg,m{stage['module']},z{teeth},8face,pair backlash0.30;4M4 bolted REX hub; phase follows actual stage axis vector.")
    a.define("P_ROTOR_CUP", cup_shape(design["rotor"]), "printed",
             f"Scoop for diameter{2*design['rotor']['radius']:g}, span180, wall{design['rotor']['wall']:g}; shaft clearance10; open-access M3 nuts.")
    for reverse in (False, True):
        a.define("P_ROTOR_CORE_R" if reverse else "P_ROTOR_CORE", rotor_core(design["rotor"], reverse), "printed",
                 "Rotor core/endplate5 thick,14.2pilot,4M4 mounting; opposite end has mirrored hole pattern.")
        if design["rotor"]["spider"]:
            a.define("P_ROTOR_YOKE_R" if reverse else "P_ROTOR_YOKE", rotor_yoke(design["rotor"], reverse), "printed",
                     f"One fused fork per cup/end, thickness{design['rotor']['arm_thickness']},width{design['rotor']['arm_width']}; twoM4 root fasteners and twoM3 cup fasteners; no overlapping separate spokes.")
    for index, stage in enumerate(design["stages"]):
        tray, window = guard(design, index)
        depth = stage["guard_depth"]
        aperture = stage["window_aperture_mm"]
        screw_length = stage["window_screw_length_mm"]
        carriage_note = (f" Four additional{stage['carriage_screw_window_bore_mm']:g}mm carriage-screw clearance holes "
                         "on36mm square around input axis, including +/-1.5mm adjustment.") if stage["type"] == "belt" else ""
        a.define(f"P_GUARD_{index+1}", tray, "printed",
                 f"Per-stage guard{depth:g} deep,2back/2.5walls, two chassis-rod tabs, rear-accessible captiveM3 cover nuts; not certified containment.")
        a.define(f"S_WINDOW_{index+1}", window, "cut_to_length",
                 f"Clear PETG sheet1, cut/drill from CAD, fourM3x{screw_length},{aperture}shaft apertures; not a printed part.{carriage_note}", 1.27)
    a.define("P_SHOE", shoe_shape(design["foot_width"]), "printed",
             f"PETG shoe{design['foot_width']}x{P['foot_length']}x{P['foot_plate_thickness']}, free M3/4mm-bush pitch hinge; replaceable sole; foot dimensions include drivetrain COG/foot-sweep tradeoff.")
    bottom = -P["foot_pivot_to_ground"]
    sole = Part.makeBox(design["foot_width"], P["foot_length"], P["sole_thickness"],
                        V(-design["foot_width"]/2, -P["foot_length"]/2, bottom))
    for x in (-design["foot_width"]/4, design["foot_width"]/4):
        sole = sole.cut(Part.makeBox(4.2, P["foot_length"]+2, 0.5, V(x-2.1, -P["foot_length"]/2-1, bottom)))
    a.define("S_SOLE", sole, "cut_to_length",
             f"Rubber/foam sole{design['foot_width']}x{P['foot_length']}x3; two4.2-wide,0.5-deep strap recesses; grip/compliance unmeasured; density0.8 assumed.", 0.8)
    strap_outer = Part.makeBox(4, P["foot_length"]+1, -6.5-bottom,
                               V(-2, -P["foot_length"]/2-0.5, bottom))
    strap_inner = Part.makeBox(6, P["foot_length"], -7-bottom-0.5,
                               V(-3, -P["foot_length"]/2, bottom+0.5))
    a.define("H_SOLE_STRAP", strap_outer.cut(strap_inner), "purchased",
             "Replaceable nylon cable tie, nominal4 wide; two per sole/plate; lock head simplified; mechanical retention, not adhesive.", 1.1)
    a.define("Q_BEARING_FIT", coupon(), "printed", "Separate21.9/22.1/22.3 bearing seat coupon; assembly quantity0.")
    a.define("Q_JOINT_FIT", joint_coupon(), "printed", "Separate4.0/4.2/6.0/6.2/8.2 bore coupon; assembly quantity0.")

    add_frame(a, design, "left", 0)
    for index in range(1, L["bay_count"]):
        add_frame(a, design, "core", index * pitch)
    add_frame(a, design, "right", span)
    add_frame(a, design, "front_left", -design["case"]["left"]["front_offset"])
    add_frame(a, design, "front_right", span+design["case"]["right"]["front_offset"])
    rod_length = span + thickness + 22
    a.define("H_PIVOT_ROD6", cylinder(3, rod_length), "cut_to_length", f"Ground steel6 x{rod_length:g}, h8 target; verify finish/straightness; supported at84 mm intervals.")
    for mirrored in (False, True):
        point = gait(0, mirrored)["P"]
        a.add("H_PIVOT_ROD6", pose(-thickness/2-11, point))
        for x in (-thickness/2-9, span+thickness/2+1):
            a.add("H_COLLAR6", pose(x, point))
    a.define("H_BODY_TIE", cylinder(2, span+32), "cut_to_length", f"Steel M4 threaded rod x{span+32:g}; simplified thread.")
    for point in design["ties"]:
        a.add("H_BODY_TIE", pose(-16, point))
        for index in range(L["bay_count"]):
            a.fastener("tie_tube", index*pitch+thickness/2, point, pitch-thickness)
        for x in (-thickness/2-0.8, span+thickness/2):
            a.fastener("washer", x, point, 0.8, 4)
        a.fastener("locknut", -thickness/2-5.8, point, diameter=4)
        a.fastener("locknut", span+thickness/2+0.8, point, diameter=4)
    add_legs(a, design)
    for axis, center in design["axes"].items():
        if axis == "O":
            continue
        low = min(s["outer"] for s in a.supports[axis])-16
        high = max(s["outer"] for s in a.supports[axis])+16
        a.add(a.stock("shaft", high-low, 8), pose(low, center), motion(design, axis), "rotor" if axis == "I" else "drivetrain")
        for x, flip in ((low, True), (high, False)):
            a.fastener("endwasher", x, center, diameter=4, flip=flip, motion=motion(design, axis))
            a.fastener("button", x+(-0.8 if flip else 0.8), center, 8, 4, not flip, motion(design, axis))
        locating = [support for support in a.supports[axis] if support["locating"]]
        if len(locating) != 1 or locating[0]["sign"] != -1:
            raise RuntimeError(f"Expected exactly one right locating bearing for {axis}")
        outer = locating[0]["outer"]
        bearing_low, bearing_high = outer-7.1, outer-0.1
        inner_collar = bearing_low-9.9
        outer_collar = outer+2.5
        for x in (inner_collar, outer_collar):
            a.add("H_COLLAR8", pose(x, center), motion(design, axis), "drivetrain")
        a.fastener("inner_spacer", inner_collar+8, center, 1.7, motion=motion(design, axis))
        a.fastener("inner_spacer", bearing_high, center, 2.6, motion=motion(design, axis))
    add_rotor(a, design)
    for index, stage in enumerate(design["stages"]):
        left = stage["side"] == "left"
        sign, origin = (-1, 0) if left else (1, span)
        near = origin+sign*stage["body_offset"]
        if stage["type"] == "belt":
            for teeth, axis in ((24, stage["input_axis"]), (48, stage["output_axis"])):
                center, rotating = design["axes"][axis], motion(design, axis)
                a.add(f"H_PULLEY{teeth}", pose(near-12, center), rotating, "drivetrain")
                a.add("H_REX_HUB", hub_pose(near-20, center), rotating, "drivetrain")
                for y, z in square_holes():
                    point = (center[0]+y, center[1]+z)
                    if teeth == 24:
                        a.fastener("bolt", near-4, point, 16, 4, True, rotating, "drivetrain")
                    else:
                        a.fastener("washer", near, point, 0.8, 4, motion=rotating, group="drivetrain")
                        a.fastener("bolt", near+0.8, point, 20, 4, True, rotating, "drivetrain")
            a.add("H_BELT520", pose(near-10.5), assembly_group="drivetrain")
        else:
            for wheel, suffix in ((False, "PINION"), (True, "WHEEL")):
                axis = stage["output_axis"] if wheel else stage["input_axis"]
                center, rotating = design["axes"][axis], motion(design, axis)
                a.add(f"P_{stage['id']}_{suffix}", pose(near+sign*8, center, flip=not left), rotating, "drivetrain")
                a.add("H_REX_HUB", hub_pose(near+sign*16, center, flip=not left), rotating, "drivetrain")
                for y, z in square_holes():
                    point = (center[0]+y, center[1]+z)
                    a.fastener("washer", near-sign*0.8, point, 0.8, 4, left, rotating, "drivetrain")
                    a.fastener("bolt", near-sign*0.8, point, 16, 4, left, rotating, "drivetrain")
        back = origin+sign*stage["guard_back_offset"]
        depth = stage["guard_depth"]
        info = design["case"][stage["side"]]["stages"][str(index)]
        a.add(f"P_GUARD_{index+1}", pose(back, flip=left), assembly_group="guard")
        a.add(f"S_WINDOW_{index+1}", pose(back+sign*depth, flip=left), assembly_group="guard_lid")
        for point in info["cover_corners"]:
            a.fastener("washer", back+sign*(depth+1), point, 0.5, flip=left, group="guard_lid")
            a.fastener("bolt", back+sign*(depth+1.5), point, stage["window_screw_length_mm"],
                       flip=not left, group="guard_lid")
            a.fastener("nut", back+sign*2.5, point, flip=not left, group="guard")
    for side, case in design["case"].items():
        left = side == "left"
        sign, origin = (-1, 0) if left else (1, span)
        front_offset = case["front_offset"]
        part_id = f"H_CASE_TIE_{side.upper()}"
        a.define(part_id, cylinder(2, front_offset+32), "cut_to_length",
                 f"Steel M4 case tie length{front_offset+32:g}; front carrier and guard-tab supports.")
        for post_index, point in enumerate(case["posts"]):
            a.add(part_id, pose(origin-sign*16, point, flip=left))
            intervals = [(thickness/2, thickness/2)]
            for key, info in case["stages"].items():
                if info["mount_row"] == post_index//2:
                    distance = design["stages"][int(key)]["guard_back_offset"]
                    intervals.append((distance, distance+2))
            intervals.append((front_offset-thickness/2, front_offset-thickness/2))
            intervals.sort()
            for (_, end), (begin, _) in zip(intervals, intervals[1:]):
                a.fastener("tie_tube", origin+sign*end, point, begin-end, flip=left)
            a.fastener("washer", origin-sign*(thickness/2+0.8), point, 0.8, 4, left)
            a.fastener("locknut", origin-sign*(thickness/2+5.8), point, diameter=4, flip=left)
            a.fastener("washer", origin+sign*(front_offset+thickness/2), point, 0.8, 4, left)
            a.fastener("locknut", origin+sign*(front_offset+thickness/2+0.8), point, diameter=4, flip=left)
    a.finalize()


if __name__ == "__main__":
    if args.search:
        search()
    for candidate in selected_designs():
        if not args.only or candidate["id"] == args.only:
            build(candidate)
