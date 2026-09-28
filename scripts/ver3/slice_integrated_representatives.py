"""Offline OrcaSlicer inspection of five frozen r7 STLs; never contacts a printer."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import plistlib
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = "f50978e55384d1b03417ed7115395e6e2c010e85"
PARTS = {
    "P_INPUT_PINION": "A",
    "P_COMPOUND_1": "A",
    "T_GUIDE_COUPON": "common",
    "T_JOURNAL_COUPON": "common",
    "T_DIAMETER_COUPON": "common",
}
PROFILES = {
    "machine": "Bambu Lab P1S 0.4 nozzle",
    "process": "0.16mm Optimal @BBL X1C",
    "filament": "Generic PETG",
}
PROCESS_OVERRIDES = {
    "wall_generator": "arachne",
    "wall_loops": "4",
    "sparse_infill_density": "100%",
    "sparse_infill_pattern": "rectilinear",
    "top_shell_layers": "5",
    "bottom_shell_layers": "5",
    "enable_arc_fitting": "0",
    "curr_bed_type": "Textured PEI Plate",
    "support_type": "normal(auto)",
    "support_style": "default",
    "support_on_build_plate_only": "1",
    "support_threshold_angle": "30",
    "support_top_z_distance": "0.2",
    "support_bottom_z_distance": "0.2",
    "support_interface_top_layers": "3",
    "support_object_xy_distance": "0.35",
    "brim_type": "outer_only",
    "brim_width": "5",
    "brim_object_gap": "0.2",
    "outer_wall_speed": "40",
    "inner_wall_speed": "60",
    "internal_solid_infill_speed": "60",
    "top_surface_speed": "40",
    "initial_layer_speed": "20",
    "initial_layer_infill_speed": "30",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def flatten_profile(resources, category, name):
    catalog = {}
    for path in (resources / category).rglob("*.json"):
        data = json.loads(path.read_text())
        if "name" in data:
            if data["name"] in catalog:
                raise ValueError("Duplicate bundled profile: " + data["name"])
            catalog[data["name"]] = path, data
    chain = []
    while name:
        path, data = catalog[name]
        if any(row[0] == path for row in chain):
            raise ValueError("Cyclic profile inheritance")
        chain.append((path, data))
        name = data.get("inherits")
    merged = {}
    for _, data in reversed(chain):
        merged.update(data)
    # The CLI accepts leaf files without resolving their bundled parents.
    # Flatten explicitly, then check the exported effective configuration.
    merged.pop("inherits", None)
    provenance = [
        {"path": "profiles/BBL/" + str(p.relative_to(resources)), "sha256": sha(p)}
        for p, _ in reversed(chain)
    ]
    return merged, provenance


def verify_effective(data, support):
    expected = {
        "printer_model": "Bambu Lab P1S",
        "nozzle_diameter": ["0.4"],
        "filament_type": ["PETG"],
        "filament_density": ["1.27"],
        "layer_height": "0.16",
        "initial_layer_print_height": "0.2",
        "printable_area": ["0x0", "256x0", "256x256", "0x256"],
        **PROCESS_OVERRIDES,
        "enable_support": "1" if support else "0",
    }
    for key, value in expected.items():
        if data.get(key) != value:
            raise ValueError(f"Effective setting mismatch: {key}: {data.get(key)!r} != {value!r}")


def placement(project):
    with zipfile.ZipFile(project) as archive:
        model = ET.fromstring(archive.read("3D/3dmodel.model"))
    items = [node for node in model.iter() if node.tag.endswith("}item")]
    if len(items) != 1:
        raise ValueError("Expected one representative build item")
    values = [float(value) for value in items[0].attrib["transform"].split()]
    if len(values) != 12 or any(abs(values[i]) > 1e-7 for i in (2, 5, 6, 7, 11)):
        raise ValueError("Unexpected build-axis rotation or vertical translation")
    if abs(values[8] - 1) > 1e-7 or abs(values[0] * values[4] - values[1] * values[3] - 1) > 1e-7:
        raise ValueError("Unexpected scale or mirror in arranged item")
    return {
        "sourceStlToBedTransformRowMajor4x4": [
            [values[0], values[3], values[6], values[9]],
            [values[1], values[4], values[7], values[10]],
            [values[2], values[5], values[8], values[11]],
            [0, 0, 0, 1],
        ],
        "arrangedRotationZDeg": math.degrees(math.atan2(values[1], values[0])),
    }


def run(app, output, selected):
    output.mkdir(parents=True, exist_ok=False)
    resources = app / "Contents/Resources/profiles/BBL"
    executable = app / "Contents/MacOS/OrcaSlicer"
    info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    frozen = json.loads(subprocess.check_output(
        ["git", "show", CANDIDATE + ":docs/ver3/integrated_r7/manifest.json"],
        cwd=ROOT, text=True))
    frozen_files = {row["path"]: row for row in frozen["files"]}
    configs = {}
    sources = {}
    for kind, name in PROFILES.items():
        configs[kind], sources[kind] = flatten_profile(resources, kind, name)
    configs["process"].update(PROCESS_OVERRIDES)
    write_json(output / "machine.json", configs["machine"])
    write_json(output / "filament.json", configs["filament"])
    records = []
    for part in selected:
        relative = f"STL/Ver.3/integrated_r7/{PARTS[part]}/{part}.stl"
        source = ROOT / relative
        if sha(source) != frozen_files[relative]["sha256"]:
            raise ValueError("Frozen STL changed: " + relative)
        folder = output / part
        folder.mkdir()
        target = folder / (part + ".stl")
        shutil.copyfile(source, target)
        support = part in ("P_INPUT_PINION", "P_COMPOUND_1")
        process = {**configs["process"], "enable_support": "1" if support else "0"}
        write_json(folder / "process.json", process)
        common = [
            str(executable), "--datadir", str(output / "config"), "--debug", "2",
            "--load-settings", str(output / "machine.json") + ";" + str(folder / "process.json"),
            "--load-filaments", str(output / "filament.json"),
            "--orient", "0", "--arrange", "1", "--ensure-on-bed", "--scale", "1",
            "--outputdir", str(folder),
        ]
        with (folder / "settings_probe.log").open("w") as log:
            subprocess.run(common + ["--info", "--export-settings", str(folder / "effective.json"),
                                     str(target)], stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=180, cwd=folder)
        effective = json.loads((folder / "effective.json").read_text())
        verify_effective(effective, support)
        command = common + ["--slice", "0", "--export-3mf", part + ".3mf", str(target)]
        with (folder / "slice.log").open("w") as log:
            completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=900, cwd=folder)
        record = {
            "partId": part, "stl": relative, "stlSha256": sha(target),
            "processSha256": sha(folder / "process.json"),
            "effectiveSettingsSha256": sha(folder / "effective.json"),
            "supportEnabled": support, "exitCode": completed.returncode,
            "orientationPolicy": "Preserve the exported build Z; arrange may rotate about Z only",
            "scale": 1,
            "layerInspectionStatus": "PENDING",
        }
        if completed.returncode == 0:
            project = folder / (part + ".3mf")
            record.update(placement(project))
            record["privateProjectSha256"] = sha(project)
            record["gcodeSha256"] = sha(folder / "plate_1.gcode")
        records.append(record)
        write_json(output / "run.json", {
            "reviewedArtifactCommit": CANDIDATE,
            "orcaBundleVersion": info["CFBundleShortVersionString"],
            "sourceProfiles": sources, "profileNames": PROFILES,
            "processOverrides": PROCESS_OVERRIDES,
            "machineSettingsSha256": sha(output / "machine.json"),
            "filamentSettingsSha256": sha(output / "filament.json"),
            "profileInheritance": "Explicitly flattened, then checked against CLI effective settings",
            "printerContacted": False, "physicalPrintingPerformed": False,
            "actualHardwareAndMaterialMatched": False,
            "parts": records,
        })
        print(part, "slice exit", completed.returncode, flush=True)
        if completed.returncode:
            raise RuntimeError(f"OrcaSlicer failed for {part}; inspect its private slice.log")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--part", choices=PARTS, action="append")
    args = parser.parse_args()
    run(args.app.resolve(), args.output.resolve(), args.part or list(PARTS))
