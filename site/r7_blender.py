"""Build and render exact same-source r7 scenes in one separate Blender CLI.

Validation requires ordinary Python only:
    python3 site/r7_blender.py --validate

Run each phase serially, never against a live Blender scene:
    blender --background --factory-startup --python site/r7_blender.py -- --build
    blender --background --factory-startup --python site/r7_blender.py -- --stills
    blender --background --factory-startup --python site/r7_blender.py -- --assembly

No walking animation is synthesized from clearance summaries. Native creation
and rendering are separate phases. Assembly timing is illustrative, not physical.
"""

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r7_render_plan import timeline, subtitle_vtt

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "site/dist/r7-preview/TeoJansen_Rhinoceros"
OUTPUT = ROOT / "site/dist/r7-blender-prep/r7_candidate.blend"
MEDIA = ROOT / "site/dist/r7-visuals"
FRAMES = ROOT / "site/dist/r7-render-frames"
WIDTH, HEIGHT = 1280, 720
LIGHTS = [((1.0, -1.1, 1.8), 95, 1.8), ((-1.2, -0.3, 0.8), 70, 1.5), ((0.4, 1.3, 1.3), 110, 1.4)]


def base_color(design, part, category):
    if category == "sheet_cut":
        return (0.25, 0.40, 0.46, 1)
    if category != "printed":
        return (0.30, 0.37, 0.43, 1)
    if part.startswith(("P_ROTOR_CAGE", "P_FOOT", "P_LEG_AC", "P_LEG_DE")):
        return (0.07, 0.11, 0.14, 1)
    if part.startswith(("P_CHASSIS", "P_COMPOUND", "P_SYNC", "P_OUTPUT")):
        return {"A": (0.38, 0.18, 0.035, 1), "B": (0.025, 0.12, 0.34, 1), "C": (0.012, 0.18, 0.10, 1)}[design]
    return (0.58, 0.62, 0.58, 1)


def fit_camera(scene, points):
    from mathutils import Vector
    direction = Vector((1.2, -1.6, 0.9)).normalized()
    right = Vector((1.6, 1.2, 0)).normalized()
    up = direction.cross(right).normalized()
    if not points:
        raise ValueError("Camera has no exact mesh bounds")
    x, y = [p.dot(right) for p in points], [p.dot(up) for p in points]
    depth = sum(p.dot(direction) for p in points)/len(points)
    center = right*((min(x)+max(x))/2) + up*((min(y)+max(y))/2) + direction*depth
    fraction = 0.51 if scene.name.endswith("_ASSEMBLY") else 0.58
    width = max((max(x)-min(x))/0.90, (max(y)-min(y))*WIDTH/HEIGHT/fraction, 0.35)
    center -= up*(0.02*width*HEIGHT/WIDTH)
    scene.camera.location = center + direction*4
    scene.camera.data.ortho_scale = width
    return center, width


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_handoff():
    handoff = json.loads((PREVIEW / "blender-handoff.json").read_text())
    if handoff["schemaVersion"] != 2 or handoff["localOnly"] is not True:
        raise ValueError("Only the local schema2 handoff is accepted")
    source = json.loads((ROOT / "site/r7-source.json").read_text())
    if handoff["candidateCommit"] != source["artifactCommit"] or handoff["sourceContractSha256"] != source["contractSha256"]:
        raise ValueError("Blender and site reference different candidate revisions")
    models = {}
    for ident, entry in handoff["designs"].items():
        for key in ("model", "guide"):
            path = (PREVIEW / entry[key]).resolve()
            if not path.is_relative_to(PREVIEW.resolve()) or not path.is_file():
                raise ValueError("Invalid Blender handoff path")
        compressed = (PREVIEW / entry["model"]).read_bytes()
        guide_bytes = (PREVIEW / entry["guide"]).read_bytes()
        if digest(compressed) != entry["transportSha256"] or digest(guide_bytes) != entry["guideSha256"]:
            raise ValueError("Blender model or guide fingerprint differs")
        raw = gzip.decompress(compressed)
        if digest(raw) != entry["modelSha256"]:
            raise ValueError("Blender GLB fingerprint differs")
        magic, version, length = struct.unpack_from("<4sII", raw)
        if (magic, version, length) != (b"glTF", 2, len(raw)):
            raise ValueError("Expected a complete GLB2 model")
        size, chunk = struct.unpack_from("<I4s", raw, 12)
        if chunk != b"JSON":
            raise ValueError("Missing GLB JSON")
        document = json.loads(raw[20:20+size])
        models[ident] = {"gltf": document, "binary": raw[28+size:], "guide": json.loads(guide_bytes)}
        nodes = [node for node in document["nodes"] if node.get("extras", {}).get("role") == "assembly"]
        if len(nodes) != entry["instanceCount"] or {n["extras"]["instanceId"] for n in nodes} != set(models[ident]["guide"]["instances"]):
            raise ValueError("Blender handoff lost a canonical instance")
    if set(models) != set("ABC"):
        raise ValueError("Blender comparison needs the same three source candidates")
    return handoff, models


