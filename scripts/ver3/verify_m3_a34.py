"""Bounded whole-A checks; frozen 3.1 generators remain unmodified."""

import argparse
from copy import deepcopy
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys

import numpy as np

from build_m3_trial import ROOT, write_json, sha
from build_m3_a34 import DOC, CAD, REVISION
from walker_geometry import body_points, rigids, link_pose, nominal_thread_pair


def rotation(axis, angle, point):
    x, y, z = np.asarray(axis) / np.linalg.norm(axis)
    c, s = math.cos(angle), math.sin(angle)
    q = 1 - c
    r = np.array([[c+x*x*q, x*y*q-z*s, x*z*q+y*s],
                  [y*x*q+z*s, c+y*y*q, y*z*q-x*s],
                  [z*x*q-y*s, z*y*q+x*s, c+z*z*q]])
    matrix = np.eye(4)
    matrix[:3, :3], matrix[:3, 3] = r, point - r @ point
    return matrix


def displacement(vector):
    result = np.eye(4)
    result[:3, 3] = vector
    return result


def transform(item, theta, common, body_z, compression, frames):
    """Same nominal pose convention as the frozen r7 finite-motion checker."""
    motion = item["motion"]
    kind = motion["kind"]
    if kind == "body":
        return np.eye(4)
    if kind in ("shaft", "crank"):
        return rotation([1, 0, 0], theta*motion["speed"],
                        np.array([0, motion["axisYz"][0], body_z+motion["axisYz"][1]]))
    p, initial, reference = frames[(motion["station"], motion["side"], motion["phase"])]
    if kind == "joint":
        node = motion["node"]
        result = displacement(np.r_[0, p[node] - initial[node]])
        if node == "A":
            center = np.r_[0, p[node]+[motion["station"], body_z]]
            result = rotation([1, 0, 0], theta, center) @ result
        return result
    name = motion["link"] if kind == "link" else "CEF"
    now = np.array(link_pose(p, reference, rigids()[name], motion["station"], body_z))
    before = np.array(link_pose(initial, reference, rigids()[name], motion["station"], body_z))
    result = now @ np.linalg.inv(before)
    if kind == "foot" and motion["piece"] in ("SLIDER", "ROCKER", "ROCKER_PIN", "SPRING"):
        gamma = math.atan2(*(p["E"]-p["C"])[::-1]) - math.radians(common["foot"]["pitchReferenceBodyAngleDeg"])
        result = displacement([0, -math.sin(gamma)*compression, math.cos(gamma)*compression]) @ result
    return result


