"""Check the saved walking .blend in a fresh isolated Blender process, read-only."""

import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r7_walk_render import NATIVE, MEDIA, inputs, mesh_source
from r7_blender import require_background, accessor_values

TOLERANCES = {"baseVertexMm": 1e-5, "worldCornerMm": .15, "rotationGram": 2e-6, "rockerFloorMm": .001}


def main():
    bpy = require_background()
    import numpy as np
    bpy.ops.wm.open_mainfile(filepath=str(NATIVE), load_ui=False)
    reports = {}
    for design in "ABC":
        packet, meta, values = inputs(design, False)
        scene = bpy.data.scenes["R7_WALK_" + design]
        bpy.context.window.scene = scene
        model = mesh_source(design)
        objects = {o["instance_id"]: o for o in scene.objects if "instance_id" in o}
        if set(objects) != set(packet["instances"]) or len(objects) != packet["instanceCount"]:
            raise ValueError("Native walking inventory differs")
        if scene["motion_packet_sha256"] != meta["motionSha256"] or scene["motion_evaluator_sha256"] != meta["evaluatorSha256"]:
            raise ValueError("Native animation and source model differ")
        canonical = {node["extras"]["instanceId"]: np.asarray(node["matrix"]).reshape(4, 4).T
                     for node in model["gltf"]["nodes"] if node.get("extras", {}).get("role") == "assembly"}
        mesh_maximum, compared_meshes = 0., set()
        for mesh in model["gltf"]["meshes"]:
            part = mesh["name"]
            matching = next((o for o in objects.values() if o["part_id"] == part), None)
            if matching is None:
                raise ValueError("A canonical mesh has no native object")
            vertices = np.asarray(accessor_values(model, mesh["primitives"][0]["attributes"]["POSITION"]))
            current = np.empty(len(matching.data.vertices) * 3)
            matching.data.vertices.foreach_get("co", current)
            if len(current) != vertices.size:
                raise ValueError("Native base geometry was decimated")
            mesh_maximum = max(mesh_maximum, float(np.abs(current.reshape(-1, 3) - vertices).max()) * 1000)
            triangles = np.asarray([v[0] for v in accessor_values(model, mesh["primitives"][0]["indices"])]).reshape(-1, 3)
            actual = np.array([tuple(p.vertices) for p in matching.data.polygons])
            if not np.array_equal(triangles, actual):
                raise ValueError("Native triangles differ from corrected geometry")
            compared_meshes.add(part)
        coil_ids = [name for name, obj in objects.items() if obj.get("procedural_geometry") == "PROCEDURAL_COIL_V1"]
        if len(coil_ids) != 12 or any(objects[name]["part_id"] != "H_FOOT_SPRING" for name in coil_ids):
            raise ValueError("Procedural springs lost their canonical identity")
        maximum_corner_mm, maximum_gram, minimum_rocker_z = 0., 0., float("inf")
        rocker_vertices = {}
        for name, obj in objects.items():
            if packet["motionGroups"][packet["instances"][name][1]].get("piece") == "ROCKER":
                vertices = np.empty(len(obj.data.vertices) * 3)
                obj.data.vertices.foreach_get("co", vertices)
                rocker_vertices[name] = vertices.reshape(-1, 3)
        frames = sorted({1, 2, 19, 37, meta["frameCount"] // 2, meta["frameCount"] - 1, meta["frameCount"]})
        for frame in frames:
            scene.frame_set(frame)
            scene.view_layers[0].update()
            row = values[frame - 1]
            body = row[:16].reshape(4, 4).copy()
            body[:3, 3] *= .001
            for name, obj in objects.items():
                group = packet["instances"][name][1]
                delta = row[(group + 1) * 16:(group + 2) * 16].reshape(4, 4).copy()
                delta[:3, 3] *= .001
                expected = body @ delta @ canonical[name]
                actual = np.array(obj.matrix_world)
                corners = np.c_[np.asarray(obj.bound_box), np.ones(8)]
                maximum_corner_mm = max(maximum_corner_mm, float(np.linalg.norm((corners @ (actual - expected).T)[:, :3], axis=1).max()) * 1000)
                maximum_gram = max(maximum_gram, float(np.abs(actual[:3, :3].T @ actual[:3, :3] - np.eye(3)).max()))
                if name in rocker_vertices:
                    minimum_rocker_z = min(minimum_rocker_z, float((rocker_vertices[name] @ actual[2, :3] + actual[2, 3]).min()) * 1000)
        if (mesh_maximum > TOLERANCES["baseVertexMm"] or maximum_corner_mm > TOLERANCES["worldCornerMm"]
                or maximum_gram > TOLERANCES["rotationGram"] or minimum_rocker_z < -TOLERANCES["rockerFloorMm"]):
            raise ValueError(f"{design}: excessive native quantization {mesh_maximum}, {maximum_corner_mm}, {maximum_gram}")
        reports[design] = {
            "instanceCount": len(objects), "comparedCanonicalMeshes": len(compared_meshes),
            "proceduralSprings": len(coil_ids), "sampledFilmFrames": frames,
            "maximumNativeBaseVertexDifferenceMm": mesh_maximum,
            "maximumSampledWorldCornerDifferenceMm": maximum_corner_mm,
            "maximumNativeRotationGramError": maximum_gram,
            "minimumSampledRockerVertexZMm": minimum_rocker_z,
            "motionSha256": meta["motionSha256"], "evaluatorSha256": meta["evaluatorSha256"],
        }
    result = {
        "schemaVersion": 1, "revisionId": "r7-floor2-walking-kinematic-v1", "status": "PASS",
        "nativeSha256": hashlib.sha256(NATIVE.read_bytes()).hexdigest(),
        "instanceCounts": {d: r["instanceCount"] for d, r in reports.items()},
        "proceduralSpringsPerDesign": 12, "tolerances": TOLERANCES, "designs": reports,
        "scope": "Exact base vertices/triangles and IDs; sampled keyed rigid poses include Blender float32 Euler/quaternion quantization. Procedural coils use fixed wire/radius/turns. Not a new collision or physical qualification.",
    }
    (MEDIA / "native-validation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
