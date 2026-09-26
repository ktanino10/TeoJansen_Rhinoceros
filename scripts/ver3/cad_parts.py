"""Build inspectable B-rep assemblies using FreeCAD's bundled Python.

No GUI session is opened or modified. The configuration and core.py are the
parametric source; FCStd documents contain named, dimension-tagged Part features.
"""

from __future__ import annotations

from collections import Counter
import csv
import gzip
import json
import math
from pathlib import Path
import sys

import FreeCAD as App
import Part
import MeshPart
import numpy as np
from scipy.spatial import ConvexHull

from core import (CONFIG, ROOT, OUT, LINKS, axial_layout, dump, gait,
                  gear_outline, generate_search, link_pose, local_link,
                  pose, selected_designs, structure_nodes)

V = App.Vector
H = CONFIG["hardware"]
L = CONFIG["linkage"]
G = CONFIG["gears"]
R = CONFIG["rotor"]
S = CONFIG["structure"]
PLASTIC = CONFIG["assumptions"]["printed_density_g_cm3"]
CAD = ROOT / "FreeCAD" / "Ver.3"
PRINT = ROOT / "STL" / "Ver.3"


def cylinder(radius, height, x=0, y=0, z=0):
    return Part.makeCylinder(radius, height, V(x, y, z))


def disk(radius, height, bore=0):
    shape = cylinder(radius, height)
    return shape.cut(cylinder(bore / 2, height + 2, z=-1)) if bore else shape


def polygon(points, height):
    vertices = [V(float(x), float(y), 0) for x, y in points]
    wire = Part.makePolygon(vertices + [vertices[0]])
    return Part.Face(wire).extrude(V(0, 0, height))


def hexagon(across_flats, height, x=0, y=0, z=0):
    radius = across_flats / math.sqrt(3)
    shape = polygon([(x + radius * math.cos(i * math.pi / 3),
                      y + radius * math.sin(i * math.pi / 3)) for i in range(6)], height)
    shape.translate(V(0, 0, z))
    return shape


def capsule(first, second, width, height):
    first, second = np.asarray(first), np.asarray(second)
    delta = second - first
    normal = width / 2 * np.array([-delta[1], delta[0]]) / np.linalg.norm(delta)
    block = polygon([first + normal, second + normal, second - normal, first - normal], height)
    return block.fuse(cylinder(width / 2, height, *first)).fuse(
        cylinder(width / 2, height, *second))


def ring_at(point, outer, bore, thickness):
    shape = disk(outer / 2, thickness, bore)
    shape.translate(V(*point, 0))
    return shape


def drilled(shape, locations, diameter, height, z=-1):
    for x, y in locations:
        shape = shape.cut(cylinder(diameter / 2, height, x, y, z))
    return shape


def square_holes():
    half = H["hub_hole_square"] / 2
    return [(x, y) for x in (-half, half) for y in (-half, half)]


def bearing_screw_points(center=(0, 0)):
    return [(center[0] + 16 * math.cos(t * math.pi / 2),
             center[1] + 16 * math.sin(t * math.pi / 2)) for t in (0, 2)]


def rex(length):
    shape = cylinder(4, length).common(hexagon(7, length))
    shape.rotate(V(0, 0, 0), V(0, 0, 1), H["rex_clocking_degrees"])
    return shape


def shaft(length):
    shape = rex(length)
    for z in (0, length - 10):
        shape = shape.cut(cylinder(1.65, 10, z=z))
    return shape


def hub():
    # Envelope model, not a copy of the manufacturer's patented flexure shape.
    shape = disk(16, 8).fuse(cylinder(7, 2, z=8))
    bore = hexagon(7.08, 12, z=-1)
    bore.rotate(V(0, 0, 0), V(0, 0, 1), H["rex_clocking_degrees"])
    shape = shape.cut(bore)
    shape = drilled(shape, square_holes(), 3.3, 10, -1)
    slit = Part.makeBox(14, 0.7, 8, V(3, -0.35, 0))
    shape = shape.cut(slit)
    clamp_bore = Part.makeCylinder(1.65, 24, V(10, -12, 4), V(0, 1, 0))
    shape = shape.cut(clamp_bore)
    return shape


def hub_pose(x, yz=(0, 0), angle=0, flip=False):
    # Reflecting the15deg bore requires a90deg index; the square bolt pattern is invariant.
    index = math.radians(H["reversed_hub_index_degrees"]) if flip else 0
    return pose(x, yz, angle + index, flip)


def bearing():
    return Part.makeCompound([disk(11, 7, 19.2), disk(6, 7, 8),
                              disk(9.6, 0.4, 12.2).translated(V(0, 0, 0.6)),
                              disk(9.6, 0.4, 12.2).translated(V(0, 0, 6.0))])


def bolt(diameter, length, head="socket"):
    if head == "countersunk":
        shape = Part.makeCone(4, 2, 2, V(0, 0, 0))
        shape = shape.fuse(cylinder(2, length - 2, z=2))
        return shape.cut(hexagon(2.5, 1.6, z=-0.1))
    head_d = {3: 5.5, 4: 7, 6: 10}[diameter]
    head_h = diameter if head == "socket" else 2.2
    if head != "socket":
        head_d = 7.6
    shape = cylinder(diameter / 2, length)
    shape = shape.fuse(cylinder(head_d / 2, head_h, z=-head_h))
    drive = 2.5 if head == "button" else {3: 2.5, 4: 3.0, 6: 5.0}[diameter]
    socket = hexagon(drive, head_h / 2 + 0.1, z=-head_h - 0.1)
    return shape.cut(socket)


def nut(diameter, locking=False):
    across = {3: 5.5, 4: 7.0, 6: 10.0}[diameter]
    height = {3: 2.4, 4: 3.2, 6: 5.0}[diameter]
    if locking:
        height = {3: 4.0, 4: 5.0, 6: 6.0}[diameter]
    return hexagon(across, height).cut(cylinder(diameter / 2, height + 2, z=-1))