def physics(args, assembly):
    from export_floor_envelopes import export
    from m3_a34_analysis import analyze
    from walker_floor import check

    snapshot = args.work / "snapshot"
    (snapshot / "A/docs").mkdir(parents=True, exist_ok=True)
    (snapshot / "A/CAD").mkdir(exist_ok=True)
    (snapshot / "A/docs/assembly.json").write_bytes((DOC / "assembly.json").read_bytes())
    alias = snapshot / "A/CAD/Walker_A.FCStd"
    target = CAD / "Walker_A_3_4.FCStd"
    if alias.is_symlink():
        if alias.resolve() != target.resolve():
            raise ValueError("Snapshot native alias targets a different file")
    elif alias.exists():
        raise ValueError("Refusing to overwrite a non-alias snapshot CAD")
    else:
        alias.symlink_to(target)
    export("A", args.freecad_lib, DOC / "floor_envelopes.json", snapshot)
    envelopes = json.loads((DOC / "floor_envelopes.json").read_text())

    def contact_sink(a, gait, contact, result):
        report = check(a, envelopes, contact, case_id="3.4_nominal_dense")
        report.update(revisionId=REVISION, nativeSha256=sha(target),
                      scope="720 nominal phases, all non-contact parts; rocker core includes continuous +/-5deg. No full manufacturing-tolerance sweep.",
                      physicalFloorTest=False)
        write_json(DOC / "floor_check.json", report)
        (args.work / "contact.json.gz").write_bytes(gzip.compress(json.dumps(contact).encode(), mtime=0))

    print("STAGE_BEGIN new_mass_per_node_analysis", flush=True)
    new = analyze("A", 0.5, assembly_override=assembly, output_dir=DOC, contact_sink=contact_sink)
    print("STAGE_END new_mass_per_node_analysis", flush=True)
    old_assembly = json.loads((ROOT / "docs/ver3/integrated_r7/A/assembly.json").read_text())
    print("STAGE_BEGIN unchanged31_control", flush=True)
    control = analyze("A", 0.5, assembly_override=old_assembly, output_dir=args.work / "control31")
    frozen = json.loads((ROOT / "docs/ver3/integrated_r7/A/work_budget.json").read_text())
    for before, after in zip(frozen["cases"], control["cases"]):
        for key in ("requiredInputMaximumNm", "rawPhaseMinimumMarginNm"):
            if abs(before[key] - after[key]) > 1e-9:
                raise ValueError("3.1 control no longer reproduces frozen torque results")
    write_json(DOC / "drive_comparison.json", {
        "revisionId": REVISION, "control31Reproduced": True,
        "oldMassG": control["cadMassKg"]*1000, "newMassG": new["cadMassKg"]*1000,
        "perNodeDiameterMm": assembly["parameters"]["common"]["legJournals"]["perNodeDiameterMm"],
        "sameLoadRadiusRatioForChangedNodes": 1.5,
        "reactionMethod": "Re-solved actual CAD masses/contact and signed joint reactions; not whole-loss multiplication by1.5.",
        "caseRows": [{"case": a["case"], "oldRequiredNm": a["requiredInputMaximumNm"],
                      "newRequiredNm": b["requiredInputMaximumNm"], "rawSupplyMinimumNm": b["rawSupplyMinimumNm"],
                      "rawPhaseMarginNm": b["rawPhaseMinimumMarginNm"],
                      "halfSupplyPhaseMarginNm": b["halfProxyPhaseMinimumMarginNm"],
                      "oldJournalWorkNmm": a["workPerCycleNmm"]["legJournals"],
                      "newJournalWorkNmm": b["workPerCycleNmm"]["legJournals"]}
                     for a, b in zip(control["cases"], new["cases"])],
        "actualLoadedRpm": None, "physicalSelfStart": "UNKNOWN",
        "sourceHashes": {str(p.relative_to(ROOT)): sha(p) for p in (
            Path(__file__), ROOT/"scripts/ver3/m3_a34_analysis.py", DOC/"assembly.json", DOC/"work_budget.json")},
    })
    print("STAGE_END unchanged31_control", flush=True)
    if json.loads((DOC / "floor_check.json").read_text())["status"] != "PASS":
        raise ValueError("New nominal full-machine floor check failed")


