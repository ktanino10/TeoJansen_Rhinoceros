"""Compile measured legacy geometry and the final, consistently defined results."""

from collections import Counter
import csv
import hashlib
import json
import math
from html import escape

import trimesh

from core import CONFIG, ROOT, OUT, dump

OUT.mkdir(parents=True, exist_ok=True)
with (OUT/"legacy_measurements.csv").open("w", newline="") as stream:
    writer = csv.writer(stream)
    writer.writerow(["file", "x_extent", "y_extent", "z_extent", "faces", "unit_assumption", "sha256"])
    for path in sorted((ROOT/"STL"/"Ver.2").glob("*.stl")):
        mesh = trimesh.load_mesh(path, process=False)
        writer.writerow([str(path.relative_to(ROOT)), *[round(float(v), 6) for v in mesh.extents],
                         len(mesh.faces), "raw STL coordinates interpreted as mm; no150% multiplier",
                         hashlib.sha256(path.read_bytes()).hexdigest()])

rows, designs = [], []
for ident in "ABC":
    assembly = json.loads((OUT/f"assembly_{ident}.json").read_text())
    cad = json.loads((OUT/f"cad_validation_{ident}.json").read_text())
    walk = json.loads((OUT/f"walk_{ident}.json").read_text())
    startup = json.loads((OUT/f"startup_{ident}.json").read_text())
    contact = json.loads((OUT/f"contact_review_{ident}.json").read_text())
    validation = json.loads((OUT/f"validation_{ident}.json").read_text())
    design, values = assembly["design"], walk["validation"]
    assembly_hash = hashlib.sha256((OUT/f"assembly_{ident}.json").read_bytes()).hexdigest()
    walk_hash = hashlib.sha256((OUT/f"walk_{ident}.json").read_bytes()).hexdigest()
    if walk["assembly_sha256"] != assembly_hash:
        raise RuntimeError(f"{ident}: stale walking source in comparison")
    for label, data in (("startup", startup), ("contact audit", contact)):
        if data.get("assembly_sha256") != assembly_hash or data.get("walking_sha256") != walk_hash:
            raise RuntimeError(f"{ident}: regenerate {label} against the current CAD and walking inputs")
    nominal = next(case for case in startup["scenarios"] if case["case"] == "nominal")
    counts = Counter(item["part_id"] for item in assembly["instances"])
    episode = values["worst_anchor_episode"]
    row = dict(
        prototype=ident, rotor_diameter_mm=2*design["rotor"]["radius"],
        rotor_span_mm=design["rotor"]["span"], stages=len(design["stages"]), reduction=design["ratio"],
        stage_types="+".join(stage["type"] for stage in design["stages"]),
        nominal_solid_and_hardware_mass_g=cad["nominal_total_mass_g"],
        nominal_printed_solid_mass_g=cad["nominal_printed_mass_g"],
        frame_mass_g=cad["frame_printed_mass_g"], component_instances=len(assembly["instances"]),
        printed_unique_assembly_parts=sum(part["category"] == "printed" and counts[name] > 0 for name, part in assembly["parts"].items()),
        printed_instances=cad["printed_instances"], hubs=counts["H_REX_HUB"], bearings=counts["H_608"],
        nominal_peak_required_input_Nm=nominal["peak_required_input_nm"],
        nominal_peak_crank_deg=nominal["peak_angle_deg"],
        wind5_Cq005_input_Nm=startup["rotor_input_nm_range"]["5.0"][0],
        wind5_Cq020_input_Nm=startup["rotor_input_nm_range"]["5.0"][1],
        wind8_Cq005_input_Nm=startup["rotor_input_nm_range"]["8.0"][0],
        wind8_Cq020_input_Nm=startup["rotor_input_nm_range"]["8.0"][1],
        video_seconds=walk["video_seconds"], physical_seconds=walk["physical_seconds"],
        time_scale=walk["time_scale"], input_rpm=walk["input_rpm"],
        travel_three_cycles_mm=values["forward_travel_mm"],
        maximum_single_episode_material_anchor_drift_mm=values["max_stance_material_anchor_drift_mm"],
        body_advance_during_worst_anchor_episode_mm=episode["body_advance_in_episode_mm"],
        worst_episode_is_partial=episode["partial_at_clip_boundary"],
        maximum_single_episode_horizontal_path_mm=values["max_single_contact_episode_horizontal_path_mm"],
        maximum_active_foot_gap_mm=values["max_active_foot_gap_mm"],
        minimum_mesh_floor_clearance_mm=values["minimum_mesh_floor_clearance_mm"],
        minimum_nominal_geometric_support_margin_mm=values["minimum_support_margin_mm"],
        minimum_model_loaded_feet=values["minimum_active_feet"],
        strict3mm_contact_target_pass=values["strict_3mm_contact_target_pass"],
        all_near_feet_frame_sampled_anchor_drift_mm=contact["max_anchor_offset_all_episodes_mm"],
        all_near_feet_complete_episode_max_mm=contact["worst_complete_episode"]["max_anchor_offset_mm"],
        minimum_geometrically_near_feet=contact["minimum_near_contact_feet"],
        maximum_absolute_near_foot_ground_gap_mm=contact["maximum_absolute_ground_gap_of_near_feet_mm"],
        AC_euler_proxy_ratio=startup["ac_euler_proxy_ratio"],
        geometry_checks_pass=validation["structure_limits_pass"] and validation["bom_count_consistent"],
    )
    rows.append(row)
    designs.append(dict(comparison=row, design=design, startup=startup, walking=values, contact_audit=contact, cad=cad))
