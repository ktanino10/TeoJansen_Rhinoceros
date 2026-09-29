"""Isolated Blender renderer of the browser's exact analytical motion packets.

node site/r7-walk-export.mjs --design C --preview
blender --background --factory-startup --python site/r7_walk_render.py -- --design C --preview

Production: export ABC without --preview, then --build-native, then --design C/A/B
serially. A single temporary PNG is streamed to ffmpeg; no frame dump is retained.
"""

import argparse
import fcntl
import gzip
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r7_blender import accessor_values, base_color, require_background

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "site/dist/TeoJansen_Rhinoceros"
STATES = ROOT / "site/dist/r7-walk-state"
MEDIA = ROOT / "docs/ver3/r7_walking_v1"
NATIVE = ROOT / "Blender/Ver.3/integrated_r7/r7_walking_v1.blend"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inputs(design, preview):
    import numpy as np
    raw = (MEDIA / f"motion_{design}.json").read_bytes()
    packet = json.loads(raw)
    prefix = ("preview_" if preview else "") + design
    meta = json.loads((STATES / f"{prefix}.json").read_text())
    binary = (STATES / meta["binary"]).read_bytes()
    if (meta["motionSha256"] != digest(raw) or meta["binarySha256"] != digest(binary)
            or meta["evaluatorSha256"] != digest((ROOT / "site/r7-walk-math.js").read_bytes())):
        raise ValueError("Renderer and browser motion sources differ")
    values = np.frombuffer(binary, dtype="<f8").reshape(meta["frameCount"], meta["strideFloat64"])
    return packet, meta, values


def mesh_source(design):
    catalog = json.loads((PUBLIC / "assets/r7-walking-index.json").read_text())
    entry = catalog["designs"][design]
    compressed = (PUBLIC / entry["modelUrl"]).read_bytes()
    if digest(compressed) != entry["transportSha256"]:
        raise ValueError("Renderer GLB transport hash differs")
    raw = gzip.decompress(compressed)
    if digest(raw) != entry["modelSha256"]:
        raise ValueError("Renderer canonical GLB hash differs")
    magic, version, total = struct.unpack_from("<4sII", raw)
    size, chunk = struct.unpack_from("<I4s", raw, 12)
    if (magic, version, total, chunk) != (b"glTF", 2, len(raw), b"JSON"):
        raise ValueError("Invalid exact GLB source")
    return {"gltf": json.loads(raw[20:20 + size]), "binary": raw[28 + size:]}


def bake(obj, path, rows):
    import bpy
    import numpy as np
    data = np.asarray(rows)
    if data.ndim == 1:
        data = data[:, None]
    obj.animation_data_create()
    if obj.animation_data.action:
        action = obj.animation_data.action
        bag = action.layers[0].strips[0].channelbag(obj.animation_data.action_slot)
    else:
        action = bpy.data.actions.new(obj.name + "_RIGID_MOTION")
        slot = action.slots.new(id_type="OBJECT", name=obj.name)
        bag = action.layers.new("ANALYTICAL FRAME SAMPLES").strips.new(type="KEYFRAME").channelbag(slot, ensure=True)
        obj.animation_data.action = action
        obj.animation_data.action_slot = slot
    for axis in range(data.shape[1]):
        curve = bag.fcurves.new(data_path=path, index=axis)
        curve.keyframe_points.add(len(data))
        coordinates = np.column_stack([np.arange(1, len(data) + 1), data[:, axis]]).ravel()
        curve.keyframe_points.foreach_set("co", coordinates)
        for key in curve.keyframe_points:
            key.interpolation = "LINEAR"
        curve.update()


def bake_matrices(obj, rows):
    from mathutils import Matrix
    locations, rotations, previous = [], [], None
    for flat in rows:
        matrix = Matrix([flat[n:n + 4].tolist() for n in (0, 4, 8, 12)])
        matrix.translation *= .001
        q = matrix.to_quaternion()
        if previous is not None and q.dot(previous) < 0:
            q.negate()
        locations.append(tuple(matrix.translation))
        rotations.append(tuple(q))
        previous = q
    obj.rotation_mode = "QUATERNION"
    bake(obj, "location", locations)
    bake(obj, "rotation_quaternion", rotations)


