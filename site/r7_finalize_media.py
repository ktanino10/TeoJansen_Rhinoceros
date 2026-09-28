"""Verify and persist only the approved source-bound r7 display artifacts."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "site/dist/r7-visuals"
DEST = ROOT / "docs/ver3/r7_display_floor2"
BLEND_SOURCE = ROOT / "site/dist/r7-blender-prep/r7_candidate.blend"
BLEND_DEST = ROOT / "Blender/Ver.3/integrated_r7/r7_floor2.blend"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def finalize():
    source = json.loads((ROOT / "site/r7-source.json").read_text())
    gate = json.loads((ROOT / "site/dist/r7-floor2-gate.json").read_text())
    native = json.loads((MEDIA / "native-display-validation.json").read_text())
    if source.get("publicationHold") or source["publicationAuthorized"] is not True:
        raise ValueError("Display publication is still held")
    if gate["artifactCommit"] != source["artifactCommit"] or gate["status"] != "PASS":
        raise ValueError("Corrected display-floor gate is missing or stale")
    if native["sourceCommit"] != source["artifactCommit"] or native["status"] != "PASS":
        raise ValueError("Native exact-shape/inventory check is missing or stale")
    names = ["comparison.png", *(f"hero_{d}.png" for d in "ABC"),
             *(f"diagnostic_{d}_{phase:03}.png" for d in "ABC" for phase in (0, 120, 240)),
             *(f"{mode}_{d}.{extension}" for d in "ABC" for mode in ("assembly", "disassembly") for extension in ("mp4", "vtt", "json")),
             *(f"diagnostic_{d}.json" for d in "ABC"), "native-display-validation.json", "render-source.json"]
    for d in "ABC":
        report = json.loads((MEDIA/f"diagnostic_{d}.json").read_text())
        if (report["artifactCommit"] != source["artifactCommit"] or report["canonicalRockerNullPreserved"] is not True
                or len(report["frames"]) != 3 or report["newDynamicsOrForcesSolved"] is not False):
            raise ValueError("A diagnostic belongs to another revision or invents solved states")
        for frame in report["frames"]:
            if frame["floorCorrectionApplied"] or frame["interpolationUsed"] or frame["maximumRotationGramError"] > 1e-9:
                raise ValueError("Diagnostic deformed or repositioned canonical geometry")
            if frame.get("belowReferencePlaneParts"):
                raise ValueError(f"{d}: a diagnostic still has below-plane parts")
        for mode in ("assembly", "disassembly"):
            path = MEDIA/f"{mode}_{d}.mp4"
            timing = json.loads((MEDIA/f"{mode}_{d}.json").read_text())
            if timing["sourceCommit"] != source["artifactCommit"]:
                raise ValueError("Animation source commit differs")
            stream = json.loads(subprocess.check_output([
                "ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                "-show_entries", "stream=width,height,nb_read_frames", "-of", "json", str(path)], text=True))["streams"][0]
            if (stream["width"], stream["height"], int(stream["nb_read_frames"])) != (1280, 720, timing["frameCount"]):
                raise ValueError("Encoded clip differs from exact-state timing")
            subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"], check=True)
    DEST.mkdir(parents=True, exist_ok=True)
    files = {}
    for name in names:
        source_path = MEDIA/name
        destination = DEST/name
        if not source_path.is_file():
            raise ValueError(f"Missing display media: {name}")
        shutil.copyfile(source_path, destination)
        files[str(destination.relative_to(ROOT))] = {"bytes": destination.stat().st_size, "sha256": digest(destination.read_bytes())}
    gate_dest = DEST/"display-floor-gate.json"
    shutil.copyfile(ROOT / "site/dist/r7-floor2-gate.json", gate_dest)
    files[str(gate_dest.relative_to(ROOT))] = {"bytes": gate_dest.stat().st_size, "sha256": digest(gate_dest.read_bytes())}
    BLEND_DEST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(BLEND_SOURCE, BLEND_DEST)
    if BLEND_DEST.stat().st_size >= 100_000_000:
        raise ValueError("Native blend exceeds GitHub's file-size limit")
    files[str(BLEND_DEST.relative_to(ROOT))] = {"bytes": BLEND_DEST.stat().st_size, "sha256": digest(BLEND_DEST.read_bytes())}
    manifest = {
        "schemaVersion": 1, "revisionId": source["revisionId"], "artifactCommit": source["artifactCommit"],
        "sourceCommit": source["inputCommit"], "sourceHash": source["sourceHash"],
        "contractSha256": source["contractSha256"], "allSavedDisplayFramesFloorGate": "PASS",
        "completeWalkingVideoGenerated": False, "physicalTestsPerformed": False, "manufacturingRelease": False,
        "geometrySource": "All canonical vertices, triangles, stable instance IDs and millimetre transforms; no mesh simplification.",
        "assemblyScope": "Constant-held canonical schema2 inventories and finite path samples, reverse reference for removal. Physical timing and interpolation are not asserted.",
        "diagnosticScope": "0/120/240deg saved states, polar rigid display frame, geometric loaded-pad angle only if unique; source rocker null preserved, unresolved feet and coil deformation omitted.",
        "files": files,
    }
    (DEST/"display-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n")
    print(f"Persisted {len(files)} checked r7 media/native files, {sum(f['bytes'] for f in files.values()):,} bytes.")


if __name__ == "__main__":
    finalize()