def collar(diameter):
    outer_radius = diameter / 2 + 5
    shape = disk(outer_radius, 8, diameter + 0.05)
    shape = shape.cut(Part.makeBox(diameter, 0.8, 8, V(diameter / 2, -0.4, 0)))
    cross = Part.makeCylinder(1.65, 24, V(diameter / 2 + 2.5, -12, 4), V(0, 1, 0))
    return shape.cut(cross)


def link_shape(part_id):
    coords = local_link(part_id)
    count = len(coords)
    pairs = list(zip(coords, coords[1:] + coords[:1])) if count == 3 else [(coords[0], coords[1])]
    width = L["ac_link_width"] if part_id == "L_AC" else L["link_width"]
    pieces = [capsule(a, b, width, L["link_thickness"]) for a, b in pairs]
    shape = pieces[0].multiFuse(pieces[1:]) if len(pieces) > 1 else pieces[0]
    for name, point in zip(LINKS[part_id.removesuffix("_R")], coords):
        bore = L["fixed_pivot_bore"] if name == "P" else 6.2 if name == "A" else 4.2
        boss_radius = 7 if name == "P" else 5 if name == "A" else 4
        shape = shape.fuse(cylinder(boss_radius, 3, *point))
        shape = shape.cut(cylinder(bore / 2, 5, *point, -1))
    return shape.removeSplitter()


def cheek():
    radius = L["OA"] * L["scale"]
    shape = disk(18, 8).fuse(capsule((0, 0), (radius, 0), 10, 8))
    shape = shape.cut(cylinder(4.1, 10, z=-1))
    shape = shape.cut(cylinder(7.1, 2.15, z=-0.05))
    shape = shape.cut(cylinder(6.5, 3.6, z=4.5))
    shape = drilled(shape, square_holes(), 4.4, 10)
    for x, y in square_holes():
        shape = shape.cut(Part.makeCone(2.2, 4.2, 2, V(x, y, 6)))
    shape = drilled(shape, [(radius, 0)], 4.4, 10)
    # A shallow datum notch, away from loaded holes, makes phase setup inspectable.
    shape = shape.cut(Part.makeBox(2, 1.2, 1, V(-18, -0.6, 7.2)))
    return shape


def gear(shape_cfg, role):
    teeth = shape_cfg["pinion_teeth"] if role == "pinion" else shape_cfg["wheel_teeth"]
    phase = -math.pi / 2 - math.pi / teeth if role == "pinion" else math.pi / 2
    co, si = math.cos(phase), math.sin(phase)
    points = [(co * x - si * y, si * x + co * y)
              for x, y in gear_outline(shape_cfg["module"], teeth)]
    shape = polygon(points, 8)
    shape = shape.cut(cylinder(7.1, 10, z=-1))
    if role == "wheel":
        root = shape_cfg["module"] * (teeth / 2 - 1.25)
        center = (22 + root - 6) / 2
        radius = min((root - 6 - 22) / 2, (center - 8) / 2)
        holes = [(center * math.cos(i * math.pi / 3),
                  center * math.sin(i * math.pi / 3)) for i in range(6)]
        shape = drilled(shape, holes, radius * 2, 10)
    return drilled(shape, square_holes(), 4.4, 10)


def plate(center, style, thickness, rib_width, tower, floating):
    nodes, edges = structure_nodes(center, tower)
    radii = {name: S["bearing_preserve_radius"] if name in ("O", "I")
             else S["pivot_preserve_radius"] if name in ("P", "J")
             else S["tie_preserve_radius"] for name in nodes}
    if style == "ribs" or not tower:
        pieces = [capsule(nodes[a], nodes[b], rib_width, thickness) for a, b in edges]
        pieces += [cylinder(radii[n], thickness, *p) for n, p in nodes.items()]
        shape = pieces[0].multiFuse(pieces[1:]).removeSplitter()
    else:
        cloud = np.array([(p[0] + radii[n] * math.cos(i * math.pi / 16),
                           p[1] + radii[n] * math.sin(i * math.pi / 16))
                          for n, p in nodes.items() for i in range(32)])
        hull = ConvexHull(cloud)
        shape = polygon(cloud[hull.vertices], thickness)
    for name, point in nodes.items():
        if name in ("O", "I"):
            shape = drilled(shape, [point], H["bearing_shoulder_bore"], thickness + 2)
            float_this = not floating if name == "I" and tower else floating
            depth = H["bearing_pocket_floating"] if float_this else H["bearing_pocket_locating"]
            shape = shape.cut(cylinder(H["bearing_seat_diameter"] / 2, depth, *point))
            for x, y in bearing_screw_points(point):
                shape = shape.cut(cylinder(1.65, thickness + 2, x, y, -1))
                shape = shape.cut(hexagon(5.8, 2.6, x, y, thickness - 2.6))
        elif name in ("P", "J"):
            shape = drilled(shape, [point], H["pivot_rod_diameter"] + 0.2, thickness + 2)
        else:
            shape = drilled(shape, [point], 4.4, thickness + 2)
    if not tower:
        shape = shape.cut(cylinder(R["radius"] + 6, thickness + 2, 0, center, -1))
    return shape.removeSplitter()


def retainer():
    shape = disk(22, 2, 20.2)
    return drilled(shape, bearing_screw_points(), 3.3, 4)


def cup_bolt_points():
    points = []
    for angle in (35, 70):
        t = math.radians(angle)
        points.append((R["cup_offset"] + 18 * math.cos(t), 18 * math.sin(t)))
    return points


