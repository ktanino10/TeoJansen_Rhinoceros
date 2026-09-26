"""Point-foot quasi-static support on a rigid plane with body pitch/roll free.

Enumerates lower-hull foot triangles rather than declaring all near-height feet
coplanar. It establishes geometric support possibilities, not stable dynamics.
"""

import argparse
import csv
import hashlib
import itertools
import json
import math

import numpy as np

from core import CONFIG, OUT, animated_transform, axial_layout, dump, gait

parser = argparse.ArgumentParser()
parser.add_argument("--only", choices=["A", "B", "C"], default="A")
args = parser.parse_args()
manifest = json.loads((OUT / f"assembly_{args.only}.json").read_text())
design = manifest["design"]
parts = manifest["parts"]
total_mass = sum(parts[x["part_id"]]["mass_g"] for x in manifest["instances"])
triples = list(itertools.combinations(range(6), 3))
rows = []
missing = []
min_margin = float("inf")
max_tilt = 0
direction_failures = []
for degree in range(361):
    theta = math.radians(degree)
    center = np.zeros(3)
    for item in manifest["instances"]:
        part = parts[item["part_id"]]
        matrix = np.array(animated_transform(item, theta, design))
        center += part["mass_g"] * (matrix @ np.array(part["local_center_of_mass_mm"] + [1]))[:3]
    center /= total_mass
    feet, velocities = [], []
    for bay, phase in enumerate(CONFIG["linkage"]["phases"]):
        for mirrored in (False, True):
            angle = theta + math.radians(phase)
            point = gait(angle, mirrored)["F"]
            layout = axial_layout(design["structure"]["plate_thickness_mm"], mirrored, design.get("foot_offset", 0))
            x = bay * CONFIG["linkage"]["bay_pitch"] + layout["L_CEF"] + 1.5
            feet.append([x, point[0], point[1] + CONFIG["linkage"]["crank_height"]])
            delta = (gait(angle + 1e-5, mirrored)["F"] - gait(angle - 1e-5, mirrored)["F"]) / 2e-5
            velocities.append(np.array([0, *delta]))
    feet = np.array(feet)
    possibilities = []
    for triple in triples:
        triangle = feet[list(triple)]
        u, v = triangle[1] - triangle[0], triangle[2] - triangle[0]
        normal = np.cross(u, v)
        length = np.linalg.norm(normal)
        if length < 1e-8:
            continue
        normal /= length
        if normal[2] < 0:
            normal *= -1
        if normal[2] <= math.cos(math.radians(10)):
            continue
        clearance = (feet - triangle[0]) @ normal
        if clearance.min() < -1e-6:
            continue
        projected = center - np.dot(center - triangle[0], normal) * normal
        bary = np.linalg.lstsq(np.column_stack([u, v]), projected - triangle[0], rcond=None)[0]
        bary = np.array([1 - bary.sum(), *bary])
        if bary.min() < -1e-8:
            continue
        margins = []
        for i in range(3):
            edge = triangle[(i + 1) % 3] - triangle[i]
            margins.append(np.linalg.norm(np.cross(edge, projected - triangle[i])) / np.linalg.norm(edge))
        tilt = math.degrees(math.acos(float(normal[2])))
        tangent = np.array([0.0, 1.0, 0.0])
        tangent -= normal * np.dot(tangent, normal)
        tangent /= np.linalg.norm(tangent)
        speeds = [float(velocities[i] @ tangent) for i in triple]
        same_direction = all(s > 0 for s in speeds) or all(s < 0 for s in speeds)
        possibilities.append((tilt, min(margins), triple, normal, bary, same_direction))
    if not possibilities:
        missing.append(degree)
        rows.append([degree, False, "", "", "", "", "", ""])
        continue
    tilt, margin, triple, normal, bary, same_direction = min(possibilities, key=lambda x: x[0])
    min_margin = min(min_margin, margin)
    max_tilt = max(max_tilt, tilt)
    if not same_direction:
        direction_failures.append(degree)
    rows.append([degree, True, ":".join(map(str, triple)), tilt, margin,
                 float(normal[0]), float(normal[1]), same_direction])
with (OUT / f"ground_support_{args.only}.csv").open("w", newline="") as stream:
    writer = csv.writer(stream)
    writer.writerow(["crank_deg", "supported", "contact_legs", "body_tilt_deg",
                     "cog_edge_margin_mm", "ground_normal_body_x", "ground_normal_body_y", "same_stance_direction"])
    writer.writerows(rows)
result = {
    "prototype": args.only, "samples": 361,
    "role": "Auxiliary point-foot diagnostic, not the final finite-shoe walking solver. See walk_*.json and contact_review_*.json.",
    "assembly_sha256": hashlib.sha256((OUT / f"assembly_{args.only}.json").read_bytes()).hexdigest(),
    "unsupported_angles_deg": missing,
    "opposed_stance_direction_angles_deg": direction_failures,
    "supported_fraction": (361 - len(missing)) / 361,
    "minimum_cog_margin_mm": min_margin,
    "maximum_required_body_tilt_deg": max_tilt,
    "model": "Rigid plane / six point feet; all lower-hull triangles tested; nonnegative barycentric normal forces; least-tilt feasible pose chosen per phase, limited to10deg.",
    "limitations": "Geometric quasi-static support only. Body pitch/roll and contact triangle may switch; no inertia or contact stabilization. Uses F joint centers as point feet, not detailed rounded-toe solids. Wind force/overturning excluded. Slicer masses and actual COG must replace nominal CAD.",
}
dump(OUT / f"ground_support_{args.only}.json", result)
print(json.dumps(result, indent=2))