def motion(args, assembly):
    import FreeCAD as App
    import Part
    doc = App.openDocument(str(CAD / "Walker_A_3_4.FCStd"))
    items = assembly["instances"]
    common = assembly["parameters"]["common"]
    body_z = assembly["bodyOriginZMm"]
    changed = set(assembly["m3Integration"]["changedInstances"])
    originals = {i["name"]: doc.getObject(i["name"]).Shape.copy() for i in items}
    reference = body_points(0, common=common)
    keys = {(i["motion"]["station"], i["motion"]["side"], i["motion"]["phase"])
            for i in items if "phase" in i["motion"]}
    cache, hits = {}, []
    count = 0

    def moved(shape, matrix):
        result = shape.copy()
        result.Placement = App.Placement(App.Matrix(*matrix.ravel().tolist())).multiply(result.Placement)
        return result

    for degrees, stroke in itertools.product(range(0, 360, 10), (0, 6)):
        count += 1
        theta = math.radians(degrees)
        frames = {k: (body_points(theta+k[2], common=common), body_points(k[2], common=common), reference) for k in keys}
        matrices = {i["name"]: transform(i, theta, common, body_z, stroke, frames) for i in items}
        shapes = {i["name"]: moved(originals[i["name"]], matrices[i["name"]]) for i in items}
        boxes = []
        effective = []
        for item in items:
            box = shapes[item["name"]].BoundBox
            boxes.append([box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax])
            effective.append(matrices[item["name"]] @ np.asarray(item["transform"]))
        boxes = np.asarray(boxes)
        for i, first in enumerate(items):
            low = np.maximum(boxes[i, :3], boxes[i+1:, :3])
            high = np.minimum(boxes[i, 3:], boxes[i+1:, 3:])
            for j in np.flatnonzero(np.all(high-low > 1e-6, axis=1)) + i + 1:
                second = items[j]
                if not ({first["name"], second["name"]} & changed):
                    continue
                if first["motion"]["kind"] == second["motion"]["kind"] == "body":
                    continue
                if nominal_thread_pair({**first, "transform": effective[i].tolist()},
                                       {**second, "transform": effective[j].tolist()}):
                    continue
                relative = np.linalg.inv(effective[i]) @ effective[j]
                key = (first["part_id"], second["part_id"], tuple(np.round(relative.ravel(), 10)))
                if key not in cache:
                    a, b = shapes[first["name"]], shapes[second["name"]]
                    cache[key] = sum(abs(v.Volume) for s in a.Solids for t in b.Solids for v in s.common(t).Solids)
                if cache[key] > 1e-5:
                    hits.append({"crankDeg": degrees, "compressionMm": stroke, "a": first["name"], "b": second["name"],
                                 "overlapMm3": cache[key]})
        print("STAGE_END a34_motion", count, degrees, stroke, "unique", len(cache), "hits", len(hits), flush=True)
        if hits:
            break
    App.closeDocument(doc.Name)
    write_json(DOC / "motion_check.json", {
        "revisionId": REVISION, "status": "FAIL" if hits else "PASS",
        "complete": count == 72, "poses": count, "uniqueBrepPairs": len(cache), "intersections": hits,
        "nativeSha256": sha(CAD/"Walker_A_3_4.FCStd"),
        "scope": "All changed instances against the complete current assembly at10deg crank increments and0/6mm foot compression. Unchanged pairs retain their frozen3.1 evidence; no continuous collision or physical assembly claim.",
        "rockerAngleDeg": 0, "physicalMotionTest": False,
    })
    if hits:
        raise ValueError("New moving-body interference; stop before publication")