def coil_nodes(bpy, foot):
    tree = bpy.data.node_groups.new("PROCEDURAL_COIL_V1", "GeometryNodeTree")
    tree.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    compression = tree.interface.new_socket(name="Compression mm", in_out="INPUT", socket_type="NodeSocketFloat")
    compression.min_value, compression.max_value = 0, foot["workingCompressionLimitMm"]
    inlet = tree.nodes.new("NodeGroupInput")
    output = tree.nodes.new("NodeGroupOutput")
    spiral = tree.nodes.new("GeometryNodeCurveSpiral")
    spiral.inputs["Resolution"].default_value = 24
    spiral.inputs["Rotations"].default_value = foot["springTotalTurns"]
    radius = (foot["springOuterDiameterMm"] - foot["springWireMm"]) / 2000
    spiral.inputs["Start Radius"].default_value = radius
    spiral.inputs["End Radius"].default_value = radius
    multiply = tree.nodes.new("ShaderNodeMath")
    multiply.operation = "MULTIPLY"
    multiply.inputs[1].default_value = -.001
    tree.links.new(inlet.outputs["Compression mm"], multiply.inputs[0])
    add = tree.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    add.inputs[1].default_value = (foot["springFreeLengthMm"] - foot["springWireMm"]) / 1000
    tree.links.new(multiply.outputs[0], add.inputs[0])
    tree.links.new(add.outputs[0], spiral.inputs["Height"])
    translate = tree.nodes.new("GeometryNodeTransform")
    translate.inputs["Translation"].default_value = (0, 0, foot["springWireMm"] / 2000)
    tree.links.new(spiral.outputs["Curve"], translate.inputs["Geometry"])
    circle = tree.nodes.new("GeometryNodeCurvePrimitiveCircle")
    circle.inputs["Resolution"].default_value = 8
    circle.inputs["Radius"].default_value = foot["springWireMm"] / 2000
    tube = tree.nodes.new("GeometryNodeCurveToMesh")
    tree.links.new(translate.outputs["Geometry"], tube.inputs["Curve"])
    tree.links.new(circle.outputs["Curve"], tube.inputs["Profile Curve"])
    tube.inputs["Fill Caps"].default_value = True
    tree.links.new(tube.outputs["Mesh"], output.inputs["Geometry"])
    return tree, compression.identifier


