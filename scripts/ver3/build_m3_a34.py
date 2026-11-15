"""Integrate bounded M3 changes into the actual 3.1 A document, preserving it."""

import argparse
from collections import Counter
from copy import deepcopy
import csv
import gzip
import json
import math
from pathlib import Path
import sys

from build_m3_trial import ROOT, BASE, sha, write_json

DOC = ROOT / "docs/ver3/m3_a34"
CAD = ROOT / "FreeCAD/Ver.3/m3_a34"
PRINT = ROOT / "STL/Ver.3/m3_a34"
REVISION = "v3.4-a-m3-r1"
NODES = {"A", "D"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freecad-lib", required=True)
    args = parser.parse_args()
    sys.path.insert(0, args.freecad_lib)
    import FreeCAD as App
    import Part
    import MeshPart
    import numpy as np
    from cad_parts import bolt, cylinder, disk, hexagon
    from walker_geometry import body_points, rigids

    V = App.Vector
    for path in (DOC, CAD, PRINT):
        path.mkdir(parents=True, exist_ok=True)
    original = json.loads((ROOT / "docs/ver3/integrated_r7/A/assembly.json").read_text())
    data = deepcopy(original)
    data["revisionId"] = REVISION
    data["designId"] = "A"
    data["publicVersion"] = "3.4"
    data["baseCommit"] = BASE
    data["manufacturingRelease"] = False
    data["fullAssemblyVerification"] = {"status": "PENDING", "scope": "New M3 geometry; old qualification is not inherited"}
    data["physicalQualification"] = {"status": "UNKNOWN", "physicalPrintingPerformed": False}
    data["cadMeshes"] = "FreeCAD/Ver.3/m3_a34/render_geometry.json.gz"
    for key in ("incrementalGeometryUpdate", "incrementalGuardUpdate", "incrementalFloorDetailsUpdate",
                "nativeStepStatus", "nativeLabelOverrides", "stockLabelMetadataUpdate"):
        data.pop(key, None)
    common = data["parameters"]["common"]
    common["legJournals"].update(diameterMm=6, sleeveBoreMm=3.2,
                                perNodeDiameterMm={n: 6 if n in NODES else 4 for n in ("A", "P", "B", "C", "D", "E")},
                                perNodeSleeveBoreMm={n: 3.2 if n in NODES else 2.2 for n in ("A", "P", "B", "C", "D", "E")},
                                loadPath="M3/smooth6mm at A/D; P/B/C/E and feet retain4mm. Root annular printed seat is in clamp path; do not claim all-metal roots.")
    points = body_points(common=common)
    source_doc = App.openDocument(str(ROOT / "FreeCAD/Ver.3/integrated_r7/A/Walker_A.FCStd"))
    shapes = {}
    for item in original["instances"]:
        pid = item["part_id"]
        if pid in shapes:
            continue
        shape = source_doc.getObject(item["name"]).Shape.copy()
        inverse = App.Placement(App.Matrix(*np.asarray(item["transform"]).ravel().tolist())).inverse()
        shape.Placement = inverse.multiply(shape.Placement)
        shapes[pid] = shape
    changed = set()
    changed_parts = set()
    replacements = {}

    def transformed(shape, matrix):
        result = shape.copy()
        result.Placement = App.Placement(App.Matrix(*np.asarray(matrix).ravel().tolist())).multiply(result.Placement)
        return result

    def axis_pose(origin, axis, clock=0):
        rotation = App.Rotation(V(*axis), clock).multiply(App.Rotation(V(0, 0, 1), V(*axis)))
        m = App.Placement(V(*origin), rotation).Matrix
        return [[getattr(m, f"A{r}{c}") for c in range(1, 5)] for r in range(1, 5)]

    def define(pid, shape, category, spec, density=1.27, sku=None):
        print("STAGE_BEGIN", pid, flush=True)
        shape = shape.removeSplitter()
        if not shape.isValid() or len(shape.Solids) != 1 or shape.Volume <= 0:
            raise ValueError(f"{pid}: invalid or disconnected new solid")
        shape = shape.Solids[0]
        inertia = shape.MatrixOfInertia
        shapes[pid] = shape
        data["parts"][pid] = {
            "category": category, "spec": spec, "description": spec, "sku": sku,
            "solid_volume_mm3": shape.Volume, "local_com_mm": list(shape.CenterOfMass),
            "centralVolumeInertiaMm5": [[getattr(inertia, f"A{r}{c}") for c in range(1, 4)] for r in range(1, 4)],
            "mass_g": shape.Volume * density / 1000,
            "mass_basis": "actual new B-rep volume x explicitly assumed material density",
        }
        changed_parts.add(pid)
        print("STAGE_END", pid, flush=True)

    def change(item, pid, matrix=None):
        before = item["part_id"]
        item["part_id"] = pid
        if matrix is not None:
            item["transform"] = matrix
        obj = source_doc.getObject(item["name"])
        obj.Shape = shapes[pid]
        obj.Placement = App.Placement(App.Matrix(*np.asarray(item["transform"]).ravel().tolist())).multiply(shapes[pid].Placement)
        obj.PartId = pid
        obj.RevisionId = REVISION
        obj.Specification = data["parts"][pid]["spec"]
        obj.NominalMassGram = data["parts"][pid]["mass_g"]
        changed.add(item["name"])
        replacements[item["name"]] = {"beforePart": before, "afterPart": pid}

    def add(pid, matrix, motion, group):
        name = f"{pid}_{sum(i['part_id'] == pid for i in data['instances']) + 1:03}"
        obj = source_doc.addObject("Part::Feature", name)
        obj.Shape = shapes[pid]
        obj.Placement = App.Placement(App.Matrix(*np.asarray(matrix).ravel().tolist())).multiply(shapes[pid].Placement)
        for key, value in (("PartId", pid), ("RevisionId", REVISION), ("Category", data["parts"][pid]["category"])):
            obj.addProperty("App::PropertyString", key, "Source")
            setattr(obj, key, value)
        item = {"name": obj.Name, "part_id": pid, "transform": matrix, "motion": deepcopy(motion), "group": group}
        data["instances"].append(item)
        changed.add(obj.Name)
        return item

    for length in (15, 20, 30):
        define(f"H_M34_BOLT_M3_{length}", bolt(3, length), "purchased",
               f"M3x{length} socket head,2.5mm hex,nominal0.5pitch; Sengoku stainless grade not stated", 7.9, f"M3_{length}")
    define("H_M34_NUT_M3", hexagon(5.5, 2.4).cut(cylinder(1.5, 4, z=-1)), "purchased",
           "Akizuki114372 brass M3x0.5; acceptance assumption AF5.5/H2.4", 8.5, "114372")
    define("H_M34_WASHER3", disk(4, 0.5, 3.2), "purchased", "Sengoku BSW3mm M3x8x0.5,brass/Ni; ID acceptance3.2", 8.5, "EEHD-6EC4")
    define("H_M34_THRUST6", disk(6.5, 1, 6.4), "purchased", "Sengoku BSW6mm M6x13x1.0,brass/Ni; ID acceptance6.4", 8.5, "EEHD-6EC8")
    for length in (8, 20):
        define(f"H_M34_SLEEVE_{length}", disk(3, length, 3.2), "purchased",
               "Smooth continuous6mm OD/3.2mm ID sleeve; no threaded sliding surface; actual OD/ID/ends must be measured",
               8.5, "EEHD-6CJF" if length == 8 else "CE-320N")

    # Enlarge and counterbore only the selected joint bosses, not entire links.
    for old_pid in list(shapes):
        if not old_pid.startswith("P_LEG_"):
            continue
        name, hand = old_pid.split("_")[2:]
        nodes = [n for n in rigids()[name] if n in NODES]
        if not nodes:
            continue
        side = -1 if hand == "L" else 1
        x = 54.65 + common["legLayers"][name] * common["legLayerPitchMm"]
        shape = shapes[old_pid].copy()
        for node in nodes:
            y, z = points[node]
            shape = shape.fuse(Part.makeCylinder(6.5, 3.1, V(side*x, y, z), V(side, 0, 0)))
            shape = shape.cut(Part.makeCylinder(3.1, 5.1, V(side*(x-1), y, z), V(side, 0, 0)))
            for first in (x, x + 2.8):
                shape = shape.cut(Part.makeCylinder(6.7, 0.3, V(side*first, y, z), V(side, 0, 0)))
        pid = old_pid.replace("P_LEG_", "P_M34_LEG_")
        define(pid, shape, "printed", f"{name}/{hand}: selected6.2 bores,13mm bosses and0.3mm face relief; original centres/layers preserved")
        for item in data["instances"]:
            if item["part_id"] == old_pid:
                change(item, pid)

    for old_pid in list(shapes):
        if not old_pid.startswith("P_CRANK_JOURNAL_"):
            continue
        side, degrees = (int(v) for v in old_pid.removeprefix("P_CRANK_JOURNAL_").split("_"))
        radius = 15 * common["linkScale"]
        tip = (radius * math.cos(math.radians(degrees)), radius * math.sin(math.radians(degrees)))
        shape = shapes[old_pid].copy()
        shape = shape.fuse(Part.makeCylinder(6.2, 4.95, V(side*49.5, *tip), V(side, 0, 0)))
        shape = shape.cut(Part.makeCylinder(1.65, 10, V(side*46, *tip), V(side, 0, 0)))
        shape = shape.cut(Part.makeCylinder(3.075, 4.05, V(side*50.5, *tip), V(side, 0, 0)))
        shape = shape.cut(Part.makeCylinder(4.1, 3.5, V(side*46, *tip), V(side, 0, 0)))
        shape = shape.cut(Part.makeCylinder(3.1, 20.5, V(side*29, *tip), V(side, 0, 0)))
        pid = old_pid.replace("P_CRANK", "P_M34_CRANK")
        define(pid, shape, "printed", "A root:6.2mm axial M3-head/tool channel,side-loaded8mm washer seat; continuous6mm sleeve; retained5mm-AF drive/journals")
        for item in data["instances"]:
            if item["part_id"] == old_pid:
                change(item, pid)
    for hand, side in ((("L", -1), ("R", 1)) if "P" in NODES else ()):
        old_pid = "P_CHASSIS_" + hand
        shape = shapes[old_pid].copy()
        for station in (-84, 0, 84):
            yz = points["P"] + [station, 0]
            start = -56 if side < 0 else 31
            pocket = -54.2 if side < 0 else 42.5
            driver = -41.5 if side < 0 else 32
            shape = shape.cut(Part.makeCylinder(1.65, 25, V(start, *yz), V(1, 0, 0)))
            shape = shape.cut(Part.makeCylinder(3.075, 11.7, V(pocket, *yz), V(1, 0, 0)))
            shape = shape.cut(Part.makeCylinder(3.1, 9.5, V(driver, *yz), V(1, 0, 0)))
        pid = "P_M34_CHASSIS_" + hand
        define(pid, shape, "printed", "Original keyed frame with enlarged P socket and M3 head access; other bearing/guard seats retained")
        for item in data["instances"]:
            if item["part_id"] == old_pid:
                change(item, pid)

    define("P_M34_LAYER_SPACER_7_4", disk(5, 7.4, 6.3), "printed",
           "A interlayer free spacer:6.3mm bore/10mm OD; not a clamp-load spacer")
    pins = {}
    for item in list(data["instances"]):
        motion = item["motion"]
        if item["group"] == "legs" and motion.get("kind") == "joint" and motion["node"] in NODES:
            key = (motion["station"], motion["side"], motion["phase"], motion["node"])
            pins.setdefault(key, []).append(item)
    for (_, side, _, node), items in pins.items():
        first = 42.5 if node == "P" else 50.5 if node == "A" else 54.5
        length = 20 if node in {"A", "P"} else 8
        start = 41 if node == "P" else 49 if node == "A" else 54
        end = first + length
        example = items[0]
        yz = np.asarray(example["transform"])[:3, 3][1:]
        axis = (side, 0, 0)
        nut_index = 0
        washer_index = 0
        levels = sorted({common["legLayers"][name] for name, labels in rigids().items() if node in labels})
        for item in items:
            old_pid = item["part_id"]
            x = abs(item["transform"][0][3])
            if old_pid.startswith("H_SLEEVE_2_"):
                change(item, f"H_M34_SLEEVE_{length}")
            elif old_pid.startswith("H_BOLT_M2_"):
                change(item, f"H_M34_BOLT_M3_{30 if node in {'A', 'P'} else 15}",
                       axis_pose((side*start, *yz), axis))
            elif old_pid == "H_NUT_M2":
                change(item, "H_M34_NUT_M3", axis_pose((side*(end + 0.5 + 2.4*nut_index), *yz), axis))
                nut_index += 1
            elif old_pid == "H_WASHER_2":
                change(item, "H_M34_WASHER3", axis_pose((side*(start if washer_index == 0 else end), *yz), axis))
                washer_index += 1
            elif old_pid == "H_WASHER_4":
                begins = [54.65 + level*4.1 for level in levels]
                if any(abs(x - (begin + 3.1)) < 1e-6 for begin in begins):
                    new_x = x - 0.3
                elif any(abs(x + 0.8 - begin) < 1e-6 for begin in begins):
                    new_x = x + 0.1
                else:
                    raise ValueError("Unclassified thrust washer seat")
                change(item, "H_M34_THRUST6", axis_pose((side*new_x, *yz), axis))
            elif old_pid == "P_LAYER_SPACER_7.4":
                change(item, "P_M34_LAYER_SPACER_7_4")
        if node == "P":
            add("H_M34_WASHER3", axis_pose((side*end, *yz), axis), example["motion"], "legs")

    trial = App.openDocument(str(ROOT / "FreeCAD/Ver.3/m3_r1/M3AssemblyTrial.FCStd"))
    trial_gear = trial.getObject("P_M3_GEAR42_001").Shape.copy()
    # Reflect into the original X10..13.2 tooth plane; extend the hub toward -X.
    mapping = App.Matrix(0, 0, -1, 13.2, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1)
    new_gear = trial_gear.copy()
    new_gear.transformShape(mapping)
    App.closeDocument(trial.Name)
    new_gear = new_gear.fuse(Part.makeCylinder(3.15, 17.2, V(-4, 0, 0), V(1, 0, 0)))
    corners = [V(-5, 5.12/math.sqrt(3)*math.cos(math.pi/6+i*math.pi/3),
                  5.12/math.sqrt(3)*math.sin(math.pi/6+i*math.pi/3)) for i in range(6)]
    keyed_bore = Part.Face(Part.makePolygon(corners + [corners[0]])).extrude(V(20, 0, 0))
    new_gear = new_gear.cut(keyed_bore).cut(Part.makeBox(14.1, 12, 0.8, V(-4.1, 0, -0.4)))
    define("P_M34_SYNC_DRIVE", new_gear, "printed", "3.2 side-entry seat mapped into A front/centre sync gears; bore clocked30deg to existing metal shaft;42T plane unchanged")
    for station, number, nuts in ((-84, 10, (31, 32)), (0, 11, (37, 38))):
        gear_item = next(i for i in data["instances"] if i["part_id"] == "P_SYNC_DRIVE" and i["transform"][1][3] == station)
        change(gear_item, "P_M34_SYNC_DRIVE")
        by_name = {i["name"]: i for i in data["instances"]}
        b = by_name[f"H_BOLT_M3_16_{number:03}"]
        change(b, "H_M34_BOLT_M3_20", axis_pose((3, station+6, 64.5), (0, 0, 1)))
        for index, ident in enumerate(nuts):
            change(by_name[f"H_NUT_M3_{ident:03}"], "H_M34_NUT_M3",
                   axis_pose((3, station+6, 75.5+2.4*index), (0, 0, 1), 90))
        for z in (64.5, 75):
            add("H_M34_WASHER3", axis_pose((3, station+6, z), (0, 0, 1)), gear_item["motion"], "synchronization")

    counts = Counter(i["part_id"] for i in data["instances"])
    data["parts"] = {pid: p for pid, p in data["parts"].items() if counts[pid]}
    for pid, part in data["parts"].items():
        part["quantity"] = counts[pid]
    mass = sum(data["parts"][i["part_id"]]["mass_g"] for i in data["instances"])
    moments = sum((np.asarray(i["transform"]) @ np.r_[data["parts"][i["part_id"]]["local_com_mm"], 1])[:3]
                  * data["parts"][i["part_id"]]["mass_g"] for i in data["instances"])
    data["nominalTotalMassG"] = mass
    data["nominalCenterOfMassMm"] = (moments / mass).tolist()
    data["nominalPrintedMassG"] = sum(p["mass_g"]*counts[pid] for pid, p in data["parts"].items() if p["category"] == "printed")
    data["m3Integration"] = {"changedInstances": sorted(changed), "changedParts": sorted(changed_parts & counts.keys()),
                           "replacements": replacements, "convertedPinNodes": sorted(NODES),
                           "retainedM2": "P fixed pivot (M3 nut intersects AC),B (6mm sleeve/13mm thrust washer intersects frame during motion),C/E three-body joints,6 foot guides,6 rockers,2 synchronization idlers",
                           "r1Trial": "docs/ver3/m3_r1/assembly.json",
                           "rootAssembly": "Side-load head washer before feeding M3x30 through the6.2mm channel; prepare leg/crank outside the frame.",
                           "toolChannelToHexCircumcircleGapMm": 15*common["linkScale"] - 3.1 - 5.12/math.sqrt(3)}
    data["sourceHashes"] = {str(p.relative_to(ROOT)): sha(p) for p in (
        Path(__file__), ROOT / "docs/ver3/integrated_r7/A/assembly.json",
        ROOT / "FreeCAD/Ver.3/integrated_r7/A/Walker_A.FCStd",
        ROOT / "FreeCAD/Ver.3/m3_r1/M3AssemblyTrial.FCStd")}

    world = {i["name"]: source_doc.getObject(i["name"]).Shape.copy() for i in data["instances"]}
    old_world = {i["name"]: transformed(shapes[i["part_id"]], i["transform"]) for i in original["instances"]}
    collisions, tested = [], 0
    for index, item in enumerate(data["instances"]):
        for other in data["instances"][index+1:]:
            if not ({item["name"], other["name"]} & changed):
                continue
            a, b = world[item["name"]], world[other["name"]]
            if not a.BoundBox.intersect(b.BoundBox):
                continue
            tested += 1
            overlap = sum(abs(x.Volume) for s in a.Solids for t in b.Solids for x in s.common(t).Solids)
            if overlap > 1e-5:
                before = 0.
                if item["name"] in old_world and other["name"] in old_world:
                    before = old_world[item["name"]].common(old_world[other["name"]]).Volume
                collisions.append({"a": item["name"], "b": other["name"], "overlapMm3": overlap, "oldOverlapMm3": before})
        if index % 100 == 0:
            print("STAGE_END collision", index, tested, len(collisions), flush=True)
    checks = {"revisionId": REVISION, "staticStatus": "FAIL" if collisions else "PASS",
              "changedInstances": len(changed), "testedStaticPairs": tested, "newIntersections": collisions,
              "nominalMassG": mass, "massChangeFrom31G": mass - original["nominalTotalMassG"],
              "fullMotionStatus": "PENDING", "floorStatus": "PENDING", "physicalQualification": "UNKNOWN"}
    write_json(DOC / "assembly.json", data)
    write_json(DOC / "checks.json", checks)
    if collisions:
        App.closeDocument(source_doc.Name)
        raise ValueError("New static interference; see m3_a34/checks.json before exporting")

    print("STAGE_BEGIN export_complete_A", flush=True)
    source_doc.Label = "Ver.3.4 A M3 development"
    for item in data["instances"]:
        obj = source_doc.getObject(item["name"])
        obj.RevisionId = REVISION
    source_doc.recompute()
    native = CAD / "Walker_A_3_4.FCStd"
    source_doc.saveAs(str(native))
    print("STAGE_END native_saved", flush=True)
    print("STAGE_BEGIN STEP_export", flush=True)
    Part.export([source_doc.getObject(i["name"]) for i in data["instances"]], str(CAD / "Walker_A_3_4.step"))
    print("STAGE_END STEP_export", flush=True)
    App.closeDocument(source_doc.Name)
    library = json.loads(gzip.decompress((ROOT / original["cadMeshes"]).read_bytes()))
    library = {pid: entry for pid, entry in library.items() if counts[pid]}
    print_rows = []
    source_prints = {p["partId"]: p for p in json.loads((ROOT / "docs/ver3/integrated_r7/A/print_geometry.json").read_text())["printedParts"]}
    for pid, part in data["parts"].items():
        if pid in changed_parts:
            mesh = MeshPart.meshFromShape(Shape=shapes[pid], LinearDeflection=0.04, AngularDeflection=0.08, Relative=False)
            vertices, faces = mesh.Topology
            library[pid] = {"category": part["category"], "vertices": [list(v) for v in vertices],
                            "triangles": [list(f) for f in faces]}
            print("STAGE_END mesh", pid, flush=True)
        if part["category"] != "printed":
            continue
        if pid in changed_parts:
            shape = shapes[pid].copy()
            shape.rotate(V(), V(0, 1, 0), 90 if pid == "P_M34_SYNC_DRIVE" else -90)
            shape.translate(V(0, 0, -shape.BoundBox.ZMin))
            mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=0.04, AngularDeflection=0.08, Relative=False)
            if not mesh.isSolid():
                raise ValueError("Open print mesh: " + pid)
            path = PRINT / f"{pid}.stl"
            mesh.write(str(path))
            orientation = "provided STL Z+ up; inspect support/first layer; not yet sliced in this placement"
        else:
            path = ROOT / source_prints[pid]["stl"]
            orientation = "unchanged canonical3.1 print orientation; historical slice scope only"
        print_rows.append((REVISION, pid, str(path.relative_to(ROOT)), counts[pid], "changed" if pid in changed_parts else "unchanged3.1",
                           orientation, "physical fit/strength UNKNOWN", sha(path)))
    (CAD / "render_geometry.json.gz").write_bytes(gzip.compress(json.dumps(library, separators=(",", ":")).encode(), mtime=0))
    with (DOC / "print-list.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("revision", "part_id", "file", "needed", "change", "orientation", "qualification", "sha256"))
        writer.writerows(print_rows)
    with (DOC / "BOM.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("part_id", "category", "quantity", "sku", "unit_nominal_mass_g", "total_nominal_mass_g", "spec"))
        writer.writerows((pid, p["category"], counts[pid], p["sku"], p["mass_g"], p["mass_g"]*counts[pid], p["spec"])
                         for pid, p in data["parts"].items())
    print("STAGE_BEGIN native_STEP_reopen", flush=True)
    reopened = App.openDocument(str(native))
    for item in data["instances"]:
        obj = reopened.getObject(item["name"])
        if obj.PartId != item["part_id"] or not obj.Shape.isValid() or obj.Shape.Volume <= 0:
            raise ValueError("Native identity/shape mismatch: " + item["name"])
    step = Part.read(str(CAD / "Walker_A_3_4.step"))
    native_solids = sorted(s.Volume for i in data["instances"] for s in reopened.getObject(i["name"]).Shape.Solids)
    step_solids = sorted(s.Volume for s in step.Solids)
    checks.update(nativeReopened=True, instanceCount=len(data["instances"]), stepSolids=len(step.Solids),
                  stepVolumeDifferenceMm3=abs(sum(step_solids)-sum(native_solids)), nativeSha256=sha(native),
                  maximumSolidVolumeDifferenceMm3=max(abs(a-b) for a,b in zip(native_solids,step_solids)),
                  stepCorrespondenceMethod="same solid count and sorted per-solid volumes; do not use compound.Volume as a sum")
    write_json(DOC / "checks.json", checks)
    if len(native_solids) != len(step_solids) or any(abs(a-b) > max(0.001, abs(a)*1e-7) for a,b in zip(native_solids,step_solids)):
        raise ValueError("STEP/native solid correspondence mismatch")
    App.closeDocument(reopened.Name)
    write_json(DOC / "checks.json", checks)
    print("STAGE_END export_complete_A", len(data["instances"]), mass, flush=True)


if __name__ == "__main__":
    main()