def access(args, assembly):
    import FreeCAD as App
    import Part
    from cad_parts import cylinder, hexagon
    doc = App.openDocument(str(CAD / "Walker_A_3_4.FCStd"))
    items = assembly["instances"]
    shapes = {i["name"]: doc.getObject(i["name"]).Shape.copy() for i in items}
    targets = [i for i in items if i["part_id"].startswith("H_M34_BOLT_M3_")]
    if len(targets) != 14:
        raise ValueError("Expected all14 changed fastener locations")
    rows = []

    def moved(shape, matrix):
        value = shape.copy()
        value.Placement = App.Placement(App.Matrix(*matrix.ravel().tolist())).multiply(value.Placement)
        return value

    def intersections(shape, members, exclude=()):
        found = []
        for member in members:
            if member["name"] in exclude:
                continue
            other = shapes[member["name"]]
            if not shape.BoundBox.intersect(other.BoundBox):
                continue
            volume = sum(abs(v.Volume) for a in shape.Solids for b in other.Solids for v in a.common(b).Solids)
            if volume > 1e-5:
                found.append({"with": member["name"], "volumeMm3": volume})
        return found

    for target in targets:
        motion_data = target["motion"]
        if target["group"] == "synchronization":
            station = motion_data["axisYz"][0]
            members = [i for i in items if (i["part_id"] == "P_M34_SYNC_DRIVE" and i["transform"][1][3] == station)
                       or (i["group"] == "synchronization" and i["part_id"].startswith("H_M34") and i["motion"]["axisYz"][0] == station)]
        else:
            station, side, phase = (motion_data[k] for k in ("station", "side", "phase"))
            members = [i for i in items if (i["motion"].get("station"), i["motion"].get("side"), i["motion"].get("phase")) == (station, side, phase)
                       and i["motion"].get("node") != "P"]
            members += [i for i in items if i["part_id"].startswith("P_M34_CRANK")
                        and i["transform"][1][3] == station
                        and (shapes[i["name"]].BoundBox.XMax > 0) == (side > 0)]
            members += [i for i in items if i["group"] == "mainshafts"
                        and i["part_id"] in {"H_BOLT_M3_16", "H_NUT_M3"}
                        and i["motion"].get("axisYz", [None])[0] == station
                        and 40 <= side*i["transform"][0][3] <= 51]
        matrix = np.asarray(target["transform"])
        axis, start = matrix[:3, 2], matrix[:3, 3]
        failures = []
        for distance in (24, 12, 8, 6, 3, 0):
            value = moved(shapes[target["name"]], displacement(-axis*distance))
            failures.extend({"offsetMm": distance, **r} for r in intersections(value, members, (target["name"],)))
        key = Part.makeCylinder(2, 25, App.Vector(*(start-axis*28)), App.Vector(*axis))
        key_failures = intersections(key, members, (target["name"],))
        nuts = [i for i in members if i["part_id"] == "H_M34_NUT_M3"
                and (i["group"] == "synchronization" or i["motion"].get("node") == motion_data["node"])]
        outer = max(nuts, key=lambda i: np.dot(np.asarray(i["transform"])[:3, 3], axis))
        tool = cylinder(5, 2, z=0.2).fuse(Part.makeBox(31, 4, 2, App.Vector(4, -2, 0.2)))
        tool = tool.cut(hexagon(5.8, 4, z=-0.5)).cut(Part.makeBox(8, 5.8, 4, App.Vector(-8, -2.9, -0.5)))
        approaches = []
        outer_matrix = np.asarray(outer["transform"])
        for angle in range(0, 360, 45):
            r = rotation([0, 0, 1], math.radians(angle), np.zeros(3))
            contacts = intersections(moved(tool, outer_matrix@r), members, (outer["name"],))
            if not contacts:
                approaches.append(angle)
        rows.append({"bolt": target["name"], "preparedMemberIds": [i["name"] for i in members],
                     "preparedMemberHash": hashlib.sha256(json.dumps(sorted(i["name"] for i in members)).encode()).hexdigest(),
                     "boltInsertionOffsetsMm": [24, 12, 8, 6, 3, 0], "boltInsertionIntersections": failures,
                     "keyApproachIntersections": key_failures, "clearSpannerAnglesDeg": approaches,
                     "status": "PASS" if not failures and not key_failures and approaches else "FAIL"})
        print("STAGE_END a34_access", target["name"], rows[-1]["status"], flush=True)
    App.closeDocument(doc.Name)
    result = {"revisionId": REVISION, "status": "PASS" if all(r["status"] == "PASS" for r in rows) else "FAIL",
              "nativeSha256": sha(CAD/"Walker_A_3_4.FCStd"), "locations": rows,
              "scope": "Declared separate leg/crank or gear subassemblies, not in-place whole-machine access.4mm key approach envelope;10mm-wide,2mm-thick spanner-head gauge with31mm handle. Real tools, washer side-loading and hand clearance remain physical checks.",
              "physicalAssemblyPerformed": False}
    write_json(DOC/"access_check.json", result)
    if result["status"] != "PASS":
        raise ValueError("A new fastener has no checked assembly/tool approach")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("physics", "motion", "access"))
    parser.add_argument("--freecad-lib", required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, args.freecad_lib)
    data = json.loads((DOC / "assembly.json").read_text())
    if data["revisionId"] != REVISION:
        raise ValueError("Wrong integration revision")
    {"physics": physics, "motion": motion, "access": access}[args.mode](args, data)
