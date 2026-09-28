"""Check saved display coordinates against source noncontact envelopes; no solver rerun."""

import ast
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r7_data import Snapshot
from r7_motion_diagnostic import canonical_functions, display_body_pose

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "site/dist/r7-floor2-gate.json"


def source_floor_api(snapshot, api):
    raw = snapshot.read("scripts/ver3/walker_contact.py")
    tree = ast.parse(raw)
    original = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ContactGait")
    initializer = next(n for n in original.body if isinstance(n, ast.FunctionDef) and n.name == "__init__")
    cls = ast.ClassDef(name="ContactGait", bases=[], keywords=[], body=[initializer], decorator_list=[])
    namespace = {**api, "hashlib": hashlib, "json": json}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])),
                 "canonical ContactGait initialization only", "exec"), namespace)

    def body_points(theta=0, which="reference", common=None):
        if common is None:
            raise ValueError("The saved assembly parameters are required")
        return api["points_many"](np.array(theta), api["dimensions"](which, common), common["linkScale"])[0]

    namespace["body_points"] = body_points
    raw = snapshot.read("scripts/ver3/walker_floor.py")
    tree = ast.parse(raw)
    names = {"identity", "minimum_cloud", "rocker_minimum", "radial_lower_bound", "check"}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    if {n.name for n in nodes} != names:
        raise ValueError("Canonical noncontact envelope functions changed")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "canonical walker_floor.py", "exec"), namespace)
    return namespace


def verify_saved_frames():
    snapshot = Snapshot()
    api, provenance = canonical_functions(snapshot)
    floor_api = source_floor_api(snapshot, api)
    reports = {}
    for design in snapshot.contract["designs"]:
        ident = design["id"]
        assembly = json.loads(snapshot.verify(design["assembly"]))
        envelopes = json.loads(snapshot.verify(design["nativeFloorEnvelopes"]))
        source_check = json.loads(snapshot.verify(design["nonContactFloorClearance"]))
        contact = json.loads(snapshot.verify(design["contactFrames"]))
        if (source_check["status"] != "PASS" or source_check["allNonContactInstancesChecked"] is not True
                or source_check["complete"] is not True
                or source_check["nativeSha256"] != design["native"]["sha256"]
                or source_check["envelopesSha256"] != design["nativeFloorEnvelopes"]["sha256"]
                or contact["assemblySha256"] != design["assembly"]["sha256"]
                or contact["sourceHash"] != snapshot.source["sourceHash"]):
            raise ValueError("Floor correction, native or contact-frame evidence is not the same revision")
        frames = contact["frames"]
        if len(frames) != 73:
            raise ValueError("Expected all 73 source contact states")
        raw_contact = {"data": {
            "theta_rad": [math.radians(f["crankDeg"]) for f in frames],
            "body_z_slopex_slopey": [f["bodyHeightAndSlopes"] for f in frames],
            "spring_compression_mm": [f["springCompressionMm"] for f in frames],
            "normal_n": [f["normalN"] for f in frames],
        }}
        source = floor_api["check"](assembly, envelopes, raw_contact, case_id="saved_73_frames_no_solver_execution")
        if source["status"] != "PASS" or source["checkedInstances"] != len(assembly["instances"]):
            raise ValueError(f"{ident}: corrected source-map floor alignment failed: {source['failures']}")
        common = assembly["parameters"]["common"]
        ref_z = assembly["bodyOriginZMm"]
        dims = api["dimensions"]("reference", common)
        order = {(p["stationYmm"], p["side"]): i for i, p in enumerate(contact["footOrder"])}

        def points(theta):
            return api["points_many"](np.array(theta), dims, common["linkScale"])[0]

        reference = points(0)
        keyset = {(i["motion"]["station"], i["motion"]["side"], i["motion"]["phase"])
                  for i in assembly["instances"] if "phase" in i["motion"]}
        display_rows = []
        for frame in frames:
            theta = math.radians(frame["crankDeg"])
            body, _, _ = display_body_pose(frame, ref_z)
            kinematics = {key: (points(theta+key[2]), points(key[2]), reference) for key in keyset}
            minimum, lowest = math.inf, None
            for item in assembly["instances"]:
                part = envelopes["parts"][item["part_id"]]
                motion = item["motion"]
                compression = 0
                if motion["kind"] == "foot":
                    compression = frame["springCompressionMm"][order[(motion["station"], motion["side"])]]
                    # The undeformed spring envelope is deliberately conservative, not a rendered coil deformation.
                    if motion["piece"] == "SPRING":
                        compression = 0
                # A neutral basis is swept across the entire rocker stop range below, not substituted as a solved angle.
                delta = api["transform"](item, theta, common, ref_z, compression, 0, kinematics)
                matrix = body @ delta @ np.asarray(item["transform"])
                r, t = matrix[:3, :3], matrix[:3, 3]
                local_normal = r[2][None, :]
                if motion.get("piece") == "ROCKER":
                    pivot = np.asarray(part["rockerPivot"])
                    cloud = np.asarray(part["points"]) - pivot
                    low = float(floor_api["rocker_minimum"](cloud, local_normal, np.asarray(part["rockerAxis"]),
                                                          math.radians(common["foot"]["rockerTravelDeg"]))[0]
                                + r[2] @ pivot + t[2])
                    if not part.get("excludedContactGeometry") or len(part["removedNativePadVolumeMm3"]) != 2:
                        raise ValueError("Only the two exact rolling-pad volumes may be excluded")
                else:
                    low = float(floor_api["minimum_cloud"](part["points"], part.get("circles", []), local_normal)[0] + t[2])
                if low < minimum:
                    minimum, lowest = low, item["name"]
            if minimum < 0:
                raise ValueError(f"{ident} {frame['crankDeg']}deg: rigid display of noncontact geometry crosses Z0: {lowest} {minimum}")
            display_rows.append({"crankDeg": frame["crankDeg"], "minimumNonContactDisplayZMm": minimum,
                                 "lowestInstance": lowest, "checkedInstances": len(assembly["instances"])})
        reports[ident] = {
            "instanceCount": len(assembly["instances"]), "sourceFramesSha256": design["contactFrames"]["sha256"],
            "nativeFloorEnvelopesSha256": design["nativeFloorEnvelopes"]["sha256"],
            "sourceSavedFrameCheck": source, "orthogonalDisplayFrames": display_rows,
            "representativePhases": [r for r in display_rows if r["crankDeg"] in (0, 120, 240)],
            "allSavedFramesPassed": True, "minimumDisplayNoncontactZMm": min(r["minimumNonContactDisplayZMm"] for r in display_rows),
        }
        print(ident, "73 saved frames; all", len(assembly["instances"]), "instances; source reserves PASS;",
              "display noncontact minimum", reports[ident]["minimumDisplayNoncontactZMm"], "mm", flush=True)
    report = {
        "artifactCommit": snapshot.commit, "sourceCommit": snapshot.source["inputCommit"],
        "sourceHash": snapshot.source["sourceHash"], "contractSha256": snapshot.source["contractSha256"],
        "canonicalFunctionSources": provenance, "status": "PASS", "designs": reports,
        "scope": "Saved 73 phases only, using fixed canonical envelopes and kinematics; no contact/force/dynamics recomputation. Continuous crank sweep and physical tolerances not newly verified.",
        "rockerHandling": "Canonical independent angle stays null. Only exact pad volumes excluded; remaining core checked over the entire +/-5deg stop range.",
        "floorOrMeshShifted": False,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")
    return report


if __name__ == "__main__":
    verify_saved_frames()