def accessor_values(model, index):
    document, binary = model["gltf"], model["binary"]
    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    components = 3 if accessor["type"] == "VEC3" else 1
    code = {5126: "f", 5125: "I"}[accessor["componentType"]]
    offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    values = struct.unpack_from(f"<{accessor['count'] * components}{code}", binary, offset)
    return [tuple(values[n:n+components]) for n in range(0, len(values), components)]


def require_background():
    import bpy
    if not bpy.app.background:
        raise RuntimeError("Refusing to modify a live interactive Blender scene")
    return bpy


def bake_channels(obj, data_path, samples):
    """Constant-held source states, with no unvalidated interpolation."""
    import bpy
    values = [(frame, value if isinstance(value, (list, tuple)) else [float(value)]) for frame, value in samples]
    action = None
    bag = None
    for axis in range(len(values[0][1])):
        compact = [(values[0][0], values[0][1][axis])]
        for frame, row in values[1:]:
            if row[axis] != compact[-1][1]:
                compact.append((frame, row[axis]))
        if len(compact) == 1:
            continue
        if action is None:
            obj.animation_data_create()
            if obj.animation_data.action:
                action = obj.animation_data.action
                bag = action.layers[0].strips[0].channelbag(obj.animation_data.action_slot)
            else:
                action = bpy.data.actions.new(obj.name + "_SOURCE_STATES")
                slot = action.slots.new(id_type="OBJECT", name=obj.name)
                strip = action.layers.new("CANONICAL BOUNDARIES").strips.new(type="KEYFRAME")
                bag = strip.channelbag(slot, ensure=True)
                obj.animation_data.action = action
                obj.animation_data.action_slot = slot
        curve = bag.fcurves.new(data_path=data_path, index=axis)
        curve.keyframe_points.add(len(compact))
        curve.keyframe_points.foreach_set("co", [v for pair in compact for v in pair])
        for key in curve.keyframe_points:
            key.interpolation = "CONSTANT"
        curve.update()


