"""Derive forward travel from stance anchors on a plane, not an arbitrary slide."""

import argparse
import csv
import hashlib
import json
import math

import numpy as np

from core import CONFIG, ROOT, OUT, animated_transform, dump, foot_centers, walking_transform
from mechanics import FootGeometry, MassModel

parser = argparse.ArgumentParser()
parser.add_argument("--only", choices=["A", "B", "C"])
args = parser.parse_args()


def derive(manifest):
    design = manifest["design"]
    ident = design["id"]
    manifest_path = OUT/f"assembly_{ident}.json"
    if json.loads(manifest_path.read_text()) != manifest:
        raise RuntimeError("Assembly changed before walking derivation began")
    source_paths = {
        "assembly_sha256": manifest_path,
        "geometry_sha256": ROOT/manifest["cad_meshes"],
        "core_sha256": ROOT/"scripts/ver3/core.py",
    }
    source_hashes = {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in source_paths.items()}
    fps, input_rpm, cycles = 24, 120, 3
    scale = {"A": 1, "B": 8, "C": 2}[ident]
    physical_seconds = cycles*design["ratio"]/input_rpm*60
    video_seconds = physical_seconds/scale
    video_intervals = round(video_seconds*fps)
    steps = cycles*1440
    if steps % video_intervals:
        raise RuntimeError("Video timing must fit the common0.25deg comparison grid")
    substeps = steps//video_intervals
    mass = MassModel(manifest)
    mass_error = mass.verify()
    geometry = FootGeometry(manifest)
    anchors, local_anchors = {}, {}
    previous_contacts = []
    previous_rotation = np.eye(3)
    previous_translation = np.zeros(2)
    previous_feet = None
    previous_normal = None
    previous_weights = np.ones(6)/6
    frames, diagnostics = [], []
    sample_rows, episodes, active_episodes = [], [], {}
    sensitivity = {name: {"inside_samples": 0, "minimum_margin_mm": float("inf")} for name in
                   ("cog_x_minus5", "cog_x_plus5", "cog_y_minus5", "cog_y_plus5",
                    "wind_y_minus3", "wind_y_plus3", "wind_y_minus5", "wind_y_plus5",
                    "wind_y_minus8", "wind_y_plus8")}
    worst_drift = 0.0
    worst_gap = 0.0
    worst_tilt = 0.0
    minimum_margin = float("inf")
    minimum_contacts = 6
    opposite_samples = []
    yaw = 0.0
    for step in range(steps+1):
        theta = 2*math.pi*cycles*step/steps
        center = mass.at(theta)
        solutions = geometry.options(theta, center, previous_normal, tolerance=0.25)
        if not solutions:
            raise RuntimeError(f"{ident}: no geometrically supported pose at crank{math.degrees(theta)%360:.3f}deg")
        def score(solution):
            change = 0 if previous_normal is None else float(np.linalg.norm(solution["normal"]-previous_normal))
            shared = len(set(solution["contacts"]) & set(previous_contacts))
            return (not solution["same_direction"], len(solution["contacts"]) < 3,
                    change+0.0001*solution["tilt_deg"], -shared, -solution["support_margin_mm"])
        chosen = min(solutions, key=score)
        normal, base_rotation = chosen["normal"], chosen["rotation"]
        feet = foot_centers(design, theta)
        weights, contact_centers = geometry.normal_loads(chosen, center, feet)
        contacts = sorted(contact_centers)
        common = [i for i in contacts if i in previous_contacts]
        if len(common) >= 2:
            current = np.array([base_rotation@(feet[i]+local_anchors[i]) for i in common])[:, :2]
            target = np.array([anchors[i] for i in common])
            fit_weights = weights[common]/weights[common].sum()
            c0 = current-np.sum(current*fit_weights[:, None], axis=0)
            t0 = target-np.sum(target*fit_weights[:, None], axis=0)
            sine = float(np.sum(fit_weights*(c0[:, 0]*t0[:, 1]-c0[:, 1]*t0[:, 0])))
            cosine = float(np.sum(fit_weights*np.sum(c0*t0, axis=1)))
            yaw = math.atan2(sine, cosine)
        yaw_rotation = np.array([[math.cos(yaw), -math.sin(yaw), 0],
                                 [math.sin(yaw), math.cos(yaw), 0], [0, 0, 1]])
        rotation = yaw_rotation@base_rotation
        if common:
            offsets = np.array([anchors[i]-(rotation@(feet[i]+local_anchors[i]))[:2] for i in common])
            translation_xy = np.average(offsets, axis=0, weights=weights[common])
        elif previous_feet is not None:
            # Carry the outgoing stance through the handoff, then set new anchors.
            changes = np.array([(rotation@(feet[i]+local_anchors[i]))[:2]
                                -(previous_rotation@(previous_feet[i]+local_anchors[i]))[:2]
                                for i in previous_contacts])
            delta = np.average(changes, axis=0, weights=previous_weights[previous_contacts])
            translation_xy = previous_translation-delta
        else:
            translation_xy = np.zeros(2)
        translation_z = -chosen["min_height"]+0.02
        body = np.eye(4)
        body[:3, :3] = rotation
        body[:3, 3] = [*translation_xy, translation_z]
        for index in list(active_episodes):
            if index not in contacts:
                episodes.append(active_episodes.pop(index))
        for index in contacts:
            material = (rotation@(feet[index]+local_anchors[index]))[:2]+translation_xy if index in local_anchors else None
            if index not in previous_contacts:
                local_anchors[index] = contact_centers[index]
                anchors[index] = (rotation@(feet[index]+local_anchors[index]))[:2]+translation_xy
                material = anchors[index].copy()
                active_episodes[index] = dict(foot=index, start_theta=theta, end_theta=theta,
                                             start_body_y=float(translation_xy[1]), end_body_y=float(translation_xy[1]),
                                             max_anchor_drift_mm=0.0, horizontal_path_mm=0.0,
                                             last_material_xy=material.tolist(),
                                             material_point_body_relative_to_F=local_anchors[index].tolist())
            drift = np.linalg.norm(material-anchors[index])
            worst_drift = max(worst_drift, float(drift))
            episode = active_episodes[index]
            episode["horizontal_path_mm"] += float(np.linalg.norm(material-episode["last_material_xy"]))
            episode["last_material_xy"] = material.tolist()
            episode["max_anchor_drift_mm"] = max(episode["max_anchor_drift_mm"], float(drift))
            episode["end_theta"], episode["end_body_y"] = theta, float(translation_xy[1])
        if not chosen["same_direction"]:
            opposite_samples.append(math.degrees(theta)%360)
        worst_gap = max(worst_gap, chosen["max_contact_gap_mm"])
        worst_tilt = max(worst_tilt, chosen["tilt_deg"])
        minimum_margin = min(minimum_margin, chosen["support_margin_mm"])
        minimum_contacts = min(minimum_contacts, len(contacts))
        equations = chosen["support_equations"]
        for name, delta in (("cog_x_minus5", [-5, 0, 0]), ("cog_x_plus5", [5, 0, 0]),
                            ("cog_y_minus5", [0, -5, 0]), ("cog_y_plus5", [0, 5, 0])):
            q = (base_rotation@(center+delta))[:2]
            margin = float((-(equations[:, :2]@q+equations[:, 2])).min())
            sensitivity[name]["inside_samples"] += int(margin >= 0)
            sensitivity[name]["minimum_margin_mm"] = min(sensitivity[name]["minimum_margin_mm"], margin)
        rotor_center = np.array([CONFIG["linkage"]["bay_count"]*CONFIG["linkage"]["bay_pitch"]/2,
                                 design["axes"]["I"][0], design["axes"]["I"][1]+CONFIG["linkage"]["crank_height"]])
        rotor_height = float(base_rotation[2]@rotor_center-chosen["min_height"])
        projected_cog = (base_rotation@center)[:2]
        area = 2*design["rotor"]["radius"]*design["rotor"]["span"]/1e6
        weight = mass.mass_g/1000*CONFIG["assumptions"]["gravity_m_s2"]
        for speed in (3, 5, 8):
            force = 0.5*CONFIG["assumptions"]["air_density_kg_m3"]*area*CONFIG["assumptions"]["drag_coefficient"]*speed**2
            shift = force*rotor_height/weight
            for sign, word in ((-1, "minus"), (1, "plus")):
                name = f"wind_y_{word}{speed}"
                q = projected_cog+np.array([0, sign*shift])
                margin = float((-(equations[:, :2]@q+equations[:, 2])).min())
                sensitivity[name]["inside_samples"] += int(margin >= 0)
                sensitivity[name]["minimum_margin_mm"] = min(sensitivity[name]["minimum_margin_mm"], margin)
        frame = dict(frame=step//substeps+1, theta=theta, body_matrix=body.tolist(),
                     contacts=contacts, ground_z=0,
                     normal_load_fractions=weights.tolist(), near_contacts=chosen["contacts"],
                     contact_gap_mm=chosen["max_contact_gap_mm"],
                     support_margin_mm=chosen["support_margin_mm"])
        if step % substeps == 0:
            frames.append(frame)
        diagnostics.append((float(body[0, 3]), float(body[1, 3]), float(body[2, 3])))
        sample_rows.append([theta, *weights.tolist(), *normal.tolist(), *body[:3, 3].tolist(),
                            chosen["support_margin_mm"], chosen["max_contact_gap_mm"], len(contacts)])
        previous_rotation, previous_translation = rotation, translation_xy
        previous_feet, previous_contacts, previous_normal = feet, contacts, normal
        previous_weights = weights
    travel = np.array(frames[-1]["body_matrix"])[:3, 3]-np.array(frames[0]["body_matrix"])[:3, 3]
    if abs(travel[1]) < 20:
        raise RuntimeError(f"{ident}: no meaningful contact-derived forward travel: {travel}")
    episodes.extend(active_episodes.values())
    for episode in episodes:
        episode.pop("last_material_xy")
        episode["body_advance_in_episode_mm"] = abs(episode["end_body_y"]-episode["start_body_y"])
        episode["physical_seconds"] = (episode["end_theta"]-episode["start_theta"])/(2*math.pi)*design["ratio"]/input_rpm*60
        episode["partial_at_clip_boundary"] = episode["start_theta"] == 0 or abs(episode["end_theta"]-2*math.pi*cycles) < 1e-9
    worst_episode = max(episodes, key=lambda e: e["max_anchor_drift_mm"])
    for value in sensitivity.values():
        value["inside_fraction"] = value["inside_samples"]/(steps+1)
    with (OUT/f"walk_samples_{ident}.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["theta", *[f"normal_fraction_{i}" for i in range(6)], "normal_x", "normal_y", "normal_z",
                         "body_x", "body_y", "body_z", "support_margin_mm", "near_contact_gap_mm", "loaded_feet"])
        writer.writerows(sample_rows)

    # Floor verification uses actual CAD-derived vertices when an AABB is inconclusive.
    boxes = {}
    for part_id, mesh in geometry.meshes.items():
        vertices = np.array(mesh["vertices"])
        low, high = vertices.min(axis=0), vertices.max(axis=0)
        boxes[part_id] = np.array([[x, y, z] for x in (low[0], high[0])
                                  for y in (low[1], high[1]) for z in (low[2], high[2])])
    minimum_floor = float("inf")
    exact_fallbacks = 0
    for frame in frames:
        for instance in manifest["instances"]:
            matrix = np.array(walking_transform(instance, frame, design))
            part_id = instance["part_id"]
            height = float((boxes[part_id]@matrix[2, :3]+matrix[2, 3]).min())
            if height < 0:
                vertices = np.array(geometry.meshes[part_id]["vertices"])
                height = float((vertices@matrix[2, :3]+matrix[2, 3]).min())
                exact_fallbacks += 1
            minimum_floor = min(minimum_floor, height)
            if height < -0.03:
                raise RuntimeError(f"{ident}: actual CAD part{instance['name']} penetrates floor by{-height:.3f}mm at frame{frame['frame']}")
    if any(hashlib.sha256(path.read_bytes()).hexdigest() != source_hashes[key] for key, path in source_paths.items()):
        raise RuntimeError("Canonical geometry changed during walking derivation; rerun after CAD is frozen")
    return {
        "schema": 1, "prototype": ident, "fps": fps,
        "video_seconds": video_seconds, "physical_seconds": physical_seconds,
        "time_scale": scale, "input_rpm": input_rpm, "crank_cycles": cycles,
        "render_frame_end": video_intervals,
        "frames": frames,
        **source_hashes,
        "validation": {
            "dense_solver_steps": steps+1, "mass_transform_error_mm": mass_error,
            "forward_axis": [0, int(np.sign(travel[1])), 0],
            "forward_travel_mm": abs(float(travel[1])),
            "lateral_drift_mm": float(travel[0]),
            "mean_physical_speed_mm_s": abs(float(travel[1]))/physical_seconds,
            "max_stance_material_anchor_drift_mm": worst_drift,
            "strict_3mm_contact_target_pass": worst_drift <= 3.0,
            "body_advance_per_crank_cycle_mm": abs(float(travel[1]))/cycles,
            "max_single_contact_episode_horizontal_path_mm": max(e["horizontal_path_mm"] for e in episodes),
            "total_material_horizontal_path_all_feet_three_cycles_mm": sum(e["horizontal_path_mm"] for e in episodes),
            "worst_anchor_episode": worst_episode,
            "slip_definition": "Maximum horizontal offset of one persistent material point from its touchdown anchor within one uninterrupted >=2%-weight contact episode, maximized over all feet/three cycles. Horizontal path is accumulated within each episode; it is not the same statistic.",
            "loaded_foot_threshold_fraction": 0.02,
            "max_active_foot_gap_mm": worst_gap,
            "minimum_support_margin_mm": minimum_margin,
            "minimum_active_feet": minimum_contacts,
            "max_body_tilt_deg": worst_tilt,
            "minimum_mesh_floor_clearance_mm": minimum_floor,
            "floor_checked_frames": len(frames),
            "exact_mesh_floor_fallbacks": exact_fallbacks,
            "opposed_stance_direction_sample_count": len(opposite_samples),
            "opposed_stance_angles_deg": sorted(set(round(a, 3) for a in opposite_samples)),
            "finite_contact_tolerance_mm": 0.25,
            "fixed_pose_sensitivity": sensitivity,
        },
        "contact_episodes": episodes,
        "method": "Support poses from actual shoe/sole CAD contact geometry; nonnegative normal-force/moment balance. Horizontal translation/yaw fitted to persistent, load-weighted stance-material anchors with outgoing-contact handoff. No arbitrary forward velocity.",
        "limitations": [
            "Prescribed rotor input and rigid-link kinematics, not wind-powered self-starting or contact dynamics.",
            "0.25mm near-contact tolerance is a numerical/sole-compliance assumption; sole force-deflection and foot-hinge dynamics unmeasured.",
            "The3mm target is an engineering target, not a user requirement or a pass claimed for manufacturing. Failed targets remain reported; links are never stretched to hide residuals.",
            "CG support polygons are necessary geometric checks, not proof of stability of flexible members or passive foot hinges.",
            "Small positive geometric margins do not cover print/assembly/mass uncertainty. The +/-5mm COG and wind-COP sensitivities keep the nominal poses fixed, and exclude yaw dynamics.",
            "No wind force, inertia, impact, rolling contact or ground friction dynamics in the rendered walking scene.",
            "Frames include one closing endpoint; render1 through render_frame_end for the declared video duration.",
        ],
    }


if __name__ == "__main__":
    for ident in [args.only] if args.only else ("A", "B", "C"):
        manifest = json.loads((OUT/f"assembly_{ident}.json").read_text())
        result = derive(manifest)
        dump(OUT/f"walk_{ident}.json", result)
        print(ident, json.dumps(result["validation"], indent=2))
