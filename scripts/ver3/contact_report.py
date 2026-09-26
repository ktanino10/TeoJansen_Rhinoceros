"""Audit all geometrically near feet, independent of the load threshold."""

import hashlib
import json
import math

import numpy as np

from core import ROOT, OUT, dump, foot_centers
from mechanics import FootGeometry

for ident in "ABC":
    manifest = json.loads((OUT/f"assembly_{ident}.json").read_text())
    walk = json.loads((OUT/f"walk_{ident}.json").read_text())
    assembly_hash = hashlib.sha256((OUT/f"assembly_{ident}.json").read_bytes()).hexdigest()
    if walk["assembly_sha256"] != assembly_hash:
        raise RuntimeError(f"{ident}: walking source is stale; regenerate before contact audit")
    if walk["geometry_sha256"] != hashlib.sha256((ROOT/manifest["cad_meshes"]).read_bytes()).hexdigest():
        raise RuntimeError(f"{ident}: contact geometry differs from the walking source")
    geometry = FootGeometry(manifest)
    active, episodes = {}, []
    minimum_count, maximum_gap = 6, 0.0
    for frame in walk["frames"]:
        matrix = np.array(frame["body_matrix"])
        rotation, translation = matrix[:3, :3], matrix[:3, 3]
        centers = foot_centers(manifest["design"], frame["theta"])
        contacts = []
        for index, center in enumerate(centers):
            world = (geometry.vertices+center)@rotation.T+translation
            gap = float(world[:, 2].min())
            if gap > 0.270001:
                if index in active:
                    episodes.append(active.pop(index))
                continue
            contacts.append(index)
            maximum_gap = max(maximum_gap, gap)
            if index not in active:
                local = geometry.vertices[world[:, 2] <= gap+1e-6].mean(axis=0)
                material = rotation@(center+local)+translation
                active[index] = dict(foot=index, start_frame=frame["frame"], end_frame=frame["frame"],
                                     start_theta=frame["theta"], end_theta=frame["theta"],
                                     local_material_point=local.tolist(), anchor_xy=material[:2].tolist(),
                                     last_xy=material[:2].tolist(), max_anchor_offset_mm=0.0, horizontal_path_mm=0.0,
                                     start_body_y=float(translation[1]), end_body_y=float(translation[1]))
            item = active[index]
            material = rotation@(center+item["local_material_point"])+translation
            item["max_anchor_offset_mm"] = max(item["max_anchor_offset_mm"], float(np.linalg.norm(material[:2]-item["anchor_xy"])))
            item["horizontal_path_mm"] += float(np.linalg.norm(material[:2]-item["last_xy"]))
            item["last_xy"] = material[:2].tolist()
            item["end_theta"], item["end_frame"], item["end_body_y"] = frame["theta"], frame["frame"], float(translation[1])
        minimum_count = min(minimum_count, len(contacts))
    episodes.extend(active.values())
    for item in episodes:
        item.pop("last_xy")
        item["partial_at_clip_boundary"] = item["start_frame"] == 1 or item["end_frame"] == len(walk["frames"])
        item["body_advance_same_episode_mm"] = abs(item["end_body_y"]-item["start_body_y"])
        item["physical_seconds"] = (item["end_theta"]-item["start_theta"])/(2*math.pi)*manifest["design"]["ratio"]/120*60
    complete = [item for item in episodes if not item["partial_at_clip_boundary"]]
    worst = max(episodes, key=lambda item: item["max_anchor_offset_mm"])
    worst_complete = max(complete, key=lambda item: item["max_anchor_offset_mm"])
    summary = dict(
        prototype=ident, assembly_sha256=assembly_hash,
        walking_sha256=hashlib.sha256((OUT/f"walk_{ident}.json").read_bytes()).hexdigest(),
        method="All geometrically near feet, regardless of computed normal load. One fixed sole material point per uninterrupted near-contact episode.",
        sampling="Declared24fps rendered-frame poses, plus closing endpoint; physical frame spacing differs with explicitly declared playback scale. These are sampled maxima, not continuous-time friction measurements.",
        contact_gap_limit_mm=0.27, fixed_floor_offset_mm=0.02, contact_tolerance_above_lowest_surface_mm=0.25,
        minimum_near_contact_feet=minimum_count, maximum_absolute_ground_gap_of_near_feet_mm=maximum_gap,
        max_anchor_offset_all_episodes_mm=worst["max_anchor_offset_mm"],
        maximum_single_episode_path_mm=max(item["horizontal_path_mm"] for item in episodes),
        worst_episode=worst, worst_complete_episode=worst_complete, episodes=episodes,
        limitations="Material-point movement includes rocking as well as contact-fit residual; it is not a measured Coulomb slip distance. Clip-entry partial episodes are explicitly marked. No trajectory, geometry or load weighting was changed by this audit.")
    dump(OUT/f"contact_review_{ident}.json", summary)
    print(ident, "all-near maximum", worst["max_anchor_offset_mm"], "complete", worst_complete["max_anchor_offset_mm"],
          "min near feet", minimum_count, "absolute gap", maximum_gap)