def build_native():
    bpy = require_background()
    from mathutils import Matrix, Vector
    from bpy_extras.object_utils import world_to_camera_view

    handoff, models = read_handoff()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    libraries, materials = {}, {}
    view_direction = Vector((1.2, -1.6, 0.9)).normalized()
    view_right = Vector((1.6, 1.2, 0)).normalized()

    def material(category):
        if category not in materials:
            item = bpy.data.materials.new("CAD_" + category)
            item.use_nodes = True
            nodes = item.node_tree.nodes
            shader = nodes.get("Principled BSDF")
            shader.inputs["Roughness"].default_value = 0.36
            shader.inputs["Metallic"].default_value = 0.7 if category in ("purchased", "cut_to_length") else 0
            obj_info = nodes.new("ShaderNodeObjectInfo")
            item.node_tree.links.new(obj_info.outputs["Color"], shader.inputs["Base Color"])
            if category == "sheet_cut":
                shader.inputs["Alpha"].default_value = 0.16
                shader.inputs["Roughness"].default_value = 0.25
                item.surface_render_method = "DITHERED"
            materials[category] = item
        return materials[category]

    def emission(name, rgb):
        if name not in materials:
            item = bpy.data.materials.new(name)
            item.use_nodes = True
            item.node_tree.nodes.clear()
            shader = item.node_tree.nodes.new("ShaderNodeEmission")
            shader.inputs["Color"].default_value = (*rgb, 1)
            output = item.node_tree.nodes.new("ShaderNodeOutputMaterial")
            item.node_tree.links.new(shader.outputs[0], output.inputs["Surface"])
            materials[name] = item
        return materials[name]

    white = emission("ANNOTATION_WHITE", (0.8, 0.87, 0.91))
    amber = emission("ANNOTATION_AMBER", (1, 0.61, 0.22))
    cyan = emission("ANNOTATION_CYAN", (0.30, 0.70, 0.77))
    muted = emission("ANNOTATION_MUTED", (0.44, 0.56, 0.63))

    def collection(scene, design, offset=(0, 0, 0)):
        model = models[design]
        result = bpy.data.collections.new(f"{scene.name}_{design}")
        scene.collection.children.link(result)
        for mesh in model["gltf"]["meshes"]:
            key = (design, mesh["name"])
            if key not in libraries:
                primitive = mesh["primitives"][0]
                vertices = accessor_values(model, primitive["attributes"]["POSITION"])
                indices = [v[0] for v in accessor_values(model, primitive["indices"])]
                geometry = bpy.data.meshes.new(f"{design}_{mesh['name']}")
                geometry.from_pydata(vertices, [], [indices[n:n+3] for n in range(0, len(indices), 3)])
                geometry.update()
                edges = {}
                for polygon in geometry.polygons:
                    for edge in polygon.edge_keys:
                        edges.setdefault(edge, []).append(polygon.index)
                threshold = math.cos(math.radians(35))
                for edge in geometry.edges:
                    adjacent = edges[edge.key]
                    edge.use_edge_sharp = len(adjacent) != 2 or geometry.polygons[adjacent[0]].normal.dot(
                        geometry.polygons[adjacent[1]].normal) < threshold
                for polygon in geometry.polygons:
                    polygon.use_smooth = True
                geometry.materials.append(material(mesh["extras"]["category"]))
                geometry["source_vertex_count"] = len(vertices)
                geometry["source_triangle_count"] = len(indices)//3
                libraries[key] = geometry
        objects = {}
        for node in model["gltf"]["nodes"]:
            meta = node.get("extras", {})
            if meta.get("role") != "assembly":
                continue
            obj = bpy.data.objects.new(f"{scene.name}:{design}:{meta['instanceId']}", libraries[(design, meta["partId"])])
            result.objects.link(obj)
            obj.rotation_mode = "QUATERNION"
            values = node["matrix"]
            obj.matrix_world = Matrix([[values[col*4+row] for col in range(4)] for row in range(4)])
            obj.matrix_world.translation += Vector(offset)
            obj.color = base_color(design, meta["partId"], meta["category"])
            obj["instance_id"], obj["part_id"], obj["category"] = meta["instanceId"], meta["partId"], meta["category"]
            obj["design_id"] = design
            obj["source_commit"] = handoff["candidateCommit"]
            obj["canonical_matrix_column_major_m"] = values
            obj["presentation_offset_m"] = list(offset)
            objects[meta["instanceId"]] = obj
        scene.view_layers[0].update()
        return objects

    def setup(scene):
        bpy.context.window.scene = scene
        scene.render.engine = "BLENDER_EEVEE"
        scene.eevee.taa_render_samples = 32
        scene.render.resolution_x, scene.render.resolution_y = WIDTH, HEIGHT
        scene.render.resolution_percentage = 100
        scene.render.fps = 24
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGB"
        scene.view_settings.view_transform = "AgX"
        scene["source_commit"] = handoff["candidateCommit"]
        scene["revision"] = handoff["revision"]["revisionId"]
        scene["status"] = "LOCAL CANDIDATE / PHYSICAL SELF-START AND WALKING UNVERIFIED"
        scene["walking_animation"] = "NOT GENERATED: canonical world/body/foot frames pending"
        scene.unit_settings.system = "METRIC"
        scene.unit_settings.scale_length = 1
        scene.world = bpy.data.worlds.new(scene.name + "_world")
        scene.world.use_nodes = True
        scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.025, 0.045, 0.062, 1)
        scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.4
        for index, (position, energy, size) in enumerate(LIGHTS):
            lamp = bpy.data.objects.new(scene.name + f"_light{index}", bpy.data.lights.new(scene.name + f"_light{index}", "AREA"))
            lamp.location = position
            lamp.data.energy, lamp.data.size = energy, size
            lamp.rotation_euler = (Vector((0, 0, 0.20))-lamp.location).to_track_quat("-Z", "Y").to_euler()
            scene.collection.objects.link(lamp)
        camera = bpy.data.objects.new(scene.name + "_camera", bpy.data.cameras.new(scene.name + "_camera"))
        camera.data.type = "ORTHO"
        camera.data.clip_start, camera.data.clip_end = 0.001, 100
        camera.rotation_euler = (-view_direction).to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(camera)
        scene.camera = camera

    def corners(objects, visible=None, offsets=None):
        points = []
        for name, obj in objects.items():
            if visible is not None and name not in visible:
                continue
            extra = Vector((offsets or {}).get(name, (0, 0, 0))) * 0.001
            points.extend(obj.matrix_world @ Vector(corner) + extra for corner in obj.bound_box)
        return points

    def fit(scene, points):
        return fit_camera(scene, points)

    def text(scene, value, x, y, size, mat, *, align="LEFT", first=None, last=None):
        curve = bpy.data.curves.new("LABEL_" + value[:35], "FONT")
        curve.body, curve.size, curve.align_x = value, size/WIDTH, align
        curve.materials.append(mat)
        obj = bpy.data.objects.new(curve.name, curve)
        scene.collection.objects.link(obj)
        obj.parent = scene.camera
        # A driver keeps HUD typography independent of camera framing at each stage.
        obj.location = (x/WIDTH-0.5, (0.5-y/HEIGHT)*HEIGHT/WIDTH, -0.012)
        for axis in (0, 1):
            driver = obj.driver_add("location", axis).driver
            variable = driver.variables.new()
            variable.name, variable.type = "w", "SINGLE_PROP"
            variable.targets[0].id_type = "CAMERA"
            variable.targets[0].id = scene.camera.data
            variable.targets[0].data_path = "ortho_scale"
            driver.expression = f"{obj.location[axis]:.15g}*w"
        for axis in (0, 1, 2):
            driver = obj.driver_add("scale", axis).driver
            variable = driver.variables.new()
            variable.name, variable.type = "w", "SINGLE_PROP"
            variable.targets[0].id_type = "CAMERA"
            variable.targets[0].id = scene.camera.data
            variable.targets[0].data_path = "ortho_scale"
            driver.expression = "w"
        obj["annotation_only"] = True
        if first is not None:
            obj.hide_render = obj.hide_viewport = first != 1
            visibility = [(1, first != 1)]
            if first > 1:
                visibility.append((first, False))
            visibility.append((last+1, True))
            bake_channels(obj, "hide_render", visibility)
            bake_channels(obj, "hide_viewport", visibility)
        return obj

    def labels(scene, title, subtitle):
        text(scene, "R7 / INTEGRATED DESIGN CANDIDATE", 40, 35, 15, cyan)
        text(scene, title, 40, 78, 27, white)
        text(scene, subtitle, 40, 109, 15, muted)
        text(scene, "EXACT CAD / PHYSICAL START AND WALKING UNVERIFIED / NOT A MANUFACTURING RELEASE", 40, 674, 15, amber)
        text(scene, f"GEOMETRY {handoff['candidateCommit'][:7]} / schema2 / no legacy video substitution", 40, 700, 13, muted)

    comparison = bpy.context.scene
    comparison.name = "R7_COMPARE"
    setup(comparison)
    groups = {}
    projected_widths = []
    for design in "ABC":
        group = collection(comparison, design)
        groups[design] = group
        points = corners(group)
        projected_widths.append(max(p.dot(view_right) for p in points)-min(p.dot(view_right) for p in points))
    spacing = max(projected_widths) + 0.10
    for index, design in enumerate("ABC"):
        delta = view_right * (index-1) * spacing
        for obj in groups[design].values():
            obj.matrix_world.translation += delta
            obj["presentation_offset_m"] = list(delta)
    comparison.view_layers[0].update()
    fit(comparison, [p for group in groups.values() for p in corners(group)])
    labels(comparison, "ONE PHYSICAL SCALE. THREE R7 CANDIDATES.", "Static uncompressed assembly reference / no floor-contact claim")
    comparison.view_layers[0].update()
    for design in "ABC":
        objects = groups[design]
        center = sum((obj.matrix_world.translation for obj in objects.values()), Vector())/len(objects)
        px = world_to_camera_view(comparison, comparison.camera, center).x*WIDTH
        row = models[design]["guide"]["summary"]
        text(comparison, f"{design}  {row['rotorDiameterMm']:g} mm / {row['reduction']:g}:1", px, 572, 20, cyan, align="CENTER")
        text(comparison, f"{row['cadMassG']:.1f} g nominal | JPY {row['firstBuildCostJpy']:,.0f}", px, 601, 15, white, align="CENTER")
    text(comparison, "Individual first-build cost assumptions. Shipping / uncertain tax separate; no purchases performed.", 40, 640, 14, muted)
    comparison["media_name"] = "comparison.png"

    MEDIA.mkdir(parents=True, exist_ok=True)
    plans = {}
    for design in "ABC":
        guide = models[design]["guide"]
        hero = bpy.data.scenes.new(f"R7_{design}_HERO")
        setup(hero)
        objects = collection(hero, design)
        fit(hero, corners(objects))
        row = guide["summary"]
        labels(hero, f"{design} / {row['rotorDiameterMm']:g} mm ROTOR / {row['reduction']:g}:1",
               f"{row['cadMassG']:.3f} g nominal / {guide['model']['instanceCount']} exact instances / stock + printed + sheet parts")
        text(hero, "Uncompressed reference pose, not a solved walking frame.", 40, 636, 16, muted)
        hero["media_name"] = f"hero_{design}.png"

        scene = bpy.data.scenes.new(f"R7_{design}_ASSEMBLY")
        setup(scene)
        objects = collection(scene, design)
        plan = timeline(guide)
        plans[design] = plan
        scene.frame_start, scene.frame_end = 1, plan["frameEnd"]
        scene["schema2_guide"] = json.dumps(guide, ensure_ascii=False)
        scene["render_plan"] = json.dumps(plan, ensure_ascii=False)
        scene["animation_status"] = "Constant-held exact states; reversible reference, not physical execution"
        scene["media_name"] = f"assembly_{design}.mp4"
        stage_points = {}
        for entry in plan["entries"]:
            stage_points.setdefault(entry["stageIndex"], []).extend(corners(objects, set(entry["displayedIds"]), entry["state"]["offsets"]))
        all_points = corners(objects)
        camera_samples, scale_samples = [], []
        for entry in plan["entries"]:
            start = entry["timelineFrame"]
            camera_points = (corners(objects, set(entry["displayedIds"]), entry["state"]["offsets"])
                             if entry["state"]["kind"] == "foot-bench" else stage_points[entry["stageIndex"]])
            _, width = fit(scene, camera_points or all_points)
            camera_samples.append((start, list(scene.camera.location)))
            scale_samples.append((start, width))
        scene.camera.location = camera_samples[0][1]
        bake_channels(scene.camera, "location", camera_samples)
        scene.camera.data.ortho_scale = scale_samples[0][1]
        for frame, value in scale_samples:
            scene.camera.data.ortho_scale = value
            scene.camera.data.keyframe_insert("ortho_scale", frame=frame)
        action = scene.camera.data.animation_data.action
        bag = action.layers[0].strips[0].channelbag(scene.camera.data.animation_data.action_slot)
        for curve in bag.fcurves:
            for key in curve.keyframe_points:
                key.interpolation = "CONSTANT"
        for name, obj in objects.items():
            base = obj.location.copy()
            visibility, positions, colors = [], [], []
            for entry in plan["entries"]:
                frame = entry["timelineFrame"]
                state = entry["state"]
                visibility.append((frame, name not in entry["displayedIds"]))
                positions.append((frame, list(base + Vector(state["offsets"].get(name, [0, 0, 0]))*0.001)))
                active = name in state["focusIds"]
                colors.append((frame, (0.80, 0.40, 0.08, 1) if active else (0.38, 0.46, 0.50, 1)))
            obj.hide_render = obj.hide_viewport = visibility[0][1]
            obj.location, obj.color = positions[0][1], colors[0][1]
            bake_channels(obj, "hide_render", visibility)
            bake_channels(obj, "hide_viewport", visibility)
            bake_channels(obj, "location", positions)
            bake_channels(obj, "color", colors)
        labels(scene, f"{design} / ASSEMBLY AND REMOVAL REFERENCE", "12 ordered stages / playback time is illustrative / stopped crank at 0 degrees")
        text(scene, "AMBER: CURRENT / GRAY: STILL PRESENT / REMOVED: NOT DISPLAYED / PET SHOWN TRANSLUCENT", 40, 643, 13, muted)
        for entry in plan["entries"]:
            start, end = entry["timelineFrame"], entry["lastFrame"]
            text(scene, f"{entry['stageIndex']:02}  {entry['stageTitle']}", 40, 149, 19, cyan, first=start, last=end)
            for row, note in enumerate(entry["notes"]):
                text(scene, note, 40, 562+row*22, 13, amber if "SUPPORT" in note or "UNKNOWN" in note else white, first=start, last=end)
        for index, stage in enumerate(guide["steps"]):
            first = next(entry["timelineFrame"] for entry in plan["entries"] if entry["stageIndex"] == index)
            scene.timeline_markers.new(f"{stage['id']} {stage['title']}", frame=first)
        scene.frame_set(1)
        (MEDIA/f"assembly_{design}.vtt").write_text(subtitle_vtt(plan))
        (MEDIA/f"disassembly_{design}.vtt").write_text(subtitle_vtt(timeline(guide, reverse=True)))
    bpy.data.texts.new("R7_SOURCE_HANDOFF.json").write(json.dumps(handoff, ensure_ascii=False, indent=2))
    for design, plan in plans.items():
        bpy.data.texts.new(f"R7_{design}_ASSEMBLY_PLAN.json").write(json.dumps(plan, ensure_ascii=False))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.window.scene = comparison
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT), compress=True)
    (MEDIA/"render-source.json").write_text(json.dumps({"source": handoff, "planHashes": {
        design: digest(json.dumps(plan, ensure_ascii=False).encode()) for design, plan in plans.items()},
        "walking": "not generated; canonical frames pending", "publicationAuthorized": False}, ensure_ascii=False, indent=2)+"\n")
    print(f"Built editable source-bound scene: {OUTPUT}", flush=True)