with (OUT/"comparison.csv").open("w", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
dump(OUT/"comparison.json", {
    "status": "Reviewable engineering first cut; not manufacturing release or wind-walking demonstration",
    "definitions": {
        "mass": "All-solid CAD print volume plus catalog/assumed hardware; not slicer or measured mass.",
        "slip": "Largest horizontal material-anchor offset within one continuous >=2%-load episode; maxima over all feet/three cycles include clip-entry partial episodes. Not a three-cycle accumulated displacement. All-near-foot frame-sampled audit is separate and ignores the load threshold.",
        "path": "Horizontal path accumulated within one such episode; global maximum may belong to a different episode.",
        "support": "Necessary geometric containment with0.25mm near-contact tolerance, not practical stability proof.",
    },
    "designs": designs,
})

# A compact, self-contained SVG plot; all curves read the generated numerical CSV.
plot = ['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="510" viewBox="0 0 1200 510">',
        '<rect width="1200" height="510" fill="#ffffff"/>',
        '<style>text{font-family:Arial,sans-serif}</style>',
        '<text x="30" y="30" font-size="20" fill="#111827">Ver.3 / provisional input torque by crank phase</text>',
        '<text x="30" y="52" font-size="12" fill="#475569">Same friction cases; purple band=8 m/s with assumed Cq0.05-0.20. Not measured wind performance.</text>']
for panel, record in enumerate(designs):
    ident = record["comparison"]["prototype"]
    with (OUT/f"startup_profile_{ident}.csv").open() as stream:
        samples = list(csv.DictReader(stream))
    scale = max(float(sample["required_input_nm"])*1000 for sample in samples)
    wind = [v*1000 for v in record["startup"]["rotor_input_nm_range"]["8.0"]]
    scale = max(scale, wind[1])*1.1
    x0, y0, width, height = 50+400*panel, 100, 330, 320
    plot.append(f'<text x="{x0}" y="82" font-size="17">{ident} / {record["comparison"]["reduction"]:g}:1</text>')
    low, high = y0+height*(1-wind[1]/scale), y0+height*(1-wind[0]/scale)
    plot.append(f'<rect x="{x0}" y="{low}" width="{width}" height="{high-low}" fill="#ede9fe"/>')
    for level in range(5):
        value = scale*level/4
        y = y0+height*(1-level/4)
        plot.append(f'<path d="M{x0},{y}h{width}" stroke="#e2e8f0"/>')
        plot.append(f'<text x="{x0-5}" y="{y+4}" font-size="10" text-anchor="end">{value:.1f}</text>')
    for case, ink in (("low", "#0f766e"), ("nominal", "#2563eb"), ("high", "#b45309")):
        values = [sample for sample in samples if sample["scenario"] == case]
        path = "M"+" L".join(f'{x0+float(s["crank_deg"])/360*width:.2f},{y0+height*(1-float(s["required_input_nm"])*1000/scale):.2f}' for s in values)
        plot.append(f'<path d="{path}" fill="none" stroke="{ink}" stroke-width="1.6"/>')
    plot.append(f'<text x="{x0}" y="440" font-size="11">0 deg</text><text x="{x0+width}" y="440" font-size="11" text-anchor="end">360 deg</text>')
    plot.append(f'<text x="{x0}" y="458" font-size="11">mN m; panel scales differ (see labels)</text>')
plot.append('<text x="50" y="490" font-size="12" fill="#0f766e">Low friction</text><text x="220" y="490" font-size="12" fill="#2563eb">Nominal assumptions</text><text x="470" y="490" font-size="12" fill="#b45309">High friction</text></svg>')
(OUT/"drawings"/"startup_torque.svg").write_text("".join(plot)+"\n")

for ident, row in zip("ABC", rows):
    print(ident, f'{row["nominal_solid_and_hardware_mass_g"]/1000:.3f} kg',
          f'input nominal {row["nominal_peak_required_input_Nm"]:.5f} Nm',
          f'episode drift {row["maximum_single_episode_material_anchor_drift_mm"]:.3f} mm',
          f'3mm target {row["strict3mm_contact_target_pass"]}')