def cup():
    length = R["span"] - 2 * R["endplate_thickness"]
    angles = np.linspace(0, math.pi, 49)
    outer = [(R["cup_offset"] + R["cup_radius"] * math.cos(t),
              R["cup_radius"] * math.sin(t)) for t in angles]
    inner = [(R["cup_offset"] + (R["cup_radius"] - R["wall"]) * math.cos(t),
              (R["cup_radius"] - R["wall"]) * math.sin(t)) for t in reversed(angles)]
    shape = polygon(outer + inner, length)
    for point in cup_bolt_points():
        for z in (0, length - 6):
            tab = cylinder(6, 6, *point, z)
            # Tabs overlap the scoop wall and give accessible nut-bearing lands.
            shape = shape.fuse(tab)
            shape = shape.cut(cylinder(1.65, 8, *point, z - 1))
            if z == 0:
                shape = shape.cut(hexagon(5.8, 2.6, *point, 3.4))
            else:
                shape = shape.cut(hexagon(5.8, 2.6, *point, length - 6))
    shape = shape.cut(cylinder(5, length + 2, z=-1))
    return shape.removeSplitter()


def rotor_endplate(reverse=False):
    shape = disk(R["radius"], R["endplate_thickness"], 8.2)
    shape = shape.cut(cylinder(7.1, 2.1, z=-0.05))
    points = [(x, -y if reverse else y) for x, y in cup_bolt_points()]
    shape = drilled(shape, square_holes(), 4.4, 7)
    return drilled(shape, points + [(-x, -y) for x, y in points], 3.3, 7)


def guard_shapes(gear_cfg):
    center = gear_cfg["center_distance_mm"]
    radius = max(gear_cfg["tip_diameters_mm"]) / 2
    y_min, y_max = -radius - 9, radius + 9
    z_min = -gear_cfg["tip_diameters_mm"][1] / 2 - 9
    z_max = center + gear_cfg["tip_diameters_mm"][0] / 2 + 9
    corners = [(y_min + 5, z_min + 5), (y_max - 5, z_min + 5),
               (y_min + 5, z_max - 5), (y_max - 5, z_max - 5)]
    outer = Part.makeBox(y_max - y_min, z_max - z_min, 42, V(y_min, z_min, 0))
    cavity = Part.makeBox(y_max - y_min - 5, z_max - z_min - 5, 40.1,
                          V(y_min + 2.5, z_min + 2.5, -0.1))
    tray = outer.cut(cavity)
    tray = drilled(tray, [(0, 0), (0, center)], 20, 44)
    p = gait(0)["P"]
    tray = drilled(tray, [(p[0], p[1]), (-p[0], p[1])], 18, 44)
    tray = drilled(tray, S["tie_nodes"], 6, 44)
    mounts = [(-16, 0), (16, 0), (-16, center), (16, center)]
    tray = drilled(tray, mounts, 3.3, 44)
    for point in corners:
        boss = cylinder(5, 42, *point)
        tray = tray.fuse(boss)
        tray = tray.cut(cylinder(1.65, 44, *point, -1))
        tray = tray.cut(hexagon(5.8, 2.7, *point, 39.4))
    lid = Part.makeBox(y_max - y_min, z_max - z_min, 1.0, V(y_min, z_min, 0))
    lid = drilled(lid, corners, 3.3, 4)
    return tray.removeSplitter(), lid, corners


def coupon():
    shape = Part.makeBox(92, 32, 8)
    for i, diameter in enumerate((21.9, 22.1, 22.3)):
        shape = shape.cut(cylinder(diameter / 2, 7.2, 15 + 30 * i, 16))
        shape = shape.cut(cylinder(10.1, 10, 15 + 30 * i, 16, -1))
    return shape


def joint_coupon():
    shape = Part.makeBox(76, 22, 5)
    for x, diameter in zip((8, 20, 32, 44), (4.0, 4.2, 6.0, 6.2)):
        shape = shape.cut(cylinder(diameter / 2, 7, x, 11, -1))
    shape = shape.cut(cylinder(L["fixed_pivot_bore"] / 2, 7, 62, 11, -1))
    return shape


