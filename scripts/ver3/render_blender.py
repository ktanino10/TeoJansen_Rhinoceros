"""Render the Ver.3 CAD assemblies, without reconstructing any parts.

Run with the installed Blender, not a live interactive Blender session::

    blender -b --factory-startup --threads 4 --python scripts/ver3/render_blender.py -- \
        --profile system --phase preview

The default system profile produces a separately named native/preview package.
Use ``--profile first-cut`` explicitly for the preserved single-stage workflow.
Its phases ``build``, ``stills``, ``video`` and ``validate`` can run separately.
The latter phases reopen the saved blend. Raw frames are kept only in the
explicit work directory (or a temporary directory), never in the repository.
Render stages reload the canonical manifests and gzip meshes, rejecting stale
native files. Wait for CAD regeneration to finish before starting ``build``.
``--keep-frames`` permits resuming an interrupted video render; otherwise the
successfully encoded sequence's own PNGs are removed.

All mechanical meshes come from render_geometry.json.gz. All operation frames
come from core.animated_transform. Only presentation offsets, text, arrows,
lighting and a non-contact studio ground are added. The exploded scene is a
separate illustration using copies of the same meshes, not an insertion study.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
from itertools import product
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector
import numpy as np

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import CONFIG, animated_transform  # noqa: E402


NATIVE = ROOT / "Blender" / "Ver.3" / "first_cut_ABC.blend"
MEDIA = ROOT / "docs" / "ver3" / "media"
REPORT = NATIVE.with_name("visual_validation.json")
PORTABLE_RENDER_PATH = "//media/"
MM = 0.001
FPS = 24
FRAMES = 145
EXPLODED_FRAMES = 121
WIDTH, HEIGHT = 1280, 720
OPERATION_NOTICE = "PRESCRIBED KINEMATICS / NOT WIND OR CONTACT DYNAMICS"
WIND_NOTICE = "90 x 180 mm rotor: quasi-static wind budget NOT met."
C_NOTICE = "PARAMETRIC GENERATIVE FRAME / NOT TOPOLOGY OPTIMIZATION"
GROUP_NAMES = {
    "frame": "01 FRAME AND BEARINGS",
    "hardware": "02 FRAME HARDWARE",
    "crank": "03 OPEN CRANK MODULES",
    "legs": "04 SIX JANSEN LEGS",
    "pivot": "05 PIVOT SPACERS",
    "rotor": "06 ROTOR AND INPUT SHAFT",
    "drivetrain": "07 SINGLE SPUR STAGE",
    "guard": "08 REMOVABLE GUARD TRAY",
    "guard_lid": "09 PETG WINDOW",
}
DESIGN_NAMES = {
    "A": "ROBUST BASELINE",
    "B": "3:1 INPUT-TORQUE COMPARISON",
    "C": "GENERATED RIB FRAME",
}
PALETTE = {
    "A": (0.82, 0.52, 0.17, 1),
    "B": (0.055, 0.30, 0.82, 1),
    "C": (0.025, 0.49, 0.36, 1),
}
VIEW_DIRECTION = Vector((0.83, -1.35, 0.77)).normalized()
VIEW_RIGHT = Vector((-VIEW_DIRECTION.y, VIEW_DIRECTION.x, 0)).normalized()
OFFSETS = {key: VIEW_RIGHT * ((index - 1) * 0.46)
           for index, key in enumerate("ABC")}
BASE_CENTER = Vector((0.145, 0, 0.153))


def log(message):
    print(f"[ver3-visual] {message}", flush=True)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_paths(key):
    return (ROOT / f"docs/ver3/assembly_{key}.json",
            ROOT / f"FreeCAD/Ver.3/{key}/render_geometry.json.gz")


def read_inputs(design_ids="ABC", profile="first-cut"):
    manifests, libraries, fingerprints = {}, {}, {}
    for key in design_ids:
        manifest_path, mesh_path = source_paths(key)
        manifest_bytes = manifest_path.read_bytes()
        mesh_bytes = mesh_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        if manifest["units"] != "mm":
            raise ValueError(f"{manifest_path}: expected millimetres")
        if profile == "first-cut" and manifest["animation"]["frames"] != FRAMES:
            raise ValueError("Update the visualization frame range for the new manifest")
        if profile == "first-cut" and (
                "gears" not in manifest["design"] or manifest["design"].get("stages")):
            raise RuntimeError(
                f"{key}: {manifest['design'].get('name', 'unknown design')} "
                f"({len(manifest['instances'])} instances) is not the requested single-stage "
                "first-cut assembly. Do not mix first-cut and multi-stage revisions.")
        if profile == "system" and not manifest["design"].get("stages"):
            raise RuntimeError(f"{key}: multi-stage system input is not ready; do not substitute first-cut data")
        library = json.loads(gzip.decompress(mesh_bytes))
        names = [instance["name"] for instance in manifest["instances"]]
        if len(names) != len(set(names)):
            raise ValueError(f"Duplicate instance IDs in {manifest_path}")
        if set(library) != set(manifest["parts"]):
            raise ValueError(f"CAD mesh library and part IDs differ for {key}")
        for instance in manifest["instances"]:
            if instance["part_id"] not in library:
                raise ValueError(f"Missing exact CAD mesh for {instance['name']}")
        manifests[key], libraries[key] = manifest, library
        fingerprints[key] = {
            "manifest": str(manifest_path.relative_to(ROOT)),
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "meshes": str(mesh_path.relative_to(ROOT)),
            "meshes_sha256": hashlib.sha256(mesh_bytes).hexdigest(),
        }
    for key in design_ids:
        for field, path in zip(("manifest", "meshes"), source_paths(key)):
            if sha256(path) != fingerprints[key][f"{field}_sha256"]:
                raise RuntimeError(
                    f"Canonical input changed while being read: {path}. "
                    "Wait for CAD regeneration to finish, then retry.")
    fingerprints["core_sha256"] = sha256(Path(__file__).with_name("core.py"))
    fingerprints["design_config_sha256"] = sha256(Path(__file__).with_name("design.json"))
    kinematic_config = {field: CONFIG[field] for field in ("linkage", "hardware")}
    fingerprints["kinematic_config_sha256"] = hashlib.sha256(
        json.dumps(kinematic_config, sort_keys=True).encode()).hexdigest()
    if profile == "system":
        fingerprints["visualization_profile"] = "system"
    return manifests, libraries, fingerprints


def matrix_metres(rows):
    matrix = Matrix(rows)
    matrix.translation *= MM
    return matrix


def add_collection(parent, name):
    collection = bpy.data.collections.new(name)
    parent.children.link(collection)
    return collection


def material(name, color, metallic=0, roughness=0.4, alpha=1):
    result = bpy.data.materials.new(name)
    result.use_nodes = True
    result.diffuse_color = (*color[:3], alpha)
    shader = result.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color[:3], 1)
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Alpha"].default_value = alpha
    if alpha < 1:
        result.surface_render_method = "BLENDED"
        shader.inputs["Transmission Weight"].default_value = 0.15
        shader.inputs["IOR"].default_value = 1.57
    return result


def emission_material(name, color):
    result = bpy.data.materials.new(name)
    result.use_nodes = True
    nodes = result.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (*color[:3], 1)
    emission.inputs["Strength"].default_value = 1
    result.node_tree.links.new(emission.outputs[0], output.inputs["Surface"])
    return result


def create_materials():
    materials = {
        "ivory": material("PRINT | Warm matte ivory", (0.76, 0.79, 0.77, 1), roughness=0.42),
        "graphite": material("PRINT | Graphite", (0.10, 0.13, 0.16, 1), roughness=0.4),
        "steel": material("BUY | Stainless hardware", (0.48, 0.55, 0.62, 1), 0.8, 0.29),
        "hub": material("BUY | Machined metal REX hub", (0.61, 0.65, 0.68, 1), 0.8, 0.24),
        "shaft": material("CUT | Positive REX shaft", (0.42, 0.48, 0.57, 1), 0.82, 0.23),
        "bearing": material("BUY | Bearing envelope", (0.26, 0.31, 0.38, 1), 0.85, 0.23),
        "window": material("CUT | Purchased transparent PETG sheet",
                           (0.64, 0.86, 0.90, 1), roughness=0.16, alpha=0.045),
        "ground": material("STUDIO | Non-contact ground", (0.006, 0.010, 0.016, 1),
                           roughness=0.65),
        "text": emission_material("ANNOTATION | White", (0.81, 0.87, 0.91)),
        "muted": emission_material("ANNOTATION | Muted", (0.38, 0.50, 0.59)),
        "warning": emission_material("ANNOTATION | Amber", (1, 0.55, 0.16)),
        "cyan": emission_material("ANNOTATION | Cyan", (0.21, 0.76, 0.88)),
    }
    for key, color in PALETTE.items():
        materials[key] = material(f"PRINT | {key} design accent", color, roughness=0.37)
        materials[f"{key}_label"] = emission_material(f"ANNOTATION | {key}", color)
    return materials


def part_material(part_id, category, key, materials):
    if part_id == "S_GUARD_WINDOW" or part_id.startswith("S_WINDOW_"):
        return materials["window"]
    if "BELT" in part_id.upper() or "SOLE" in part_id.upper():
        return materials["graphite"]
    if part_id == "H_REX_HUB":
        return materials["hub"]
    if part_id == "H_608":
        return materials["bearing"]
    if part_id.startswith("H_shaft"):
        return materials["shaft"]
    if category != "printed":
        return materials["steel"]
    if part_id.startswith("P_GUARD") or part_id == "P_BEARING_RETAINER":
        return materials["graphite"]
    if part_id.startswith("P_FRAME"):
        return materials["ivory" if key == "A" else key]
    if part_id.startswith(("L_AB", "L_PC", "P_ROTOR_END")):
        return materials["ivory"]
    if part_id.startswith(("L_AC", "L_DE")):
        return materials["graphite"]
    return materials[key]


def smooth_cad_normals(mesh):
    """Split shading at real CAD creases; leave every vertex and face unchanged."""
    normals = np.empty(len(mesh.polygons) * 3, dtype=np.float32)
    mesh.polygons.foreach_get("normal", normals)
    normals = normals.reshape((-1, 3))
    edge_faces = {}
    for polygon in mesh.polygons:
        for edge in polygon.edge_keys:
            edge_faces.setdefault(edge, []).append(polygon.index)
    threshold = math.cos(math.radians(35))
    for edge in mesh.edges:
        adjacent = edge_faces.get(edge.key, [])
        edge.use_edge_sharp = (len(adjacent) != 2 or
                              float(np.dot(normals[adjacent[0]], normals[adjacent[1]])) < threshold)
    mesh.polygons.foreach_set("use_smooth", np.ones(len(mesh.polygons), dtype=np.bool_))


def add_action(obj, values, name, first_frame=1):
    """Bake only changing transform channels with continuous quaternion signs."""
    action = None
    channelbag = None
    channel_count = 0
    for data_path, samples in values.items():
        samples = np.asarray(samples, dtype=np.float64)
        for axis in range(samples.shape[1]):
            channel = samples[:, axis]
            if float(np.ptp(channel)) < 1e-10:
                continue
            if action is None:
                action = bpy.data.actions.new(name)
                slot = action.slots.new(id_type="OBJECT", name=obj.name)
                layer = action.layers.new("BAKED | no scripts or handlers")
                strip = layer.strips.new(type="KEYFRAME")
                channelbag = strip.channelbag(slot, ensure=True)
                obj.animation_data_create()
                obj.animation_data.action = action
                obj.animation_data.action_slot = slot
            curve = channelbag.fcurves.new(data_path=data_path, index=axis)
            curve.keyframe_points.add(len(channel))
            coordinates = np.column_stack((
                np.arange(first_frame, first_frame + len(channel)), channel))
            curve.keyframe_points.foreach_set("co", coordinates.ravel())
            for point in curve.keyframe_points:
                point.interpolation = "LINEAR"
            curve.update()
            channel_count += 1
    obj["baked_channels"] = channel_count
    return channel_count


def build_design(key, manifest, library, materials, *, frame_count=FRAMES,
                 display_name=None, offset=None, loop=False, bounds=None,
                 source_fingerprints=None):
    root_collection = bpy.data.collections.new(f"{key} | {display_name or DESIGN_NAMES[key]}")
    root = bpy.data.objects.new(f"{key}::PRESENTATION_OFFSET_ONLY", None)
    root_collection.objects.link(root)
    root.location = OFFSETS[key] if offset is None else offset
    root.empty_display_size = 0.018
    root["presentation_only"] = True
    root["note"] = "Static layout offset only. No forward locomotion is simulated."
    root["canonical_units"] = "mm"
    if source_fingerprints is not None:
        for field, value in source_fingerprints.items():
            if field.endswith("_sha256"):
                root[f"source_{field}"] = value
    group_labels = dict(GROUP_NAMES)
    for name in sorted({item["group"] for item in manifest["instances"]} - group_labels.keys()):
        group_labels[name] = f"{len(group_labels) + 1:02d} {name.replace('_', ' ').upper()}"
    groups = {}
    for name, label in group_labels.items():
        groups[name] = add_collection(root_collection, f"{key} | {label}")
        groups[name]["assembly_group"] = name
    meshes = {}
    local_boxes = {}
    for part_id, geometry in library.items():
        mesh = bpy.data.meshes.new(f"{key}::CAD::{part_id}")
        mesh.from_pydata(np.asarray(geometry["vertices"]) * MM, [], geometry["triangles"])
        mesh.update()
        smooth_cad_normals(mesh)
        mesh.materials.append(part_material(part_id, geometry["category"], key, materials))
        mesh["part_id"] = part_id
        mesh["design_id"] = key
        mesh["source"] = manifest["cad_meshes"]
        mesh["source_units"] = "mm; coordinates converted to metres only"
        if source_fingerprints is not None:
            mesh["source_meshes_sha256"] = source_fingerprints["meshes_sha256"]
        mesh.use_fake_user = True
        meshes[part_id] = mesh
        if bounds is not None:
            vertices = np.asarray(geometry["vertices"]) * MM
            local_boxes[part_id] = np.asarray(list(product(*zip(vertices.min(axis=0),
                                                                vertices.max(axis=0)))))
    objects = {}
    for instance in manifest["instances"]:
        part_id = instance["part_id"]
        obj = bpy.data.objects.new(f"{key}::{instance['name']}", meshes[part_id])
        groups[instance["group"]].objects.link(obj)
        obj.parent = root
        obj.rotation_mode = "QUATERNION"
        obj.matrix_local = matrix_metres(instance["transform"])
        obj["canonical_instance"] = True
        obj["design_id"] = key
        obj["instance_id"] = instance["name"]
        obj["part_id"] = part_id
        obj["category"] = manifest["parts"][part_id]["category"]
        obj["assembly_group"] = instance["group"]
        obj["nominal_mass_g"] = manifest["parts"][part_id]["mass_g"]
        obj["manifest_transform_mm"] = json.dumps(instance["transform"])
        obj["motion_metadata"] = json.dumps(instance.get("motion"))
        obj["description"] = manifest["parts"][part_id]["description"]
        objects[instance["name"]] = obj

    log(f"{key}: baking all {frame_count} authoritative crank samples")
    for instance in manifest["instances"]:
        obj = objects[instance["name"]]
        positions, rotations = [], []
        previous = None
        lower, upper = np.full(3, np.inf), np.full(3, -np.inf)
        for frame in range(frame_count):
            theta = math.tau * frame / (frame_count - 1)
            transform = matrix_metres(animated_transform(instance, theta, manifest["design"]))
            if frame == 0:
                difference = np.max(np.abs(np.asarray(transform) -
                                           np.asarray(matrix_metres(instance["transform"]))))
                if difference > 1e-6:
                    raise ValueError(f"Initial core/CAD pose disagreement: {obj.name}: {difference}")
            quaternion = transform.to_quaternion()
            if previous is not None and quaternion.dot(previous) < 0:
                quaternion.negate()
            previous = quaternion.copy()
            positions.append(tuple(transform.translation))
            rotations.append(tuple(quaternion))
            if bounds is not None:
                matrix = np.asarray(transform)
                corners = local_boxes[instance["part_id"]] @ matrix[:3, :3].T + matrix[:3, 3]
                lower = np.minimum(lower, corners.min(axis=0))
                upper = np.maximum(upper, corners.max(axis=0))
        add_action(obj, {"location": positions, "rotation_quaternion": rotations},
                   f"KINEMATICS::{key}::{instance['name']}")
        obj["baked_frame_count"] = frame_count
        if bounds is not None:
            bounds[instance["name"]] = np.asarray([lower, upper])
        if loop:
            for curve in curves_for(obj):
                modifier = curve.modifiers.new("CYCLES")
                modifier.mode_before = modifier.mode_after = "REPEAT"
    return root_collection, root, objects


def configure_scene(scene, end=FRAMES):
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 64
    scene.eevee.use_raytracing = False
    scene.render.resolution_x, scene.render.resolution_y = WIDTH, HEIGHT
    scene.render.resolution_percentage = 100
    scene.render.fps = FPS
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 25
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "MILLIMETERS"
    scene.unit_settings.scale_length = 1
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.frame_start, scene.frame_end = 1, end
    scene["engineering_status"] = "FIRST-CUT ENGINEERING CONCEPT / NOT PHYSICAL VALIDATION"
    scene["motion_limitations"] = OPERATION_NOTICE
    scene["wind_budget"] = WIND_NOTICE
    scene["hardware_detail"] = "Purchased hub flexures, threads and bearing internals simplified in CAD"
    world = bpy.data.worlds.get("STUDIO | Dark blue")
    if world is None:
        world = bpy.data.worlds.new("STUDIO | Dark blue")
        world.use_nodes = True
        background = world.node_tree.nodes.get("Background")
        background.inputs["Color"].default_value = (0.045, 0.065, 0.10, 1)
        background.inputs["Strength"].default_value = 0.25
    scene.world = world


def studio(scene, materials, center, *, ground_z=-0.012, light_scale=1.0):
    collection = add_collection(scene.collection, f"{scene.name} | STUDIO")
    mesh = bpy.data.meshes.new(f"{scene.name} | Ground mesh")
    span = 3 * light_scale
    mesh.from_pydata([(-span, -span, ground_z), (span, -span, ground_z),
                      (span, span, ground_z), (-span, span, ground_z)], [], [(0, 1, 2, 3)])
    mesh.materials.append(materials["ground"])
    ground = bpy.data.objects.new("STUDIO_GROUND | No contact simulation", mesh)
    collection.objects.link(ground)
    ground["presentation_only"] = True
    for name, delta, energy, size, color in (
        ("Key", (-0.35, -0.7, 1.0), 12, 0.8, (0.86, 0.93, 1)),
        ("Fill", (0.9, -0.1, 0.6), 8, 0.65, (0.62, 0.81, 1)),
        ("Rim", (-0.35, 0.65, 0.9), 20, 0.6, (1, 0.81, 0.56)),
    ):
        light = bpy.data.lights.new(f"{scene.name} | {name}", "AREA")
        light.energy, light.shape, light.size, light.color = (
            energy * light_scale ** 2, "DISK", size * light_scale, color)
        obj = bpy.data.objects.new(light.name, light)
        collection.objects.link(obj)
        obj.location = Vector(center) + Vector(delta) * light_scale
        obj.rotation_euler = (Vector(center) - obj.location).to_track_quat("-Z", "Y").to_euler()
    return collection


def camera(scene, collection, target, width, direction=VIEW_DIRECTION):
    data = bpy.data.cameras.new(f"{scene.name} | Orthographic")
    obj = bpy.data.objects.new(data.name, data)
    collection.objects.link(obj)
    data.type, data.ortho_scale = "ORTHO", width
    data.clip_start, data.clip_end = 0.003, 30
    obj.location = Vector(target) + Vector(direction).normalized() * 2.5
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = obj
    return obj


def text(scene, collection, body, x, y, pixels, mat, align="LEFT"):
    data = bpy.data.curves.new(f"LABEL | {body[:55]}", "FONT")
    data.body, data.size, data.align_x = body, pixels / WIDTH * scene.camera.data.ortho_scale, align
    data.space_character = 1.05
    data.materials.append(mat)
    obj = bpy.data.objects.new(data.name, data)
    collection.objects.link(obj)
    obj.parent = scene.camera
    width = scene.camera.data.ortho_scale
    obj.location = ((x / WIDTH - 0.5) * width,
                    (0.5 - y / HEIGHT) * width * HEIGHT / WIDTH, -0.02)
    obj["presentation_only"] = True
    return obj


def arrow(scene, collection, start, end, materials):
    width = scene.camera.data.ortho_scale
    delta = Vector((end[0] - start[0], end[1] - start[1]))
    if delta.length < 1:
        return
    direction = delta.normalized()
    normal = Vector((-direction.y, direction.x))
    tip = Vector(end)
    paths = [[start, end],
             [tip - direction * 8 + normal * 4, tip, tip - direction * 8 - normal * 4]]
    curve = bpy.data.curves.new("ANNOTATION | Leader arrow", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth, curve.bevel_resolution = width / WIDTH * 0.7, 0
    curve.materials.append(materials["muted"])
    for path in paths:
        spline = curve.splines.new("POLY")
        spline.points.add(len(path) - 1)
        for point, xy in zip(spline.points, path):
            point.co = ((xy[0] / WIDTH - 0.5) * width,
                        (0.5 - xy[1] / HEIGHT) * width * HEIGHT / WIDTH, -0.021, 1)
    obj = bpy.data.objects.new(curve.name, curve)
    collection.objects.link(obj)
    obj.parent = scene.camera
    obj["presentation_only"] = True


def project(scene, point):
    position = world_to_camera_view(scene, scene.camera, Vector(point))
    return position.x * WIDTH, (1 - position.y) * HEIGHT


def common_labels(scene, collection, materials, title, subtitle):
    text(scene, collection, "VER.3  /  FIRST-CUT MECHANICAL CONCEPT",
         40, 35, 16, materials["cyan"])
    text(scene, collection, title, 40, 78, 31, materials["text"])
    text(scene, collection, subtitle, 41, 111, 17, materials["muted"])
    text(scene, collection, OPERATION_NOTICE, 40, 663, 20, materials["warning"])
    text(scene, collection, WIND_NOTICE, 40, 692, 17, materials["muted"])


def hide_groups(scene, collection, key, groups):
    layer = scene.view_layers[0].layer_collection.children[collection.name]
    for group in groups:
        layer.children[f"{key} | {GROUP_NAMES[group]}"].exclude = True


def create_overview(designs, manifests, materials):
    scene = bpy.data.scenes.new("00 | ALL THREE - BAKED OPERATION")
    configure_scene(scene)
    for collection, _, _ in designs.values():
        scene.collection.children.link(collection)
    center = BASE_CENTER + Vector((0, 0, 0.037))
    setting = studio(scene, materials, center)
    camera(scene, setting, center, 1.56)
    common_labels(scene, setting, materials, "ONE MECHANISM. THREE FIRST-CUT DESIGNS.",
                  "Exact FreeCAD solids  /  528 instances each  /  six legs, three open crank bays")
    for index, key in enumerate("ABC"):
        x = (index - 1) * 0.46 / 1.56 * WIDTH + WIDTH / 2
        gears = manifests[key]["design"]["gears"]
        mass = sum(manifests[key]["parts"][i["part_id"]]["mass_g"]
                   for i in manifests[key]["instances"]) / 1000
        text(scene, setting, f"{key}  /  {DESIGN_NAMES[key]}", x, 202, 20,
             materials[f"{key}_label"], "CENTER")
        text(scene, setting, f"{gears['pinion_teeth']}:{gears['wheel_teeth']}   m{gears['module']:g}"
             f"   |   nominal {mass:.2f} kg", x, 562, 18, materials["text"], "CENTER")
    text(scene, setting, "B: 3:1 input-torque comparison", 41, 604, 16, materials["muted"])
    text(scene, setting, C_NOTICE, 41, 630, 16, materials["muted"])
    scene.timeline_markers.new("START - prescribed crank cycle", frame=1)
    scene.timeline_markers.new("Half crank revolution", frame=73)
    scene.timeline_markers.new("CLOSED - one full crank revolution", frame=145)
    return scene


def create_hero(key, design, manifest, materials):
    collection, _, _ = design
    scene = bpy.data.scenes.new(f"0{ord(key) - ord('A') + 1} | {key} - ASSEMBLED")
    configure_scene(scene)
    scene.collection.children.link(collection)
    model_center = BASE_CENTER + OFFSETS[key]
    target = model_center - VIEW_RIGHT * 0.140 + Vector((0, 0, 0.010))
    setting = studio(scene, materials, model_center)
    camera(scene, setting, target, 0.90)
    gears = manifest["design"]["gears"]
    mass = sum(manifest["parts"][i["part_id"]]["mass_g"] for i in manifest["instances"]) / 1000
    common_labels(scene, setting, materials, f"{key}  /  {DESIGN_NAMES[key]}",
                  f"{gears['pinion_teeth']}:{gears['wheel_teeth']} teeth  |  "
                  f"module {gears['module']:g}  |  one spur stage")
    text(scene, setting, f"{mass:.2f} kg", 44, 232, 36, materials[f"{key}_label"])
    text(scene, setting, "NOMINAL ALL-SOLID MASS", 45, 259, 13, materials["muted"])
    text(scene, setting, "CAD + assumed/catalog hardware", 45, 281, 13, materials["muted"])
    lines = ["6 mirrored Jansen legs", "3 open crank bays",
             "Positive REX shafts + metal hubs", "Removable tray + PETG window"]
    for index, line in enumerate(lines):
        text(scene, setting, line, 45, 354 + index * 30, 16, materials["text"])
    text(scene, setting, "Crank phases: 0 / 180 / 0 deg", 45, 515, 16, materials["muted"])
    if key == "C":
        text(scene, setting, C_NOTICE, 41, 629, 16, materials["cyan"])
    else:
        text(scene, setting, "Purchased hub flexures and bearing internals are simplified.",
             41, 629, 15, materials["muted"])
    return scene


def create_drive(design, materials):
    collection, _, _ = design
    scene = bpy.data.scenes.new("04 | A - DRIVETRAIN CUTAWAY")
    configure_scene(scene)
    scene.collection.children.link(collection)
    center = OFFSETS["A"] + Vector((0.245, 0, 0.197))
    setting = studio(scene, materials, center)
    direction = Vector((1, -0.38, 0.28)).normalized()
    right = Vector((-direction.y, direction.x, 0)).normalized()
    camera(scene, setting, center - right * 0.10 + Vector((0, 0, -0.007)),
           0.76, direction)
    hide_groups(scene, collection, "A", ("guard", "guard_lid"))
    common_labels(scene, setting, materials, "A  /  RIGHT-END DRIVETRAIN",
                  "CUTAWAY / COVER REMOVED  |  actual guard tray and window hidden")
    for index, line in enumerate((
        "27:54 teeth  /  module 2.5",
        "One external spur stage",
        "Input: -2 turns / crank turn",
        "Output: +1 crank turn",
        "Metal REX hubs; no friction-drive claim",
    )):
        text(scene, setting, line, 42, 210 + index * 31, 16, materials["text"])
    text(scene, setting, "No independent swing animation:", 42, 409, 15, materials["cyan"])
    text(scene, setting, "every pose comes from core.py.", 42, 434, 15, materials["cyan"])
    text(scene, setting, "The same motion is baked into all fasteners, shafts and links.",
         42, 627, 15, materials["muted"])
    return scene


def smoothstep(frame, start, end):
    fraction = max(0, min(1, (frame - start) / (end - start)))
    return fraction * fraction * (3 - 2 * fraction)


def exploded_offset(instance, frame):
    """Illustrative group separation only; not a physical insertion trajectory."""
    group, part_id = instance["group"], instance["part_id"]
    if group == "guard_lid":
        return Vector((0.24, 0, 0.075)) * smoothstep(frame, 5, 29)
    if group == "guard":
        return Vector((0.17, 0, 0.020)) * smoothstep(frame, 25, 49)
    if group == "drivetrain":
        return Vector((0.075, 0, 0.085)) * smoothstep(frame, 37, 65)
    if group == "rotor":
        return Vector((-0.015, 0, 0.165)) * smoothstep(frame, 37, 65)
    spread = smoothstep(frame, 65, 101)
    x = instance["transform"][0][3]
    if group == "frame":
        if part_id in ("H_PIVOT_ROD6", "H_TIE_ROD"):
            return Vector((0, 0.115, 0.075)) * spread
        return Vector(((x - 126) * 0.00042, 0, 0.045)) * spread
    if group in ("legs", "crank", "pivot"):
        bay = instance.get("motion", {}).get("bay")
        if bay is None:
            bay = min((0, 84, 168), key=lambda value: abs(x - value - 31))
        return Vector(((bay - 84) * 0.00062, (bay - 84) * 0.00022, -0.005)) * spread
    if group == "hardware":
        return Vector((0, 0.115, 0.075)) * spread
    raise ValueError(f"Unclassified exploded group: {group}")


def copy_illustration(instance, original, collection, root, prefix):
    obj = bpy.data.objects.new(f"{prefix}::{instance['name']}", original.data)
    collection.objects.link(obj)
    obj.parent = root
    obj.rotation_mode = "QUATERNION"
    obj.matrix_local = matrix_metres(instance["transform"])
    obj["source_design"] = original["design_id"]
    obj["instance_id"] = instance["name"]
    obj["part_id"] = instance["part_id"]
    obj["visualization_copy"] = True
    obj["note"] = "Same unmodified CAD mesh; illustrative position only"
    return obj


def create_exploded(design, manifest, materials):
    _, _, canonical = design
    scene = bpy.data.scenes.new("06 | A - ILLUSTRATIVE EXPLODED")
    configure_scene(scene, EXPLODED_FRAMES)
    collection = add_collection(scene.collection, "EXPLAIN | A - exact mesh instances")
    root = bpy.data.objects.new("EXPLAIN::STATIC_ROOT", None)
    collection.objects.link(root)
    for instance in manifest["instances"]:
        obj = copy_illustration(instance, canonical[instance["name"]], collection, root, "EXPLODED")
        initial = matrix_metres(instance["transform"]).translation
        positions = [tuple(initial + exploded_offset(instance, frame))
                     for frame in range(1, EXPLODED_FRAMES + 1)]
        add_action(obj, {"location": positions}, f"ILLUSTRATION::{instance['name']}")
    center = Vector((0.23, 0, 0.225))
    setting = studio(scene, materials, center)
    camera(scene, setting, center + Vector((0, 0, 0.055)), 1.37)
    text(scene, setting, "VER.3  /  FIRST-CUT MECHANICAL CONCEPT",
         40, 35, 16, materials["cyan"])
    text(scene, setting, "A  /  EXPLODED GROUP ILLUSTRATION", 40, 78, 31, materials["text"])
    text(scene, setting, "ILLUSTRATIVE OFFSETS / NOT A VALIDATED PHYSICAL INSERTION PATH",
         40, 111, 17, materials["warning"])
    for index, body in enumerate(("01  WINDOW / TRAY", "02  GEARS / ROTOR", "03  FRAME / CRANK BAYS")):
        text(scene, setting, body, 44 + 412 * index, 144, 19, materials["cyan"])
    text(scene, setting, "Normal kinematics PAUSED. Group motion does not prove clearance or assembly feasibility.",
         40, 627, 17, materials["text"])
    text(scene, setting, OPERATION_NOTICE, 40, 662, 19, materials["warning"])
    text(scene, setting, WIND_NOTICE, 40, 692, 17, materials["muted"])
    scene["explosion_limitations"] = "ILLUSTRATIVE ONLY; no collision/insertion-path validation"
    for frame, label in ((1, "ASSEMBLED / crank paused"),
                         (29, "01 WINDOW"), (49, "01 TRAY"),
                         (65, "02 GEARS AND ROTOR"), (101, "03 FRAME AND CRANK GROUPS"),
                         (121, "HOLD - illustration, not an insertion path")):
        scene.timeline_markers.new(label, frame=frame)
    return scene


def create_connection(design, manifest, materials):
    _, _, canonical = design
    scene = bpy.data.scenes.new("05 | A - REX CONNECTION INSPECTION")
    configure_scene(scene)
    collection = add_collection(scene.collection, "EXPLAIN | Actual gear / hub / shaft meshes")
    root = bpy.data.objects.new("INSPECT::STATIC_ROOT", None)
    collection.objects.link(root)
    for instance in manifest["instances"]:
        part_id, group = instance["part_id"], instance["group"]
        is_output_drive = (group == "drivetrain" and
                           instance.get("motion", {}).get("speed") == 1)
        if not is_output_drive and part_id != "H_shaft_8_85p5":
            continue
        obj = copy_illustration(instance, canonical[instance["name"]], collection, root, "INSPECT")
        if group == "drivetrain":
            if part_id == "H_REX_HUB":
                obj.location.x += 0.18
            elif part_id.startswith("P_GEAR"):
                obj.location.x += 0.10
            else:
                obj.location.x += 0.065
    center = Vector((0.35, 0, 0.150))
    setting = studio(scene, materials, center)
    direction = Vector((0.78, -0.84, 0.37)).normalized()
    camera(scene, setting, center, 0.56, direction)
    common_labels(scene, setting, materials, "POSITIVE REX / HUB / GEAR CONNECTION",
                  "CUTAWAY / AXIALLY SEPARATED  |  output connection only; surrounding assemblies omitted")
    text(scene, setting, "Actual CAD meshes only. Metal hub flexures and fastener threads remain simplified.",
         40, 603, 16, materials["text"])
    text(scene, setting, "Offsets explain the interface; they do not specify a feasible physical assembly path.",
         40, 628, 16, materials["muted"])
    scene.view_layers[0].update()
    for body, xy, world in (
        ("POSITIVE REX SHAFT", (55, 198), (0.298, 0, 0.150)),
        ("PRINTED INVOLUTE GEAR", (55, 545), (0.376, -0.058, 0.183)),
        ("METAL REX HUB", (940, 240), (0.468, -0.004, 0.154)),
    ):
        text(scene, setting, body, *xy, 17, materials["cyan"])
        arrow(scene, setting, (xy[0] + 40, xy[1] + 12), project(scene, world), materials)
    scene["explosion_limitations"] = "AXIAL OFFSETS ONLY; not a physical insertion-path study"
    return scene


def create_frame_inspection(designs, manifests, materials):
    scene = bpy.data.scenes.new("07 | A-C - ACTUAL FRAME COMPARISON")
    configure_scene(scene)
    collection = add_collection(scene.collection, "EXPLAIN | Isolated original frame solids")
    direction = Vector((1, -0.15, 0.14)).normalized()
    right = Vector((-direction.y, direction.x, 0)).normalized()
    for index, key in enumerate("AC"):
        root = bpy.data.objects.new(f"FRAME_INSPECT::{key}::PRESENTATION_ROOT", None)
        collection.objects.link(root)
        root.location = right * ((index * 2 - 1) * 0.115)
        instance = next(item for item in manifests[key]["instances"]
                        if item["part_id"] == "P_FRAME_TOWER_LOC")
        copy_illustration(instance, designs[key][2][instance["name"]],
                          collection, root, f"FRAME_INSPECT::{key}")
    center = Vector((0, 0, 0.196))
    setting = studio(scene, materials, center)
    camera(scene, setting, center, 0.58, direction)
    common_labels(scene, setting, materials, "ACTUAL CAD FRAME / A VERSUS C",
                  "ISOLATED PARTS  |  same scale, unmodified FreeCAD meshes; surrounding hardware omitted")
    for key, x, title in (("A", 386, "A / SOLID BASELINE"),
                          ("C", 894, "C / GENERATED RIBS")):
        text(scene, setting, title, x, 177, 22, materials[f"{key}_label"], "CENTER")
        text(scene, setting, "P_FRAME_TOWER_LOC", x, 548, 16, materials["muted"], "CENTER")
    text(scene, setting, C_NOTICE, 40, 600, 20, materials["cyan"])
    text(scene, setting, "The generated ribs are source CAD geometry, not a rendering effect or a continuum-FEA claim.",
         40, 628, 16, materials["text"])
    return scene


def build():
    if not bpy.app.background:
        raise RuntimeError("Refusing to operate in a live Blender scene. Use blender -b.")
    manifests, libraries, fingerprints = read_inputs()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    materials = create_materials()
    designs = {key: build_design(key, manifests[key], libraries[key], materials) for key in "ABC"}
    overview = create_overview(designs, manifests, materials)
    for key in "ABC":
        create_hero(key, designs[key], manifests[key], materials)
    create_drive(designs["A"], materials)
    create_connection(designs["A"], manifests["A"], materials)
    create_exploded(designs["A"], manifests["A"], materials)
    create_frame_inspection(designs, manifests, materials)
    for key in "ABC":
        embedded = bpy.data.texts.new(f"SOURCE | assembly_{key}.json")
        embedded.write(json.dumps(manifests[key], ensure_ascii=False, indent=2))
    record = bpy.data.texts.new("SOURCE | fingerprints.json")
    record.write(json.dumps(fingerprints, indent=2))
    config_snapshot = bpy.data.texts.new("SOURCE | kinematic_config.json")
    config_snapshot.write(json.dumps(
        {field: CONFIG[field] for field in ("linkage", "hardware")}, indent=2))
    notes = bpy.data.texts.new("READ ME | FIRST-CUT VISUALIZATION")
    notes.write(
        "FIRST-CUT ENGINEERING CONCEPT. NOT PHYSICAL VALIDATION.\n\n"
        + OPERATION_NOTICE + "\n" + WIND_NOTICE + "\n"
        + "B: 3:1 input-torque comparison.\n" + C_NOTICE + "\n\n"
        "Scenes 00-04: 145 integer frames, 24 fps, one complete prescribed crank revolution.\n"
        "A/C input shafts: -2 revolutions. B input shaft: -3 revolutions.\n"
        "All 528 instances per design come from the supplied CAD solids and manifests.\n"
        "Canonical transforms are in millimetres; Blender coordinates are metres.\n"
        "The three root offsets are static presentation layout, not locomotion.\n"
        "Only moving transform channels are baked. No handlers, drivers, or script trust.\n"
        "Scene 04 hides both guard collections and explicitly labels the cutaway.\n"
        "Scene 05 reuses real meshes with explanatory axial offsets.\n"
        "Scene 06 is a 121-frame staged exploded illustration with kinematics paused.\n"
        "Scene 07 compares the actual isolated A/C tower frame meshes at equal scale.\n"
        "Exploded motions are NOT physical insertion paths and prove no clearances.\n"
        "Hardware envelopes retain the source CAD's simplified internals/flexures.\n"
        "Nominal mass is all-solid CAD plus assumed/catalog hardware, not a weigh-in.\n"
        "Ground is a studio background below the mechanism, not a contact solver.\n\n"
        "Saved render output is relative (//media/). Meshes, fonts and animation are self-contained.\n"
        "Regenerate via scripts/ver3/render_blender.py in isolated headless Blender.\n")
    for scene in bpy.data.scenes:
        bpy.context.window.scene = scene
        scene.frame_set(1)
    bpy.context.window.scene = overview
    empty = bpy.data.scenes.get("Scene")
    if empty is not None and empty != overview:
        bpy.data.scenes.remove(empty)
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.region_3d.view_perspective = "CAMERA"
                area.spaces.active.shading.color_type = "MATERIAL"
                area.spaces.active.overlay.show_extras = False
    prepare_native_paths()
    bpy.context.preferences.filepaths.save_version = 0
    NATIVE.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(NATIVE), compress=True)
    log(f"Native saved: {NATIVE} ({NATIVE.stat().st_size / 1_000_000:.2f} MB)")


def open_native():
    if not NATIVE.is_file():
        raise FileNotFoundError(f"Build the native file first: {NATIVE}")
    bpy.ops.wm.open_mainfile(filepath=str(NATIVE), use_scripts=False)


def prepare_native_paths():
    for scene in bpy.data.scenes:
        scene.render.filepath = PORTABLE_RENDER_PATH
        scene.render.threads_mode = "FIXED"
        scene.render.threads = 4
    for screen in bpy.data.screens:
        for area in screen.areas:
            for space in area.spaces:
                if space.type == "FILE_BROWSER" and space.params:
                    space.params.directory = b"//"


def validate_native_portability():
    external_paths = [path for path in bpy.utils.blend_paths(absolute=False, packed=False)
                      if path and path != "<builtin>"]
    if external_paths or bpy.data.libraries:
        raise AssertionError(f"Native file has external dependencies: {external_paths}")
    if any(block.filepath for block in bpy.data.texts):
        raise AssertionError("Native text blocks must be embedded, not external files")
    for font in bpy.data.fonts:
        if font.filepath != "<builtin>" and not font.packed_file:
            raise AssertionError(f"Native file needs an external font: {font.name}")
    browser_paths = []
    for screen in bpy.data.screens:
        for area in screen.areas:
            for space in area.spaces:
                if space.type == "FILE_BROWSER" and space.params:
                    directory = space.params.directory.decode("utf-8")
                    if directory and not directory.startswith("//"):
                        raise AssertionError(f"Saved file-browser directory is not relative: {screen.name}")
                    browser_paths.append(directory)
    previous_scene = bpy.context.window.scene
    cameras = {}
    for scene in sorted(bpy.data.scenes, key=lambda item: item.name):
        bpy.context.window.scene = scene
        scene.frame_set(1)
        if scene.render.filepath != PORTABLE_RENDER_PATH:
            raise AssertionError(f"Saved render output is not portable: {scene.name}")
        cam = scene.camera
        if cam is None or scene.objects.get(cam.name) != cam or cam.type != "CAMERA":
            raise AssertionError(f"Missing saved scene camera: {scene.name}")
        if cam.data.type != "ORTHO" or cam.data.ortho_scale <= 0:
            raise AssertionError(f"Invalid saved camera projection: {scene.name}")
        if not np.isfinite(np.asarray(cam.matrix_world)).all():
            raise AssertionError(f"Invalid saved camera transform: {scene.name}")
        cameras[scene.name] = {
            "camera": cam.name,
            "world_matrix": [list(row) for row in cam.matrix_world],
            "orthographic_width_m": cam.data.ortho_scale,
            "frame_range": [scene.frame_start, scene.frame_end],
            "render_filepath": scene.render.filepath,
            "render_threads": scene.render.threads,
        }
    bpy.context.window.scene = previous_scene
    return {
        "external_dependencies": external_paths,
        "linked_libraries": len(bpy.data.libraries),
        "file_browser_directories": browser_paths,
        "saved_cameras": cameras,
    }


def verify_native_inputs():
    manifests, libraries, fingerprints = read_inputs()
    embedded = json.loads(bpy.data.texts["SOURCE | fingerprints.json"].as_string())
    critical_embedded = {key: value for key, value in embedded.items()
                         if key != "design_config_sha256"}
    critical_current = {key: value for key, value in fingerprints.items()
                        if key != "design_config_sha256"}
    changed = sorted(key for key in critical_embedded.keys() | critical_current.keys()
                     if critical_embedded.get(key) != critical_current.get(key))
    if changed:
        raise RuntimeError(
            f"Canonical inputs changed since the blend was built: {', '.join(changed)}. "
            "After CAD regeneration finishes, run --phase build before rendering or validation.")
    unrelated_config_change = embedded["design_config_sha256"] != fingerprints["design_config_sha256"]
    if unrelated_config_change:
        log("Non-kinematic design.json fields changed; meshes, manifests, core and motion inputs "
            "are unchanged.")
    return manifests, libraries, fingerprints, embedded, unrelated_config_change


def find_scene(prefix):
    matches = [scene for scene in bpy.data.scenes if scene.name.startswith(prefix)]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one scene beginning with {prefix!r}")
    return matches[0]


def render_image(scene, path, frame=1, video=False, samples=64):
    bpy.context.window.scene = scene
    scene.frame_set(frame)
    scene.render.resolution_x, scene.render.resolution_y = ((960, 540) if video else (WIDTH, HEIGHT))
    scene.eevee.taa_render_samples = samples
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True, scene=scene.name)


def stills(samples):
    verify_native_inputs()
    MEDIA.mkdir(parents=True, exist_ok=True)
    outputs = [
        ("01 |", "hero_A.png", 1),
        ("02 |", "hero_B.png", 1),
        ("03 |", "hero_C.png", 1),
        ("00 |", "comparison.png", 1),
        ("04 |", "drivetrain_detail.png", 1),
        ("05 |", "rex_connection.png", 1),
        ("06 |", "exploded_A.png", 121),
        ("07 |", "frame_AC_detail.png", 1),
    ]
    for prefix, name, frame in outputs:
        render_image(find_scene(prefix), MEDIA / name, frame, samples=samples)
        log(f"Still ready: {name}")
    verify_native_inputs()


def run_command(arguments):
    subprocess.run([str(value) for value in arguments], check=True)


def encode_sequence(directory, destination, *, frame_count=None, comment=None):
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-framerate", FPS, "-start_number", "1", "-i", directory / "%04d.png",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-threads", "4",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-metadata", f"comment={comment or (OPERATION_NOTICE + '. ' + WIND_NOTICE)}",
        "-an",
    ]
    if frame_count is not None:
        command += ["-frames:v", frame_count]
    run_command(command + [destination])


def remove_owned_frames(directory, count):
    for frame in range(1, count + 1):
        path = directory / f"{frame:04d}.png"
        if path.is_file():
            path.unlink()
    if directory.exists() and not any(directory.iterdir()):
        directory.rmdir()


def video(work_dir, samples, keep_frames):
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required; no automatic installation is attempted")
    verify_native_inputs()
    MEDIA.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    segments = [
        ("00 |", "operation_overview", FRAMES),
        ("04 |", "operation_drive", FRAMES),
        ("06 |", "exploded", EXPLODED_FRAMES),
    ]
    encoded = []
    for prefix, name, count in segments:
        directory = work_dir / f"{name}-{sha256(NATIVE)[:12]}-{samples}"
        directory.mkdir(exist_ok=True)
        scene = find_scene(prefix)
        for frame in range(1, count + 1):
            path = directory / f"{frame:04d}.png"
            if not path.is_file():
                render_image(scene, path, frame, video=True, samples=samples)
            if frame == 1 or frame % 24 == 0 or frame == count:
                log(f"{name}: {frame}/{count}")
        verify_native_inputs()
        destination = (MEDIA / "exploded.mp4" if name == "exploded"
                       else work_dir / f"{name}.mp4")
        encode_sequence(directory, destination)
        encoded.append(destination)
        if not keep_frames:
            remove_owned_frames(directory, count)
    concatenate = work_dir / "operation_segments.txt"
    concatenate.write_text("\n".join(f"file '{path.as_posix()}'" for path in encoded[:2]) + "\n")
    run_command([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat",
        "-safe", "0", "-i", concatenate, "-c", "copy", "-movflags", "+faststart",
        MEDIA / "operation.mp4",
    ])
    run_command([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", encoded[0],
        "-vf", "fps=12,scale=600:-1:flags=lanczos,split[s0][s1];"
        "[s0]palettegen=max_colors=128:stats_mode=diff[p];"
        "[s1][p]paletteuse=dither=bayer:bayer_scale=3",
        "-loop", "0", MEDIA / "preview.gif",
    ])
    if (MEDIA / "preview.gif").stat().st_size > 6_000_000:
        raise RuntimeError("GIF exceeds the requested 6 MB limit")
    if not keep_frames:
        for path in encoded[:2] + [concatenate]:
            path.unlink()
    log("H.264 operation/exploded films and <=6 MB GIF ready")


def curves_for(obj):
    animation = obj.animation_data
    if animation is None or animation.action is None:
        return []
    result = []
    for layer in animation.action.layers:
        for strip in layer.strips:
            bag = strip.channelbag(animation.action_slot)
            if bag is not None:
                result.extend(bag.fcurves)
    return result


def validate():
    manifests, libraries, fingerprints, embedded, unrelated_config_change = verify_native_inputs()
    required_media = [
        "hero_A.png", "hero_B.png", "hero_C.png", "comparison.png",
        "drivetrain_detail.png", "rex_connection.png", "exploded_A.png",
        "frame_AC_detail.png", "operation.mp4", "exploded.mp4", "preview.gif",
    ]
    missing = [name for name in required_media if not (MEDIA / name).is_file()]
    if missing:
        raise RuntimeError(f"Visualization package incomplete; generate missing media: {missing}")
    if bpy.app.handlers.frame_change_pre or bpy.app.handlers.frame_change_post:
        raise AssertionError("Animation unexpectedly depends on registered frame handlers")
    if any(text_block.use_module for text_block in bpy.data.texts):
        raise AssertionError("Blend unexpectedly contains an automatic Python text module")
    if any(obj.animation_data and obj.animation_data.drivers for obj in bpy.data.objects):
        raise AssertionError("Blend unexpectedly contains animation drivers")
    canonical = [obj for obj in bpy.data.objects if obj.get("canonical_instance")]
    report = {
        "validated_utc": datetime.now(timezone.utc).isoformat(),
        "blender_version": bpy.app.version_string,
        "reopened_with_scripts_disabled": True,
        "python_frame_handlers": 0,
        "automatic_python_text_modules": 0,
        "animation_drivers": 0,
        "renderer_sha256": sha256(Path(__file__)),
        "source_fingerprints": fingerprints,
        "build_source_fingerprints": embedded,
        "non_kinematic_config_changed_since_build": unrelated_config_change,
        "canonical_instances": len(canonical),
        "operation_frames": [1, FRAMES],
        "fps": FPS,
        "exploded_frames": [1, EXPLODED_FRAMES],
        "limitations": [OPERATION_NOTICE, WIND_NOTICE, C_NOTICE,
                        "Exploded offsets are illustrative, not a physical insertion path",
                        "Hardware internals and flexures retain source simplifications"],
        "designs": {},
        "media_complete": True,
        "native_portability": validate_native_portability(),
    }
    for key in "ABC":
        manifest, library = manifests[key], libraries[key]
        objects = {obj["instance_id"]: obj for obj in canonical if obj["design_id"] == key}
        if set(objects) != {instance["name"] for instance in manifest["instances"]}:
            raise AssertionError(f"{key}: canonical instance IDs differ")
        max_vertex_error = 0
        for part_id, geometry in library.items():
            mesh = bpy.data.meshes[f"{key}::CAD::{part_id}"]
            coordinates = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
            mesh.vertices.foreach_get("co", coordinates)
            actual = coordinates.reshape((-1, 3)) / MM
            expected = np.asarray(geometry["vertices"])
            if actual.shape != expected.shape:
                raise AssertionError(f"{key}/{part_id}: vertex count differs")
            error = float(np.max(np.abs(actual - expected)))
            max_vertex_error = max(error, max_vertex_error)
            faces = [list(polygon.vertices) for polygon in mesh.polygons]
            if faces != geometry["triangles"] or error > 0.0001:
                raise AssertionError(f"{key}/{part_id}: source mesh changed")
        moving = 0
        curves = 0
        for instance in manifest["instances"]:
            obj = objects[instance["name"]]
            if obj["part_id"] != instance["part_id"] or obj.modifiers:
                raise AssertionError(f"{obj.name}: changed identity or geometric modifier")
            if obj.animation_data and obj.animation_data.drivers:
                raise AssertionError(f"{obj.name}: scripted driver found")
            animation_curves = curves_for(obj)
            if animation_curves:
                moving += 1
                for curve in animation_curves:
                    if len(curve.keyframe_points) != FRAMES:
                        raise AssertionError(f"{obj.name}: incomplete per-frame bake")
                    if tuple(curve.range()) != (1, FRAMES):
                        raise AssertionError(f"{obj.name}: invalid baked range")
                curves += len(animation_curves)
        root = bpy.data.objects[f"{key}::PRESENTATION_OFFSET_ONLY"]
        if root.animation_data:
            raise AssertionError(f"{key}: presentation root must not animate locomotion")
        report["designs"][key] = {
            "instances": len(objects), "mesh_datablocks": len(library),
            "moving_objects": moving, "baked_transform_channels": curves,
            "max_vertex_error_mm": max_vertex_error,
            "nominal_mass_kg": sum(manifest["parts"][i["part_id"]]["mass_g"]
                                   for i in manifest["instances"]) / 1000,
            "gear_ratio": manifest["design"]["gears"]["ratio"],
        }
    scene = find_scene("00 |")
    bpy.context.window.scene = scene
    max_position_error, max_rotation_error, first = 0, 0, {}
    for frame in range(1, FRAMES + 1):
        scene.frame_set(frame)
        theta = math.tau * (frame - 1) / (FRAMES - 1)
        for key in "ABC":
            manifest = manifests[key]
            for instance in manifest["instances"]:
                obj = bpy.data.objects[f"{key}::{instance['name']}"]
                expected = np.asarray(matrix_metres(animated_transform(instance, theta, manifest["design"])))
                actual = np.asarray(obj.matrix_local)
                position_error = float(np.max(np.abs(expected[:3, 3] - actual[:3, 3]))) / MM
                rotation_error = float(np.max(np.abs(expected[:3, :3] - actual[:3, :3])))
                max_position_error = max(max_position_error, position_error)
                max_rotation_error = max(max_rotation_error, rotation_error)
                if position_error > 0.001 or rotation_error > 0.00001:
                    raise AssertionError(f"Authoritative pose mismatch: {obj.name}, frame {frame}")
                if frame == 1:
                    first[obj.name] = actual.copy()
                if frame == FRAMES and not np.allclose(first[obj.name], actual, atol=1e-6, rtol=0):
                    raise AssertionError(f"Cycle does not close: {obj.name}")
        if frame == 1 or frame % 24 == 0 or frame == FRAMES:
            log(f"Reopened-bake verification: {frame}/{FRAMES}")
    report["max_baked_position_error_mm"] = max_position_error
    report["max_baked_rotation_matrix_error"] = max_rotation_error
    report["closed_crank_cycle"] = True
    exploded_scene = find_scene("06 |")
    bpy.context.window.scene = exploded_scene
    for frame in (1, 29, 49, 65, 101, 121):
        exploded_scene.frame_set(frame)
        for instance in manifests["A"]["instances"]:
            obj = bpy.data.objects[f"EXPLODED::{instance['name']}"]
            expected = matrix_metres(instance["transform"])
            expected.translation += exploded_offset(instance, frame)
            if not np.allclose(np.asarray(obj.matrix_local), np.asarray(expected), atol=1e-6, rtol=0):
                raise AssertionError(f"Exploded illustration mismatch: {obj.name}/{frame}")
    report["illustrative_exploded_keyframes_verified"] = True
    report["assets"] = {}
    for path in [NATIVE] + [MEDIA / name for name in required_media]:
        if path.stat().st_size >= 100_000_000:
            raise AssertionError(f"Asset exceeds 100 MB: {path}")
        item = {"bytes": path.stat().st_size, "sha256": sha256(path)}
        if path.suffix == ".png":
            with path.open("rb") as stream:
                header = stream.read(24)
            if header[:8] != b"\x89PNG\r\n\x1a\n":
                raise AssertionError(f"Invalid PNG signature: {path}")
            dimensions = struct.unpack(">II", header[16:24])
            if dimensions != (WIDTH, HEIGHT):
                raise AssertionError(f"Unexpected still dimensions: {path}: {dimensions}")
            item["dimensions"] = list(dimensions)
        if path.suffix in (".mp4", ".gif"):
            result = subprocess.run([
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration,size:stream=codec_name,width,height,nb_frames,r_frame_rate,pix_fmt",
                "-of", "json", str(path)], check=True, capture_output=True, text=True)
            item["ffprobe"] = json.loads(result.stdout)
            if path.suffix == ".mp4":
                stream = item["ffprobe"]["streams"][0]
                if stream["codec_name"] != "h264" or stream["pix_fmt"] != "yuv420p":
                    raise AssertionError(f"Not broadly playable H.264: {path}")
                expected_frames = FRAMES * 2 if path.name == "operation.mp4" else EXPLODED_FRAMES
                if ((stream["width"], stream["height"]) != (960, 540) or
                        stream["r_frame_rate"] != "24/1" or int(stream["nb_frames"]) != expected_frames):
                    raise AssertionError(f"Unexpected video dimensions, rate or frame count: {path}")
                duration = float(item["ffprobe"]["format"]["duration"])
                if abs(duration - expected_frames / FPS) > 0.01:
                    raise AssertionError(f"Unexpected video duration: {path}: {duration}")
            else:
                stream = item["ffprobe"]["streams"][0]
                if (stream["codec_name"] != "gif" or not 480 <= stream["width"] <= 640 or
                        path.stat().st_size > 6_000_000):
                    raise AssertionError(f"GIF does not meet preview limits: {path}")
            subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(path),
                            "-f", "null", "-"], check=True, capture_output=True)
            item["complete_decode_verified"] = True
        report["assets"][str(path.relative_to(ROOT))] = item
    REPORT.write_text(json.dumps(report, indent=2) + "\n")
    log(f"Validation passed: {REPORT}")
    return report


def main():
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("system", "first-cut"), default="system")
    parser.add_argument("--phase", choices=("preview", "all", "build", "stills", "motion",
                                           "walking", "video", "validate"), default="all")
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--video-samples", type=int, default=24)
    parser.add_argument("--keep-frames", action="store_true")
    args = parser.parse_args(arguments)
    if not bpy.app.background:
        raise RuntimeError("This renderer must run in isolated headless Blender")
    if args.samples < 1 or args.video_samples < 1:
        raise ValueError("Sample counts must be positive")
    if args.profile == "system":
        import render_system
        render_system.run(sys.modules[__name__], args)
        return
    if args.phase == "preview":
        parser.error("The preserved first-cut profile needs an explicit phase; no production render was started")
    started = time.monotonic()
    if args.phase in ("all", "build"):
        build()
    if args.phase != "build":
        open_native()
    if args.phase in ("all", "stills"):
        stills(args.samples)
    if args.phase in ("all", "video"):
        work_dir = args.work_dir or Path(tempfile.mkdtemp(prefix="ver3-visual-"))
        if work_dir.resolve().is_relative_to(ROOT):
            raise ValueError("Raw frame work directory must be outside the repository")
        video(work_dir, args.video_samples, args.keep_frames)
    if args.phase in ("all", "validate"):
        open_native()
        validate()
    log(f"{args.phase} complete in {time.monotonic() - started:.1f}s")


if __name__ == "__main__":
    main()