def create_scene(design, preview=False):
    bpy = require_background()
    import numpy as np
    from mathutils import Matrix, Vector
    packet, meta, values = inputs(design, preview)
    model = mesh_source(design)
    scene = bpy.data.scenes.new("R7_WALK_" + design)
    bpy.context.window.scene = scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 12
    scene.render.resolution_x, scene.render.resolution_y = (640, 480) if preview else (960, 720)
    scene.render.resolution_percentage = 100
    scene.render.fps = meta["fps"]
    scene.frame_start, scene.frame_end = 1, meta["frameCount"]
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = .55
    scene.eevee.motion_blur_steps = 2
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.compression = 15
    scene.render.use_file_extension = True
    scene.view_settings.view_transform = "AgX"
    scene.world = bpy.data.worlds.new("WALK_LIGHT_WORLD_" + design)
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (.7, .79, .75, 1)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = .25
    scene.unit_settings.system = "METRIC"
    scene["motion_revision"] = packet["revisionId"]
    scene["source_artifact_commit"] = packet["source"]["artifactCommit"]
    scene["manufacturing_release"] = False
    scene["physical_qualified_count"] = 0
    scene["motion_packet_sha256"] = meta["motionSha256"]
    scene["motion_evaluator_sha256"] = meta["evaluatorSha256"]
    scene["render_recipe"] = json.dumps(meta)

    def object_for(name, data=None):
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        return obj

    materials = {}
    def material(category, guard=False):
        key = (category, guard)
        if key not in materials:
            item = bpy.data.materials.new(f"WALK_{design}_{category}_{guard}")
            item.use_nodes = True
            shader = item.node_tree.nodes.get("Principled BSDF")
            shader.inputs["Roughness"].default_value = .45
            shader.inputs["Metallic"].default_value = .6 if category in ("purchased", "cut_to_length") else .05
            color = item.node_tree.nodes.new("ShaderNodeObjectInfo")
            item.node_tree.links.new(color.outputs["Color"], shader.inputs["Base Color"])
            if guard:
                shader.inputs["Alpha"].default_value = .13 if category == "sheet_cut" else .19
                item.surface_render_method = "DITHERED"
                item.use_transparency_overlap = False
            materials[key] = item
        return materials[key]

    body = object_for("WALK_BODY_" + design)
    body["rigid_body_only"] = True
    bake_matrices(body, values[:, :16])
    parents, pivots = [], {}
    theta = values[:, -4]
    for index, motion in enumerate(packet["motionGroups"]):
        parent = object_for(f"WALK_GROUP_{design}_{index:03}")
        parent.parent = body
        parent["canonical_motion"] = json.dumps(motion)
        rows = values[:, 16 * (index + 1):16 * (index + 2)]
        if motion["kind"] in ("shaft", "crank"):
            pivot = Vector((0, motion["axisYz"][0] / 1000, (motion["axisYz"][1] + packet["bodyReferenceZMm"]) / 1000))
            parent.location = pivot
            parent.rotation_mode = "XYZ"
            bake(parent, "rotation_euler", np.column_stack([theta * motion["speed"], np.zeros(len(theta)), np.zeros(len(theta))]))
            pivots[index] = pivot
        else:
            bake_matrices(parent, rows)
        parents.append(parent)
    libraries = {}
    for mesh in model["gltf"]["meshes"]:
        primitive = mesh["primitives"][0]
        geometry = bpy.data.meshes.new(f"WALK_{design}_{mesh['name']}")
        vertices = accessor_values(model, primitive["attributes"]["POSITION"])
        indices = [v[0] for v in accessor_values(model, primitive["indices"])]
        geometry.from_pydata(vertices, [], [indices[i:i + 3] for i in range(0, len(indices), 3)])
        geometry.update()
        for polygon in geometry.polygons:
            polygon.use_smooth = True
        category = mesh["extras"]["category"]
        guard = category == "sheet_cut" or mesh["name"].startswith(("P_ROTOR_CAGE", "P_GUARD"))
        geometry.materials.append(material(category, guard))
        geometry["canonical_part_id"] = mesh["name"]
        geometry["canonical_vertex_count"] = len(vertices)
        geometry["canonical_triangle_count"] = len(indices) // 3
        libraries[mesh["name"]] = geometry
    coil_tree, compression_socket = coil_nodes(bpy, packet["foot"])
    objects = []
    for node in model["gltf"]["nodes"]:
        info = node.get("extras", {})
        if info.get("role") != "assembly":
            continue
        name, part = info["instanceId"], info["partId"]
        if packet["instances"][name][0] != part:
            raise ValueError("Canonical instance mapping changed")
        group = packet["instances"][name][1]
        obj = object_for(f"WALK_{design}:{name}", libraries[part])
        objects.append(obj)
        obj.parent = parents[group]
        rows = node["matrix"]
        base = Matrix([[rows[c * 4 + r] for c in range(4)] for r in range(4)])
        if group in pivots:
            base.translation -= pivots[group]
        obj.matrix_basis = base
        obj.color = base_color(design, part, info["category"])
        if info["category"] == "printed" and not part.startswith(("P_ROTOR_CAGE", "P_FOOT", "P_LEG_AC", "P_LEG_DE")):
            obj.color = tuple(min(1, x * 1.35 + .08) for x in obj.color[:3]) + (1,)
        obj["instance_id"], obj["part_id"], obj["motion_group"] = name, part, group
        obj["canonical_matrix_column_major_m"] = rows
        motion = packet["motionGroups"][group]
        if motion.get("piece") == "SPRING":
            foot_index = next(i for i, f in enumerate(packet["footOrder"]) if f["stationYmm"] == motion["station"] and f["side"] == motion["side"])
            obj["procedural_geometry"] = "PROCEDURAL_COIL_V1"
            obj["compression_mm"] = float(values[0, 16 * (len(parents) + 1) + foot_index * 6])
            modifier = obj.modifiers.new("Actual seats / fixed wire / variable pitch", "NODES")
            modifier.node_group = coil_tree
            modifier[compression_socket] = obj["compression_mm"]
            driver = modifier.driver_add(f'["{compression_socket}"]').driver
            driver.expression = "compression"
            variable = driver.variables.new()
            variable.name, variable.type = "compression", "SINGLE_PROP"
            variable.targets[0].id = obj
            variable.targets[0].data_path = '["compression_mm"]'
            bake(obj, '["compression_mm"]', values[:, 16 * (len(parents) + 1) + foot_index * 6])
    if len(objects) != packet["instanceCount"]:
        raise ValueError("Native walking scene omitted canonical instances")
    camera_data = bpy.data.cameras.new("WALK_CAMERA_" + design)
    camera = object_for("WALK_CAMERA_" + design, camera_data)
    scene.camera = camera
    camera_data.type = "ORTHO"
    camera_data.clip_start = .001
    direction = Vector((1.8, -1.2, .8)).normalized()
    camera.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
    scene.frame_set(1)
    scene.view_layers[0].update()
    bounds = [obj.matrix_world @ Vector(corner) for obj in objects if "procedural_geometry" not in obj for corner in obj.bound_box]
    right = camera.rotation_euler.to_matrix() @ Vector((1, 0, 0))
    up = camera.rotation_euler.to_matrix() @ Vector((0, 1, 0))
    xx, yy = [p.dot(right) for p in bounds], [p.dot(up) for p in bounds]
    target = right * ((min(xx) + max(xx)) / 2) + up * ((min(yy) + max(yy)) / 2)
    target += direction * (sum(p.dot(direction) for p in bounds) / len(bounds))
    camera_data.ortho_scale = max((max(xx) - min(xx)) / .78, (max(yy) - min(yy)) * 4 / 3 / .70)
    location = target + direction * 2
    body_matrices = values[:, :16].reshape(-1, 4, 4)
    z0 = packet["bodyReferenceZMm"]
    trajectory = (body_matrices[:, :3, 3] + body_matrices[:, :3, 2] * z0) / 1000
    trajectory[:, 2] = 0
    bake(camera, "location", trajectory + np.array(location))
    for index, (xyz, energy, size) in enumerate([((.7, -.5, 1.1), 8, 1.2), ((-.7, -.2, .8), 5.5, 1.1), ((.3, .7, 1.2), 9.5, 1.5)]):
        light = object_for(f"WALK_LIGHT_{design}_{index}", bpy.data.lights.new(f"WALK_LIGHT_{design}_{index}", "AREA"))
        light.location = xyz
        light.data.energy, light.data.shape, light.data.size = energy, "DISK", size
        light.rotation_euler = (target - light.location).to_track_quat("-Z", "Y").to_euler()
    floor_material = bpy.data.materials.new("WALK_FLOOR_" + design)
    floor_material.diffuse_color = (.62, .69, .60, 1)
    floor_material.use_nodes = True
    nodes, links = floor_material.node_tree.nodes, floor_material.node_tree.links
    shader = nodes["Principled BSDF"]
    shader.inputs["Roughness"].default_value = .9
    position = nodes.new("ShaderNodeNewGeometry")
    separate = nodes.new("ShaderNodeSeparateXYZ")
    links.new(position.outputs["Position"], separate.inputs[0])
    masks = []
    for frequency, width in ((100, .025), (20, .012)):
        lines = []
        for axis in ("X", "Y"):
            multiply = nodes.new("ShaderNodeMath")
            multiply.operation = "MULTIPLY"
            multiply.inputs[1].default_value = frequency
            links.new(separate.outputs[axis], multiply.inputs[0])
            fraction = nodes.new("ShaderNodeMath")
            fraction.operation = "FRACT"
            links.new(multiply.outputs[0], fraction.inputs[0])
            line = nodes.new("ShaderNodeMath")
            line.operation = "LESS_THAN"
            line.inputs[1].default_value = width
            links.new(fraction.outputs[0], line.inputs[0])
            lines.append(line)
        mask = nodes.new("ShaderNodeMath")
        mask.operation = "MAXIMUM"
        links.new(lines[0].outputs[0], mask.inputs[0])
        links.new(lines[1].outputs[0], mask.inputs[1])
        masks.append(mask)
    fine = nodes.new("ShaderNodeMixRGB")
    fine.inputs[1].default_value = (.62, .69, .60, 1)
    fine.inputs[2].default_value = (.32, .40, .32, 1)
    links.new(masks[0].outputs[0], fine.inputs[0])
    major = nodes.new("ShaderNodeMixRGB")
    major.inputs[2].default_value = (.10, .20, .13, 1)
    links.new(fine.outputs[0], major.inputs[1])
    links.new(masks[1].outputs[0], major.inputs[0])
    links.new(major.outputs[0], shader.inputs["Base Color"])
    floor_mesh = bpy.data.meshes.new("FIXED_Z0_FLOOR")
    floor_mesh.from_pydata([(-2, -2, 0), (2, -2, 0), (2, 2, 0), (-2, 2, 0)], [], [(0, 1, 2, 3)])
    floor_mesh.materials.append(floor_material)
    object_for("FIXED_Z0_FLOOR", floor_mesh)
    text_material = bpy.data.materials.new("WALK_ANNOTATION_" + design)
    text_material.use_nodes = True
    text_material.node_tree.nodes.clear()
    emission = text_material.node_tree.nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (.001, .004, .002, 1)
    output = text_material.node_tree.nodes.new("ShaderNodeOutputMaterial")
    text_material.node_tree.links.new(emission.outputs[0], output.inputs["Surface"])
    font_path = Path("/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc")
    if not font_path.is_file():
        raise RuntimeError("The existing Japanese render font is missing; no font is downloaded")
    font = bpy.data.fonts.load(str(font_path))

    def text(body_text, x, y, size, japanese=False, name=None):
        curve = bpy.data.curves.new(name or body_text[:40], "FONT")
        curve.body = body_text
        curve.size = size / 960 * camera_data.ortho_scale
        curve.materials.append(text_material)
        if japanese:
            curve.font = font
        obj = object_for(name or body_text[:40], curve)
        obj.parent = camera
        width = camera_data.ortho_scale
        obj.location = ((x / 960 - .5) * width, (.5 - y / 720) * width * .75, -.025)
        obj["annotation_not_mechanical_part"] = True
        if japanese:
            depsgraph = bpy.context.evaluated_depsgraph_get()
            outlined = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))
            replacement = object_for(obj.name + "_OUTLINES", outlined)
            replacement.parent, replacement.matrix_basis = camera, obj.matrix_basis.copy()
            replacement["annotation_not_mechanical_part"] = True
            bpy.data.objects.remove(obj, do_unlink=True)
            return replacement
        return obj

    text(f"r7 {design}案 | 連続歩行シミュレーション", 28, 35, 26, japanese=True)
    text("床是正版の実CAD / 計算表示・実機未検証", 28, 65, 18, japanese=True)
    text(f"INPUT 120 rpm / TIME x16 / {abs(packet['inputTurnsPerCrank']):g}:1 / 4 CYCLES" if not preview else
         f"FIRST PREVIEW / INPUT 120 rpm / TIME x16 / {abs(packet['inputTurnsPerCrank']):g}:1", 28, 94, 17)
    hud = text("CRANK 0.0 deg | t=0.0 s | ADVANCE 0.0 mm", 28, 649, 18, name="WALK_HUD_" + design)
    text("空中ロッカーは中立復帰の仮定 / ばねは固定線径の手続き形状", 28, 680, 16, japanese=True)
    text("風・衝撃の動力学ではありません。実自己始動・実30 cm歩行は未確認。", 28, 706, 15, japanese=True)
    textblock = bpy.data.texts.new(f"WALK_{design}_MOTION.json")
    textblock.write(json.dumps(packet, separators=(",", ":")))
    scene.frame_set(1)
    scene.view_layers[0].update()
    return scene, meta, values, hud