def open_verified_native():
    bpy = require_background()
    handoff, models = read_handoff()
    bpy.ops.wm.open_mainfile(filepath=str(OUTPUT))
    native_handoff = json.loads(bpy.data.texts["R7_SOURCE_HANDOFF.json"].as_string())
    if native_handoff != handoff:
        raise ValueError("Native source handoff is stale; rebuild before rendering")
    return bpy, handoff, models


def restyle_native():
    """Adjust lighting/camera framing only; source object states stay untouched."""
    bpy, _, models = open_verified_native()
    from mathutils import Matrix, Vector
    for scene in bpy.data.scenes:
        if not scene.name.startswith("R7_"):
            continue
        bpy.context.window.scene = scene
        scene.frame_set(1)
        for index, (_, energy, size) in enumerate(LIGHTS):
            light = bpy.data.objects[scene.name+f"_light{index}"]
            light.data.energy, light.data.size = energy, size
        objects = {o["instance_id"]: o for o in scene.objects if "instance_id" in o}
        if scene.name.endswith("_ASSEMBLY"):
            design = next(iter(objects.values()))["design_id"]
            plan = timeline(models[design]["guide"])
            points_by_stage = {}
            for entry in plan["entries"]:
                points = points_by_stage.setdefault(entry["stageIndex"], [])
                for name in entry["displayedIds"]:
                    obj = objects[name]
                    values = obj["canonical_matrix_column_major_m"]
                    matrix = Matrix([[values[c*4+r] for c in range(4)] for r in range(4)])
                    delta = Vector(entry["state"]["offsets"].get(name, (0, 0, 0)))*0.001
                    points.extend(matrix @ Vector(p)+delta for p in obj.bound_box)
            all_points = [Vector(p) for p in points_by_stage[12]]
            scene.camera.animation_data_clear()
            scene.camera.data.animation_data_clear()
            locations, widths = [], []
            for entry in plan["entries"]:
                _, width = fit_camera(scene, points_by_stage[entry["stageIndex"]] or all_points)
                locations.append((entry["timelineFrame"], list(scene.camera.location)))
                widths.append((entry["timelineFrame"], width))
            scene.camera.location = locations[0][1]
            bake_channels(scene.camera, "location", locations)
            for frame, width in widths:
                scene.camera.data.ortho_scale = width
                scene.camera.data.keyframe_insert("ortho_scale", frame=frame)
            bag = scene.camera.data.animation_data.action.layers[0].strips[0].channelbag(scene.camera.data.animation_data.action_slot)
            for curve in bag.fcurves:
                for point in curve.keyframe_points:
                    point.interpolation = "CONSTANT"
        else:
            all_objects = [o for o in scene.objects if "instance_id" in o]
            for obj in all_objects:
                obj.color = base_color(obj["design_id"], obj["part_id"], obj["category"])
            scene.view_layers[0].update()
            fit_camera(scene, [obj.matrix_world @ Vector(p) for obj in all_objects for p in obj.bound_box])
    bpy.context.window.scene = bpy.data.scenes["R7_COMPARE"]
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT), compress=True)
    print("Updated presentation only; exact geometry and assembly-state keys unchanged.", flush=True)