class Assembly:
    def __init__(self, design):
        self.design = design
        self.ident = design["id"]
        self.doc = App.newDocument("Ver3_" + self.ident)
        self.definitions = {}
        self.instances = []
        self.meshes = {}
        self.counter = Counter()
        self.printdir = PRINT / self.ident
        self.caddir = CAD / self.ident
        self.printdir.mkdir(parents=True, exist_ok=True)
        self.caddir.mkdir(parents=True, exist_ok=True)
        self.groups = {}
        for category in ("printed", "purchased", "cut_to_length"):
            self.groups[category] = self.doc.addObject("App::DocumentObjectGroup", category)

    def define(self, part_id, shape, category, description, density=None, mass=None):
        shape = shape.removeSplitter()
        if not shape.isValid() or not shape.Solids:
            raise RuntimeError(f"{self.ident}/{part_id}: invalid or non-solid geometry")
        if category == "printed" and len(shape.Solids) != 1:
            raise RuntimeError(f"{self.ident}/{part_id}: printable part is not one solid")
        density = density or (PLASTIC if category == "printed" else 7.85)
        shape_mass = shape.Volume * density / 1000
        centroid = V(0, 0, 0)
        for solid in shape.Solids:
            centroid += solid.CenterOfMass * solid.Volume
        centroid /= shape.Volume
        self.definitions[part_id] = {
            "shape": shape, "category": category, "description": description,
            "mass_g": mass if mass is not None else shape_mass,
            "solid_volume_mm3": shape.Volume, "solids": len(shape.Solids),
            "local_center_of_mass_mm": [centroid.x, centroid.y, centroid.z],
            "mass_basis": ("catalogue" if part_id == "H_REX_HUB" or part_id.startswith("H_PULLEY") else "assumed unit mass") if mass is not None else "nominal solid volume x assumed density",
        }

    def add(self, part_id, matrix, motion=None, assembly_group="frame", note=""):
        definition = self.definitions[part_id]
        self.counter[part_id] += 1
        name = f"{part_id}_{self.counter[part_id]:03d}"
        feature = self.doc.addObject("Part::Feature", name)
        feature.Label = name
        feature.Shape = definition["shape"]
        m = App.Matrix(*[v for row in matrix for v in row])
        feature.Placement = App.Placement(m)
        for prop, value in (("PartId", part_id), ("Category", definition["category"]),
                            ("Specification", definition["description"]), ("AssemblyGroup", assembly_group),
                            ("ConceptNote", note or "Procedurally generated concept; regenerate from design.json")):
            feature.addProperty("App::PropertyString", prop, "Ver3")
            setattr(feature, prop, value)
        feature.addProperty("App::PropertyFloat", "NominalMassGram", "Ver3")
        feature.NominalMassGram = definition["mass_g"]
        self.groups[definition["category"]].addObject(feature)
        instance = dict(name=name, part_id=part_id, transform=matrix, group=assembly_group)
        if motion:
            instance["motion"] = motion
        self.instances.append(instance)
        return name

    def stock(self, kind, length=0, diameter=3):
        token = f"{length:.3f}".rstrip("0").rstrip(".").replace(".", "p")
        part_id = f"H_{kind}_{diameter}_{token}" if length else f"H_{kind}_{diameter}"
        if part_id in self.definitions:
            return part_id
        density = 7.85
        if kind == "bolt":
            shape = bolt(diameter, length)
            desc = f"ISO 4762 M{diameter}x{length:g}, socket head; simplified thread"
        elif kind == "button":
            shape = bolt(diameter, length, "button")
            desc = f"ISO 7380-1 M{diameter}x{length:g}; simplified thread"
        elif kind == "countersunk":
            shape = bolt(diameter, length, "countersunk")
            desc = f"ISO 10642 M4x{length:g}, 90-degree countersunk, 2.5 mm hex; flush below cheek face; simplified thread"
        elif kind in ("nut", "locknut"):
            shape = nut(diameter, kind == "locknut")
            desc = f"ISO {'10511 prevailing-torque' if kind == 'locknut' else '4032'} M{diameter} nut; simplified thread"
        elif kind == "washer":
            outer = {3: 7, 4: 9, 6: 12}[diameter]
            shape = disk(outer / 2, length, diameter + 0.2)
            desc = f"Washer {diameter + 0.2:g} ID x {outer:g} OD x {length:g}; verify purchased thickness"
        elif kind == "sleeve":
            shape = disk(2, length, 3.2)
            density = 8.5
            desc = f"Cut brass tube 3.2 ID x 4 OD x {length:g}, deburred; bearing journal/rigid clamp stack"
        elif kind == "crank_sleeve":
            shape = disk(3, length, 4.2)
            density = 8.5
            desc = f"Cut brass tube 4.2 ID x 6 OD x {length:g}; crank journal/spacer"
        elif kind == "pivot_sleeve":
            inner, outer = H["pivot_rod_diameter"] + 0.1, H["pivot_rod_diameter"] + 2
            shape = disk(outer / 2, length, inner)
            density = 8.5
            desc = f"Cut brass sleeve {inner:g} ID x {outer:g} OD x {length:g}; stationary pivot journal"
        elif kind == "inner_spacer":
            shape = disk(5, length, 8.1)
            desc = f"Steel spacer/shim 8.1 ID x 10 OD x {length:g}; INNER RING ONLY"
        elif kind == "tie_tube":
            shape = disk(5, length, 6)
            density = 2.7
            desc = f"Cut aluminium tube 6 ID x 10 OD x {length:g}; square ends"
        elif kind == "shaft":
            shape = shaft(length)
            desc = (f"8 mm REX, 7 mm AF, corner datum{H['rex_clocking_degrees']:g}deg, cut to {length:g}; "
                    "M4x10 axial tapped holes both ends; machining/procurement verification pending")
        elif kind == "endwasher":
            shape = disk(6, 0.8, 4.2)
            desc = "Steel end-stop washer 4.2 ID x 12 OD x 0.8; positive shaft retention"
        else:
            raise ValueError(kind)
        category = "cut_to_length" if kind in (
            "sleeve", "crank_sleeve", "pivot_sleeve", "inner_spacer", "tie_tube", "shaft") else "purchased"
        self.define(part_id, shape, category, desc, density)
        return part_id

    def fastener(self, kind, x, yz, length=0, diameter=3, flip=False, motion=None, group="hardware"):
        return self.add(self.stock(kind, length, diameter), pose(x, yz, flip=flip), motion, group)

    def flange(self, face, yz, flip=False, motion=None, group="drivetrain", bolt_length=16):
        sign = -1 if flip else 1
        self.add("H_REX_HUB", pose(face - sign * 8, yz, flip=flip), motion, group)
        for y, z in square_holes():
            # These holes rotate with their supporting hub/gear group.
            point = (yz[0] + y, yz[1] + z)
            self.fastener("washer", face + sign * 8, point, 0.8, 4, flip, motion, group)
            self.fastener("bolt", face + sign * 8.8, point, bolt_length, 4, not flip, motion, group)

    def joint(self, node, bay, phase, layout, mirrored=False):
        ids = [part for part, names in LINKS.items() if node in names]
        intervals = sorted((layout[part], layout[part] + 3) for part in ids)
        points = gait(phase, mirrored)
        point = points[node]
        motion = dict(type="joint", node=node, phase=phase, bay=bay, mirrored=mirrored)
        first = intervals[0][0] - 0.1
        last = intervals[-1][1] + 0.1
        self.fastener("washer", bay + first - 0.5, point, 0.5, motion=motion, group="legs")
        self.fastener("washer", bay + last, point, 0.5, motion=motion, group="legs")
        for start, end in intervals:
            self.fastener("sleeve", bay + start - 0.1, point, 3.2, motion=motion, group="legs")
        for (_, previous_end), (next_start, _) in zip(intervals, intervals[1:]):
            left, right = previous_end + 0.1, next_start - 0.1
            gap = right - left
            if gap < 0.5:
                raise RuntimeError("No thrust-washer clearance")
            self.fastener("washer", bay + left, point, 0.5, motion=motion, group="legs")
            if gap > 0.5001:
                self.fastener("sleeve", bay + left + 0.5, point, gap - 0.5, motion=motion, group="legs")
        underhead = first - 0.5
        required = last + 0.5 + 4 + 1 - underhead
        screw_length = 5 * math.ceil(required / 5)
        self.fastener("bolt", bay + underhead, point, screw_length, motion=motion, group="legs")
        self.fastener("locknut", bay + last + 0.5, point, motion=motion, group="legs")

    def turn_to_right_end(self, names, span):
        rotation = np.diag([-1.0, -1.0, 1.0, 1.0])
        rotation[0, 3] = span
        for instance in self.instances:
            if instance["name"] in names:
                matrix = rotation @ np.array(instance["transform"])
                instance["transform"] = matrix.tolist()
                self.doc.getObject(instance["name"]).Placement = App.Placement(
                    App.Matrix(*matrix.ravel().tolist()))

    def finalize(self):
        self.doc.recompute()
        native = self.caddir / f"Ver3_{self.ident}.FCStd"
        temporary_native = self.caddir / f"Ver3_{self.ident}.new.FCStd"
        self.doc.saveAs(str(temporary_native))
        temporary_native.replace(native)
        objects = [obj for obj in self.doc.Objects if obj.TypeId == "Part::Feature"]
        Part.export(objects, str(self.caddir / f"Ver3_{self.ident}.step"))
        # Export a tessellation of the same local CAD solids, not a second model.
        for part_id, definition in self.definitions.items():
            shape = definition["shape"]
            vertices, triangles = shape.tessellate(0.16)
            self.meshes[part_id] = {
                "vertices": [[v.x, v.y, v.z] for v in vertices],
                "triangles": triangles, "category": definition["category"],
            }
            if definition["category"] == "printed":
                printable = shape.copy()
                printable.translate(V(0, 0, -printable.BoundBox.ZMin))
                mesh = MeshPart.meshFromShape(Shape=printable, LinearDeflection=0.12,
                                             AngularDeflection=0.18, Relative=False)
                mesh.write(str(self.printdir / (part_id + ".stl")))
        for path in self.printdir.glob("*.stl"):
            if path.stem not in self.definitions or self.definitions[path.stem]["category"] != "printed":
                path.unlink()
        with gzip.open(self.caddir / "render_geometry.json.gz", "wt", encoding="utf8") as stream:
            json.dump(self.meshes, stream, separators=(",", ":"))
        definitions = {part_id: {key: value for key, value in item.items() if key != "shape"}
                       for part_id, item in self.definitions.items()}
        manifest = {
            "id": self.ident, "units": "mm", "design": self.design,
            "cad_meshes": str((self.caddir / "render_geometry.json.gz").relative_to(ROOT)),
            "parts": definitions, "instances": self.instances,
            "animation": CONFIG["animation"],
            "coordinates": "X shaft / Y stride / Z vertical; matrices row-major, mm",
            "stl_orientation": "Local CAD axes; each printable translated so its lowest Z is0. Guard closed back and shoe plate are on bed. Coupons have BOM quantity0 intentionally.",
            "limitations": "No rigid-body/ground/wind simulation. Bought parts are dimensional envelopes with simplified threads/bearing internals/hub flexures.",
        }
        dump(OUT / f"assembly_{self.ident}.json", manifest)
        with (OUT / f"BOM_{self.ident}.csv").open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["prototype", "part_id", "category", "quantity",
                             "specification", "nominal_unit_mass_g", "nominal_total_mass_g", "mass_basis"])
            for part_id, item in sorted(definitions.items()):
                count = self.counter[part_id]
                writer.writerow([self.ident, part_id, item["category"], count, item["description"],
                                 round(item["mass_g"], 4), round(count * item["mass_g"], 4), item["mass_basis"]])
        # Native reopen is part of generation, not inferred from the filename.
        App.closeDocument(self.doc.Name)
        reopened = App.openDocument(str(native))
        read_objects = [o for o in reopened.Objects if o.TypeId == "Part::Feature"]
        invalid = [o.Name for o in read_objects if not o.Shape.isValid() or not o.Shape.Solids]
        if invalid or len(read_objects) != len(self.instances):
            raise RuntimeError(f"Native reopen failure: {invalid}")
        native_solids = [solid for obj in read_objects for solid in obj.Shape.Solids]
        cad_volume = sum(solid.Volume for solid in native_solids)
        step = Part.read(str(self.caddir / f"Ver3_{self.ident}.step"))
        step_volume = sum(solid.Volume for solid in step.Solids)
        error = abs(step_volume - cad_volume) / cad_volume
        if not step.isValid() or len(native_solids) != len(step.Solids) or error > 1e-6:
            raise RuntimeError(f"STEP/native volume mismatch: {error}")
        total_mass = sum(self.counter[p] * d["mass_g"] for p, d in definitions.items())
        centroid = np.zeros(3)
        for instance in self.instances:
            part = definitions[instance["part_id"]]
            point = np.array(part["local_center_of_mass_mm"] + [1])
            centroid += part["mass_g"] * (np.array(instance["transform"]) @ point)[:3]
        summary = {
            "prototype": self.ident, "native_objects": len(read_objects),
            "native_valid": True, "step_solids": len(step.Solids),
            "step_volume_relative_error": error,
            "printed_unique_parts": sum(p["category"] == "printed" for p in definitions.values()),
            "printed_instances": sum(self.counter[p] for p, d in definitions.items() if d["category"] == "printed"),
            "nominal_total_mass_g": total_mass,
            "nominal_center_of_mass_mm": (centroid / total_mass).tolist(),
            "nominal_printed_mass_g": sum(self.counter[p] * d["mass_g"] for p, d in definitions.items() if d["category"] == "printed"),
            "frame_printed_mass_g": sum(self.counter[p] * d["mass_g"] for p, d in definitions.items() if p.startswith("P_FRAME")),
            "files_bytes": {f.name: f.stat().st_size for f in self.caddir.iterdir() if f.is_file()},
        }
        dump(OUT / f"cad_validation_{self.ident}.json", summary)
        App.closeDocument(reopened.Name)
        print(json.dumps(summary, indent=2), flush=True)


