"""Small Ver.3.2 M3 bench revision. Does not rebuild or overwrite r7 walkers."""

import argparse
from collections import Counter
import csv
import gzip
import hashlib
from html import escape
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/ver3/m3_r1"
CAD = ROOT / "FreeCAD/Ver.3/m3_r1"
PRINT = ROOT / "STL/Ver.3/m3_r1"
REVISION = "v3.2-m3-r1-bench"
BASE = "18dd3f40fb811b3d50cfa527b6fafbfa55a6e781"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freecad-lib", required=True)
    args = parser.parse_args()
    sys.path.insert(0, args.freecad_lib)
    import FreeCAD as App
    import Part
    import MeshPart
    import numpy as np
    from cad_parts import bolt, capsule, cylinder, disk, hexagon, polygon
    from walker_geometry import gear_pair_metrics, involute_outline

    V = App.Vector
    for path in (DOC, CAD, PRINT):
        path.mkdir(parents=True, exist_ok=True)
    parts, instances, shapes = {}, [], {}
    document = App.newDocument("M3Bench")

    def moved(shape, xyz=(0, 0, 0), angle=0):
        result = shape.copy()
        if angle:
            result.rotate(V(), V(0, 0, 1), angle)
        result.translate(V(*xyz))
        return result

    def define(pid, shape, category, description, quantity, density=1.27):
        print("STAGE_BEGIN", pid, flush=True)
        shape = shape.removeSplitter()
        if not shape.isValid() or len(shape.Solids) != 1 or shape.Volume <= 0:
            raise ValueError(f"{pid}: expected one valid positive solid")
        shapes[pid] = shape
        parts[pid] = {
            "category": category, "description": description, "quantity": quantity,
            "volumeMm3": shape.Volume, "nominalMassG": shape.Volume * density / 1000,
            "densityGcm3Assumed": density,
        }
        if category == "printed":
            mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=0.03,
                                          AngularDeflection=0.12, Relative=False)
            if not mesh.isSolid():
                raise ValueError(f"{pid}: mesh is not closed")
            mesh.write(str(PRINT / f"{pid}.stl"))
        print("STAGE_END", pid, flush=True)

    def add(pid, xyz=(0, 0, 0), angle=0, group="gear", axis=None, offset=None):
        name = f"{pid}_{sum(i['part_id'] == pid for i in instances) + 1:03}"
        placement = App.Placement(V(*xyz), App.Rotation(V(0, 0, 1), 0 if offset is not None else angle))
        if axis is not None:
            placement = App.Placement(V(*xyz), App.Rotation(V(0, 0, 1), V(*axis)))
        if offset is not None:
            placement = App.Placement(V(*offset), App.Rotation(V(0, 0, 1), angle)).multiply(placement)
        obj = document.addObject("Part::Feature", name)
        obj.Shape = shapes[pid]
        obj.Placement = placement
        for key, value in (("PartId", pid), ("RevisionId", REVISION),
                           ("Category", parts[pid]["category"])):
            obj.addProperty("App::PropertyString", key, "Source")
            setattr(obj, key, value)
        matrix = placement.Matrix
        instances.append({"name": obj.Name, "part_id": pid, "group": group,
                          "transform": [[getattr(matrix, f"A{r}{c}") for c in range(1, 5)]
                                        for r in range(1, 5)]})
        return obj

    # Existing paired involute and six-spoke geometry, not a scaled STL.
    outline = involute_outline(1, 42, 25, 0.3)
    face = polygon(outline, 3.2)
    root_radius = 42 / 2 - 1.25
    rim = face.cut(cylinder(root_radius - 3, 5, z=-1))
    gear = rim.fuse(cylinder(9.5, 3.2))
    for i in range(6):
        angle = i * math.pi / 3
        gear = gear.fuse(capsule((0, 0), ((root_radius - 2) * math.cos(angle),
                                         (root_radius - 2) * math.sin(angle)), 3.5, 3.2))
    hub = cylinder(9.5, 14, z=3.2)
    hub = hub.cut(Part.makeBox(24, 10, 16, V(-12, 5, 3)))
    hub = hub.cut(Part.makeBox(24, 10, 16, V(-12, -15, 3)))
    # The side-open nut and washer slots are visible in the actual solid.
    hub = hub.fuse(Part.makeCylinder(4.7, 3, V(6, 5, 10.2), V(0, 1, 0)))
    gear = gear.fuse(hub).cut(hexagon(5.12, 20, z=-1))
    gear = gear.cut(Part.makeBox(12, 0.8, 14.1, V(0, -0.4, 3.2)))
    gear = gear.cut(Part.makeCylinder(1.65, 30, V(6, -12, 10.2), V(0, 1, 0)))
    washer_slot = Part.makeBox(12, 0.6, 8.2, V(6, 5, 6.1))
    washer_slot = washer_slot.fuse(Part.makeCylinder(4.1, 0.6, V(6, 5, 10.2), V(0, 1, 0)))
    nut_slot = hexagon(5.7, 3)
    nut_slot.rotate(V(), V(1, 0, 0), -90)
    nut_slot.translate(V(6, 5.5, 10.2))
    nut_slot = nut_slot.fuse(Part.makeBox(12, 3, 5.7, V(6, 5.5, 7.35)))
    gear = gear.cut(washer_slot).cut(nut_slot)
    define("P_M3_GEAR42", gear, "printed", "42T positive hex drive; side-loaded captive inner nut; not an r7 drop-in", 2)
    gear = shapes["P_M3_GEAR42"]

    bracket = cylinder(7.5, 3).fuse(cylinder(7.5, 3, z=9))
    bracket = bracket.fuse(Part.makeBox(7.2, 15, 12, V(-14, -7.5, 0)))
    bracket = bracket.cut(cylinder(3.075, 14, z=-1))
    boss = cylinder(6.5, 2.8, z=12)
    boss = boss.cut(cylinder(4.1, 0.6, z=12))
    boss = boss.cut(Part.makeBox(10, 8.2, 0.6, V(0, -4.1, 12)))
    boss = boss.cut(hexagon(5.7, 3, z=12.5))
    boss = boss.cut(Part.makeBox(10, 5.7, 3, V(0, -2.85, 12.5)))
    bracket = bracket.fuse(boss)
    define("P_M3_PIVOT", bracket, "printed", "12mm metal compression path; 6mm free gap; captive inner nut; bench clevis", 1)
    bracket = shapes["P_M3_PIVOT"]
    eye = capsule((0, 0), (26.5, 0), 13, 5.4)
    for x in (0, 26.5):
        eye = eye.cut(cylinder(3.1, 8, x=x, z=-1))
    define("P_M3_LINK", eye, "printed", "26.5mm pitch retained; 6.2mm smooth sleeve bores; enlarged local bosses", 1)
    eye = shapes["P_M3_LINK"]

    coupon = Part.makeBox(48, 18, 4)
    for x, diameter in ((8, 6.1), (24, 6.2), (40, 6.3)):
        coupon = coupon.cut(cylinder(diameter / 2, 6, x=x, y=9, z=-1))
    define("Q_SLEEVE_FIT", coupon, "printed", "Left-to-right bores 6.1 / 6.2 / 6.3 mm; no machine quantity", 0)
    nut_coupon = Part.makeBox(48, 26, 4)
    for x, af in ((8, 5.6), (24, 5.7), (40, 5.8)):
        nut_coupon = nut_coupon.cut(hexagon(af, 2.6, x=x, y=8, z=1.4))
        nut_coupon = nut_coupon.cut(cylinder(1.65, 6, x=x, y=8, z=-1))
    for x, af in ((8, 5.08), (24, 5.12), (40, 5.2)):
        nut_coupon = nut_coupon.cut(hexagon(af, 6, x=x, y=20, z=-1))
    define("Q_NUT_HEX_FIT", nut_coupon, "printed", "Near row nut AF 5.6/5.7/5.8; far row shaft AF 5.08/5.12/5.2 mm", 0)
    define("H_M3_20", bolt(3, 20), "purchased", "Sengoku EEHD-6D5E; M3x20 socket head, pitch 0.5 nominal, stainless grade unknown", 3, 7.9)
    define("H_M3_NUT", hexagon(5.5, 2.4).cut(cylinder(1.5, 4, z=-1)), "purchased",
           "Akizuki 114372; brass M3x0.5; AF5.5/H2.4 are acceptance assumptions, not supplier tolerances", 6, 8.5)
    define("H_M3_WASHER", disk(4, 0.5, 3.2), "purchased",
           "Sengoku EEHD-6EC4 BSW3mm; nickel-plated brass M3x8x0.5; actual bore/tolerances to measure", 6, 8.5)
    define("H_M3_SLEEVE12", disk(3, 12, 3.2), "purchased",
           "Sengoku EEHD-6CJH BS3x12; approx OD6, M3 through hole; end groove not modelled, inspect actual edge", 1, 8.5)
    define("H_HEX5_30", hexagon(5, 30), "cut_to_length",
           "Two 30mm lengths from the existing 3.1 HEX5 brass-stock family; no end tapping; price not refreshed", 2, 8.5)

    for center, angle in (((0, 0, 0), 0), ((42, 0, 0), 180 + 180 / 42)):
        add("P_M3_GEAR42", center, angle)
        add("H_HEX5_30", (0, 0, -6), angle, offset=center)
        for pid, y in (("H_M3_20", -5.5), ("H_M3_WASHER", -5.5),
                       ("H_M3_WASHER", 5), ("H_M3_NUT", 5.5), ("H_M3_NUT", 7.9)):
            add(pid, (6, y, 10.2), angle, axis=(0, 1, 0), offset=center)
    origin = (0, 62, 0)
    add("P_M3_PIVOT", origin, group="pivot")
    add("P_M3_LINK", (0, 62, 3.3), group="pivot")
    add("H_M3_SLEEVE12", origin, group="pivot")
    for pid, z in (("H_M3_20", -0.5), ("H_M3_WASHER", -0.5),
                   ("H_M3_WASHER", 12), ("H_M3_NUT", 12.5), ("H_M3_NUT", 14.9)):
        add(pid, (0, 62, z), group="pivot")
    # Coupons are real, separate document objects, excluded from the bench BOM.
    for pid, xyz in (("Q_SLEEVE_FIT", (65, 0, 0)), ("Q_NUT_HEX_FIT", (65, 30, 0))):
        obj = document.addObject("Part::Feature", pid)
        obj.Shape = moved(shapes[pid], xyz)
        obj.addProperty("App::PropertyString", "PartId", "Source")
        obj.PartId = pid

    counts = Counter(item["part_id"] for item in instances)
    if any(counts[pid] != data["quantity"] for pid, data in parts.items()):
        raise ValueError("Bench BOM/instance count mismatch")
    print("STAGE_BEGIN native_export", flush=True)
    document.recompute()
    native = CAD / "M3AssemblyTrial.FCStd"
    document.saveAs(str(native))
    Part.export([obj for obj in document.Objects if hasattr(obj, "Shape")], str(CAD / "M3AssemblyTrial.step"))
    library = {}
    for pid, shape in shapes.items():
        mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=0.03,
                                      AngularDeflection=0.12, Relative=False)
        vertices, triangles = mesh.Topology
        library[pid] = {"category": parts[pid]["category"], "vertices": [list(v) for v in vertices],
                        "triangles": [list(t) for t in triangles]}
    (CAD / "render_geometry.json.gz").write_bytes(gzip.compress(json.dumps(library, separators=(",", ":")).encode(), mtime=0))
    App.closeDocument(document.Name)
    reopened = App.openDocument(str(native))
    native_shapes = [obj.Shape for obj in reopened.Objects if hasattr(obj, "Shape")]
    if len(native_shapes) != len(instances) + 2 or any(not s.isValid() or s.Volume <= 0 for s in native_shapes):
        raise ValueError("Native reload failed")
    step = Part.read(str(CAD / "M3AssemblyTrial.step"))
    expected_volumes = sorted(s.Volume for s in native_shapes)
    exported_volumes = sorted(s.Volume for s in step.Solids)
    if len(expected_volumes) != len(exported_volumes) or any(abs(a - b) > 0.01 for a, b in zip(expected_volumes, exported_volumes)):
        raise ValueError("STEP/native solid correspondence failed")
    App.closeDocument(reopened.Name)
    print("STAGE_END native_export", flush=True)

    print("STAGE_BEGIN finite_checks", flush=True)
    collisions = []
    for i, item in enumerate(instances):
        left = shapes[item["part_id"]].copy()
        left.Placement = App.Placement(App.Matrix(*np.asarray(item["transform"]).ravel().tolist()))
        for other in instances[i + 1:]:
            if item["group"] != other["group"]:
                continue
            right = shapes[other["part_id"]].copy()
            right.Placement = App.Placement(App.Matrix(*np.asarray(other["transform"]).ravel().tolist()))
            if not left.BoundBox.intersect(right.BoundBox):
                continue
            volume = left.common(right).Volume
            if volume > 1e-5:
                collisions.append({"a": item["name"], "b": other["name"], "volumeMm3": volume})
    rotation_rows = []
    for angle in range(-80, 81, 10):
        moving = moved(eye, (0, 0, 3.3), angle)
        rotation_rows.append({"degrees": angle, "intersectionMm3": moving.common(bracket).Volume,
                              "clearanceMm": moving.distToShape(bracket)[0]})
    gear_rows = []
    for angle in np.linspace(0, 360 / 42, 19):
        first = moved(gear, angle=float(angle))
        second = moved(gear, (42, 0, 0), 180 + 180 / 42 - float(angle))
        gear_rows.append({"degrees": float(angle), "intersectionMm3": first.common(second).Volume})
    insertions = []
    for pid, seat in (("H_M3_NUT", 5.5), ("H_M3_WASHER", 5)):
        component = shapes[pid].copy()
        component.rotate(V(), V(1, 0, 0), -90)
        for distance in range(13):
            insertions.append({"joint": "gear", "part": pid, "sideOffsetMm": distance,
                               "intersectionMm3": moved(component, (6 + distance, seat, 10.2)).common(gear).Volume})
    for pid, seat in (("H_M3_NUT", 12.5), ("H_M3_WASHER", 12)):
        for distance in range(13):
            insertions.append({"joint": "pivot", "part": pid, "sideOffsetMm": distance,
                               "intersectionMm3": moved(shapes[pid], (distance, 0, seat)).common(bracket).Volume})
    tool_checks = {
        "gearHeadKeyApproachMm3": Part.makeCylinder(2, 35, V(6, -43.5, 10.2), V(0, 1, 0)).common(gear).Volume,
        "gearOuterNutSpannerEnvelopeMm3": Part.makeBox(50, 2, 10, V(1, 8.3, 5.2)).common(gear).Volume,
        "pivotHeadKeyApproachMm3": cylinder(2, 35, z=-38.5).common(bracket).Volume,
        "pivotOuterNutSpannerEnvelopeMm3": Part.makeBox(50, 10, 2, V(-5, -5, 15.1)).common(bracket).Volume,
    }
    failures = bool(collisions or any(r["intersectionMm3"] > 1e-5 for r in rotation_rows + gear_rows + insertions)
                    or any(v > 1e-5 for v in tool_checks.values()))
    metrics = gear_pair_metrics(1, 42, 42, 25, 0.3)
    base_radius = 21 * math.cos(math.radians(25))
    inv = lambda angle: math.tan(angle) - angle
    root_half_angle = ((math.pi / 2 - 0.15) / 42 + inv(math.radians(25))
                       - inv(math.acos(base_radius / root_radius)))
    root_thickness = 2 * root_radius * math.sin(root_half_angle)
    metrics.update(rootChordMm=root_thickness, faceWidthMm=3.2,
                   tangentialForceNPerNm=1000 / 21,
                   radialForceNPerNm=1000 / 21 * math.tan(math.radians(25)),
                   rootSectionModulusMm3=3.2 * root_thickness ** 2 / 6,
                   allowableToothLoadN=None,
                   strengthNote="Geometric root section only; no PETG strength/creep/fatigue allowable or load rating.")
    checks = {
        "revisionId": REVISION, "status": "FAIL" if failures else "PASS_WITH_SCOPE",
        "nativeReopened": True, "stepSolidCount": len(step.Solids),
        "nativeStepMaxVolumeDifferenceMm3": max(abs(a - b) for a, b in zip(expected_volumes, exported_volumes)),
        "staticIntersections": collisions, "pivotRotationSamples": rotation_rows, "gearMeshSamples": gear_rows,
        "sideInsertionSamples": insertions, "toolEnvelopeIntersections": tool_checks,
        "pivotAxialGapMm": 6 - 5.4, "pivotDiametralClearanceMm": 6.2 - 6,
        "pivotBoltProjectionMm": 20 - (12 + 2 * 0.5 + 2 * 2.4),
        "gearBoltProjectionMm": 20 - (10 + 2 * 0.5 + 2 * 2.4),
        "sleeveWallMmAssumed": (6 - 3.2) / 2, "linkHoleEdgeMm": (13 - 6.2) / 2,
        "gearMetrics": metrics, "nominalBenchMassG": sum(parts[i["part_id"]]["nominalMassG"] for i in instances),
        "physicalFitStrengthWear": "UNKNOWN", "fullWalkerMotionFloorClearance": "NOT_RUN_NOT_INTEGRATED",
        "toolAccess": "Finite 4mm-diameter straight key approach and 10mm-wide/2mm-thick outer-nut spanner envelopes. Actual tool body, hand space and torque UNKNOWN.",
        "scope": "Bench intersections and finite unloaded rotation only; no material strength, wear, preload or walking certification.",
    }
    write_json(DOC / "checks.json", checks)

    def diagram(name, title, elements, axes=(0, 2)):
        paths, all_points = [], []
        colors = {"printed": "#17685d", "purchased": "#9b611d", "cut_to_length": "#4b5b76"}
        for label, shape, category in elements:
            lines = []
            for edge in shape.Edges:
                pts = edge.discretize(Deflection=0.15)
                projected = [(tuple(v)[axes[0]], -tuple(v)[axes[1]]) for v in pts]
                lines.append(projected)
                all_points.extend(projected)
            paths.append((label, lines, colors[category]))
        x0, y0 = (min(p[i] for p in all_points) for i in range(2))
        x1, y1 = (max(p[i] for p in all_points) for i in range(2))
        scale = min(820 / max(x1 - x0, 1), 390 / max(y1 - y0, 1))
        body = [f'<svg xmlns="http://www.w3.org/2000/svg" width="960" height="600" viewBox="0 0 960 600">',
                '<rect width="960" height="600" fill="#fbfaf6"/>',
                f'<text x="24" y="30" font-size="17" font-family="sans-serif">{escape(title)}</text>',
                '<text x="24" y="54" font-size="12" font-family="sans-serif">B-rep edges / mm / bench or labelled 3.1 reference / physical fit UNKNOWN</text>']
        for _, lines, color in paths:
            for pts in lines:
                coordinates = " ".join(f"{60+(x-x0)*scale:.2f},{85+(y-y0)*scale:.2f}" for x, y in pts)
                body.append(f'<polyline points="{coordinates}" fill="none" stroke="{color}" stroke-width="1"/>')
        for index, (label, _, color) in enumerate(paths):
            body.append(f'<text x="{24+(index%2)*460}" y="{505+(index//2)*20}" fill="{color}" font-size="12" font-family="sans-serif">{escape(label)}</text>')
        body.append("</svg>")
        (DOC / name).write_text("\n".join(body) + "\n")

    # Sections are cut from the same solids; bolts/nuts are never illustration-only.
    half = Part.makeBox(180, 100, 120, V(-60, 0, -30))
    pivot_elements = []
    for pid, dz in (("P_M3_PIVOT", 0), ("P_M3_LINK", 3.3), ("H_M3_SLEEVE12", 0),
                    ("H_M3_20", -0.5), ("H_M3_WASHER", -0.5), ("H_M3_WASHER", 12),
                    ("H_M3_NUT", 12.5), ("H_M3_NUT", 14.9)):
        pivot_elements.append((pid, moved(shapes[pid], (0, 0, dz)).common(half), parts[pid]["category"]))
    diagram("pivot-3.2.svg", "3.2 M3 pivot: actual centre section (Y >= 0)", pivot_elements)
    gear_half = Part.makeBox(60, 60, 60, V(6, -30, -10))
    gear_elements = [("P_M3_GEAR42 (section X >= 6)", gear.common(gear_half), "printed")]
    for pid, y in (("H_M3_20", -5.5), ("H_M3_WASHER", -5.5), ("H_M3_WASHER", 5),
                   ("H_M3_NUT", 5.5), ("H_M3_NUT", 7.9)):
        part = shapes[pid].copy()
        part.rotate(V(), V(1, 0, 0), -90)
        gear_elements.append((pid, moved(part, (6, y, 10.2)).common(gear_half), "purchased"))
    diagram("gear-3.2.svg", "3.2 gear: actual bolt-axis section / washers and both nuts", gear_elements, axes=(1, 2))
    diagram("gear-top-3.2.svg", "3.2 gear: positive hex bore and side insertion opening", [
        ("P_M3_GEAR42 / torque by hex flats, not glue", gear, "printed")], axes=(0, 1))
    diagram("fit-3.2.svg", "3.2 fit coupons / holes and nut pockets from native CAD", [
        ("Q_SLEEVE_FIT: 6.1 / 6.2 / 6.3 mm", shapes["Q_SLEEVE_FIT"], "printed"),
        ("Q_NUT_HEX_FIT: dimensions in print list", moved(shapes["Q_NUT_HEX_FIT"], (0, 25, 0)), "printed"),
    ], axes=(0, 1))
    original = json.loads((ROOT / "docs/ver3/integrated_r7/A/assembly.json").read_text())
    reference = App.openDocument(str(ROOT / "FreeCAD/Ver.3/integrated_r7/A/Walker_A.FCStd"))
    for filename, title, ids in (
        ("input-3.1.svg", "3.1 A REFERENCE / not the new M3 bench revision",
         ("H_INPUT_SHAFT", "H_INPUT_HUB", "P_INPUT_PINION", "H_INPUT_BEARING", "H_INPUT_COLLAR", "H_BOLT_M4_12")),
        ("supports-3.1.svg", "3.1 A REFERENCE / actual shaft and locating/floating support",
         ("H_MAIN_HEX100", "P_CRANK_JOURNAL_-1_0", "P_CRANK_JOURNAL_1_180", "P_MAIN_INNER_STOP")),
    ):
        selected = []
        for pid in ids:
            items = [i for i in original["instances"] if i["part_id"] == pid]
            if filename.startswith("supports"):
                items = items[:1]
            combined = Part.makeCompound([reference.getObject(item["name"]).Shape.copy() for item in items])
            selected.append((pid, combined, original["parts"][pid]["category"]))
        if filename.startswith("supports"):
            for group in ("bearings", "bearing_caps"):
                items = [i for i in original["instances"] if i["group"] == group and i["transform"][1][3] == -84]
                combined = Part.makeCompound([reference.getObject(i["name"]).Shape.copy() for i in items])
                selected.append((group + " / both ends", combined, "printed" if group == "bearing_caps" else "purchased"))
        diagram(filename, title, selected)
    App.closeDocument(reference.Name)
    print("STAGE_END finite_checks", flush=True)

    manifest = {
        "id": "A", "units": "mm", "revisionId": REVISION, "publicVersion": "3.2",
        "status": "BENCH_PROTOTYPE_NOT_FULL_KIT", "manufacturingRelease": False,
        "physicalQualification": "UNKNOWN", "baseCommit": BASE,
        "parts": parts, "instances": instances,
        "coupons": ["Q_SLEEVE_FIT", "Q_NUT_HEX_FIT"],
        "cadMeshes": "FreeCAD/Ver.3/m3_r1/render_geometry.json.gz",
        "sourceHashes": {str(p.relative_to(ROOT)): sha(p) for p in (
            Path(__file__), ROOT / "scripts/ver3/walker_geometry.py",
            ROOT / "docs/ver3/integrated_r7/A/assembly.json",
            ROOT / "FreeCAD/Ver.3/integrated_r7/A/Walker_A.FCStd", DOC / "joints.csv")},
        "assumptions": {"printer": "Bambu Lab P1S inspection-only; user machine UNKNOWN",
                        "nozzleDiameterMm": 0.2, "material": "Generic PETG inspection-only; user material UNKNOWN",
                        "supplierGeometry": "Dimension envelopes, not supplied vendor CAD. Measure nut AF/height, sleeve OD/ID/groove and washer bore."},
    }
    write_json(DOC / "assembly.json", manifest)
    with (DOC / "print-list.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("revision", "part_id", "file", "trial_quantity", "machine_quantity",
                         "purpose", "orientation", "support_plan", "material_condition", "qualification"))
        for pid, row in parts.items():
            if row["category"] != "printed":
                continue
            writer.writerow((REVISION, pid, f"STL/Ver.3/m3_r1/{pid}.stl", max(row["quantity"], 1), "NOT_ASSIGNED",
                             row["description"], "CAD Z+ up; base Z=0 on bed",
                             "inspect local support and remove from nut slots" if pid in ("P_M3_GEAR42", "P_M3_PIVOT") else "none planned",
                             "0.2mm nozzle; PETG/P1S inspection assumption only", "PHYSICAL_PRINT_FIT_UNKNOWN"))
    write_json(DOC / "files.json", {str(p.relative_to(ROOT)): sha(p)
                                   for folder in (CAD, PRINT, DOC) for p in sorted(folder.iterdir())
                                   if p.is_file() and p.name != "files.json" and not p.name.endswith(".FCStd1")})
    if failures:
        raise ValueError("Finite bench check failed; see checks.json. Do not treat artifacts as released.")
    print("STAGE_END M3_TRIAL_COMPLETE", len(instances), "bench instances", flush=True)


if __name__ == "__main__":
    main()