def render(design, preview=False):
    bpy = require_background()
    if preview:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene, meta, values, hud = create_scene(design, preview=True)
    else:
        bpy.ops.wm.open_mainfile(filepath=str(NATIVE), load_ui=False)
        scene = bpy.data.scenes["R7_WALK_" + design]
        packet, meta, values = inputs(design, preview=False)
        if scene["motion_packet_sha256"] != meta["motionSha256"] or scene["motion_evaluator_sha256"] != meta["evaluatorSha256"]:
            raise ValueError("Native walking scene is stale")
        hud = scene.objects["WALK_HUD_" + design]
    bpy.context.window.scene = scene
    folder = ROOT / "site/dist/r7-walk-preview" if preview else MEDIA
    folder.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(STATES / f"stream_{design}_")
    movie = folder / f"walking_{design}.mp4"
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "image2pipe", "-framerate", str(meta["fps"]),
               "-vcodec", "png", "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "25",
               "-maxrate", "900k", "-bufsize", "1800k", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(movie)]
    started = time.monotonic()
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    written = []

    def annotate(current, *_):
        if current != scene:
            return
        index = min(max(current.frame_current - 1, 0), meta["frameCount"] - 1)
        theta, seconds, forward, _ = values[index, -4:]
        hud.data.body = f"CRANK {math.degrees(theta) % 360:05.1f} deg | t={seconds:05.1f} s | ADVANCE {forward:05.1f} mm"

    def stream_frame(current, *_):
        if current != scene:
            return
        index = current.frame_current - 1
        if index != len(written):
            raise RuntimeError("Animation frame stream is not consecutive")
        image = Path(current.render.frame_path(frame=current.frame_current))
        data = image.read_bytes()
        if index == 0:
            (folder / f"walking_{design}.png").write_bytes(data)
        process.stdin.write(data)
        image.unlink()
        written.append(index)
        if index % 30 == 0:
            print(f"WALK_RENDER {design} {index + 1}/{meta['frameCount']} seconds={time.monotonic() - started:.1f}", flush=True)

    bpy.app.handlers.frame_change_pre.append(annotate)
    bpy.app.handlers.render_write.append(stream_frame)
    try:
        bpy.ops.render.render(animation=True, scene=scene.name)
        if len(written) != meta["frameCount"]:
            raise RuntimeError("The complete continuous frame stream was not rendered")
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError("ffmpeg walking encode failed")
    except BaseException:
        process.stdin.close()
        process.wait()
        raise
    finally:
        bpy.app.handlers.frame_change_pre.remove(annotate)
        bpy.app.handlers.render_write.remove(stream_frame)
    (folder / f"render_{design}.json").write_text(json.dumps({
        **meta, "renderer": bpy.app.version_string, "width": scene.render.resolution_x, "height": scene.render.resolution_y,
        "sourceGeometry": "All canonical instance IDs; only twelve coils have the declared procedural wire geometry.",
        "nativeInterpolation": "Rigid translation/quaternion keys evaluated at every exact browser-exported film frame. Fast shaft Euler angles remain unwrapped and linear for subframe motion blur; no vertex interpolation.",
        "physicalTestsPerformed": False, "elapsedSeconds": time.monotonic() - started,
    }, indent=2) + "\n")
    print(f"WALK_COMPLETE {movie} bytes={movie.stat().st_size}", flush=True)


def main():
    bpy = require_background()
    parser = argparse.ArgumentParser()
    parser.add_argument("--design", choices=list("ABC"), default="C")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--build-native", action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    lock_path = ROOT / "site/dist/r7-blender-prep/render.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.build_native:
            bpy.ops.wm.read_factory_settings(use_empty=True)
            for design in "CAB":
                create_scene(design)
            bpy.context.window.scene = bpy.data.scenes["R7_WALK_C"]
            NATIVE.parent.mkdir(parents=True, exist_ok=True)
            bpy.context.preferences.filepaths.save_version = 0
            bpy.ops.wm.save_as_mainfile(filepath=str(NATIVE), compress=True)
            print("NATIVE_WALKING", NATIVE.stat().st_size, "bytes", flush=True)
        else:
            render(args.design, args.preview)


if __name__ == "__main__":
    main()
