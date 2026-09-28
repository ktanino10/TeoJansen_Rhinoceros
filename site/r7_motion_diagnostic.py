"""Three display diagnostics from saved contact states, not a new walking solver."""

import ast
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r7_data import Snapshot
from r7_blender import PREVIEW, MEDIA, read_handoff, accessor_values


def canonical_functions(snapshot):
    """Load only the reviewed pure kinematic functions, not analysis CLI side effects."""
    commercial = ast.parse(snapshot.read("scripts/ver3/commercial_r3.py"))
    keys = next(ast.literal_eval(node.value) for node in commercial.body
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "LENGTH_KEYS" for t in node.targets))
    namespace = {"np": np, "math": math, "LENGTH_KEYS": keys, "CONFIG": snapshot.json("scripts/ver3/design.json")}
    provenance = {}
    for filename, names in (
        ("walker_kinematics.py", {"circle_oriented", "points_many"}),
        ("walker_contact.py", {"dimensions"}),
        ("walker_geometry.py", {"rigids", "link_pose"}),
        ("check_integrated_motion.py", {"rotation", "displacement", "transform"}),
    ):
        path = "scripts/ver3/" + filename
        raw = snapshot.read(path)
        tree = ast.parse(raw)
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        if {node.name for node in nodes} != names:
            raise ValueError("Canonical display kinematic API changed")
        exec(compile(ast.Module(body=nodes, type_ignores=[]), path, "exec"), namespace)
        provenance[path] = {"sha256": hashlib.sha256(raw).hexdigest(), "functions": sorted(names)}
    return namespace, provenance


def display_body_pose(frame, reference_height):
    height, sx, sy = frame["bodyHeightAndSlopes"]
    dx, dy, yaw = frame["integratedPlanarComponents"]
    small = np.array([[1, 0, -sx], [0, 1, -sy], [sx, sy, 1]], dtype=float)
    left, _, right = np.linalg.svd(small)
    polar = left @ right
    if np.linalg.det(polar) < 0:
        raise ValueError("Unexpected reflected body display frame")
    c, s = math.cos(yaw), math.sin(yaw)
    rz = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    rotation = rz @ polar
    translation = np.array([dx, dy, height])
    world = np.eye(4)
    world[:3, :3] = rotation
    world[:3, 3] = translation - rotation @ np.array([0, 0, reference_height])
    return world, rz @ small, translation


def geometric_rocker_angle(rotation, guide_pitch, loaded, travel_degrees):
    if not loaded:
        return None, "UNRESOLVED_AIRBORNE: no floor contact determines this passive degree of freedom"
    axis = rotation @ np.array([0, math.cos(guide_pitch), math.sin(guide_pitch)])
    lane_direction = rotation @ np.array([1, 0, 0])
    a = lane_direction[2]
    b = np.cross(axis, lane_direction)[2]
    if math.hypot(a, b) < 1e-12:
        return None, "UNRESOLVED_NONUNIQUE: equal-height condition does not select one angle"
    base = math.atan2(-a, b)
    candidates = [base + n*math.pi for n in range(-2, 3)
                  if abs(base + n*math.pi) <= math.radians(travel_degrees) + 1e-12]
    if len(candidates) != 1:
        return None, "UNRESOLVED_RANGE: no unique equal-height display angle within mechanical travel"
    return candidates[0], "GEOMETRIC_DISPLAY_ONLY: loaded-pad centers made equal-height; not an independent solver result"