def verify_native(rebind=False):
    if rebind:
        bpy = require_background()
        handoff, models = read_handoff()
        bpy.ops.wm.open_mainfile(filepath=str(OUTPUT))
    else:
        bpy, handoff, models = open_verified_native()
    from mathutils import Matrix, Vector
    import array

    checks = {"meshes": 0, "staticInstances": 0, "stateInstances": 0, "states": 0}
    for ident, model in models.items():
        for mesh in model["gltf"]["meshes"]:
            native = bpy.data.meshes[f"{ident}_{mesh['name']}"]
            primitive = mesh["primitives"][0]
            vertices = accessor_values(model, primitive["attributes"]["POSITION"])
            native_vertices = array.array("f", [0]) * (len(native.vertices) * 3)
            native.vertices.foreach_get("co", native_vertices)
            expected = array.array("f", [v for vertex in vertices for v in vertex])
            if native_vertices.tobytes() != expected.tobytes():
                raise ValueError(f"Native mesh vertices changed: {ident}/{mesh['name']}")
            indices = [v[0] for v in accessor_values(model, primitive["indices"])]
            native_indices = array.array("i", [0]) * (len(native.polygons) * 3)
            native.polygons.foreach_get("vertices", native_indices)
            if list(native_indices) != indices:
                raise ValueError(f"Native triangles changed: {ident}/{mesh['name']}")
            checks["meshes"] += 1
        matrices = {}
        for node in model["gltf"]["nodes"]:
            if node.get("extras", {}).get("role") == "assembly":
                values = node["matrix"]
                matrices[node["extras"]["instanceId"]] = Matrix([[values[c*4+r] for c in range(4)] for r in range(4)])
        for scene_name in ("R7_COMPARE", f"R7_{ident}_HERO"):
            scene = bpy.data.scenes[scene_name]
            bpy.context.window.scene = scene
            scene.frame_set(1)
            scene.view_layers[0].update()
            objects = {obj["instance_id"]: obj for obj in scene.objects if obj.get("design_id") == ident}
            if set(objects) != set(matrices):
                raise ValueError(f"Static scene lost exact instances: {scene_name}/{ident}")
            for name, obj in objects.items():
                expected = matrices[name].copy()
                expected.translation += Vector(obj["presentation_offset_m"])
                if max(abs(obj.matrix_world[r][c]-expected[r][c]) for r in range(4) for c in range(4)) > 1e-6:
                    raise ValueError(f"Static scene placement differs: {obj.name}")
                checks["staticInstances"] += 1
        scene = bpy.data.scenes[f"R7_{ident}_ASSEMBLY"]
        bpy.context.window.scene = scene
        objects = {obj["instance_id"]: obj for obj in scene.objects if "instance_id" in obj}
        plan = timeline(model["guide"])
        if json.loads(scene["render_plan"]) != plan or set(objects) != set(matrices):
            raise ValueError("Baked assembly timeline or IDs differ from the source")
        for entry in plan["entries"]:
            scene.frame_set(entry["timelineFrame"])
            visible = set(entry["displayedIds"])
            if {name for name, obj in objects.items() if not obj.hide_render} != visible:
                raise ValueError(f"Native visibility/inventory differs: {ident}/{entry['stateId']}")
            for name in visible:
                expected = matrices[name].copy()
                expected.translation += Vector(entry["state"]["offsets"].get(name, (0, 0, 0)))*0.001
                obj = objects[name]
                if max(abs(obj.matrix_world[r][c]-expected[r][c]) for r in range(4) for c in range(4)) > 1e-6:
                    raise ValueError(f"Native state pose differs: {ident}/{entry['stateId']}/{name}")
                checks["stateInstances"] += 1
            checks["states"] += 1
    if rebind:
        for scene in bpy.data.scenes:
            if not scene.name.startswith("R7_"):
                continue
            scene["source_commit"] = handoff["candidateCommit"]
            scene["revision"] = handoff["revision"]["revisionId"]
            if scene.name.endswith("_ASSEMBLY"):
                design = scene.name.split("_")[1]
                scene["schema2_guide"] = json.dumps(models[design]["guide"], ensure_ascii=False)
            for obj in scene.objects:
                if "source_commit" in obj:
                    obj["source_commit"] = handoff["candidateCommit"]
                if obj.type == "FONT" and obj.data.body.startswith("GEOMETRY "):
                    obj.data.body = f"GEOMETRY {handoff['candidateCommit'][:7]} / schema2 / no legacy video substitution"
        text = bpy.data.texts["R7_SOURCE_HANDOFF.json"]
        text.clear()
        text.write(json.dumps(handoff, ensure_ascii=False, indent=2))
        bpy.context.window.scene = bpy.data.scenes["R7_COMPARE"]
        bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT), compress=True)
        (MEDIA/"render-source.json").write_text(json.dumps({
            "source": handoff, "nativeRebindVerified": True,
            "geometryAndStateChange": False, "publicationAuthorized": False,
            "walking": "Partial canonical states received; complete foot orientation unresolved",
        }, ensure_ascii=False, indent=2)+"\n")
    report = {"sourceCommit": handoff["candidateCommit"], "checks": checks, "status": "PASS",
              "scope": "Exact imported meshes, original/static placement and every schema2 displayed state. Not mechanical revalidation.",
              "walking": "NOT GENERATED", "manufacturingRelease": False}
    (MEDIA/"native-display-validation.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report), flush=True)


def package_native():
    bpy, handoff, _ = open_verified_native()
    for scene in bpy.data.scenes:
        scene.render.filepath = "//media/" + scene.get("media_name", scene.name + ".png")
        scene["source_commit"] = handoff["candidateCommit"]
        scene["publication_status"] = "Source-bound display only; no manufacturing or physical-walking qualification"
    for text in bpy.data.texts:
        if "/Users/" in text.as_string() or "file://" in text.as_string():
            raise ValueError("Private file path found in embedded display provenance")
    bpy.context.window.scene = bpy.data.scenes["R7_COMPARE"]
    bpy.context.scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT), compress=True)
    print("Packaged editable native with relative render paths and embedded source data only.", flush=True)