def build_reference(design):
    a = Assembly(design)
    gear_cfg = design["gears"]
    center = gear_cfg["center_distance_mm"]
    structure = design["structure"]
    thick = structure["plate_thickness_mm"]
    width = structure["rib_width_mm"]
    layout = axial_layout(thick)
    pitch = L["bay_pitch"]
    span = len(L["phases"]) * pitch
    a.define("H_REX_HUB", hub(), "purchased",
             "goBILDA 1309-0016-4008; 8 mm REX / 7 AF; 32 OD x 8 + 14 pilot x 2; four M4 on 16 square. Flexure/clamp simplified, vendor screws included.", 2.7, 14)
    a.define("H_608", bearing(), "purchased",
             "608-ZZ envelope 8x22x7; inner/outer rings and shields shown, rolling internals omitted; verify low-drag bearing and actual ring faces.", mass=12)
    a.define("H_COLLAR8", collar(8), "purchased",
             "Split collar8 ID, max18 OD x8 wide, M3 clamp; conservative envelope, procurement/torque spec pending")
    a.define("H_COLLAR6", collar(6), "purchased",
             "Split collar6 ID, max16 OD x8 wide, M3 clamp; conservative envelope, procurement/torque spec pending")
    for part_id in list(LINKS) + ["L_PBD_R", "L_CEF_R"]:
        a.define(part_id, link_shape(part_id), "printed",
                 f"PETG flat XY, 3 thick, {L['ac_link_width'] if part_id == 'L_AC' else L['link_width']} wide; reference Jansen {','.join(LINKS[part_id.removesuffix('_R')])}; {'MIRRORED' if part_id.endswith('_R') else 'reference'}; smooth brass journals, do not clamp plastic pivots")
    a.define("P_CRANK_CHEEK", cheek(), "printed",
             "PETG 8 thick, crank radius21; four4.4 bores on16 square with flush M4 countersinks, 14.2x2.1 pilot, 8.2 through bore, 13x3.5 end-stop recess, 4.4 crank-pin hole")
    a.define("P_GEAR_INPUT", gear(gear_cfg, "pinion"), "printed",
             f"20deg spur involute m{gear_cfg['module']}, z{gear_cfg['pinion_teeth']}, b8, pair backlash0.30; REX metal hub bolted with fourM4x16")
    a.define("P_GEAR_OUTPUT", gear(gear_cfg, "wheel"), "printed",
             f"20deg spur involute m{gear_cfg['module']}, z{gear_cfg['wheel_teeth']}, b8, pair backlash0.30; REX metal hub bolted with fourM4x16")
    for name, tower, floating in (
            ("P_FRAME_TOWER_LOC", True, False),
            ("P_FRAME_TOWER_FLOAT", True, True),
            ("P_FRAME_CORE", False, True)):
        a.define(name, plate(center, structure["style"], thick, width, tower, floating),
                 "printed", f"PETG {thick:g} thick; {structure['style']} frame, 22.2 bearing pockets, 20.2 shoulders; M3 captive nuts at radius16; floating={floating}")
    a.define("P_BEARING_RETAINER", retainer(), "printed",
             "PETG44 OD x2, 20.2 center aperture; OUTER-RING-only retention; twoM3 on32 PCD")
    a.define("P_ROTOR_CUP", cup(), "printed",
             "New horizontal scoop, r24, offset21, 2 wall, 170 span; four reinforced M3 end tabs; not old STL")
    a.define("P_ROTOR_END", rotor_endplate(), "printed",
             "90 OD x5;14.2x2.1 pilot, fourM4 flange holes, fourM3 scoop holes; print flat")
    a.define("P_ROTOR_END_R", rotor_endplate(True), "printed",
             "Right-hand mirrored scoop hole pattern, 90 OD x5; pilot faces outward; do NOT substitute left endplate")
    tray, lid, lid_corners = guard_shapes(gear_cfg)
    a.define("P_GUARD_TRAY", tray, "printed",
             "2.5 wall, rear panel2;20 shaft apertures; four bearing-cap mounts; rear-accessible cover nuts; install BEFORE gears; containment concept, not certified finger protection")
    a.define("S_GUARD_WINDOW", lid, "cut_to_length",
             "Transparent PETG sheet1.0, rectangular cut/drilled from CAD; fourM3x45 and rear-accessible captiveM3 nuts; not a certified impact guard", 1.27)
    a.define("Q_BEARING_FIT", coupon(), "printed",
             "Separate fit coupon:21.9/22.1/22.3 diameter pockets, 7.2 depth; NOT an assembly part")
    a.define("Q_JOINT_FIT", joint_coupon(), "printed",
             "Separate fit coupon:4.0/4.2/6.0/6.2/8.2 bores; NOT an assembly part")

    # The right drive cassette balances the forward axial offset of the feet.
    # Four journals support three paired-leg crank modules.
    right_end_names = set()
    bays = L["bay_count"]
    for index in range(bays + 1):
        right = index == bays
        x = 0 if right else index * pitch
        start_count = len(a.instances)
        tower = index in (0, bays)
        frame_id = "P_FRAME_TOWER_LOC" if index == 0 else "P_FRAME_TOWER_FLOAT" if tower else "P_FRAME_CORE"
        a.add(frame_id, pose(x - thick / 2))
        for point in ((0, 0), (0, center)) if tower else ((0, 0),):
            floating = (not right) if point[1] == center else index != 0
            depth = H["bearing_pocket_floating"] if floating else H["bearing_pocket_locating"]
            bearing_x = x - thick / 2 + (depth - 7) / 2
            a.add("H_608", pose(bearing_x, point))
            a.add("P_BEARING_RETAINER", pose(x - thick / 2 - 2, point))
            for screw_point in bearing_screw_points(point):
                extended = right
                screw_x = x - thick / 2 - 2 - (8 if extended else 0)
                a.fastener("bolt", screw_x, screw_point, thick + 2 + (8 if extended else 0))
                if extended:
                    a.fastener("sleeve", screw_x + 2, screw_point, 6)
                a.fastener("nut", x + thick / 2 - 2.5, screw_point)
        if right:
            right_end_names.update(item["name"] for item in a.instances[start_count:])

    rod_length = span + thick + 22
    a.define("H_PIVOT_ROD6", cylinder(3, rod_length), "cut_to_length",
             f"Ground steel shaft6 diameter x{rod_length:g}, h8 target; supported every{pitch:g}; verify journal finish. Smaller diameter clears AC sweep.", 7.85)
    for mirrored in (False, True):
        p_point = gait(0, mirrored)["P"]
        a.add("H_PIVOT_ROD6", pose(-thick / 2 - 11, p_point))
        for x in (-thick / 2 - 9, span + thick / 2 + 1):
            a.add("H_COLLAR6", pose(x, p_point))
    a.define("H_TIE_ROD", cylinder(2, span + 32), "cut_to_length",
             f"M4 steel threaded tie rod x{span+32:g}; simplified threads; two chassis rails", 7.85)
    for point in S["tie_nodes"]:
        a.add("H_TIE_ROD", pose(-16, point))
        for index in range(bays):
            a.fastener("tie_tube", index * pitch + thick / 2, point, pitch - thick)
        for x in (-thick / 2 - 0.8, span + thick / 2):
            a.fastener("washer", x, point, 0.8, 4)
        a.fastener("locknut", -thick / 2 - 5.8, point, diameter=4)
        a.fastener("locknut", span + thick / 2 + 0.8, point, diameter=4)

    for index, phase_deg in enumerate(L["phases"]):
        bay = index * pitch
        phase = math.radians(phase_deg)
        rotating = dict(type="crank", bay=bay, phase=phase)
        first = bay + layout["left_cheek"]
        second = bay + layout["right_cheek"]
        # Cheek pilot faces point toward their respective hubs.
        a.add("P_CRANK_CHEEK", pose(first, angle=phase), rotating, "crank")
        a.add("P_CRANK_CHEEK", pose(second + 8, angle=phase, flip=True), rotating, "crank")
        a.add("H_REX_HUB", pose(first - 8, angle=phase), rotating, "crank")
        a.add("H_REX_HUB", pose(second + 16, angle=phase, flip=True), rotating, "crank")
        for face, flip in ((first, False), (second + 8, True)):
            sign = -1 if flip else 1
            for yy, zz in square_holes():
                point = (math.cos(phase) * yy - math.sin(phase) * zz,
                         math.sin(phase) * yy + math.cos(phase) * zz)
                a.fastener("countersunk", face + sign * 8, point, 16, 4, not flip, rotating, "crank")
        # M4 end-stop washers and recessed button heads capture each shaft positively.
        for face, flip in ((first + 4.5, False), (second + 3.5, True)):
            sign = -1 if flip else 1
            a.fastener("endwasher", face, (0, 0), diameter=4, flip=flip, motion=rotating, group="crank")
            a.fastener("button", face + sign * 0.8, (0, 0), 8, 4, not flip, rotating, "crank")
        for mirrored in (False, True):
            leg_layout = axial_layout(thick, mirrored)
            for original_id in LINKS:
                part_id = original_id + "_R" if mirrored and original_id in ("L_PBD", "L_CEF") else original_id
                a.add(part_id, link_pose(part_id, bay + leg_layout[original_id], phase, mirrored),
                      dict(type="link", part_id=part_id, bay=bay, phase=phase, mirrored=mirrored), "legs")
            for node in ("B", "C", "D", "E"):
                a.joint(node, bay, phase, leg_layout, mirrored)
            p_point = gait(0, mirrored)["P"]
            for part_id in ("L_PBD", "L_PC"):
                a.fastener("pivot_sleeve", bay + leg_layout[part_id] - 0.1, p_point, 3.2, group="pivot")
            intervals = [(bay + thick / 2 + 0.2, bay + leg_layout["L_PBD"] - 0.1),
                         (bay + leg_layout["L_PBD"] + 3.1, bay + leg_layout["L_PC"] - 0.1),
                         (bay + leg_layout["L_PC"] + 3.1, (index + 1) * pitch - thick / 2 - 0.2)]
            for lo, hi in intervals:
                a.fastener("pivot_sleeve", lo, p_point, hi - lo, group="pivot")
        crank_point = gait(phase)["A"]
        crank_motion = dict(type="joint", node="A", bay=bay, phase=phase)
        a.fastener("washer", first - 0.8, crank_point, 0.8, 4, motion=crank_motion, group="crank")
        a.fastener("bolt", first - 0.8, crank_point, 45, 4, motion=crank_motion, group="crank")
        a.fastener("washer", second + 8, crank_point, 0.8, 4, motion=crank_motion, group="crank")
        a.fastener("locknut", second + 8.8, crank_point, diameter=4, motion=crank_motion, group="crank")
        # Four freely rotating journals share one positively retained crank pin.
        at = bay + layout["gap"]
        for offset, kind, length in ((0, "washer", 0.5), (0.5, "crank_sleeve", 3.2),
                                     (3.7, "washer", 0.5), (4.2, "crank_sleeve", 3.2),
                                     (7.4, "washer", 0.5), (7.9, "crank_sleeve", 3.2),
                                     (11.1, "washer", 0.5), (11.6, "crank_sleeve", 3.2),
                                     (14.8, "washer", 0.5), (15.3, "crank_sleeve", 4.7)):
            a.fastener(kind, at + offset, crank_point, length, 4, motion=crank_motion, group="crank")

    # Segment ends sit under recessed washers, never inside the AB/AC moving gap.
    left_end = layout["left_cheek"] + 4.5
    right_start = layout["right_cheek"] + 3.5
    segments = [(-16, left_end)]
    segments += [(i * pitch + right_start, (i + 1) * pitch + left_end) for i in range(bays - 1)]
    segments += [((bays - 1) * pitch + right_start, span + 46)]
    for start, end in segments:
        a.add(a.stock("shaft", end - start, 8), pose(start),
              dict(type="shaft", speed=1, center=[0, 0]), "crank")
    # First output bearing locates the assembly between collar and crank hub.
    collar_left = -thick / 2 - 11
    bearing_end = -thick / 2 + 7.1
    a.add("H_COLLAR8", pose(collar_left), dict(type="shaft", speed=1, center=[0, 0]), "crank")
    a.fastener("inner_spacer", collar_left + 8, (0, 0), 3.1, motion=dict(type="shaft", speed=1, center=[0, 0]))
    a.fastener("inner_spacer", bearing_end, (0, 0), layout["left_hub"] - bearing_end - 0.2,
               motion=dict(type="shaft", speed=1, center=[0, 0]))
    for x, flip in ((-16, True), (span + 46, False)):
        a.fastener("endwasher", x, (0, 0), diameter=4, flip=flip,
                   motion=dict(type="shaft", speed=1, center=[0, 0]))
        a.fastener("button", x + (-0.8 if flip else 0.8), (0, 0), 8, 4, not flip,
                   motion=dict(type="shaft", speed=1, center=[0, 0]))

    # Horizontal-axis turbine avoids an unengineered bevel/right-angle gear stage.
    input_motion = dict(type="shaft", speed=-gear_cfg["ratio"], center=[0, center])
    a.add(a.stock("shaft", span + 62, 8), pose(-46, (0, center)), input_motion, "rotor")
    for x in (collar_left, thick / 2 + 1):
        a.add("H_COLLAR8", pose(x, (0, center)), input_motion, "rotor")
    a.fastener("inner_spacer", collar_left + 8, (0, center), 3.1, motion=input_motion, group="rotor")
    a.fastener("inner_spacer", bearing_end, (0, center), thick / 2 + 1 - bearing_end - 0.2, motion=input_motion, group="rotor")
    for x, flip in ((-46, True), (span + 16, False)):
        a.fastener("endwasher", x, (0, center), diameter=4, flip=flip, motion=input_motion, group="rotor")
        a.fastener("button", x + (-0.8 if flip else 0.8), (0, center), 8, 4, not flip, input_motion, "rotor")
    rotor_start = (span - R["span"]) / 2
    for start, flip in ((rotor_start, False), (rotor_start + R["span"], True)):
        a.add("P_ROTOR_END_R" if flip else "P_ROTOR_END",
              pose(start, (0, center), flip=flip), input_motion, "rotor")
        sign = -1 if flip else 1
        a.add("H_REX_HUB", pose(start - sign * 8, (0, center), flip=flip), input_motion, "rotor")
        for y, z in square_holes():
            point = (y, center + z)
            a.fastener("washer", start + sign * 5, point, 0.8, 4, flip, input_motion, "rotor")
            a.fastener("bolt", start + sign * 5.8, point, 12, 4, not flip, input_motion, "rotor")
        for point in cup_bolt_points() + [(-y, -z) for y, z in cup_bolt_points()]:
            yz = (point[0], center + point[1])
            a.fastener("bolt", start - sign * 0.5, yz, 12, 3, flip, input_motion, "rotor")
            a.fastener("washer", start - sign * 0.5, yz, 0.5, 3, flip, input_motion, "rotor")
            a.fastener("nut", start + sign * 8.4, yz, diameter=3, flip=flip, motion=input_motion, group="rotor")
    for angle in (0, math.pi):
        a.add("P_ROTOR_CUP", pose(rotor_start + 5, (0, center), angle), input_motion, "rotor")

    for role, yz, motion in (
            ("INPUT", (0, center), input_motion),
            ("OUTPUT", (0, 0), dict(type="shaft", speed=1, center=[0, 0]))):
        a.add("P_GEAR_" + role, pose(-28, yz), motion, "drivetrain")
        a.flange(-28, yz, motion=motion)
    guard_x = -thick / 2 - 50
    a.add("P_GUARD_TRAY", pose(guard_x), assembly_group="guard")
    a.add("S_GUARD_WINDOW", pose(guard_x - 1), assembly_group="guard_lid")
    for point in lid_corners:
        a.fastener("bolt", guard_x - 1, point, 45, group="guard_lid")
        a.fastener("nut", guard_x + 39.5, point, group="guard")
    right_end_names.update(item["name"] for item in a.instances
                           if item["group"] in ("drivetrain", "rotor", "guard", "guard_lid"))
    a.turn_to_right_end(right_end_names, span)
    a.finalize()