def create_diagnostics(design="A", phases=(0, 120, 240)):
    snapshot = Snapshot()
    handoff, models = read_handoff()
    model = models[design]
    guide = model["guide"]
    assembly = snapshot.json(f"docs/ver3/integrated_r7/{design}/assembly.json")
    frame_reference = guide["contactFrames"]
    raw_frames = snapshot.read(f"docs/ver3/integrated_r7/{design}/contact_frames.json")
    if hashlib.sha256(raw_frames).hexdigest() != frame_reference["sha256"]:
        raise ValueError("Diagnostic contact-frame hash mismatch")
    contact = json.loads(raw_frames)
    if contact["sourceCommit"] != snapshot.source["inputCommit"] or contact["assemblySha256"] != snapshot.files[f"docs/ver3/integrated_r7/{design}/assembly.json"]["sha256"]:
        raise ValueError("Diagnostic frame and geometry versions differ")
    api, provenance = canonical_functions(snapshot)
    common, foot = assembly["parameters"]["common"], assembly["parameters"]["common"]["foot"]
    reference_z = assembly["bodyOriginZMm"]
    dimensions = api["dimensions"]("reference", common)

    def points(theta):
        return api["points_many"](np.array(theta), dimensions, common["linkScale"])[0]

    meshes = {mesh["name"]: np.asarray(accessor_values(model, mesh["primitives"][0]["attributes"]["POSITION"])) * 1000
              for mesh in model["gltf"]["meshes"]}
    initial_points = points(0)
    results = []
    for phase in phases:
        frame = next(f for f in contact["frames"] if f["crankDeg"] == phase)
        if frame["independentRockerAngleRad"] is not None:
            raise ValueError("New canonical rocker states need an explicit adapter update")
        theta = math.radians(phase)
        body, small, translation = display_body_pose(frame, reference_z)
        rotation = body[:3, :3]
        order = {(f["stationYmm"], f["side"]): index for index, f in enumerate(contact["footOrder"])}
        keys = {(i["motion"]["station"], i["motion"]["side"], i["motion"]["phase"])
                for i in assembly["instances"] if "phase" in i["motion"]}
        frames = {key: (points(theta+key[2]), points(key[2]), initial_points) for key in keys}
        calculated = [small @ np.array(p) + translation for p in frame["toesBodyMm"]]
        rigid = [rotation @ np.array(p) + translation for p in frame["toesBodyMm"]]
        feet = []
        for index, point in enumerate(calculated):
            angle, status = geometric_rocker_angle(rotation, frame["guidePitchRad"][index], frame["loadedFoot"][index],
                                                   foot["rockerTravelDeg"])
            feet.append({
                "footIndex": index, "order": contact["footOrder"][index],
                "sourceLoaded": frame["loadedFoot"][index], "sourceNormalN": frame["normalN"][index],
                "sourceCompressionMm": frame["springCompressionMm"][index],
                "calculatedCenterWorldMm": point.tolist(),
                "calculatedContactPlanePointMm": (point - [0, 0, foot["toeRadiusMm"]]).tolist(),
                "rigidDisplayCenterWorldMm": rigid[index].tolist(),
                "bodyRepresentationDifferenceMm": float(np.linalg.norm(rigid[index] - point)),
                "canonicalIndependentRockerAngleRad": None,
                "geometryDisplayRockerAngleRad": angle, "geometryDisplayStatus": status,
                "rockerFloorMinimumMm": None,
            })
        matrices, omitted = {}, {}
        maximum_gram_error, minimum_z, minimum_part = 0.0, math.inf, None
        minimum_source_z, below_plane = math.inf, {}
        for item in assembly["instances"]:
            motion = item["motion"]
            compression, rocker = 0.0, math.nan
            foot_index = None
            if motion["kind"] == "foot":
                foot_index = order[(motion["station"], motion["side"])]
                compression = frame["springCompressionMm"][foot_index]
                if motion["piece"] == "SPRING":
                    omitted[item["name"]] = "Coil-wire deformation is not a canonical solved state; compression shown as data, not scaled wire geometry."
                    continue
                if motion["piece"] == "ROCKER":
                    rocker = feet[foot_index]["geometryDisplayRockerAngleRad"]
                    if rocker is None:
                        omitted[item["name"]] = feet[foot_index]["geometryDisplayStatus"]
                        continue
            delta = api["transform"](item, theta, common, reference_z, compression, rocker, frames)
            local = delta @ np.array(item["transform"])
            final = body @ local
            error = float(np.max(np.abs(final[:3, :3].T @ final[:3, :3] - np.eye(3))))
            if error > 1e-9:
                raise ValueError("A display pose stretched/sheared a canonical CAD part")
            maximum_gram_error = max(maximum_gram_error, error)
            matrices[item["name"]] = final.tolist()
            vertices = meshes[item["part_id"]] @ final[:3, :3].T + final[:3, 3]
            low = float(vertices[:, 2].min())
            native_points = meshes[item["part_id"]] @ local[:3, :3].T + local[:3, 3]
            source_points = (native_points - [0, 0, reference_z]) @ small.T + translation
            source_low = float(source_points[:, 2].min())
            minimum_source_z = min(minimum_source_z, source_low)
            if low < 0:
                below_plane[item["name"]] = {"rigidDisplayMinimumZMm": low, "sourceSmallAngleMinimumZMm": source_low}
            if low < minimum_z:
                minimum_z, minimum_part = low, item["name"]
            if motion.get("piece") == "ROCKER":
                feet[foot_index]["rockerFloorMinimumMm"] = low
        results.append({
            "crankDeg": phase, "inputDegUnwrapped": frame["inputDegUnwrapped"],
            "sourceSecondsAtPrescribed120InputRpm": frame["secondsAtPrescribed120InputRpm"],
            "sourceIntegratedPlanarComponents": frame["integratedPlanarComponents"],
            "sourceBodyHeightAndSlopes": frame["bodyHeightAndSlopes"],
            "displayBodyWorld4x4Mm": body.tolist(), "displayBodyMethod": "Polar orthogonalization of saved small-angle map; yaw from saved integrated component; no new trajectory integration.",
            "feet": feet, "instanceWorld4x4Mm": matrices, "omittedInstances": omitted,
            "maximumRotationGramError": maximum_gram_error,
            "maximumFootCenterRepresentationDifferenceMm": max(f["bodyRepresentationDifferenceMm"] for f in feet),
            "minimumRenderedVertexZMm": minimum_z, "lowestRenderedPart": minimum_part,
            "sourceSmallAngleMinimumZMm": minimum_source_z, "belowReferencePlaneParts": below_plane,
            "floorCorrectionApplied": False, "interpolationUsed": False,
        })
    report = {
        "schemaVersion": 1, "revisionId": guide["revision"]["revisionId"], "designId": design,
        "artifactCommit": snapshot.commit, "sourceCommit": snapshot.source["inputCommit"],
        "sourceHash": snapshot.source["sourceHash"], "contactFramesSha256": frame_reference["sha256"],
        "geometrySha256": guide["model"]["sha256"], "canonicalFunctionSources": provenance,
        "displayOnly": True, "physicalTestsPerformed": False, "newDynamicsOrForcesSolved": False,
        "canonicalRockerNullPreserved": True, "representation": "Three diagnostic phases, not complete CAD walking.",
        "markerMeaning": "Saved compression-corrected pad centers and canonical center-minus-6mm reference-plane points; not measured foot contact.",
        "rockerDisplayMeaning": "For loaded feet only, equal-height symmetric pad-center geometry may select a display angle within +/-5deg. It is not the source solver's independent angle. Unloaded/ambiguous rockers are omitted and marked unresolved.",
        "frames": results,
    }
    MEDIA.mkdir(parents=True, exist_ok=True)
    path = MEDIA / f"diagnostic_{design}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n")
    for result in results:
        print(f"{design} {result['crankDeg']}deg: rendered {len(result['instanceWorld4x4Mm'])}, omitted {len(result['omittedInstances'])}, "
              f"max center representation difference {result['maximumFootCenterRepresentationDifferenceMm']:.6f}mm, "
              f"minimum actual vertex Z {result['minimumRenderedVertexZMm']:.6f}mm (no floor correction)")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--design", choices=list("ABC"), default="A")
    args = parser.parse_args()
    create_diagnostics(args.design)