def refine_bench_views():
    """Frame the six separate foot benches legibly; preserve every source part/state."""
    bpy, handoff, models = open_verified_native()
    from mathutils import Vector, Matrix
    for design in "ABC":
        scene = bpy.data.scenes[f"R7_{design}_ASSEMBLY"]
        guide = models[design]["guide"]
        plan = timeline(guide)
        objects = {o["instance_id"]: o for o in scene.objects if "instance_id" in o}
        base = {name: Matrix([[obj["canonical_matrix_column_major_m"][c*4+r] for c in range(4)] for r in range(4)])
                for name, obj in objects.items()}
        stage_points = {}
        points_by_entry = {}
        for entry in plan["entries"]:
            points = []
            for name in entry["displayedIds"]:
                delta = Vector(entry["state"]["offsets"].get(name, (0, 0, 0)))*0.001
                points.extend(base[name] @ Vector(p) + delta for p in objects[name].bound_box)
            points_by_entry[entry["stateId"]] = points
            stage_points.setdefault(entry["stageIndex"], []).extend(points)
        scene.camera.animation_data_clear()
        scene.camera.data.animation_data_clear()
        locations = []
        for entry in plan["entries"]:
            points = points_by_entry[entry["stateId"]] if entry["state"]["kind"] == "foot-bench" else stage_points[entry["stageIndex"]]
            fit_camera(scene, points or stage_points[12])
            locations.append((entry["timelineFrame"], list(scene.camera.location)))
            scene.camera.data.keyframe_insert("ortho_scale", frame=entry["timelineFrame"])
        scene.camera.location = locations[0][1]
        bake_channels(scene.camera, "location", locations)
        bag = scene.camera.data.animation_data.action.layers[0].strips[0].channelbag(scene.camera.data.animation_data.action_slot)
        for curve in bag.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "CONSTANT"
        rendered = {}
        for index, entry in enumerate(plan["entries"]):
            target = FRAMES/design/f"{index:04}.png"
            if entry["state"]["kind"] == "foot-bench":
                render_image(bpy, scene, target, entry["timelineFrame"])
            if not target.is_file():
                raise ValueError("An existing source-state render is missing")
            rendered[entry["stateId"]] = target
        encode_states(design, guide, rendered)
        encode_states(design, guide, rendered, reverse=True)
    for scene in bpy.data.scenes:
        scene.render.filepath = "//media/" + scene.get("media_name", scene.name+".png")
    bpy.context.window.scene = bpy.data.scenes["R7_COMPARE"]
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT), compress=True)
    print("Refined only isolated foot-bench camera framing; geometry, poses and inventories unchanged.", flush=True)


