"""Reproduce fixed-body CAD vertices below the saved r7 model floor, without corrections."""

import gzip
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r7_data import Snapshot
from r7_motion_diagnostic import display_body_pose

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "site/dist/r7-floor-repro"


def reproduce():
    snapshot = Snapshot()
    rows = []
    resources = {}
    for design in snapshot.contract["designs"]:
        ident = design["id"]
        assembly_bytes = snapshot.verify(design["assembly"])
        mesh_bytes = snapshot.verify(design["mesh"])
        contact_bytes = snapshot.verify(design["contactFrames"])
        assembly, mesh, contact = json.loads(assembly_bytes), json.loads(gzip.decompress(mesh_bytes)), json.loads(contact_bytes)
        resources[ident] = {key: design[key] for key in ("assembly", "mesh", "contactFrames", "native", "step")}
        for phase in (0, 120, 240):
            frame = next(f for f in contact["frames"] if f["crankDeg"] == phase)
            rigid, linear, translation = display_body_pose(frame, assembly["bodyOriginZMm"])
            results = []
            for item in assembly["instances"]:
                if item["motion"]["kind"] != "body":
                    continue
                local = np.asarray(mesh[item["part_id"]]["vertices"], dtype=float)
                matrix = np.asarray(item["transform"])
                native = local @ matrix[:3, :3].T + matrix[:3, 3]
                relative = native - [0, 0, assembly["bodyOriginZMm"]]
                calculated = relative @ linear.T + translation
                displayed = native @ rigid[:3, :3].T + rigid[:3, 3]
                index = int(np.argmin(calculated[:, 2]))
                results.append({
                    "instanceId": item["name"], "partId": item["part_id"], "group": item["group"], "motion": item["motion"],
                    "vertexIndex0Based": index,
                    "partLocalVertexMm": local[index].tolist(), "instance4x4NativeMm": item["transform"],
                    "nativeVertexMm": native[index].tolist(), "bodyRelativeVertexMm": relative[index].tolist(),
                    "sourceSmallAngleWorldVertexMm": calculated[index].tolist(),
                    "orthogonalDisplayWorldVertexMm": displayed[index].tolist(),
                    "minimumAllVerticesSourceZMm": float(calculated[:, 2].min()),
                    "minimumAllVerticesDisplayZMm": float(displayed[:, 2].min()),
                })
            results.sort(key=lambda row: row["minimumAllVerticesSourceZMm"])
            rows.append({
                "designId": ident, "crankDeg": phase, "cadReferenceBodyOriginZMm": assembly["bodyOriginZMm"],
                "sourceFrameUnmodified": frame,
                "sourceSmallAngleThenSavedYaw3x3": linear.tolist(), "sourceTranslationMm": translation.tolist(),
                "orthogonalDisplay4x4Mm": rigid.tolist(),
                "nominalModelFloorZMm": 0,
                "allBelowFloorFixedParts": [r for r in results if r["minimumAllVerticesSourceZMm"] < 0],
                "lowestFiveFixedParts": results[:5],
            })
    report = {
        "artifactCommit": snapshot.commit, "publicSourceCommit": snapshot.source["publicSourceCommit"],
        "sourceCommit": snapshot.source["inputCommit"], "sourceHash": snapshot.source["sourceHash"],
        "scope": "Fixed-body parts only. Exact source mesh doubles, original instance matrix, saved body height/slopes and advance. No linkage/rocker solver or interpolation is needed for these fixed PET panels.",
        "sourceZFormula": "native_z - cadReferenceBodyOriginZ + savedHeight + slopeX*native_x + slopeY*native_y",
        "yawNote": "Saved yaw is used for XY placement only. It does not change Z or the floor-conflict finding.",
        "floorOrCadAdjusted": False, "meshSourceResources": resources, "results": rows,
        "command": "python3 site/r7_floor_repro.py",
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "fixed_body_floor_repro.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("Reproduction:", path)
    print("SHA256:", hashlib.sha256(path.read_bytes()).hexdigest())
    for row in rows:
        low = row["lowestFiveFixedParts"][0]
        print(row["designId"], row["crankDeg"], low["instanceId"], low["minimumAllVerticesSourceZMm"])
    return report


if __name__ == "__main__":
    reproduce()
