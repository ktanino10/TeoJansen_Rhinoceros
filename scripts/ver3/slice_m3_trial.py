"""Offline 0.2mm inspection using an already installed official Orca bundle."""

import argparse
import json
from pathlib import Path
import plistlib
import shutil
import subprocess

import numpy as np
import trimesh

from build_m3_trial import ROOT, DOC, REVISION, sha, write_json
from inspect_integrated_toolpaths import (gear_check, mesh_section, nearest_model_layer,
                                         panel, parse_gcode, point_clearance)
from slice_integrated_representatives import flatten_profile, placement

PROFILES = {
    "machine": "Bambu Lab P1S 0.2 nozzle",
    "process": "0.10mm Standard @BBL X1C 0.2 nozzle",
    "filament": "Generic PETG @0.2 nozzle",
}
PARTS = {
    "Q_SLEEVE_FIT": (False, [(8, 9), (24, 9), (40, 9)], [0.1, 2, 3.9]),
    "Q_NUT_HEX_FIT": (False, [(8, 8), (24, 8), (40, 8)], [0.1, 1.3, 2, 3.9]),
    "P_M3_GEAR42": (True, [(0, 0)], [1, 2.8, 10.2, 17.1]),
    "P_M3_LINK": (False, [(0, 0), (26.5, 0)], [0.1, 2.7, 5.3]),
    "P_M3_PIVOT": (True, [(0, 0)], [0.1, 2.9, 9.2, 12.2, 14.7]),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scope", choices=("trial", "a34"), default="trial")
    args = parser.parse_args()
    app, output = args.app.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    document = DOC if args.scope == "trial" else ROOT / "docs/ver3/m3_a34"
    print_directory = ROOT / ("STL/Ver.3/m3_r1" if args.scope == "trial" else "STL/Ver.3/m3_a34")
    revision = REVISION if args.scope == "trial" else "v3.4-a-m3-r1"
    selected = PARTS
    if args.scope == "a34":
        from walker_geometry import body_points
        assembly = json.loads((document / "assembly.json").read_text())
        nodes = body_points(common=assembly["parameters"]["common"])
        selected = {
            "P_M34_SYNC_DRIVE": (True, [(0, 0)], [1, 2.8, 10.2, 17.1]),
            "P_M34_LEG_AB_R": (True, [(-nodes[n][1], nodes[n][0]) for n in ("A", "B")], [0.1, 1.5, 2.9]),
            "P_M34_CRANK_JOURNAL_1_180": (True, [(0, 0)], [1, 12, 23.8]),
        }
    public = document / "slicing"
    public.mkdir(exist_ok=True)
    configs, provenance = {}, {}
    for kind, name in PROFILES.items():
        configs[kind], provenance[kind] = flatten_profile(app / "Contents/Resources/profiles/BBL", kind, name)
    for kind in ("process", "filament"):
        if PROFILES["machine"] not in configs[kind]["compatible_printers"]:
            raise ValueError(f"Bundled {kind} profile is not compatible with the inspection machine")
    overrides = {
        "wall_generator": "arachne", "wall_loops": "4", "sparse_infill_density": "100%",
        "sparse_infill_pattern": "rectilinear", "enable_arc_fitting": "0",
        "curr_bed_type": "Textured PEI Plate", "support_type": "normal(auto)",
        "support_style": "default", "support_on_build_plate_only": "1",
        "support_top_z_distance": "0.1", "support_object_xy_distance": "0.25",
        "brim_type": "outer_only", "brim_width": "3", "brim_object_gap": "0.1",
    }
    configs["process"].update(overrides)
    for kind in ("machine", "filament"):
        write_json(output / f"{kind}.json", configs[kind])
    report = {
        "revisionId": revision, "orcaVersion": plistlib.loads((app / "Contents/Info.plist").read_bytes())["CFBundleShortVersionString"],
        "profileNames": PROFILES, "sourceProfiles": provenance, "processOverrides": overrides,
        "actualHardwareAndMaterialMatched": False, "printerContacted": False, "physicalPrintingPerformed": False,
        "scope": "Inspection-only P1S / Generic PETG; actual user printer and material UNKNOWN. No printer-ready G-code is distributed.",
        "parts": [],
    }
    for pid, (supports, holes, heights) in selected.items():
        print("STAGE_BEGIN slice", pid, flush=True)
        folder = output / pid
        folder.mkdir()
        source = print_directory / f"{pid}.stl"
        target = folder / source.name
        shutil.copyfile(source, target)
        process = {**configs["process"], "enable_support": "1" if supports else "0"}
        write_json(folder / "process.json", process)
        command = [str(app / "Contents/MacOS/OrcaSlicer"), "--datadir", str(output / "config"),
                   "--debug", "2", "--load-settings", str(output / "machine.json") + ";" + str(folder / "process.json"),
                   "--load-filaments", str(output / "filament.json"), "--orient", "0", "--arrange", "1",
                   "--ensure-on-bed", "--scale", "1", "--outputdir", str(folder)]
        with (folder / "probe.log").open("w") as log:
            subprocess.run(command + ["--info", "--export-settings", str(folder / "effective.json"), str(target)],
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120, cwd=folder)
        effective = json.loads((folder / "effective.json").read_text())
        for key, expected in {
            "printer_model": "Bambu Lab P1S", "nozzle_diameter": ["0.2"], "filament_type": ["PETG"],
            "layer_height": "0.1", "initial_layer_print_height": "0.1",
            "enable_support": "1" if supports else "0", "enable_arc_fitting": "0",
        }.items():
            if effective.get(key) != expected:
                raise ValueError(f"{pid}: effective {key} was {effective.get(key)}, expected {expected}")
        with (folder / "slice.log").open("w") as log:
            subprocess.run(command + ["--slice", "0", "--export-3mf", pid + ".3mf", str(target)],
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180, cwd=folder)
        pose = placement(folder / f"{pid}.3mf")
        transform = np.array(pose["sourceStlToBedTransformRowMajor4x4"])
        layers, metadata = parse_gcode(folder / "plate_1.gcode")
        mesh = trimesh.load(target, force="mesh")
        samples = []
        for height in heights:
            layer = nearest_model_layer(layers, height)
            outlines = mesh_section(mesh, layer.z - layer.height / 2, transform)
            image = panel(pid, layer, outlines)
            filename = f"{pid}-{layer.z:g}.png"
            image.save(public / filename)
            image.close()
            sample_holes = holes
            if pid == "P_M34_CRANK_JOURNAL_1_180" and height > 9:
                sample_holes = [(0, 0), (0, -15*assembly["parameters"]["common"]["linkScale"])]
            points = [(transform @ np.array([x, y, 0, 1]))[:2] for x, y in sample_holes]
            samples.append({"zMm": layer.z, "layerHeightMm": layer.height, "figure": f"slicing/{filename}",
                            "modelHoleCenterClearanceMm": [point_clearance(layer.model(), p) for p in points],
                            "allPathsHoleCenterClearanceMm": [point_clearance(layer.segments, p) for p in points]})
        gear_results = [gear_check(mesh, transform, nearest_model_layer(layers, z), 42) for z in (1, 2.8)] if pid in {"P_M3_GEAR42", "P_M34_SYNC_DRIVE"} else []
        if any(row["depositedEnvelopeTeeth"] != 42 or not row["allDetectedTipsOnOneRootConnectedComponent"] for row in gear_results):
            raise ValueError("The sliced tooth envelope differs from the 42-tooth CAD")
        if any(value is not None and value <= 0 for row in samples for value in row["modelHoleCenterClearanceMm"]):
            raise ValueError(f"{pid}: positive model extrusion crosses a required bore centre")
        report["parts"].append({
            "partId": pid, "stl": str(source.relative_to(ROOT)), "stlSha256": sha(source),
            "effectiveSettingsSha256": sha(folder / "effective.json"), "gcodeSha256": sha(folder / "plate_1.gcode"),
            "supportEnabled": supports, "layerCount": len(layers), "metadata": metadata,
            "samples": samples, "gearChecks": gear_results, **pose,
            "physicalPrintFitStrength": "UNKNOWN",
        })
        write_json(document / "slicing.json", report)
        print("STAGE_END slice", pid, len(layers), "layers", flush=True)
    write_json(document / "files.json", {str(p.relative_to(ROOT)): sha(p)
                                   for folder in (ROOT / ("FreeCAD/Ver.3/m3_r1" if args.scope == "trial" else "FreeCAD/Ver.3/m3_a34"), print_directory, document)
                                   for p in sorted(folder.rglob("*"))
                                   if p.is_file() and p.name != "files.json" and p.suffix not in {".FCStd1", ".FCBak"}})


if __name__ == "__main__":
    main()
