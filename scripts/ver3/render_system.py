"""Frozen-input engineering-review assets using the exact-CAD Blender renderer.

Called by render_blender.py --profile system. First-cut assets are never opened,
overwritten, or substituted for the approved belt/distributed-stage designs.
Walking entry points read the lead's schema-1 walk_*.json and bake only its
supplied frame poses. They do not solve contact or invent body speed.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from itertools import product
import json
import math
from pathlib import Path
import struct
import subprocess
import tempfile

import bpy
from mathutils import Matrix, Vector
import numpy as np


TITLES = {
    "A": "LARGE ROTOR / FEW STAGES",
    "B": "SMALL ROTOR / HIGH REDUCTION",
    "C": "MID ROTOR / GENERATED FRAME",
}
STATUS = "ENGINEERING REVIEW FIRST CUT / CONTACT RESIDUAL TARGETS NOT MET"
LIMITATION = "Physical performance unverified. No wind-powered or no-slip walking claim."
DIAGNOSTIC_NOTICE = (
    "DIAGNOSTIC KINEMATICS / 3 mm contact target NOT met / real wind walking unverified"
)
INPUT_RPS = 2.0
EXPLODED_FRAMES = 121
WALK_VIEW_DIRECTION = (1.15, -1.15, 0.45)
WALK_TIME_SCALES = {"A": 1.0, "B": 8.0, "C": 2.0}
SOURCE_SIGNATURES = ("manifest_sha256", "meshes_sha256",
                     "core_sha256", "kinematic_config_sha256")


def locations(r):
    return (r.ROOT / "Blender/Ver.3/ver3_ABC.blend",
            r.ROOT / "docs/ver3/media",
            r.ROOT / "Blender/Ver.3/ver3_validation.json")


def walking_payload_digest(trajectory):
    encoded = json.dumps(trajectory, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_walking_trajectory(trajectory, prototype):
    required = {"schema", "prototype", "fps", "video_seconds", "physical_seconds",
                "time_scale", "input_rpm", "render_frame_end", "frames", "validation",
                "assembly_sha256", "geometry_sha256", "core_sha256"}
    if not isinstance(trajectory, dict) or not required <= trajectory.keys():
        raise ValueError("Walking trajectory is missing schema-1 required fields")
    if type(trajectory["schema"]) is not int or trajectory["schema"] != 1:
        raise ValueError("Unsupported walking trajectory schema")
    if prototype not in WALK_TIME_SCALES or trajectory["prototype"] != prototype:
        raise ValueError("Walking prototype does not match the supplied assembly")
    if type(trajectory["fps"]) is not int or trajectory["fps"] != 24:
        raise ValueError("The agreed walking contract requires fps=24")
    for field in ("video_seconds", "physical_seconds", "time_scale", "input_rpm"):
        value = trajectory[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"Walking {field} must be a finite positive number")
    if not math.isclose(trajectory["time_scale"], WALK_TIME_SCALES[prototype], abs_tol=1e-9):
        raise ValueError(f"{prototype}: walking playback multiplier differs from the agreed contract")
    if not math.isclose(trajectory["input_rpm"], 120, abs_tol=1e-9):
        raise ValueError("Walking input_rpm must be the supplied 120 RPM reference")
    if not math.isclose(trajectory["physical_seconds"],
                        trajectory["video_seconds"] * trajectory["time_scale"], abs_tol=1e-6):
        raise ValueError("Walking physical/video duration and time_scale disagree")
    if not isinstance(trajectory["validation"], dict) or not trajectory["validation"]:
        raise ValueError("Lead-provided walking residual validation is required")
    frames = trajectory["frames"]
    if not isinstance(frames, list) or len(frames) < 2:
        raise ValueError("Walking requires at least two supplied frames")
    nominal_frames = trajectory["video_seconds"] * trajectory["fps"]
    rounded_frames = round(nominal_frames)
    if (type(trajectory["render_frame_end"]) is not int or
            trajectory["render_frame_end"] != rounded_frames or
            not math.isclose(nominal_frames, rounded_frames, abs_tol=1e-6) or
            len(frames) != rounded_frames + 1):
        raise ValueError("Walking requires render_frame_end=N and exactly N+1 supplied samples")
    for index, frame in enumerate(frames, 1):
        if not isinstance(frame, dict) or not {"frame", "theta", "body_matrix", "contacts"} <= frame.keys():
            raise ValueError(f"Walking frame {index} is missing required fields")
        if type(frame["frame"]) is not int or frame["frame"] != index:
            raise ValueError("Walking frame numbers must be consecutive integers starting at 1")
        theta = frame["theta"]
        if isinstance(theta, bool) or not isinstance(theta, (int, float)) or not math.isfinite(theta):
            raise ValueError(f"Walking frame {index}: theta must be finite radians")
        rows = frame["body_matrix"]
        if (not isinstance(rows, list) or len(rows) != 4 or
                any(not isinstance(row, list) or len(row) != 4 for row in rows) or
                any(isinstance(value, bool) or not isinstance(value, (int, float))
                    for row in rows for value in row)):
            raise ValueError(f"Walking frame {index}: body_matrix must be a numeric row-major 4x4 matrix")
        matrix = np.asarray(rows, dtype=float)
        rotation = matrix[:3, :3]
        if (not np.isfinite(matrix).all() or
                not np.allclose(matrix[3], (0, 0, 0, 1), atol=1e-9, rtol=0) or
                not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-6, rtol=0) or
                not math.isclose(float(np.linalg.det(rotation)), 1, abs_tol=1e-6)):
            raise ValueError(f"Walking frame {index}: body_matrix must be rigid, without scaling, shear or reflection")
        contacts = frame["contacts"]
        if (not isinstance(contacts, list) or
                any(type(leg) is not int or leg < 0 for leg in contacts) or len(contacts) != len(set(contacts))):
            raise ValueError(f"Walking frame {index}: contacts must be distinct nonnegative leg indices")
    walking_payload_digest(trajectory)
    return trajectory


def read_walking_trajectory(r, prototype):
    if prototype not in WALK_TIME_SCALES:
        raise ValueError(f"Unknown walking prototype: {prototype}")
    path = r.ROOT / f"docs/ver3/walk_{prototype}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Canonical walking trajectory has not been supplied: {path}")
    raw = path.read_bytes()
    trajectory = validate_walking_trajectory(json.loads(raw), prototype)
    _, _, fingerprints = r.read_inputs(prototype, profile="system")
    for field, expected in (
        ("assembly_sha256", fingerprints[prototype]["manifest_sha256"]),
        ("geometry_sha256", fingerprints[prototype]["meshes_sha256"]),
        ("core_sha256", fingerprints["core_sha256"]),
    ):
        if trajectory[field] != expected:
            raise RuntimeError(f"{prototype}: walking {field} does not match the frozen mechanical input")
    if path.read_bytes() != raw:
        raise RuntimeError("Walking trajectory changed during loading; no substitute motion will be generated")
    provenance = {
        **fingerprints[prototype],
        "core_sha256": fingerprints["core_sha256"],
        "kinematic_config_sha256": fingerprints["kinematic_config_sha256"],
        "trajectory_path": str(path.relative_to(r.ROOT)),
        "trajectory_sha256": hashlib.sha256(raw).hexdigest(),
        "payload_sha256": walking_payload_digest(trajectory),
    }
    return trajectory, provenance


def walking_world_matrix_mm(r, instance, frame, design):
    local = np.asarray(r.animated_transform(instance, frame["theta"], design), dtype=float)
    return np.asarray(frame["body_matrix"], dtype=float) @ local


def walking_axis(instance):
    motion = instance.get("motion", {})
    if motion.get("type") not in ("shaft", "crank"):
        return None
    center = motion.get("center", (0, 0))
    return float(center[0]), float(center[1]), float(motion.get("speed", 1))


def bake_walking_body(r, collection, prototype, frames):
    body = bpy.data.objects.new(f"WALK::{prototype}::BODY_POSE", None)
    collection.objects.link(body)
    body.rotation_mode = "QUATERNION"
    body.empty_display_size = 0.015
    body["walking_body"] = True
    body["design_id"] = prototype
    body["pose_source"] = "Unmodified canonical body_matrix at every supplied frame"
    positions, quaternions, previous = [], [], None
    for frame in frames:
        matrix = r.matrix_metres(frame["body_matrix"])
        if frame["frame"] == 1:
            body.matrix_basis = matrix
        quaternion = matrix.to_quaternion()
        if previous is not None and quaternion.dot(previous) < 0:
            quaternion.negate()
        previous = quaternion.copy()
        positions.append(tuple(matrix.translation))
        quaternions.append(tuple(quaternion))
    r.add_action(body, {"location": positions, "rotation_quaternion": quaternions},
                 f"WALKING::{prototype}::BODY_POSE")
    return body


def bake_walking_axis(r, collection, prototype, body, axis, frames, index):
    center_y, center_z, speed = axis
    pivot = bpy.data.objects.new(f"WALK::{prototype}::AXIS_{index:02d}", None)
    collection.objects.link(pivot)
    pivot.parent = body
    pivot.rotation_mode = "XYZ"
    pivot.empty_display_size = 0.01
    pivot.location = Vector((0, center_y, center_z + r.CONFIG["linkage"]["crank_height"])) * r.MM
    pivot.rotation_euler = (speed * frames[0]["theta"], 0, 0)
    pivot["walking_axis"] = True
    pivot["design_id"] = prototype
    pivot["axis_center_mm"] = [center_y, center_z]
    pivot["relative_speed"] = speed
    pivot["angle_source"] = "Unwrapped motion.speed * supplied crank theta; radians about body X"
    angles = [(speed * frame["theta"], 0, 0) for frame in frames]
    r.add_action(pivot, {"rotation_euler": angles}, f"WALKING::{prototype}::AXIS_{index:02d}")
    return pivot


def bake_walking_collection(r, manifest, source_objects, trajectory, provenance):
    """Bake body_matrix @ core pose at supplied frames; share the unchanged CAD meshes.

    Source objects must come from a fresh fingerprint-bound canonical import.
    Body poses are baked once. Shaft/crank objects keep their original transform
    beneath shared unwrapped-Euler pivots, preserving turns greater than pi per
    video frame. No root offset, speed normalization, contact solution or looping
    is applied. Returned bounds are for camera framing, not contact residuals.
    """
    if not bpy.app.background:
        raise RuntimeError("Walking baking must run in isolated headless Blender")
    prototype = manifest["id"]
    validate_walking_trajectory(trajectory, prototype)
    provenance_fields = set(SOURCE_SIGNATURES) | {
        "trajectory_path", "trajectory_sha256", "payload_sha256"}
    if not isinstance(provenance, dict) or not provenance_fields <= provenance.keys():
        raise ValueError("Walking source provenance is incomplete")
    if provenance["trajectory_path"] != f"docs/ver3/walk_{prototype}.json":
        raise ValueError("Walking trajectory provenance must use its canonical relative path")
    if walking_payload_digest(trajectory) != provenance["payload_sha256"]:
        raise ValueError("Walking payload was altered after its canonical input was read")
    if r.sha256(Path(r.__file__).with_name("core.py")) != provenance["core_sha256"]:
        raise RuntimeError("Authoritative core.py changed after walking inputs were read")
    kinematic_config = {field: r.CONFIG[field] for field in ("linkage", "hardware")}
    if hashlib.sha256(json.dumps(kinematic_config, sort_keys=True).encode()).hexdigest() != provenance["kinematic_config_sha256"]:
        raise RuntimeError("Authoritative kinematic configuration changed after walking inputs were read")
    expected_ids = {instance["name"] for instance in manifest["instances"]}
    if (not expected_ids or len(expected_ids) != len(manifest["instances"]) or
            set(source_objects) != expected_ids):
        raise ValueError("Walking source instance IDs must exactly match the canonical assembly")
    for instance in manifest["instances"]:
        obj = source_objects[instance["name"]]
        if (obj.type != "MESH" or obj.get("part_id") != instance["part_id"] or
                obj.modifiers or obj.data.shape_keys):
            raise ValueError(f"Walking requires the unmodified source CAD mesh: {instance['name']}")
        if obj.parent is None or any(
                obj.parent.get(f"source_{field}") != provenance[field] for field in SOURCE_SIGNATURES):
            raise RuntimeError(f"{instance['name']}: stale or unbound source objects; import the final mesh first")
        if obj.data.get("source_meshes_sha256") != provenance["meshes_sha256"]:
            raise RuntimeError(f"{instance['name']}: source mesh fingerprint mismatch")
    name = f"WALK | {prototype} | CANONICAL BODY POSES"
    if bpy.data.collections.get(name):
        raise RuntimeError(f"Walking collection already exists: {prototype}")
    collection = bpy.data.collections.new(name)
    collection["walking_prototype"] = prototype
    collection["frame_count"] = len(trajectory["frames"])
    collection["render_frame_end"] = trajectory["render_frame_end"]
    collection["fps"] = trajectory["fps"]
    collection["physical_seconds"] = trajectory["physical_seconds"]
    collection["video_seconds"] = trajectory["video_seconds"]
    collection["time_scale"] = trajectory["time_scale"]
    collection["input_rpm"] = trajectory["input_rpm"]
    collection["trajectory_path"] = provenance["trajectory_path"]
    collection["trajectory_sha256"] = provenance["trajectory_sha256"]
    collection["motion_basis"] = "body_matrix @ core.animated_transform(instance, theta, design)"
    collection["rotation_representation"] = "Canonical body parent + shared unwrapped-Euler axis pivots"
    collection["limitations"] = "Lead-supplied contact-fit kinematics; not verified wind/contact dynamics"
    collection["playback_label"] = (
        f"{trajectory['time_scale']:g}X PLAYBACK / {trajectory['physical_seconds']:g}s PHYSICAL "
        f"/ {trajectory['video_seconds']:g}s VIDEO")
    body = bake_walking_body(r, collection, prototype, trajectory["frames"])
    axis_collection = r.add_collection(collection, f"WALK::{prototype}::CONTINUOUS_AXES")
    pivots = {}
    groups, objects, bounds, local_boxes = {}, {}, {}, {}
    _, view_right, view_up = camera_basis(WALK_VIEW_DIRECTION)
    projection_basis = np.asarray([view_right, view_up]).T
    projection_min, projection_max = np.full(2, np.inf), np.full(2, -np.inf)
    extreme_points = np.zeros((4, 3))
    for instance in manifest["instances"]:
        source = source_objects[instance["name"]]
        group = instance["group"]
        if group not in groups:
            groups[group] = r.add_collection(collection, f"WALK::{prototype}::{group}")
        obj = bpy.data.objects.new(f"WALK::{prototype}::{instance['name']}", source.data)
        groups[group].objects.link(obj)
        obj.rotation_mode = "QUATERNION"
        obj["walking_instance"] = True
        obj["design_id"] = prototype
        obj["instance_id"] = instance["name"]
        obj["part_id"] = instance["part_id"]
        obj["assembly_group"] = group
        obj["category"] = manifest["parts"][instance["part_id"]]["category"]
        obj["nominal_mass_g"] = manifest["parts"][instance["part_id"]]["mass_g"]
        obj["description"] = manifest["parts"][instance["part_id"]]["description"]
        obj["source_trajectory_sha256"] = provenance["trajectory_sha256"]
        obj["motion_metadata"] = json.dumps(instance.get("motion"))
        obj["manifest_transform_mm"] = json.dumps(instance["transform"])
        axis = walking_axis(instance)
        if axis is None:
            obj.parent = body
        else:
            if axis not in pivots:
                pivots[axis] = bake_walking_axis(
                    r, axis_collection, prototype, body, axis, trajectory["frames"], len(pivots))
            pivot = pivots[axis]
            obj.parent = pivot
            obj.matrix_basis = (
                Matrix.Translation(-pivot.location) @ r.matrix_metres(instance["transform"])
            )
            obj["rotation_source"] = pivot.name
        mesh_name = source.data.name
        if mesh_name not in local_boxes:
            vertices = np.empty(len(source.data.vertices) * 3)
            source.data.vertices.foreach_get("co", vertices)
            vertices = vertices.reshape((-1, 3))
            local_boxes[mesh_name] = box_corners(np.asarray([vertices.min(axis=0), vertices.max(axis=0)]))
        positions, quaternions = [], []
        lower, upper = np.full(3, np.inf), np.full(3, -np.inf)
        previous = None
        for frame in trajectory["frames"]:
            local = r.matrix_metres(r.animated_transform(instance, frame["theta"], manifest["design"]))
            matrix = r.matrix_metres(frame["body_matrix"]) @ local
            if axis is None:
                if frame["frame"] == 1:
                    obj.matrix_basis = local
                quaternion = local.to_quaternion()
                if previous is not None and quaternion.dot(previous) < 0:
                    quaternion.negate()
                previous = quaternion.copy()
                positions.append(tuple(local.translation))
                quaternions.append(tuple(quaternion))
            values = np.asarray(matrix)
            corners = local_boxes[mesh_name] @ values[:3, :3].T + values[:3, 3]
            lower = np.minimum(lower, corners.min(axis=0))
            upper = np.maximum(upper, corners.max(axis=0))
            projected = corners @ projection_basis
            for projection_axis in range(2):
                low = int(np.argmin(projected[:, projection_axis]))
                high = int(np.argmax(projected[:, projection_axis]))
                if projected[low, projection_axis] < projection_min[projection_axis]:
                    projection_min[projection_axis] = projected[low, projection_axis]
                    extreme_points[projection_axis * 2] = corners[low]
                if projected[high, projection_axis] > projection_max[projection_axis]:
                    projection_max[projection_axis] = projected[high, projection_axis]
                    extreme_points[projection_axis * 2 + 1] = corners[high]
        if axis is None:
            r.add_action(obj, {"location": positions, "rotation_quaternion": quaternions},
                         f"WALKING::{prototype}::{instance['name']}")
        obj["baked_frame_count"] = len(trajectory["frames"])
        objects[instance["name"]] = obj
        bounds[instance["name"]] = np.asarray([lower, upper])
    embedded = bpy.data.texts.new(f"SOURCE | walk_{prototype}.json")
    embedded.write(json.dumps(trajectory, indent=2, allow_nan=False))
    source_record = bpy.data.texts.new(f"SOURCE | walk_{prototype}_provenance.json")
    source_record.write(json.dumps(provenance, indent=2))
    collection["camera_extreme_points_json"] = json.dumps(extreme_points.tolist())
    collection["shared_axis_count"] = len(pivots)
    return collection, objects, union_boxes(bounds.values())


def angle_storage_tolerance(angle):
    # Blender stores Euler values in float32; B reaches roughly -1206 radians.
    return max(1e-6, 2 * abs(float(np.spacing(np.float32(angle)))))


def check_walking_world_pose(r, instance, actual, expected, theta):
    position = float(np.max(np.abs(expected[:3, 3] - actual[:3, 3]))) / r.MM
    rotation = float(np.max(np.abs(expected[:3, :3] - actual[:3, :3])))
    axis = walking_axis(instance)
    position_tolerance, rotation_tolerance = 0.001, 0.00001
    if axis is not None:
        center_y, center_z, speed = axis
        angle_tolerance = angle_storage_tolerance(speed * theta)
        original = np.asarray(instance["transform"], dtype=float)
        radius = float(np.linalg.norm(
            original[1:3, 3] - (center_y, center_z + r.CONFIG["linkage"]["crank_height"])))
        position_tolerance += radius * angle_tolerance
        rotation_tolerance += angle_tolerance
    if position > position_tolerance or rotation > rotation_tolerance:
        raise AssertionError(
            f"{instance['name']}: canonical world-pose mismatch: "
            f"{position:g} mm / {rotation:g} matrix error")
    return position, rotation


def validate_walking_bake(r, manifest, objects, trajectory):
    """Check every source pose and analytic shaft/crank poses at quarter subframes."""
    prototype = manifest["id"]
    validate_walking_trajectory(trajectory, prototype)
    if set(objects) != {instance["name"] for instance in manifest["instances"]}:
        raise AssertionError("Walking bake is missing canonical instances")
    if any(bpy.context.scene.objects.get(obj.name) != obj for obj in objects.values()):
        raise RuntimeError("Link the walking collection into the active scene before validating")
    body = bpy.context.scene.objects.get(f"WALK::{prototype}::BODY_POSE")
    if body is None or body.parent is not None or body.rotation_mode != "QUATERNION":
        raise AssertionError("Walking needs exactly one canonical, unparented body-pose Empty")
    pivots, rotating = {}, []
    for instance in manifest["instances"]:
        obj = objects[instance["name"]]
        if not np.allclose(obj.scale, (1, 1, 1), atol=1e-6, rtol=0) or obj.modifiers:
            raise AssertionError(f"{obj.name}: walking includes a geometric correction")
        if not np.allclose(np.asarray(obj.matrix_parent_inverse), np.eye(4), atol=1e-7, rtol=0):
            raise AssertionError(f"{obj.name}: unexpected parent-inverse offset")
        axis = walking_axis(instance)
        if axis is None:
            if obj.parent != body:
                raise AssertionError(f"{obj.name}: wrong canonical body parent")
        else:
            pivot = obj.parent
            if (pivot is None or not pivot.get("walking_axis") or pivot.parent != body or
                    pivot.rotation_mode != "XYZ" or pivot["relative_speed"] != axis[2] or
                    tuple(pivot["axis_center_mm"]) != axis[:2] or obj.animation_data is not None):
                raise AssertionError(f"{obj.name}: rotating parts need an unwrapped Euler axis, not quaternion motion")
            expected_center = Vector((0, axis[0], axis[1] + r.CONFIG["linkage"]["crank_height"])) * r.MM
            if not np.allclose(pivot.location, expected_center, atol=1e-7, rtol=0):
                raise AssertionError(f"{pivot.name}: shaft center changed")
            expected_local = Matrix.Translation(-expected_center) @ r.matrix_metres(instance["transform"])
            if not np.allclose(np.asarray(obj.matrix_basis), np.asarray(expected_local), atol=1e-6, rtol=0):
                raise AssertionError(f"{obj.name}: original shaft-relative transform changed")
            pivots[pivot.name] = pivot
            rotating.append(instance)
    for obj in [body, *pivots.values(), *objects.values()]:
        for curve in r.curves_for(obj):
            if curve.modifiers or len(curve.keyframe_points) != len(trajectory["frames"]):
                raise AssertionError(f"{obj.name}: walking must use exactly the supplied nonrepeating samples")
            if any(point.interpolation != "LINEAR" for point in curve.keyframe_points):
                raise AssertionError(f"{obj.name}: unintended between-frame interpolation")
            if obj.get("walking_axis") and (curve.data_path != "rotation_euler" or curve.array_index != 0):
                raise AssertionError(f"{obj.name}: axis must rotate only around canonical body X")
    maximum_position, maximum_rotation, maximum_angle_error = 0.0, 0.0, 0.0
    frames = trajectory["frames"]
    for frame in frames:
        bpy.context.scene.frame_set(frame["frame"])
        if not np.allclose(np.asarray(body.matrix_world),
                           np.asarray(r.matrix_metres(frame["body_matrix"])), atol=1e-6, rtol=0):
            raise AssertionError(f"{prototype}: canonical body pose differs at {frame['frame']}")
        for pivot in pivots.values():
            expected_angle = pivot["relative_speed"] * frame["theta"]
            error = abs(pivot.rotation_euler.x - expected_angle)
            maximum_angle_error = max(maximum_angle_error, error)
            if error > angle_storage_tolerance(expected_angle):
                raise AssertionError(f"{pivot.name}: unwrapped angle differs at frame {frame['frame']}")
        for instance in manifest["instances"]:
            obj = objects[instance["name"]]
            expected = np.asarray(r.matrix_metres(walking_world_matrix_mm(
                r, instance, frame, manifest["design"])))
            position, rotation = check_walking_world_pose(
                r, instance, np.asarray(obj.matrix_world), expected, frame["theta"])
            maximum_position, maximum_rotation = max(maximum_position, position), max(maximum_rotation, rotation)
    subframe_position, subframe_rotation, subframe_count = 0.0, 0.0, 0
    for start, end in zip(frames, frames[1:]):
        prior_angles = {name: pivot["relative_speed"] * start["theta"] for name, pivot in pivots.items()}
        for fraction in (0.25, 0.5, 0.75):
            bpy.context.scene.frame_set(start["frame"], subframe=fraction)
            theta = start["theta"] + fraction * (end["theta"] - start["theta"])
            for name, pivot in pivots.items():
                speed = pivot["relative_speed"]
                angle = pivot.rotation_euler.x
                error = abs(angle - speed * theta)
                maximum_angle_error = max(maximum_angle_error, error)
                if error > angle_storage_tolerance(speed * theta):
                    raise AssertionError(f"{name}: subframe speed/ratio mismatch at {start['frame']}+{fraction}")
                step = speed * (end["theta"] - start["theta"])
                if abs(step) > 1e-6 and (angle - prior_angles[name]) * step <= 0:
                    raise AssertionError(f"{name}: subframe rotation reversed direction")
                prior_angles[name] = angle
            for instance in rotating:
                obj = objects[instance["name"]]
                expected = np.asarray(body.matrix_world @ r.matrix_metres(
                    r.animated_transform(instance, theta, manifest["design"])))
                position, rotation = check_walking_world_pose(
                    r, instance, np.asarray(obj.matrix_world), expected, theta)
                subframe_position, subframe_rotation = max(subframe_position, position), max(subframe_rotation, rotation)
            subframe_count += 1
    axes = []
    for name, pivot in pivots.items():
        speed = pivot["relative_speed"]
        curve = r.curves_for(pivot)[0] if r.curves_for(pivot) else None
        if curve is not None:
            total_turns = (curve.evaluate(frames[-1]["frame"]) - curve.evaluate(frames[0]["frame"])) / math.tau
            expected_turns = speed * (frames[-1]["theta"] - frames[0]["theta"]) / math.tau
            if abs(total_turns - expected_turns) > 0.0001:
                raise AssertionError(f"{name}: unwrapped total turns are incorrect")
        else:
            total_turns = expected_turns = 0
        axes.append({
            "object": name, "center_yz_mm": list(pivot["axis_center_mm"]), "relative_speed": speed,
            "expected_signed_turns": expected_turns, "baked_signed_turns": total_turns,
            "max_degrees_per_video_frame": max(
                abs(math.degrees(speed * (b["theta"] - a["theta"]))) for a, b in zip(frames, frames[1:])),
        })
    return {
        "verified_supplied_frames": len(frames),
        "render_frame_end": trajectory["render_frame_end"],
        "instances": len(objects),
        "world_pose_contract": "body_matrix @ core.animated_transform",
        "rotation_representation": "Canonical body parent + shared unwrapped-Euler shaft/crank axes",
        "shared_axes": axes,
        "max_position_error_mm": maximum_position,
        "max_rotation_matrix_error": maximum_rotation,
        "max_unwrapped_angle_error_radians": maximum_angle_error,
        "roundoff_budget": "1 micrometre / 1e-5 matrix baseline plus two float32 Euler ULPs times the actual axis radius",
        "subframes_verified": subframe_count,
        "subframe_offsets": [0.25, 0.5, 0.75],
        "subframe_rotating_instances": len(rotating),
        "subframe_max_position_error_mm": subframe_position,
        "subframe_max_rotation_matrix_error": subframe_rotation,
        "subframe_direction_and_ratio_verified": True,
        "time_scale": trajectory["time_scale"],
        "physical_seconds": trajectory["physical_seconds"],
        "video_seconds": trajectory["video_seconds"],
        "lead_residual_validation": trajectory["validation"],
        "scope": "All supplied world poses; shaft/crank direction and ratio also checked between frames. "
                 "Between-frame body/link interpolation is not contact or physical validation.",
    }


def available_inputs(r):
    available, pending = [], []
    for key in "ABC":
        path, _ = r.source_paths(key)
        if not path.is_file():
            pending.append(key)
            continue
        manifest = json.loads(path.read_bytes())
        (available if manifest["design"].get("stages") else pending).append(key)
    if available != list("ABC"):
        raise RuntimeError("Frozen production needs all three new assemblies; old designs will not be substituted")
    manifests, libraries, fingerprints = r.read_inputs(available, profile="system")
    for key, manifest in manifests.items():
        design = manifest["design"]
        if not design.get("rotor") or not design.get("ratio"):
            raise ValueError(f"{key}: missing multi-stage rotor/ratio metadata")
        product_ratio = math.prod(stage["ratio"] for stage in design["stages"])
        if not math.isclose(product_ratio, design["ratio"], rel_tol=1e-9):
            raise ValueError(f"{key}: stage ratios do not match the manifest's overall ratio")
        if design["ratio"] <= 0:
            raise ValueError(f"{key}: expected a positive reduction magnitude")
    return manifests, libraries, fingerprints, pending


def box_corners(box):
    return np.asarray(list(product(*zip(box[0], box[1]))), dtype=float)


def union_boxes(boxes):
    values = np.asarray(list(boxes), dtype=float)
    if not len(values):
        raise ValueError("Cannot frame an empty set of actual CAD parts")
    return np.asarray([values[:, 0].min(axis=0), values[:, 1].max(axis=0)])


def camera_basis(direction):
    direction = Vector(direction).normalized()
    right = Vector((-direction.y, direction.x, 0)).normalized()
    up = direction.cross(right).normalized()
    return direction, right, up


def fit_camera(r, scene, setting, points, region, direction):
    """Fit swept CAD bounds into a reserved pixel rectangle, without model scale."""
    direction, right, up = camera_basis(direction)
    points = np.asarray(points)
    horizontal = points @ np.asarray(right)
    vertical = points @ np.asarray(up)
    left, top, right_px, bottom = region
    width_fraction = (right_px - left) / r.WIDTH
    height_fraction = (bottom - top) / r.HEIGHT
    if width_fraction <= 0 or height_fraction <= 0:
        raise ValueError("Invalid camera-fit rectangle")
    width = max(
        float(np.ptp(horizontal)) / width_fraction,
        float(np.ptp(vertical)) / (height_fraction * r.HEIGHT / r.WIDTH),
    ) * 1.06
    if not math.isfinite(width) or width <= 0:
        raise ValueError("Invalid CAD extent for camera framing")
    center = Vector(points.mean(axis=0))
    center += right * ((float(horizontal.min()) + float(horizontal.max())) / 2 - center.dot(right))
    center += up * ((float(vertical.min()) + float(vertical.max())) / 2 - center.dot(up))
    screen_x = (left + right_px) / (2 * r.WIDTH) - 0.5
    screen_y = 0.5 - (top + bottom) / (2 * r.HEIGHT)
    target = center - right * (screen_x * width) - up * (screen_y * width * r.HEIGHT / r.WIDTH)
    camera = r.camera(scene, setting, target, width, direction)
    scene["fit_region_px"] = list(region)
    scene["fit_points_world_json"] = json.dumps(points.tolist())
    scene["camera_fit"] = "Swept exact-CAD local bounding-box corners; no per-model scaling"
    return camera


def world_points(record, instance_ids=None):
    if instance_ids is None:
        box = record["bounds"]
    else:
        box = union_boxes(record["instance_bounds"][name] for name in instance_ids)
    return box_corners(box) + np.asarray(record["root"].location)


def bake_timing(manifest, fps):
    speeds = [float(instance.get("motion", {}).get("speed", 1))
              for instance in manifest["instances"] if instance.get("motion")]
    if not speeds or not all(math.isfinite(speed) for speed in speeds):
        raise ValueError("Missing or non-finite authoritative shaft speeds")
    fastest = max(abs(speed) for speed in speeds)
    period = max(fps, math.ceil(fps * fastest / INPUT_RPS - 1e-9))
    rotor_speeds = {float(instance["motion"].get("speed", 1))
                    for instance in manifest["instances"]
                    if instance["group"] == "rotor" and instance.get("motion")}
    if len(rotor_speeds) != 1:
        raise ValueError(f"Expected a coherent rotor speed, got {rotor_speeds}")
    return {
        "period_frames": period,
        "frame_count": period + 1,
        "signed_relative_speeds": sorted(set(speeds)),
        "signed_rotor_speed": rotor_speeds.pop(),
        "crank_rps": fps / period,
        "maximum_angular_step_degrees": 360 * fastest / period,
    }


def layout_at_actual_scale(r, records):
    intervals = {}
    for key, record in records.items():
        projected = box_corners(record["bounds"]) @ np.asarray(r.VIEW_RIGHT)
        intervals[key] = (float(projected.min()), float(projected.max()))
    largest = max(upper - lower for lower, upper in intervals.values())
    gap = max(0.07, largest * 0.16)
    cursor = 0
    shifts = {}
    for key in records:
        lower, upper = intervals[key]
        shifts[key] = cursor - lower
        cursor += upper - lower + gap
    total = cursor - gap
    for key, record in records.items():
        record["root"].location = r.VIEW_RIGHT * (shifts[key] - total / 2)
        record["root"]["layout_note"] = "Static translation only; same millimetres/pixel in overview"
        record["root"]["crank_period_frames"] = record["timing"]["period_frames"]
        record["root"]["rotation_speed_source"] = "core.animated_transform and manifest motion.speed"


def create_scene(r, name, points, end, materials, region, direction=None, *, ground_z=None):
    scene = bpy.data.scenes.new(name)
    r.configure_scene(scene, end)
    scene["engineering_status"] = STATUS
    scene["wind_budget"] = LIMITATION
    scene["input_speed_note"] = "Prescribed input magnitude 120 rotor RPM; not a wind solution"
    bounds = np.asarray([np.min(points, axis=0), np.max(points, axis=0)])
    center = bounds.mean(axis=0)
    light_scale = max(0.9, float(np.max(bounds[1] - bounds[0])) / 0.65)
    setting = r.studio(scene, materials, center,
                       ground_z=float(bounds[0, 2] - 0.015) if ground_z is None else ground_z,
                       light_scale=light_scale)
    fit_camera(r, scene, setting, points, region, direction or r.VIEW_DIRECTION)
    return scene, setting


def labels(r, scene, setting, materials, title, subtitle):
    r.text(scene, setting, "VER.3  /  MECHANICAL REVIEW FIRST CUT", 40, 35, 16, materials["cyan"])
    r.text(scene, setting, title, 40, 78, 29, materials["text"])
    r.text(scene, setting, subtitle, 41, 110, 16, materials["muted"])
    r.text(scene, setting, STATUS, 40, 627, 16, materials["cyan"])
    r.text(scene, setting, r.OPERATION_NOTICE, 40, 663, 19, materials["warning"])
    r.text(scene, setting, LIMITATION, 40, 692, 15, materials["muted"])


def facts(manifest):
    design = manifest["design"]
    mass = sum(manifest["parts"][instance["part_id"]]["mass_g"]
               for instance in manifest["instances"]) / 1000
    return {
        "rotor_diameter_mm": 2 * design["rotor"]["radius"],
        "rotor_span_mm": design["rotor"]["span"],
        "stages": len(design["stages"]),
        "ratio": design["ratio"],
        "nominal_mass_kg": mass,
        "instances": len(manifest["instances"]),
    }


def comparison_notes(r, scene, records, manifests, materials, pending):
    notes = r.add_collection(scene.collection, f"{scene.name} | COMPARISON NOTES")
    scene["comparison_notes_collection"] = notes.name
    labels(r, scene, notes, materials, "ROTOR SIZE / REDUCTION / GENERATED STRUCTURE",
           "Orthographic, same scale and ground / dashed circles: nominal rotor sweep (annotations)")
    bpy.context.window.scene = scene
    scene.frame_set(1)
    scene.view_layers[0].update()
    centers = {key: r.project(scene, world_points(record).mean(axis=0))[0]
               for key, record in records.items()}
    keys = list(records)
    boundaries = [40] + [(centers[a] + centers[b]) / 2 for a, b in zip(keys, keys[1:])] + [r.WIDTH - 40]
    lanes = {key: (boundaries[index], boundaries[index + 1]) for index, key in enumerate(keys)}
    short_titles = {"A": "Large rotor", "B": "High reduction", "C": "Generated frame"}

    def lane_text(key, body, y, pixels, role, material):
        obj = r.text(scene, notes, body, centers[key], y, pixels, material, "CENTER")
        scene.view_layers[0].update()
        points = [r.project(scene, obj.matrix_world @ Vector(corner)) for corner in obj.bound_box]
        width = max(point[0] for point in points) - min(point[0] for point in points)
        allowance = 2 * min(centers[key] - lanes[key][0] - 12, lanes[key][1] - centers[key] - 12)
        if width > allowance:
            obj.data.size *= allowance / width
        obj["comparison_design"] = key
        obj["comparison_role"] = role
        obj["comparison_lane_px"] = list(lanes[key])
        return obj

    def line_paths(key, name, paths):
        curve = bpy.data.curves.new(f"NOTE | {key} {name}", "CURVE")
        curve.dimensions = "3D"
        width = scene.camera.data.ortho_scale
        curve.bevel_depth, curve.bevel_resolution = width / r.WIDTH * 0.55, 0
        curve.materials.append(materials[f"{key}_label"])
        for path in paths:
            spline = curve.splines.new("POLY")
            spline.points.add(len(path) - 1)
            for point, (x, y) in zip(spline.points, path):
                point.co = ((x / r.WIDTH - 0.5) * width,
                            (0.5 - y / r.HEIGHT) * width * r.HEIGHT / r.WIDTH, -0.021, 1)
        obj = bpy.data.objects.new(curve.name, curve)
        notes.objects.link(obj)
        obj.parent = scene.camera
        obj["presentation_only"] = True
        obj["comparison_design"] = key
        obj["comparison_role"] = name
        return obj

    sweeps = {}
    for key, record in records.items():
        manifest, info = manifests[key], facts(manifests[key])
        stages = manifest["design"]["stages"]
        types = list(dict.fromkeys(stage["type"] for stage in stages))
        drive = " + ".join(types) if len(types) > 1 else f"{len(stages)} {types[0]} stages"
        lane_text(key, f"{key} / {short_titles[key]}", 159, 23, "heading", materials[f"{key}_label"])
        lane_text(key, f"{drive} / {info['ratio']:g}:1", 187, 18, "transmission", materials["text"])
        lane_text(key, f"Swept diameter: {info['rotor_diameter_mm']:g} mm",
                  228, 17, "diameter", materials[f"{key}_label"])
        lane_text(key, f"nominal {info['nominal_mass_kg']:.2f} kg / {info['instances']} instances",
                  590, 16, "mass", materials["text"])
        rotor_origins = [instance["transform"][0][3] for instance in manifest["instances"]
                         if instance["group"] == "rotor" and instance["part_id"].startswith("P_ROTOR")]
        if not rotor_origins:
            raise ValueError(f"{key}: cannot locate the canonical rotor annotation plane")
        axis_y, axis_z = manifest["design"]["axes"]["I"]
        radius = manifest["design"]["rotor"]["radius"]
        center_mm = np.asarray((max(rotor_origins), axis_y, axis_z + r.CONFIG["linkage"]["crank_height"]))
        root = record["root"].matrix_world
        angle = np.linspace(0, math.tau, 129)
        world = [root @ Vector((center_mm + radius * np.asarray((0, math.cos(a), math.sin(a)))) * r.MM)
                 for a in angle]
        screen = [r.project(scene, point) for point in world]
        circle = line_paths(key, "swept_diameter", [screen[start:start + 4] for start in range(0, 128, 4)])
        circle["source_center_mm"] = center_mm.tolist()
        circle["source_diameter_mm"] = radius * 2
        circle["source_basis"] = "design.rotor.radius + design.axes.I; annotation only, not CAD"
        top = r.project(scene, root @ Vector((center_mm + (0, 0, radius)) * r.MM))
        bottom = r.project(scene, root @ Vector((center_mm - (0, 0, radius)) * r.MM))
        dim_x = min(point[0] for point in screen) - 14
        line_paths(key, "diameter_dimension", [
            [(dim_x, top[1]), (dim_x, bottom[1])],
            [(dim_x - 4, top[1]), top], [(dim_x - 4, bottom[1]), bottom],
            [(dim_x - 3, top[1] + 5), (dim_x, top[1]), (dim_x + 3, top[1] + 5)],
            [(dim_x - 3, bottom[1] - 5), (dim_x, bottom[1]), (dim_x + 3, bottom[1] - 5)],
            [(centers[key], 239), (dim_x, top[1] - 8)],
        ])
        sweeps[key] = {
            "diameter_mm": radius * 2, "center_mm": center_mm.tolist(),
            "projected_vertical_diameter_px": bottom[1] - top[1],
            "column_center_px": centers[key], "lane_px": list(lanes[key]),
        }
    r.text(scene, notes, "Dashed sweeps and dimension lines are annotations, not added mechanical parts.",
           40, 607, 13, materials["muted"])
    if pending:
        r.text(scene, notes, "Pending new inputs: " + ", ".join(pending) + " (old designs omitted)",
               40, 245, 15, materials["warning"])
    scene["comparison_sweeps_json"] = json.dumps(sweeps)
    scene["comparison_heading_rows"] = 2
    scene.view_layers[0].update()


def validate_comparison_notes(r, scene, manifests):
    if scene.camera.data.type != "ORTHO":
        raise AssertionError("Comparison must retain one common orthographic scale")
    bpy.context.window.scene = scene
    scene.frame_set(1)
    scene.view_layers[0].update()
    notes = bpy.data.collections[scene["comparison_notes_collection"]]
    text_extents, scale_factors = {}, []
    for obj in notes.objects:
        if obj.type != "FONT" or "comparison_lane_px" not in obj:
            continue
        points = [r.project(scene, obj.matrix_world @ Vector(corner)) for corner in obj.bound_box]
        left, right = min(point[0] for point in points), max(point[0] for point in points)
        lane_left, lane_right = obj["comparison_lane_px"]
        if left < lane_left + 10 or right > lane_right - 10:
            raise AssertionError(f"Comparison text crosses its lane: {obj.data.body}")
        text_extents[f"{obj['comparison_design']}/{obj['comparison_role']}"] = [left, right]
    sweeps = json.loads(scene["comparison_sweeps_json"])
    for key, sweep in sweeps.items():
        manifest = manifests[key]
        diameter = manifest["design"]["rotor"]["radius"] * 2
        if sweep["diameter_mm"] != diameter:
            raise AssertionError(f"{key}: swept diameter does not match the canonical rotor radius")
        center = sweep["center_mm"]
        if not np.allclose(center[1:], (
                manifest["design"]["axes"]["I"][0],
                manifest["design"]["axes"]["I"][1] + r.CONFIG["linkage"]["crank_height"])):
            raise AssertionError(f"{key}: annotation is not centered on the canonical input axis")
        if any(f"{key}/{role}" not in text_extents for role in ("heading", "transmission", "diameter")):
            raise AssertionError(f"{key}: incomplete comparison heading/diameter label")
        root = bpy.data.objects[f"{key}::PRESENTATION_OFFSET_ONLY"]
        if not np.allclose(root.scale, (1, 1, 1)) or abs(root.location.z) > 1e-8:
            raise AssertionError(f"{key}: per-model scale or ground-height offset was introduced")
        scale_factors.append(sweep["projected_vertical_diameter_px"] / diameter)
    if max(scale_factors) - min(scale_factors) > 1e-5:
        raise AssertionError("Rotor diameter annotations do not share a physical scale")
    return {"heading_rows": 2, "column_text_extents_px": text_extents,
            "nominal_rotor_sweeps": sweeps, "projected_vertical_pixels_per_mm": scale_factors[0],
            "annotation_only": True, "common_orthographic_scale": True, "common_ground_height": True}


def overview_scene(r, records, manifests, materials, pending):
    points = np.vstack([world_points(record) for record in records.values()])
    period = math.lcm(*(record["timing"]["period_frames"] for record in records.values()))
    scene, setting = create_scene(r, "00 | SYSTEM - ACTUAL-SCALE COMPARISON",
                                  points, period + 1, materials, (45, 215, 1235, 557))
    for record in records.values():
        scene.collection.children.link(record["collection"])
    comparison_notes(r, scene, records, manifests, materials, pending)
    scene["available_designs"] = "".join(records)
    scene["pending_designs"] = "".join(pending)
    scene["same_physical_scale"] = True
    scene.timeline_markers.new("Start: all actual shafts driven by their signed metadata", frame=1)
    for key, record in records.items():
        scene.timeline_markers.new(f"{key}: complete crank cycle",
                                   frame=record["timing"]["frame_count"])
    return scene


def hero_scene(r, key, record, manifest, materials):
    scene, setting = create_scene(
        r, f"1{key} | {TITLES[key]}", world_points(record),
        record["timing"]["frame_count"], materials, (420, 145, 1230, 595))
    scene.collection.children.link(record["collection"])
    info = facts(manifest)
    labels(r, scene, setting, materials, f"{key} / {TITLES[key]}",
           "Actual supplied CAD  |  no cosmetic changes to mechanical geometry")
    r.text(scene, setting, f"{info['rotor_diameter_mm']:g} mm", 44, 222, 35,
           materials[f"{key}_label"])
    r.text(scene, setting, f"ROTOR DIAMETER / {info['rotor_span_mm']:g} mm SPAN",
           45, 250, 14, materials["muted"])
    r.text(scene, setting, f"{info['ratio']:g}:1  /  {info['stages']} stages",
           44, 305, 25, materials["text"])
    tooth_pairs = " + ".join(f"{stage['type']} {stage['pinion_teeth']}:{stage['wheel_teeth']}"
                             for stage in manifest["design"]["stages"])
    r.text(scene, setting, tooth_pairs, 45, 336, 15, materials["muted"])
    r.text(scene, setting, f"{info['nominal_mass_kg']:.2f} kg nominal", 44, 389, 25,
           materials["text"])
    r.text(scene, setting, "All-solid CAD + assumed/catalog hardware", 45, 416, 13,
           materials["muted"])
    timing = record["timing"]
    rotor_rps = timing["signed_rotor_speed"] * timing["crank_rps"]
    r.text(scene, setting, f"Prescribed input: {rotor_rps:+.2f} rev/s",
           44, 474, 16, materials["cyan"])
    r.text(scene, setting, f"Crank: {timing['crank_rps']:.5f} rev/s",
           44, 502, 16, materials["text"])
    r.text(scene, setting, f"Full cycle: {timing['period_frames'] / r.FPS:g} s",
           44, 530, 16, materials["muted"])
    if key == "C":
        r.text(scene, setting, r.C_NOTICE, 40, 601, 15, materials["cyan"])
    else:
        r.text(scene, setting, "Purchased hardware internals and hub flexures retain the CAD simplifications.",
               40, 601, 14, materials["muted"])
    scene["design_id"] = key
    scene["still_output"] = f"hero_{key}.png"
    return scene


def link_selection(r, scene, record, instance_ids, name):
    collection = r.add_collection(scene.collection, name)
    collection.objects.link(record["root"])
    for instance_id in instance_ids:
        collection.objects.link(record["objects"][instance_id])


def drivetrain_scene(r, key, record, manifest, materials):
    selected = [instance["name"] for instance in manifest["instances"]
                if instance["group"] == "drivetrain" or instance["part_id"].startswith("H_shaft_")]
    points = world_points(record, selected)
    direction = Vector((1.0, -0.75, 0.40)).normalized()
    scene, setting = create_scene(
        r, f"2{key} | DRIVE AND SHAFTS - ISOLATED", points,
        record["timing"]["frame_count"], materials, (380, 156, 1225, 584), direction)
    link_selection(r, scene, record, selected, f"{key} | DRIVE / SHAFT SELECTION")
    labels(r, scene, setting, materials, f"{key} / MULTI-STAGE DRIVETRAIN",
           "CUTAWAY / DRIVE + SHAFTS ONLY  |  covers, frame, rotor body and legs omitted")
    for index, stage in enumerate(manifest["design"]["stages"]):
        r.text(scene, setting, f"{stage['id']}   {stage['pinion_teeth']}:{stage['wheel_teeth']}",
               44, 212 + index * 58, 22, materials[f"{key}_label"])
        r.text(scene, setting,
               f"{stage['side']} {stage['type']}  /  {stage['ratio']:g}:1",
               44, 238 + index * 58, 15, materials["muted"])
    r.text(scene, setting, "Signed turns per crank turn:", 44, 452, 15, materials["text"])
    r.text(scene, setting, " / ".join(f"{speed:+g}" for speed in record["timing"]["signed_relative_speeds"]),
           44, 480, 18, materials["cyan"])
    r.text(scene, setting, "Every transform: core.animated_transform", 44, 520, 14, materials["muted"])
    r.text(scene, setting, "Isolated display only; not an assembly insertion path or contact study.",
           40, 601, 15, materials["muted"])
    scene["design_id"] = key
    scene["still_output"] = f"drivetrain_{key}.png"
    scene["display_omissions"] = "covers, frame, rotor body and legs"
    return scene


def drive_ids(manifest):
    return [instance["name"] for instance in manifest["instances"]
            if instance["group"] == "drivetrain" or instance["part_id"].startswith("H_shaft_")]


def drivetrain_side_scene(r, key, record, manifest, materials, side):
    all_ids = drive_ids(manifest)
    bounds = union_boxes(record["instance_bounds"][name] for name in all_ids)
    split = float(bounds[:, 0].mean())
    selected = [name for name in all_ids if (
        record["instance_bounds"][name][0, 0] <= split if side == "left"
        else record["instance_bounds"][name][1, 0] >= split)]
    sign = -1 if side == "left" else 1
    scene, setting = create_scene(
        r, f"3{key}-{side} | {side.upper()} DRIVE", world_points(record, selected),
        record["timing"]["frame_count"], materials, (360, 164, 1230, 584),
        Vector((sign, -0.65, 0.35)))
    link_selection(r, scene, record, selected, f"{key} | {side.upper()} DRIVE SELECTION")
    labels(r, scene, setting, materials, f"{key} / {side.upper()}-END TRANSMISSION",
           "CUTAWAY / DRIVE + SHAFTS ONLY  |  surrounding assemblies omitted")
    stages = [stage for stage in manifest["design"]["stages"] if stage["side"] == side]
    for index, stage in enumerate(stages):
        y = 215 + 87 * index
        r.text(scene, setting, f"{stage['id']} / {stage['type'].upper()}", 43, y, 22,
               materials[f"{key}_label"])
        r.text(scene, setting, f"{stage['pinion_teeth']}:{stage['wheel_teeth']}  /  {stage['ratio']:g}:1",
               44, y + 29, 18, materials["text"])
    if any(stage["type"] == "belt" for stage in stages):
        r.text(scene, setting, "Purchased HTD5M belt 520 x 9", 43, 454, 16, materials["cyan"])
        r.text(scene, setting, "Belt envelope shown; tooth motion", 43, 484, 14, materials["muted"])
        r.text(scene, setting, "and compliance are not simulated.", 43, 508, 14, materials["muted"])
    r.text(scene, setting, "No mirrored reconstruction; all part placements come from the manifest.",
           40, 601, 15, materials["muted"])
    scene["still_output"] = f"drivetrain_{key}_{side}.png"
    scene["display_omissions"] = "covers, frame, rotor body and legs"
    return scene


def drive_overview_scene(r, records, manifests, materials):
    selections = {key: drive_ids(manifests[key]) for key in records}
    points = np.vstack([world_points(records[key], selections[key]) for key in records])
    period = math.lcm(*(record["timing"]["period_frames"] for record in records.values()))
    scene, setting = create_scene(
        r, "05 | ALL DISTRIBUTED DRIVES", points, period + 1, materials,
        (45, 188, 1235, 569), r.VIEW_DIRECTION)
    for key, record in records.items():
        link_selection(r, scene, record, selections[key], f"{key} | ALL DRIVE PARTS")
    labels(r, scene, setting, materials, "DISTRIBUTED TRANSMISSION / ACTUAL CAD",
           "CUTAWAY / DRIVE + SHAFTS ONLY  |  120 rotor RPM magnitude, prescribed")
    bpy.context.window.scene = scene
    scene.view_layers[0].update()
    for key, record in records.items():
        x, _ = r.project(scene, world_points(record, selections[key]).mean(axis=0))
        signed = " / ".join(f"{speed:+g}" for speed in record["timing"]["signed_relative_speeds"])
        r.text(scene, setting, f"{key} / {manifests[key]['design']['ratio']:g}:1", x, 156, 22,
               materials[f"{key}_label"], "CENTER")
        r.text(scene, setting, f"relative shaft turns: {signed}", x, 600, 14,
               materials["text"], "CENTER")
    return scene


def object_box(obj):
    values = np.empty(len(obj.data.vertices) * 3)
    obj.data.vertices.foreach_get("co", values)
    values = values.reshape((-1, 3))
    points = box_corners(np.asarray([values.min(axis=0), values.max(axis=0)]))
    matrix = np.asarray(obj.matrix_basis)
    world = points @ matrix[:3, :3].T + matrix[:3, 3]
    return np.asarray([world.min(axis=0), world.max(axis=0)])


def connection_scene(r, record, manifest, materials):
    candidates = [instance for instance in manifest["instances"]
                  if instance.get("motion", {}).get("speed") == 1
                  and instance.get("motion", {}).get("center") == manifest["design"]["axes"]["O"]]
    selected = [instance for instance in candidates if instance["group"] == "drivetrain"]
    shafts = [instance for instance in candidates if instance["part_id"].startswith("H_shaft_")]
    if not shafts or not any(instance["part_id"] == "H_REX_HUB" for instance in selected):
        raise ValueError("Cannot identify the canonical output-axis REX connection")
    selected.append(max(shafts, key=lambda instance: record["instance_bounds"][instance["name"]][1, 0]))
    collection = bpy.data.collections.new("EXPLAIN | ACTUAL A REX CONNECTION")
    boxes = []
    for instance in selected:
        original = record["objects"][instance["name"]]
        obj = r.copy_illustration(instance, original, collection, None, "REX")
        if instance["group"] == "drivetrain":
            if instance["part_id"] == "H_REX_HUB":
                obj.location.x += 0.18
            elif manifest["parts"][instance["part_id"]]["category"] == "printed":
                obj.location.x += 0.10
            else:
                obj.location.x += 0.065
        boxes.append(object_box(obj))
    scene, setting = create_scene(
        r, "40 | REX OUTPUT CONNECTION", box_corners(union_boxes(boxes)), 1,
        materials, (350, 169, 1225, 577), Vector((0.78, -0.84, 0.37)))
    scene.collection.children.link(collection)
    labels(r, scene, setting, materials, "POSITIVE REX / METAL HUB / OUTPUT GEAR",
           "CUTAWAY / AXIAL OFFSETS FOR INSPECTION  |  surrounding assemblies omitted")
    for index, line in enumerate(("Actual non-round REX shaft", "Purchased metal REX hub",
                                   "Printed output gear", "Source fasteners retained")):
        r.text(scene, setting, line, 43, 220 + index * 39, 18, materials["text"])
    r.text(scene, setting, "Hardware flexures and threads", 43, 437, 15, materials["muted"])
    r.text(scene, setting, "retain source simplifications.", 43, 462, 15, materials["muted"])
    r.text(scene, setting, "Illustrative axial offsets are not a validated physical insertion path.",
           40, 601, 16, materials["warning"])
    scene["still_output"] = "rex_connection.png"
    return scene


def exploded_translation(r, instance, frame, middle_x, bays):
    group = instance["group"]
    x = float(instance["transform"][0][3]) * r.MM
    side = -1 if x < middle_x else 1
    if group == "guard_lid":
        return Vector((side * 0.24, 0, 0.055)) * r.smoothstep(frame, 5, 29)
    if group == "guard":
        return Vector((side * 0.15, 0, 0.025)) * r.smoothstep(frame, 25, 49)
    if group == "drivetrain":
        return Vector((side * 0.09, 0, 0.08)) * r.smoothstep(frame, 37, 65)
    if group == "rotor":
        return Vector((0, 0, 0.18)) * r.smoothstep(frame, 37, 65)
    spread = r.smoothstep(frame, 65, 101)
    if group in ("legs", "crank", "feet", "pivot"):
        bay = instance.get("motion", {}).get("bay")
        if bay is None:
            bay = min(bays, key=lambda value: abs(x / r.MM - value))
        centered = (bay - (min(bays) + max(bays)) / 2) * r.MM
        return Vector((centered * 0.65, centered * 0.22, -0.005)) * spread
    if group == "frame" or group.startswith("bearing_"):
        return Vector(((x - middle_x) * 0.42, 0, 0.055)) * spread
    if group == "hardware":
        return Vector((0, 0.115, 0.08)) * spread
    raise ValueError(f"Unclassified explanatory group: {group}")


def exploded_scene(r, record, manifest, materials):
    collection = bpy.data.collections.new("EXPLAIN | A STAGED EXPLODED GROUPS")
    middle_x = float(record["bounds"][:, 0].mean())
    bays = sorted({instance["motion"]["bay"] for instance in manifest["instances"]
                   if "bay" in instance.get("motion", {})})
    if not bays:
        raise ValueError("No authoritative crank-bay metadata for the exploded grouping")
    boxes = []
    for instance in manifest["instances"]:
        obj = r.copy_illustration(instance, record["objects"][instance["name"]],
                                  collection, None, "EXPLODE")
        first = np.asarray(obj.location)
        base_box = object_box(obj)
        positions = [first + np.asarray(exploded_translation(r, instance, frame, middle_x, bays))
                     for frame in range(1, EXPLODED_FRAMES + 1)]
        r.add_action(obj, {"location": positions}, f"EXPLAIN::{instance['name']}")
        boxes.extend((base_box, base_box + (positions[-1] - first)))
    scene, setting = create_scene(
        r, "50 | A EXPLODED - NOT AN INSERTION PATH", box_corners(union_boxes(boxes)),
        EXPLODED_FRAMES, materials, (45, 175, 1235, 586))
    scene.collection.children.link(collection)
    labels(r, scene, setting, materials, "A / DISTRIBUTED ASSEMBLY GROUPS",
           "ILLUSTRATIVE OFFSETS / KINEMATICS PAUSED / NOT A VALIDATED ASSEMBLY PATH")
    for index, line in enumerate(("01 WINDOW / TRAY", "02 BELT / GEARS / ROTOR", "03 FRAME / CRANK / SHOES")):
        r.text(scene, setting, line, 44 + index * 412, 148, 18, materials["cyan"])
    r.text(scene, setting, "Simultaneous group motion does not establish clearance or a feasible insertion sequence.",
           40, 606, 15, materials["warning"])
    scene["exploded_middle_x_m"] = middle_x
    scene["exploded_bays_mm"] = bays
    scene["still_output"] = "exploded_A.png"
    scene["still_frame"] = EXPLODED_FRAMES
    for frame, title in ((1, "Assembled / crank paused"), (29, "Windows"),
                         (49, "Trays"), (65, "Transmission and rotor"),
                         (101, "Frame / crank / shoe groups"), (121, "Illustrative hold")):
        scene.timeline_markers.new(title, frame=frame)
    return scene


def ground_grid_material(r):
    name = "REVIEW | FIXED 50 MM GROUND GRID"
    material = bpy.data.materials.get(name)
    if material is not None:
        return material
    material = r.material(name, (0.008, 0.014, 0.020, 1), roughness=0.9)
    nodes, links = material.node_tree.nodes, material.node_tree.links
    position = nodes.new("ShaderNodeNewGeometry")
    separate = nodes.new("ShaderNodeSeparateXYZ")
    links.new(position.outputs["Position"], separate.inputs[0])
    stripes = []
    for axis in ("X", "Y"):
        scale = nodes.new("ShaderNodeMath"); scale.operation = "MULTIPLY"
        scale.inputs[1].default_value = 20
        links.new(separate.outputs[axis], scale.inputs[0])
        fract = nodes.new("ShaderNodeMath"); fract.operation = "FRACT"
        links.new(scale.outputs[0], fract.inputs[0])
        stripe = nodes.new("ShaderNodeMath"); stripe.operation = "LESS_THAN"
        stripe.inputs[1].default_value = 0.025
        links.new(fract.outputs[0], stripe.inputs[0])
        stripes.append(stripe)
    mask = nodes.new("ShaderNodeMath"); mask.operation = "MAXIMUM"
    links.new(stripes[0].outputs[0], mask.inputs[0])
    links.new(stripes[1].outputs[0], mask.inputs[1])
    color = nodes.new("ShaderNodeMixRGB")
    color.inputs[1].default_value = (0.008, 0.014, 0.020, 1)
    color.inputs[2].default_value = (0.045, 0.066, 0.080, 1)
    links.new(mask.outputs[0], color.inputs[0])
    links.new(color.outputs[0], nodes.get("Principled BSDF").inputs["Base Color"])
    return material


def sensitivity_minima(validation):
    cases = validation["fixed_pose_sensitivity"]
    cog = min(cases[name]["minimum_margin_mm"] for name in
              ("cog_x_minus5", "cog_x_plus5", "cog_y_minus5", "cog_y_plus5"))
    cop = min(cases[name]["minimum_margin_mm"] for name in ("wind_y_minus5", "wind_y_plus5"))
    return cog, cop


def walking_scene(r, key, walking, common_points, materials):
    trajectory = walking["trajectory"]
    metrics = trajectory["validation"]
    ground_values = {float(frame["ground_z"]) for frame in trajectory["frames"]}
    if len(ground_values) != 1:
        raise ValueError("A changing reference ground cannot be replaced by a static plane")
    scene, setting = create_scene(
        r, f"60{key} | CANONICAL WALKING", common_points, trajectory["render_frame_end"],
        materials, (45, 166, 820, 619), Vector(WALK_VIEW_DIRECTION),
        ground_z=ground_values.pop() * r.MM)
    scene.collection.children.link(walking["collection"])
    for obj in setting.objects:
        if obj.type == "MESH" and obj.name.startswith("STUDIO_GROUND"):
            obj.data.materials.clear()
            obj.data.materials.append(ground_grid_material(r))
    r.text(scene, setting, "VER.3 / DIAGNOSTIC KINEMATICS", 40, 34, 16, materials["cyan"])
    r.text(scene, setting, f"{key} / WALKING REVIEW", 40, 77, 31, materials["text"])
    r.text(scene, setting, f"{trajectory['time_scale']:g}X PLAYBACK", 1220, 78, 32,
           materials["warning"], "RIGHT")
    r.text(scene, setting,
           f"3 crank cycles / prescribed 120 rotor RPM / {trajectory['physical_seconds']:g}s physical-time model "
           f"-> {trajectory['video_seconds']:g}s video", 41, 111, 17, materials["muted"])
    r.text(scene, setting,
           f"Model advance {metrics['forward_travel_mm']:.1f} mm / equivalent-time mean "
           f"{metrics['mean_physical_speed_mm_s']:.2f} mm/s (not measured) / fixed 50 mm grid",
           41, 140, 15, materials["cyan"])
    if trajectory["time_scale"] >= 8:
        rotor = next(obj.parent for obj in walking["objects"].values()
                     if obj["assembly_group"] == "rotor" and obj.parent.get("walking_axis"))
        step_degrees = math.degrees(rotor["relative_speed"] * (
            trajectory["frames"][1]["theta"] - trajectory["frames"][0]["theta"]))
        r.text(scene, setting,
               f"Unwrapped input: {step_degrees:+.0f} deg/video frame; stroboscopic appearance is not reverse rotation.",
               41, 164, 13, materials["warning"])
    target = "MET" if metrics["strict_3mm_contact_target_pass"] else "NOT MET"
    r.text(scene, setting, "CONTACT-FIT RESIDUAL", 862, 197, 18, materials["cyan"])
    r.text(scene, setting, f"{metrics['max_stance_material_anchor_drift_mm']:.2f} mm",
           862, 240, 32, materials["warning"])
    r.text(scene, setting, f"3 mm engineering target: {target}", 862, 270, 17, materials["warning"])
    r.text(scene, setting, "Max anchor offset within one", 862, 300, 14, materials["muted"])
    r.text(scene, setting, "uninterrupted >=2%-load episode;", 862, 322, 14, materials["muted"])
    r.text(scene, setting, "clip-boundary partials included.", 862, 344, 14, materials["muted"])
    r.text(scene, setting, f"Episode path max: {metrics['max_single_contact_episode_horizontal_path_mm']:.2f} mm",
           862, 380, 16, materials["text"])
    r.text(scene, setting,
           f"Path sum: {metrics['total_material_horizontal_path_all_feet_three_cycles_mm']:.2f} mm / all feet, 3 cycles",
           862, 405, 14, materials["text"])
    r.text(scene, setting, "Material-point travel, not body advance.", 862, 426, 12, materials["muted"])
    cog, cop = sensitivity_minima(metrics)
    r.text(scene, setting, "FIXED-POSE SENSITIVITY", 862, 463, 15, materials["cyan"])
    r.text(scene, setting, f"COG +/-5 mm minimum: {cog:+.2f} mm", 862, 490, 16, materials["warning"])
    r.text(scene, setting, f"Wind-COP @5 m/s (+/-Y): {cop:+.2f} mm", 862, 515, 16, materials["warning"])
    r.text(scene, setting, f"Nominal margin min: {metrics['minimum_support_margin_mm']:.2f} mm",
           862, 549, 15, materials["muted"])
    r.text(scene, setting, f"Min active feet: {metrics['minimum_active_feet']} / NOT tripod proof",
           862, 572, 14, materials["warning"])
    r.text(scene, setting,
           f"Contact band {metrics['finite_contact_tolerance_mm']:g} mm / active >="
           f"{metrics['loaded_foot_threshold_fraction'] * 100:g}% load",
           862, 596, 13, materials["muted"])
    r.text(scene, setting, f"Source mesh floor minimum: {metrics['minimum_mesh_floor_clearance_mm']:+.2f} mm",
           862, 617, 13, materials["muted"])
    if trajectory["time_scale"] >= 8:
        r.text(scene, setting,
               "Unwrapped axis rotation checked between frames; 24 fps can still strobe. Full metrics: review_metrics.json",
               40, 634, 13, materials["cyan"])
    else:
        r.text(scene, setting, "Canonical body poses only; no added velocity. Full definitions: review_metrics.json",
               40, 634, 14, materials["cyan"])
    r.text(scene, setting, DIAGNOSTIC_NOTICE, 40, 663, 17, materials["warning"])
    r.text(scene, setting, "Prescribed contact-fit poses only; no wind, impact, ground-friction or foot-hinge dynamics.",
           40, 693, 14, materials["muted"])
    scene["walking_prototype"] = key
    scene["walking_render_frame_end"] = trajectory["render_frame_end"]
    scene["walking_closing_frame"] = len(trajectory["frames"])
    scene["still_output"] = f"walking_{key}.png"
    scene["still_frame"] = max(1, trajectory["render_frame_end"] // 2)
    scene["same_physical_scale"] = True
    return scene


def frame_scene(r, records, manifests, materials):
    key = "C" if "C" in records else next(iter(records))
    record, manifest = records[key], manifests[key]
    selected = [instance["name"] for instance in manifest["instances"]
                if instance["part_id"] == "P_FRAME_RIGHT"]
    if len(selected) != 1:
        raise ValueError(f"{key}: expected one actual right frame for the explanatory view")
    scene, setting = create_scene(
        r, "30 | GENERATED FRAME - ACTUAL CAD", world_points(record, selected), 1,
        materials, (370, 165, 1225, 579), Vector((1, -0.18, 0.12)))
    link_selection(r, scene, record, selected, f"{key} | ACTUAL P_FRAME_RIGHT")
    labels(r, scene, setting, materials, f"{key} / PARAMETRIC GENERATED FRAME",
           "ISOLATED ACTUAL CAD PART  |  no new ribs, smoothing geometry or topology claims")
    r.text(scene, setting, "P_FRAME_RIGHT", 44, 232, 23, materials["text"])
    structure = manifest["design"]["structure"]
    r.text(scene, setting, f"Plate: {structure['plate_thickness_mm']:g} mm",
           44, 278, 19, materials["muted"])
    r.text(scene, setting, f"Rib width: {structure['rib_width_mm']:g} mm",
           44, 310, 19, materials["muted"])
    r.text(scene, setting, "Geometry from FreeCAD, not a visual effect.", 44, 375, 14, materials["cyan"])
    r.text(scene, setting, r.C_NOTICE, 40, 601, 17, materials["cyan"])
    scene["still_output"] = f"frame_{key}.png"
    return scene


def save_snapshot(r, manifests, fingerprints, records, pending, native, walking_records):
    for key, manifest in manifests.items():
        block = bpy.data.texts.new(f"SOURCE | assembly_{key}.json")
        block.write(json.dumps(manifest, indent=2))
    block = bpy.data.texts.new("SOURCE | fingerprints.json")
    block.write(json.dumps(fingerprints, indent=2))
    configuration = bpy.data.texts.new("SOURCE | kinematic_config.json")
    configuration.write(json.dumps({name: r.CONFIG[name] for name in ("linkage", "hardware")}, indent=2))
    metadata = {
        "status": STATUS, "pending_designs": pending,
        "designs": {key: {
            **facts(manifests[key]), **record["timing"],
            "swept_bounds_m": record["bounds"].tolist(),
            "presentation_offset_m": list(record["root"].location),
        } for key, record in records.items()},
        "source_fingerprints": fingerprints,
        "renderer_sha256": r.sha256(Path(r.__file__)),
        "system_helper_sha256": r.sha256(Path(__file__)),
        "walking": {key: {
            "render_frame_end": value["trajectory"]["render_frame_end"],
            "supplied_frames": len(value["trajectory"]["frames"]),
            "video_seconds": value["trajectory"]["video_seconds"],
            "physical_seconds": value["trajectory"]["physical_seconds"],
            "time_scale": value["trajectory"]["time_scale"],
            "provenance": value["provenance"],
            "residual_target_pass": value["trajectory"]["validation"]["strict_3mm_contact_target_pass"],
            "rotation_representation": value["collection"]["rotation_representation"],
            "shared_axis_count": value["collection"]["shared_axis_count"],
        } for key, value in walking_records.items()},
    }
    block = bpy.data.texts.new("MODEL | metadata.json")
    block.write(json.dumps(metadata, indent=2))
    notes = bpy.data.texts.new("READ ME | FROZEN INPUT ENGINEERING REVIEW")
    notes.write(
        STATUS + "\n" + DIAGNOSTIC_NOTICE + "\n" + r.OPERATION_NOTICE + "\n" + LIMITATION + "\n\n"
        "Only the approved belt/distributed-transmission assemblies are present.\n"
        "Legacy single-stage/one-end previews were archived outside the final output directory.\n"
        "Exact source meshes, instance IDs and transforms are retained in metre coordinates.\n"
        "Overview uses one common orthographic scale and static root translations only.\n"
        "In-place cycles use a prescribed input magnitude of 120 rotor RPM.\n"
        "High-reduction designs therefore have longer, slower crank cycles.\n"
        "Source motion.speed is used without alteration; every frame is verified against core.animated_transform.\n"
        "Native F-curve repeat modifiers extend baked cycles; no Python handlers/drivers are used.\n"
        "Camera fits use swept CAD bounding boxes over each complete baked cycle.\n"
        "Drive/frame views explicitly omit surrounding parts. Exploded views use illustrative offsets,\n"
        "not validated insertion paths. No mechanical geometry is changed.\n"
        "A's purchased belt is a static dimensional envelope; pulley rotations are prescribed.\n"
        "Walking uses body_matrix @ core.animated_transform for every instance and supplied frame.\n"
        "The canonical body pose is baked once on a parent Empty. Shaft/crank objects retain\n"
        "their original local transforms under shared body-X pivots with unwrapped speed*theta Euler angles.\n"
        "B's -240 degree input step per video frame must not be replaced by the +120 degree shortest path.\n"
        "All supplied frames and quarter-subframe shaft/crank directions and ratios are checked.\n"
        "Large unwrapped Euler angles incur float32 storage rounding, recorded in the validation report.\n"
        "walk_*.json contains N+1 samples; videos render only frames 1..N for exact durations.\n"
        "Walking does not repeat an in-place loop or add a separate forward speed.\n"
        "The 3 mm material-anchor target FAILED for A/B/C. Full stance-period definitions,\n"
        "cumulative paths and fixed-pose COG +/-5 mm sensitivities are preserved.\n"
        "Displayed wind-COP minima use 5 m/s wind in +/-Y, not the worst 8 m/s case.\n"
        "Positive nominal geometric margins are not proof of all-phase or physical stability.\n"
        "The model's 0.25 mm near-contact band and >=2% load threshold can leave only\n"
        "two active feet for A/B or one for C; practical tripod stability is not established.\n"
        "B's 8X playback can alias fast rotor appearance at 24 fps; supplied poses are not changed.\n"
        "Native render and file-browser paths are relative; there are no external dependencies.\n"
        "This is a review first cut, not a verified wind-powered machine or manufacturing release.\n")
    empty = bpy.data.scenes.get("Scene")
    if empty is not None:
        bpy.data.scenes.remove(empty)
    for scene in bpy.data.scenes:
        bpy.context.window.scene = scene
        scene.frame_set(1)
    bpy.context.window.scene = bpy.data.scenes["00 | SYSTEM - ACTUAL-SCALE COMPARISON"]
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.region_3d.view_perspective = "CAMERA"
                area.spaces.active.shading.color_type = "MATERIAL"
                area.spaces.active.overlay.show_extras = False
    r.prepare_native_paths()
    bpy.context.preferences.filepaths.save_version = 0
    native.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(native), compress=True)
    if native.stat().st_size >= 100_000_000:
        raise RuntimeError("System snapshot exceeds the 100 MB native-file limit")
    r.log(f"System native ready: {native.name} ({native.stat().st_size / 1_000_000:.2f} MB)")
    return metadata


def build(r):
    manifests, libraries, fingerprints, pending = available_inputs(r)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    materials = r.create_materials()
    records = {}
    for key, manifest in manifests.items():
        timing = bake_timing(manifest, r.FPS)
        per_instance = {}
        collection, root, objects = r.build_design(
            key, manifest, libraries[key], materials, frame_count=timing["frame_count"],
            display_name=TITLES[key], offset=(0, 0, 0), loop=True, bounds=per_instance,
            source_fingerprints={
                **fingerprints[key], "core_sha256": fingerprints["core_sha256"],
                "kinematic_config_sha256": fingerprints["kinematic_config_sha256"],
            })
        records[key] = {
            "collection": collection, "root": root, "objects": objects, "timing": timing,
            "instance_bounds": per_instance, "bounds": union_boxes(per_instance.values()),
        }
    layout_at_actual_scale(r, records)
    overview_scene(r, records, manifests, materials, pending)
    drive_overview_scene(r, records, manifests, materials)
    for key in records:
        hero_scene(r, key, records[key], manifests[key], materials)
        drivetrain_scene(r, key, records[key], manifests[key], materials)
        for side in ("left", "right"):
            drivetrain_side_scene(r, key, records[key], manifests[key], materials, side)
    frame_scene(r, records, manifests, materials)
    connection_scene(r, records["A"], manifests["A"], materials)
    exploded_scene(r, records["A"], manifests["A"], materials)
    walking_records = {}
    for key in records:
        trajectory, provenance = read_walking_trajectory(r, key)
        collection, objects, bounds = bake_walking_collection(
            r, manifests[key], records[key]["objects"], trajectory, provenance)
        walking_records[key] = {
            "trajectory": trajectory, "provenance": provenance, "collection": collection,
            "objects": objects, "bounds": bounds,
        }
    common_walk_points = np.vstack([
        json.loads(value["collection"]["camera_extreme_points_json"])
        for value in walking_records.values()
    ])
    for key, value in walking_records.items():
        walking_scene(r, key, value, common_walk_points, materials)
    native, _, _ = locations(r)
    save_snapshot(r, manifests, fingerprints, records, pending, native, walking_records)
    return manifests, libraries, fingerprints


def metadata():
    return json.loads(bpy.data.texts["MODEL | metadata.json"].as_string())


def current_input_match(r, info):
    manifests, libraries, fingerprints = r.read_inputs(info["designs"], profile="system")
    before = {key: value for key, value in info["source_fingerprints"].items()
              if key != "design_config_sha256"}
    after = {key: value for key, value in fingerprints.items()
             if key != "design_config_sha256"}
    if before != after:
        raise RuntimeError("Frozen mechanical inputs changed; rebuild before rendering")
    return manifests, libraries, fingerprints


def current_walking_match(r, info):
    trajectories = {}
    for key, entry in info["walking"].items():
        trajectory, provenance = read_walking_trajectory(r, key)
        if provenance != entry["provenance"]:
            raise RuntimeError(f"{key}: canonical walking input changed after native baking")
        trajectories[key] = trajectory
    return trajectories


def write_review_metrics(r, trajectories):
    _, media, _ = locations(r)
    media.mkdir(parents=True, exist_ok=True)
    values = {
        "scope": "Lead-provided review metrics, not physical validation",
        "failure_policy": "Failed 3 mm targets remain failures; no pose or geometry is adjusted",
        "prototypes": {key: {
            "assembly_sha256": trajectory["assembly_sha256"],
            "geometry_sha256": trajectory["geometry_sha256"],
            "core_sha256": trajectory["core_sha256"],
            "video_seconds": trajectory["video_seconds"],
            "physical_seconds": trajectory["physical_seconds"],
            "time_scale": trajectory["time_scale"],
            "render_frame_end": trajectory["render_frame_end"],
            "validation": trajectory["validation"],
            "contact_episodes": trajectory["contact_episodes"],
            "method": trajectory["method"],
            "limitations": trajectory["limitations"],
        } for key, trajectory in trajectories.items()},
    }
    (media / "review_metrics.json").write_text(json.dumps(values, indent=2) + "\n")


def preview_stills(r, samples):
    info = metadata()
    current_input_match(r, info)
    trajectories = current_walking_match(r, info)
    _, media, _ = locations(r)
    media.mkdir(parents=True, exist_ok=True)
    overview = bpy.data.scenes["00 | SYSTEM - ACTUAL-SCALE COMPARISON"]
    r.render_image(overview, media / "comparison.png", 1, samples=samples)
    for scene in sorted(bpy.data.scenes, key=lambda item: item.name):
        name = scene.get("still_output")
        if name:
            r.render_image(scene, media / name, scene.get("still_frame", 1), samples=samples)
            r.log(f"Review still: {name}")
    r.run_command([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-filter_complex_threads", "4",
        "-i", media / "drivetrain_A_left.png", "-i", media / "drivetrain_A_right.png",
        "-i", media / "drivetrain_B.png", "-i", media / "drivetrain_C.png",
        "-filter_complex",
        "[0:v]scale=640:360[a];[1:v]scale=640:360[b];[2:v]scale=640:360[c];"
        "[3:v]scale=640:360[d];[a][b][c][d]xstack=inputs=4:layout=0_0|640_0|0_360|640_360[v]",
        "-map", "[v]", "-frames:v", "1", media / "drivetrain_detail.png",
    ])
    write_review_metrics(r, trajectories)
    current_input_match(r, info)
    current_walking_match(r, info)


def render_sequence(r, scene, count, label, work_dir, destination, samples, keep_frames):
    info = metadata()
    current_input_match(r, info)
    current_walking_match(r, info)
    native, _, _ = locations(r)
    directory = work_dir / f"{r.sha256(native)[:12]}-{label}-{count}-{samples}"
    directory.mkdir(parents=True, exist_ok=True)
    for frame in range(1, count + 1):
        path = directory / f"{frame:04d}.png"
        if not path.is_file():
            r.render_image(scene, path, frame, video=True, samples=samples)
        if frame == 1 or frame % 48 == 0 or frame == count:
            r.log(f"{label}: {frame}/{count}")
    current_input_match(r, info)
    current_walking_match(r, info)
    r.encode_sequence(directory, destination, frame_count=count,
                      comment=f"{STATUS}. {r.OPERATION_NOTICE}. {LIMITATION}. {scene.name}")
    if not keep_frames:
        r.remove_owned_frames(directory, count)
    return destination


def concatenate_movies(r, movies, destination, work_dir, name):
    listing = work_dir / f"{name}-concat.txt"
    listing.write_text("\n".join(
        "file '" + path.as_posix().replace("'", "'\\''") + "'" for path in movies) + "\n")
    r.run_command(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                   "-f", "concat", "-safe", "0", "-i", listing,
                   "-c", "copy", "-movflags", "+faststart", destination])
    listing.unlink()


def make_gif(r, source, destination, *, combined=False):
    modes = ((600, 6, 96), (480, 6, 64)) if combined else ((600, 10, 128), (480, 8, 96))
    for width, fps, colors in modes:
        r.run_command([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-filter_threads", "4",
            "-i", source, "-vf",
            f"fps={fps},scale={width}:-1:flags=lanczos,split[a][b];"
            f"[a]palettegen=max_colors={colors}:stats_mode=diff[p];"
            "[b][p]paletteuse=dither=bayer:bayer_scale=4",
            "-loop", "0", destination,
        ])
        if destination.stat().st_size <= 6_000_000:
            return
        r.log(f"{destination.name}: reducing preview resolution to meet the 6 MB GIF limit")
    raise RuntimeError(f"GIF still exceeds 6 MB: {destination}")


def videos(r, args, include_motion=True, include_walking=True):
    info = metadata()
    trajectories = current_walking_match(r, info)
    _, media, _ = locations(r)
    media.mkdir(parents=True, exist_ok=True)
    work_dir = args.work_dir or Path(tempfile.mkdtemp(prefix="ver3-final-render-"))
    if work_dir.resolve().is_relative_to(r.ROOT):
        raise ValueError("Raw rendered frames must stay outside the repository")
    work_dir.mkdir(parents=True, exist_ok=True)
    if include_motion:
        pieces = []
        for scene_name, label in (
            ("00 | SYSTEM - ACTUAL-SCALE COMPARISON", "operation-comparison"),
            ("05 | ALL DISTRIBUTED DRIVES", "operation-drives"),
        ):
            pieces.append(render_sequence(
                r, bpy.data.scenes[scene_name], 144, label, work_dir,
                work_dir / f"{label}.mp4", args.video_samples, args.keep_frames))
        concatenate_movies(r, pieces, media / "operation.mp4", work_dir, "operation")
        render_sequence(r, bpy.data.scenes["50 | A EXPLODED - NOT AN INSERTION PATH"],
                        120, "exploded", work_dir, media / "exploded.mp4",
                        args.video_samples, args.keep_frames)
        for path in pieces:
            path.unlink()
    if include_walking:
        clips = []
        for key, trajectory in trajectories.items():
            destination = media / f"walking_{key}.mp4"
            render_sequence(r, bpy.data.scenes[f"60{key} | CANONICAL WALKING"],
                            trajectory["render_frame_end"], f"walking-{key}", work_dir,
                            destination, args.video_samples, args.keep_frames)
            make_gif(r, destination, media / f"walking_{key}.gif")
            clips.append(destination)
        combined = work_dir / "walk-preview.mp4"
        concatenate_movies(r, clips, combined, work_dir, "walk-preview")
        make_gif(r, combined, media / "walk_preview.gif", combined=True)
        combined.unlink()
        write_review_metrics(r, trajectories)
    r.log("Requested review movies encoded; no raw frame dumps were written to the repository")


def validate(r, inputs=None, require_media=True):
    native, media, report_path = locations(r)
    info = metadata()
    manifests, libraries, fingerprints = inputs or current_input_match(r, info)
    if any(obj.animation_data and obj.animation_data.drivers for obj in bpy.data.objects):
        raise AssertionError("System native contains animation drivers")
    if bpy.app.handlers.frame_change_pre or bpy.app.handlers.frame_change_post:
        raise AssertionError("System native needs a frame handler")
    if any(block.use_module for block in bpy.data.texts):
        raise AssertionError("System native contains an automatic Python text module")
    report = {
        "validated_utc": datetime.now(timezone.utc).isoformat(),
        "status": STATUS,
        "production_video_rendered": False,
        "available_designs": list(info["designs"]),
        "pending_designs": info["pending_designs"],
        "legacy_single_stage_or_one_end_preview_included": False,
        "source_fingerprints": fingerprints,
        "source_renderer_sha256": r.sha256(Path(r.__file__)),
        "system_helper_sha256": r.sha256(Path(__file__)),
        "reopened_with_scripts_disabled": True,
        "native_portability": r.validate_native_portability(),
        "designs": {},
        "camera_fit_verified": True,
    }
    for scene in bpy.data.scenes:
        bpy.context.window.scene = scene
        scene.frame_set(1)
        scene.view_layers[0].update()
        left, top, right, bottom = scene["fit_region_px"]
        for point in json.loads(scene["fit_points_world_json"]):
            x, y = r.project(scene, point)
            if not left - 1 <= x <= right + 1 or not top - 1 <= y <= bottom + 1:
                raise AssertionError(f"Swept CAD bounds escape camera region: {scene.name}: {x}, {y}")
    for key, manifest in manifests.items():
        entry = info["designs"][key]
        canonical = {obj["instance_id"]: obj for obj in bpy.data.objects
                     if obj.get("canonical_instance") and obj["design_id"] == key}
        if set(canonical) != {instance["name"] for instance in manifest["instances"]}:
            raise AssertionError(f"{key}: canonical IDs changed")
        root = bpy.data.objects[f"{key}::PRESENTATION_OFFSET_ONLY"]
        if root.animation_data or not np.allclose(root.scale, (1, 1, 1)):
            raise AssertionError(f"{key}: model scale or forward locomotion was added")
        vertex_error = 0
        for part_id, geometry in libraries[key].items():
            mesh = bpy.data.meshes[f"{key}::CAD::{part_id}"]
            values = np.empty(len(mesh.vertices) * 3)
            mesh.vertices.foreach_get("co", values)
            values = values.reshape((-1, 3)) / r.MM
            expected = np.asarray(geometry["vertices"])
            if values.shape != expected.shape:
                raise AssertionError(f"{key}/{part_id}: changed vertex count")
            error = float(np.max(np.abs(values - expected)))
            vertex_error = max(vertex_error, error)
            if error > 0.0001 or [list(face.vertices) for face in mesh.polygons] != geometry["triangles"]:
                raise AssertionError(f"{key}/{part_id}: changed CAD mesh")
        scene = bpy.data.scenes[f"1{key} | {TITLES[key]}"]
        bpy.context.window.scene = scene
        maximum_position, maximum_rotation, first = 0, 0, {}
        for frame in range(1, entry["frame_count"] + 1):
            scene.frame_set(frame)
            theta = math.tau * (frame - 1) / entry["period_frames"]
            for instance in manifest["instances"]:
                obj = canonical[instance["name"]]
                expected = np.asarray(r.matrix_metres(r.animated_transform(instance, theta, manifest["design"])))
                actual = np.asarray(obj.matrix_local)
                position_error = float(np.max(np.abs(expected[:3, 3] - actual[:3, 3]))) / r.MM
                rotation_error = float(np.max(np.abs(expected[:3, :3] - actual[:3, :3])))
                maximum_position = max(maximum_position, position_error)
                maximum_rotation = max(maximum_rotation, rotation_error)
                if position_error > 0.001 or rotation_error > 0.00001:
                    raise AssertionError(f"{key}: authoritative pose mismatch: {obj.name}/{frame}")
                if frame == 1:
                    first[obj.name] = actual.copy()
                if frame == entry["frame_count"] and not np.allclose(first[obj.name], actual, atol=1e-6, rtol=0):
                    raise AssertionError(f"{key}: unclosed crank cycle: {obj.name}")
            if frame == 1 or frame % 240 == 0 or frame == entry["frame_count"]:
                r.log(f"System reopen verification {key}: {frame}/{entry['frame_count']}")
        moving = 0
        for obj in canonical.values():
            if obj.modifiers:
                raise AssertionError(f"{obj.name}: mechanical geometry modifier found")
            curves = r.curves_for(obj)
            if curves:
                moving += 1
            for curve in curves:
                if len(curve.keyframe_points) != entry["frame_count"]:
                    raise AssertionError(f"{obj.name}: incomplete bake")
                if len(curve.modifiers) != 1 or curve.modifiers[0].type != "CYCLES":
                    raise AssertionError(f"{obj.name}: missing native repeat modifier")
        report["designs"][key] = {
            **entry, "moving_objects": moving, "mesh_datablocks": len(libraries[key]),
            "max_vertex_error_mm": vertex_error, "max_position_error_mm": maximum_position,
            "max_rotation_matrix_error": maximum_rotation, "full_cycle_closes": True,
        }
    overview = bpy.data.scenes["00 | SYSTEM - ACTUAL-SCALE COMPARISON"]
    bpy.context.window.scene = overview
    for frame in sorted({1, overview.frame_end, *(entry["frame_count"] * 2 - 1
                                                for entry in info["designs"].values())}):
        overview.frame_set(frame)
        for key, manifest in manifests.items():
            theta = math.tau * (frame - 1) / info["designs"][key]["period_frames"]
            for instance in manifest["instances"]:
                obj = bpy.data.objects[f"{key}::{instance['name']}"]
                expected = r.matrix_metres(r.animated_transform(instance, theta, manifest["design"]))
                if not np.allclose(np.asarray(obj.matrix_local), np.asarray(expected), atol=1e-6, rtol=0):
                    raise AssertionError(f"{obj.name}: native repeated-cycle timing mismatch at {frame}")
    report["native_repeated_cycles_verified"] = True
    report["comparison_layout"] = validate_comparison_notes(r, overview, manifests)
    report["canonical_instances"] = sum(len(m["instances"]) for m in manifests.values())
    trajectories = current_walking_match(r, info)
    report["walking"] = {}
    for key, trajectory in trajectories.items():
        bpy.context.window.scene = bpy.data.scenes[f"60{key} | CANONICAL WALKING"]
        objects = {obj["instance_id"]: obj for obj in bpy.data.objects
                   if obj.get("walking_instance") and obj["design_id"] == key}
        result = validate_walking_bake(r, manifests[key], objects, trajectory)
        if bpy.context.scene.frame_end != trajectory["render_frame_end"]:
            raise AssertionError(f"{key}: walking render range incorrectly includes the closure endpoint")
        result["strict_3mm_contact_target_pass"] = trajectory["validation"]["strict_3mm_contact_target_pass"]
        result["fixed_pose_sensitivity"] = trajectory["validation"]["fixed_pose_sensitivity"]
        report["walking"][key] = result
    exploded = bpy.data.scenes["50 | A EXPLODED - NOT AN INSERTION PATH"]
    bpy.context.window.scene = exploded
    for frame in (1, 29, 49, 65, 101, 121):
        exploded.frame_set(frame)
        for instance in manifests["A"]["instances"]:
            obj = bpy.data.objects[f"EXPLODE::{instance['name']}"]
            expected = r.matrix_metres(instance["transform"])
            expected.translation += exploded_translation(
                r, instance, frame, exploded["exploded_middle_x_m"], exploded["exploded_bays_mm"])
            if not np.allclose(np.asarray(obj.matrix_world), np.asarray(expected), atol=1e-6, rtol=0):
                raise AssertionError(f"Illustrative explosion differs from its declared offsets: {obj.name}/{frame}")
    report["exploded_stages_verified"] = [1, 29, 49, 65, 101, 121]
    required_names = [
        "comparison.png", "hero_A.png", "hero_B.png", "hero_C.png",
        "drivetrain_detail.png", "rex_connection.png", "exploded_A.png", "frame_C.png",
        "operation.mp4", "exploded.mp4", "walking_A.mp4", "walking_B.mp4", "walking_C.mp4",
        "walking_A.gif", "walking_B.gif", "walking_C.gif", "walk_preview.gif", "review_metrics.json",
    ]
    missing = [name for name in required_names if not (media / name).is_file()]
    if require_media and missing:
        raise RuntimeError(f"Final review media still missing: {missing}")
    report["missing_media"] = missing
    report["production_video_rendered"] = require_media and not missing
    report["media_refresh_pending"] = not require_media
    report["assets"] = {}
    for path in [native] + sorted(p for p in media.iterdir() if p.is_file()):
        size = path.stat().st_size
        if size >= 100_000_000:
            raise AssertionError(f"Asset exceeds 100 MB: {path}")
        item = {"bytes": size, "sha256": r.sha256(path)}
        if path.suffix == ".png":
            with path.open("rb") as stream:
                header = stream.read(24)
            if header[:8] != b"\x89PNG\r\n\x1a\n" or struct.unpack(">II", header[16:24]) != (1280, 720):
                raise AssertionError(f"Unexpected still dimensions or format: {path}")
            item["dimensions"] = [1280, 720]
        if path.suffix in (".mp4", ".gif"):
            result = subprocess.run([
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration,size:stream=codec_name,width,height,nb_frames,r_frame_rate,pix_fmt",
                "-of", "json", str(path)], check=True, capture_output=True, text=True)
            probe = json.loads(result.stdout)
            item["ffprobe"] = probe
            stream = probe["streams"][0]
            if path.suffix == ".mp4":
                expected_count = (288 if path.name == "operation.mp4" else
                                  120 if path.name == "exploded.mp4" else
                                  trajectories[path.stem[-1]]["render_frame_end"])
                if (stream["codec_name"] != "h264" or stream["pix_fmt"] != "yuv420p" or
                        (stream["width"], stream["height"]) != (960, 540) or
                        stream["r_frame_rate"] != "24/1" or int(stream["nb_frames"]) != expected_count or
                        abs(float(probe["format"]["duration"]) - expected_count / 24) > 0.001):
                    raise AssertionError(f"Invalid review movie timing or codec: {path}")
            elif stream["codec_name"] != "gif" or not 480 <= stream["width"] <= 640 or size > 6_000_000:
                raise AssertionError(f"GIF does not meet preview limits: {path}")
            subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"],
                           check=True, capture_output=True)
            item["complete_decode_verified"] = True
        report["assets"][str(path.relative_to(r.ROOT))] = item
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    r.log(f"Review geometry/poses verified; physical/contact target failures retained: {report_path.name}")
    return report


def run(r, args):
    native, _, _ = locations(r)
    captured = None
    if args.phase in ("preview", "build", "all"):
        captured = build(r)
    if args.phase == "build":
        return
    if not native.is_file():
        raise FileNotFoundError("Build the frozen-input review native before rendering or validation")
    bpy.ops.wm.open_mainfile(filepath=str(native), use_scripts=False)
    if args.phase in ("preview", "stills", "all"):
        preview_stills(r, args.samples)
    if args.phase in ("all", "video", "motion", "walking"):
        videos(r, args, include_motion=args.phase != "walking",
               include_walking=args.phase != "motion")
    if args.phase in ("preview", "all", "validate"):
        bpy.ops.wm.open_mainfile(filepath=str(native), use_scripts=False)
        validate(r, captured, require_media=args.phase != "preview")