def render_image(bpy, scene, path, frame=1, scale=100):
    bpy.context.window.scene = scene
    scene.frame_set(frame)
    scene.render.resolution_percentage = scale
    scene.render.filepath = str(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    began = time.monotonic()
    bpy.ops.render.render(write_still=True, scene=scene.name)
    if not path.is_file() or path.stat().st_size < 1000:
        raise ValueError(f"Render produced no usable image: {path}")
    print(f"R7_RENDER {scene.name} frame={frame} seconds={time.monotonic()-began:.2f} {path.name}", flush=True)


def render_stills(preview=False):
    bpy, _, _ = open_verified_native()
    names = ["R7_COMPARE"] + [f"R7_{key}_HERO" for key in "ABC"]
    for name in names:
        scene = bpy.data.scenes[name]
        path = MEDIA / (("preview_" if preview else "") + scene["media_name"])
        render_image(bpy, scene, path, scale=50 if preview else 100)


def encode_states(design, guide, rendered, reverse=False):
    import os
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("Existing ffmpeg is required; no installation is performed")
    plan = timeline(guide, reverse=reverse)
    mode = "disassembly" if reverse else "assembly"
    numbered = FRAMES / f"{design}_{mode}_encode"
    numbered.mkdir(parents=True, exist_ok=True)
    made = []
    try:
        for entry in plan["entries"]:
            for frame in range(entry["timelineFrame"], entry["lastFrame"]+1):
                path = numbered/f"{frame:06}.png"
                if path.exists():
                    path.unlink()
                os.link(rendered[entry["stateId"]], path)
                made.append(path)
        output = MEDIA/f"{mode}_{design}.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(plan["fps"]),
                        "-i", str(numbered/"%06d.png"), "-frames:v", str(plan["frameEnd"]),
                        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart", "-an", str(output)], check=True)
        probe = subprocess.check_output(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                                         "-show_entries", "stream=width,height,nb_read_frames,r_frame_rate,duration",
                                         "-of", "json", str(output)], text=True)
        stream = json.loads(probe)["streams"][0]
        if (stream["width"], stream["height"]) != (WIDTH, HEIGHT) or int(stream["nb_read_frames"]) != plan["frameEnd"]:
            raise ValueError("Encoded explanation frame count or size differs from source-state timing")
        (MEDIA/f"{mode}_{design}.vtt").write_text(subtitle_vtt(plan))
        (MEDIA/f"{mode}_{design}.json").write_text(json.dumps({
            "sourceCommit": guide["revision"]["canonicalCommit"], "design": design,
            "reverseReference": reverse, "fps": plan["fps"], "frameCount": plan["frameEnd"], "stream": stream,
            "stateSequence": [{"id": e["stateId"], "frame": e["timelineFrame"], "lastFrame": e["lastFrame"]}
                              for e in plan["entries"]],
            "meaning": plan["timeMeaning"], "interpolation": plan["motionMeaning"],
            "originalGeometry": True, "physicalAssemblyPerformed": False,
        }, ensure_ascii=False, indent=2)+"\n")
        print(f"ENCODED {output.name} {plan['frameEnd']} frames", flush=True)
    finally:
        for path in made:
            path.unlink(missing_ok=True)
        numbered.rmdir()


def render_assembly(only=None):
    bpy, handoff, models = open_verified_native()
    cache = FRAMES/"source.json"
    expected = {"sourceCommit": handoff["candidateCommit"], "renderScriptSha256": digest(Path(__file__).read_bytes()),
                "handoffSha256": digest(json.dumps(handoff, sort_keys=True).encode())}
    FRAMES.mkdir(parents=True, exist_ok=True)
    if cache.exists() and json.loads(cache.read_text()) != expected:
        raise ValueError("Render cache belongs to another source/script; preserve or remove it explicitly before rendering")
    cache.write_text(json.dumps(expected))
    for design in (only or "ABC"):
        scene = bpy.data.scenes[f"R7_{design}_ASSEMBLY"]
        guide = models[design]["guide"]
        plan = timeline(guide)
        rendered = {}
        for index, entry in enumerate(plan["entries"]):
            target = FRAMES/design/f"{index:04}.png"
            if not target.exists():
                render_image(bpy, scene, target, entry["timelineFrame"])
            rendered[entry["stateId"]] = target
        encode_states(design, guide, rendered)
        encode_states(design, guide, rendered, reverse=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate", action="store_true")
    mode.add_argument("--build", action="store_true")
    mode.add_argument("--verify-native", action="store_true")
    mode.add_argument("--stills", action="store_true")
    mode.add_argument("--assembly", action="store_true")
    mode.add_argument("--restyle", action="store_true")
    mode.add_argument("--rebind-native", action="store_true")
    mode.add_argument("--package-native", action="store_true")
    mode.add_argument("--refine-bench", action="store_true")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--design", choices=list("ABC"))
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else None)
    if args.validate:
        handoff, models = read_handoff()
        print(f"Validated Blender handoff: {sum(len(m['guide']['instances']) for m in models.values())} exact instances; "
              "same schema2 inventories and fixed source. No native build/render/walking animation performed.")
    else:
        import fcntl
        source = json.loads((ROOT / "site/r7-source.json").read_text())
        if source.get("publicationHold") and (args.stills or args.assembly):
            raise RuntimeError("Production rendering is on hold: " + source["publicationHold"])
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        with (OUTPUT.parent/"render.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.build:
                build_native()
            elif args.verify_native:
                verify_native()
            elif args.rebind_native:
                verify_native(rebind=True)
            elif args.stills:
                render_stills(args.preview)
            elif args.restyle:
                restyle_native()
            elif args.package_native:
                package_native()
            elif args.refine_bench:
                refine_bench_views()
            else:
                render_assembly(args.design)
