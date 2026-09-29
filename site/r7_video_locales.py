"""Localize annotations over one reusable, text-free render per frozen r7 design.

Use an existing private directory outside the Pages output for --master-dir.
Blender: --preview C --frame 39, or --render-clean C (serially C/A/B).
Ordinary Python: --compose-preview C --frame 39, --compose C, then --finalize.
No canonical geometry, motion packet, native scene, or earlier media is rewritten.
"""

import argparse
import fcntl
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/ver3/r7_walking_v1"
OUTPUT = ROOT / "docs/ver3/r7_walking_locales_v1"
CATALOG = ROOT / "site/r7_video_texts.json"
NATIVE = ROOT / "Blender/Ver.3/integrated_r7/r7_walking_v1.blend"
REVISION = "r7-floor2-walking-localized-v1"
FONTS = {
    "ja": Path("/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"),
    "en": Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
}


def fingerprint(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return {"sha256": h.hexdigest(), "bytes": path.stat().st_size}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def source(design):
    manifest = json.loads((BASE / "walking-manifest.json").read_text())
    native = manifest["files"][str(NATIVE.relative_to(ROOT))]
    if fingerprint(NATIVE) != native:
        raise ValueError("The frozen mechanical native scene has changed")
    packet_path = BASE / f"motion_{design}.json"
    render = json.loads((BASE / f"render_{design}.json").read_text())
    packet = json.loads(packet_path.read_text())
    if fingerprint(packet_path)["sha256"] != render["motionSha256"]:
        raise ValueError("Source motion and source film differ")
    if (render["fps"], render["width"], render["height"], render["timeFactor"], render["cycles"]) != (24, 960, 720, 16, 4):
        raise ValueError("Only the unchanged source movie settings are accepted")
    return manifest, packet, render


def probe(path):
    result = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-count_frames", "-show_streams", "-of", "json", str(path)], text=True))
    if len(result["streams"]) != 1 or result["streams"][0]["codec_type"] != "video":
        raise ValueError("Expected exactly one silent video stream")
    stream = result["streams"][0]
    return {"width": stream["width"], "height": stream["height"], "fps": stream["r_frame_rate"],
            "frameCount": int(stream["nb_read_frames"]), "durationSeconds": float(stream["duration"]),
            "codec": stream["codec_name"], "pixelFormat": stream["pix_fmt"]}


def verify_timing(path, meta):
    info = probe(path)
    if ((info["width"], info["height"], info["fps"], info["frameCount"])
            != (meta["width"], meta["height"], f'{meta["fps"]}/1', meta["frameCount"])
            or abs(info["durationSeconds"] - meta["frameCount"] / meta["fps"]) > .002):
        raise ValueError(f"Movie dimensions, frame count or timing changed: {path}")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path), "-f", "null", "-"], check=True)
    return info


def pose_labels(design, meta):
    script = """
import fs from 'node:fs';
import {createMotion, TAU} from './site/r7-walk-math.js';
const design=process.argv[1], count=Number(process.argv[2]), fps=Number(process.argv[3]);
const m=createMotion(JSON.parse(fs.readFileSync(`docs/ver3/r7_walking_v1/motion_${design}.json`)));
const rows=Array.from({length:count},(_,i)=>{
  const p=m.at(Math.min(i/fps*16,m.cycleSeconds*4)/m.cycleSeconds*TAU);
  return {phase:p.phase*180/Math.PI,seconds:p.seconds,forward:p.forwardMm};
});
console.log(JSON.stringify(rows));
"""
    return json.loads(subprocess.check_output(["node", "--input-type=module", "-e", script, design,
                                               str(meta["frameCount"]), str(meta["fps"])], cwd=ROOT, text=True))


def render_clean(design, folder, preview_frame=None):
    import bpy
    if not bpy.app.background:
        raise RuntimeError("Refusing to touch a live Blender scene")
    base, packet, meta = source(design)
    folder.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(NATIVE), load_ui=False)
    scene = bpy.data.scenes["R7_WALK_" + design]
    bpy.context.window.scene = scene
    if (scene.frame_start, scene.frame_end, scene.render.fps,
            scene.render.resolution_x, scene.render.resolution_y) != (1, meta["frameCount"], 24, 960, 720):
        raise ValueError("Native camera/film settings differ from the source movie")
    mechanical = {o["instance_id"]: o for o in scene.objects if "instance_id" in o}
    if set(mechanical) != set(packet["instances"]):
        raise ValueError("The clean scene lost mechanical instances")
    if preview_frame is not None and not 0 <= preview_frame < meta["frameCount"]:
        raise ValueError("Preview frame is outside the unchanged source timeline")
    scene.frame_set(1 if preview_frame is None else preview_frame + 1)
    scene.view_layers[0].update()
    before = {name: tuple(v for row in obj.matrix_world for v in row) for name, obj in mechanical.items()}
    camera_before = tuple(v for row in scene.camera.matrix_world for v in row)
    annotations = [o for o in scene.objects if o.get("annotation_not_mechanical_part")]
    if len(annotations) != 6 or any("instance_id" in o for o in annotations):
        raise ValueError("Unexpected annotation layer; do not hide a mechanical part")
    for obj in annotations:
        obj.hide_render = True
    scene.view_layers[0].update()
    if (before != {name: tuple(v for row in obj.matrix_world for v in row) for name, obj in mechanical.items()}
            or camera_before != tuple(v for row in scene.camera.matrix_world for v in row)):
        raise ValueError("Removing annotations changed the mechanism or camera")
    if preview_frame is not None:
        scene.render.filepath = str(folder / f"clean_{design}_{preview_frame:06}.png")
        bpy.ops.render.render(write_still=True, scene=scene.name)
        print("CLEAN_PREVIEW", scene.render.filepath, flush=True)
        return

    movie = folder / f"clean_{design}.mp4"
    receipt = folder / f"clean_{design}.json"
    if movie.exists() or receipt.exists():
        raise ValueError("A retained master already exists; reuse it instead of silently rerendering")
    scene.render.filepath = str(folder / f"transient_{design}_")
    process = subprocess.Popen([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "image2pipe",
        "-framerate", "24", "-vcodec", "png", "-i", "-", "-c:v", "libx264rgb",
        "-preset", "medium", "-crf", "10", "-maxrate", "9000k", "-bufsize", "18000k",
        "-pix_fmt", "rgb24", "-movflags", "+faststart", "-an", str(movie)], stdin=subprocess.PIPE)
    samples = {0, min(39, meta["frameCount"] - 1), meta["frameCount"] - 1}
    written, raw_hashes = [], []
    began = time.monotonic()

    def save_frame(current, *_):
        if current != scene:
            return
        index = current.frame_current - 1
        if index != len(written):
            raise RuntimeError("Clean frames are not consecutive")
        path = Path(current.render.frame_path(frame=current.frame_current))
        data = path.read_bytes()
        if index in samples:
            (folder / f"clean_{design}_{index:06}.png").write_bytes(data)
        raw_hashes.append(hashlib.sha256(data).hexdigest())
        process.stdin.write(data)
        path.unlink()
        written.append(index)
        if index % 120 == 0:
            print(f"CLEAN_RENDER {design} {index + 1}/{meta['frameCount']} {time.monotonic() - began:.1f}s", flush=True)

    bpy.app.handlers.render_write.append(save_frame)
    try:
        bpy.ops.render.render(animation=True, scene=scene.name)
        if len(written) != meta["frameCount"]:
            raise RuntimeError("The full clean frame stream was not rendered")
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError("Clean master encoding failed")
    except BaseException:
        process.stdin.close()
        process.wait()
        raise
    finally:
        bpy.app.handlers.render_write.remove(save_frame)
    info = verify_timing(movie, meta)
    if movie.stat().st_size >= 100_000_000:
        raise ValueError("Private master exceeded the bounded per-file budget")
    write_json(receipt, {
        "schemaVersion": 1, "designId": design, "native": base["files"][str(NATIVE.relative_to(ROOT))],
        "motionSha256": meta["motionSha256"], "evaluatorSha256": meta["evaluatorSha256"],
        "baseManifestSha256": fingerprint(BASE / "walking-manifest.json")["sha256"],
        "movie": {**fingerprint(movie), **info}, "sampleFrames": sorted(samples),
        "rawFrameSha256": raw_hashes, "hiddenAnnotationObjects": [o.name for o in annotations],
        "mechanicalInstanceCount": len(mechanical), "cameraAndMechanicalTransformsUnchanged": True,
        "privateMaster": True, "lossless": False,
        "encoding": "High-quality RGB 4:4:4 H.264 CRF10/VBV9Mbps; private reusable intermediate, not a browser delivery.",
        "geometryRenders": 1, "renderer": bpy.app.version_string, "elapsedSeconds": time.monotonic() - began,
    })
    print("CLEAN_MASTER", design, movie.stat().st_size, flush=True)


@lru_cache(maxsize=2)
def fonts(language, sizes):
    from PIL import ImageFont
    path = FONTS[language]
    if not path.is_file():
        raise RuntimeError(f"Existing font required; no font is downloaded: {path.name}")
    return {name: ImageFont.truetype(str(path), size) for name, size in sizes}


def annotation(image, catalog, language, design, ratio, row):
    from PIL import ImageDraw
    result = image.copy()
    draw = ImageDraw.Draw(result)
    layout = catalog["layout"]
    data = catalog["locales"][language]
    font_set = fonts(language, tuple(layout["fontSizesPx"].items()))
    boxes = {}
    for key, xy in layout["positionsPx"].items():
        text = data[key].format(design=design, ratio=f"{ratio:g}", **row)
        box = draw.textbbox(tuple(xy), text, font=font_set[key], anchor="lt")
        if (box[2] - box[0] > layout["maximumTextWidthPx"]
                or not any(box[0] >= r[0] and box[1] >= r[1] and box[2] <= r[2] and box[3] <= r[3]
                           for r in layout["safeAnnotationRegionsPx"])):
            raise ValueError(f"Annotation would be clipped or cover the model: {language}/{key}: {box}")
        draw.text(tuple(xy), text, fill=tuple(layout["textColorRgb"]), font=font_set[key], anchor="lt")
        boxes[key] = list(box)
    return result, boxes


def outside_annotation_difference(first, second, catalog):
    import numpy as np
    mask = np.ones((720, 960), dtype=bool)
    for x0, y0, x1, y1 in catalog["layout"]["safeAnnotationRegionsPx"]:
        mask[y0:y1, x0:x1] = False
    return int(np.abs(np.asarray(first, dtype=int) - np.asarray(second, dtype=int))[mask].max())


def master_quality(design, folder, indices):
    import numpy as np
    from PIL import Image
    select = "+".join(f"eq(n\\,{index})" for index in indices)
    raw = subprocess.check_output([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(folder / f"clean_{design}.mp4"),
        "-vf", f"select={select}", "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    frame_bytes = 960 * 720 * 3
    if len(raw) != frame_bytes * len(indices):
        raise ValueError("Master quality samples do not match the source frame indices")
    rows = []
    for offset, index in enumerate(indices):
        original = np.asarray(Image.open(folder / f"clean_{design}_{index:06}.png").convert("RGB"), dtype=float)
        decoded = np.frombuffer(raw[offset * frame_bytes:(offset + 1) * frame_bytes], dtype=np.uint8).reshape(720, 960, 3)
        difference = original - decoded
        mse = float(np.mean(difference ** 2))
        psnr = 10 * math.log10(255 ** 2 / max(mse, 1e-12))
        rows.append({"frameIndex": index, "psnrDb": psnr, "meanAbsoluteChannelError": float(np.abs(difference).mean())})
        if psnr < 38:
            raise ValueError(f"Private master is not sufficiently faithful to the clean source: {design}/{index}: {psnr}dB")
    return {"minimumPsnrDb": min(r["psnrDb"] for r in rows), "thresholdPsnrDb": 38, "samples": rows}


def preview(design, folder, frame):
    from PIL import Image
    _, packet, meta = source(design)
    catalog = json.loads(CATALOG.read_text())
    row = pose_labels(design, meta)[frame]
    clean = Image.open(folder / f"clean_{design}_{frame:06}.png").convert("RGB")
    report = {}
    for language in ("ja", "en"):
        result, boxes = annotation(clean, catalog, language, design, abs(packet["inputTurnsPerCrank"]), row)
        if outside_annotation_difference(clean, result, catalog) != 0:
            raise ValueError("Localization changed model pixels outside annotation margins")
        path = folder / f"preview_{design}_{language}_{frame:06}.png"
        result.save(path)
        report[language] = {"file": path.name, "boxesPx": boxes, "row": row}
    write_json(folder / f"preview_{design}_{frame:06}.json", {"layout": catalog["layout"], "languages": report})
    print(json.dumps(report, ensure_ascii=False, indent=2))


def vtt_time(seconds):
    ms = round(seconds * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02}.{ms % 1000:03}"


def compose(design, folder):
    from PIL import Image
    _, packet, meta = source(design)
    catalog = json.loads(CATALOG.read_text())
    master = folder / f"clean_{design}.mp4"
    receipt = json.loads((folder / f"clean_{design}.json").read_text())
    if (fingerprint(master) != {k: receipt["movie"][k] for k in ("sha256", "bytes")}
            or receipt["motionSha256"] != meta["motionSha256"]
            or receipt["native"] != fingerprint(NATIVE)):
        raise ValueError("Retained master source changed")
    rows = pose_labels(design, meta)
    reader = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(master),
                               "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    encoders = {}
    for language in ("ja", "en"):
        target = OUTPUT / language
        target.mkdir(parents=True, exist_ok=True)
        encoders[language] = subprocess.Popen([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-video_size", "960x720", "-framerate", "24", "-i", "-", "-c:v", "libx264",
            "-preset", "slow", "-crf", "25", "-maxrate", "900k", "-bufsize", "1800k",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(target / f"walking_{design}.mp4")],
            stdin=subprocess.PIPE)
    box_limits = {}
    decoded_hashes = []
    try:
        for index, row in enumerate(rows):
            raw = reader.stdout.read(960 * 720 * 3)
            if len(raw) != 960 * 720 * 3:
                raise RuntimeError("Clean master ended before the required source frame")
            decoded_hashes.append(hashlib.sha256(raw).hexdigest())
            image = Image.frombytes("RGB", (960, 720), raw)
            for language, encoder in encoders.items():
                picture, boxes = annotation(image, catalog, language, design, abs(packet["inputTurnsPerCrank"]), row)
                encoder.stdin.write(picture.tobytes())
                box_limits[language] = boxes
                if index == 0:
                    picture.save(OUTPUT / language / f"walking_{design}.png", optimize=True)
                if index in receipt["sampleFrames"]:
                    if outside_annotation_difference(image, picture, catalog) != 0:
                        raise ValueError("An annotation changed pixels in the mechanism region")
                    picture.save(folder / f"localized_{design}_{language}_{index:06}.png")
        if reader.stdout.read(1):
            raise ValueError("Clean master contains extra frames")
        reader.stdout.close()
        if reader.wait() != 0:
            raise RuntimeError("Clean master decoding failed")
        for encoder in encoders.values():
            encoder.stdin.close()
            if encoder.wait() != 0:
                raise RuntimeError("Localized movie encoding failed")
    except BaseException:
        reader.stdout.close()
        reader.wait()
        for encoder in encoders.values():
            encoder.stdin.close()
            encoder.wait()
        raise
    languages = {}
    for language in ("ja", "en"):
        target = OUTPUT / language
        movie = target / f"walking_{design}.mp4"
        info = verify_timing(movie, meta)
        if info["pixelFormat"] != "yuv420p" or movie.stat().st_size >= 100_000_000:
            raise ValueError("Localized delivery is not a bounded browser MP4")
        duration = meta["frameCount"] / meta["fps"]
        forward = 4 * packet["forwardPerCycleMm"]
        cues = [text.format(design=design, forward=forward) for text in catalog["locales"][language]["captions"]]
        (target / f"walking_{design}.vtt").write_text("WEBVTT\n\n" + "\n\n".join(
            f"{vtt_time(i * duration / 4)} --> {vtt_time((i + 1) * duration / 4)}\n{text}"
            for i, text in enumerate(cues)) + "\n")
        languages[language] = {**info, "bytes": movie.stat().st_size, "lastAnnotationBoxesPx": box_limits[language]}
    write_json(OUTPUT / f"render_{design}.json", {
        "schemaVersion": 1, "revisionId": REVISION, "designId": design,
        "motionSha256": meta["motionSha256"], "evaluatorSha256": meta["evaluatorSha256"],
        "privateMaster": {k: v for k, v in receipt.items() if k != "rawFrameSha256"},
        "sharedDecodedFramesSha256": hashlib.sha256("".join(decoded_hashes).encode()).hexdigest(),
        "sameCleanFramesForBothLanguages": True, "maximumChangedPixelOutsideAnnotationRegions": 0,
        "captionCatalog": fingerprint(CATALOG), "languages": languages,
        "masterQuality": master_quality(design, folder, receipt["sampleFrames"]),
        "encoder": {"codec": "libx264", "preset": "slow", "crf": 25, "maxrate": "900k",
                    "bufsize": "1800k", "pixelFormat": "yuv420p"},
    })
    print("LOCALIZED", design, {k: v["bytes"] for k, v in languages.items()}, flush=True)


def finalize():
    catalog = json.loads(CATALOG.read_text())
    base = json.loads((BASE / "walking-manifest.json").read_text())
    designs, checks = {}, {}
    files = [CATALOG, Path(__file__)]
    for design in "ABC":
        _, packet, meta = source(design)
        report_path = OUTPUT / f"render_{design}.json"
        report = json.loads(report_path.read_text())
        if (report["captionCatalog"] != fingerprint(CATALOG) or report["motionSha256"] != meta["motionSha256"]
                or report["sameCleanFramesForBothLanguages"] is not True
                or report["maximumChangedPixelOutsideAnnotationRegions"] != 0):
            raise ValueError("Localized media and annotation catalog differ")
        files.append(report_path)
        row = {k: meta[k] for k in ("fps", "frameCount", "durationSeconds", "prescribedSeconds", "timeFactor", "cycles", "motionSha256")}
        row.update(width=960, height=720, forwardMm=4 * packet["forwardPerCycleMm"], locales={})
        for language, strings in catalog["locales"].items():
            media = {}
            for key, extension in (("video", "mp4"), ("poster", "png"), ("captions", "vtt")):
                path = OUTPUT / language / f"walking_{design}.{extension}"
                files.append(path)
                media[key] = {"path": str(path.relative_to(ROOT)), **fingerprint(path)}
            media["poster"].update(width=960, height=720)
            media["captions"].update(lang=language, label=strings["captionLabel"], default=False)
            media["title"] = strings["accessibleTitle"].format(design=design)
            media["description"] = strings["description"].format(design=design, forward=row["forwardMm"])
            row["locales"][language] = media
        designs[design] = row
        checks[design] = {
            "frameCount": meta["frameCount"], "fps": meta["fps"],
            "sourceNativeSha256": report["privateMaster"]["native"]["sha256"],
            "motionSha256": report["motionSha256"],
            "sameCleanFramesForBothLanguages": True, "modelPixelsUnchangedBeforeDeliveryEncoding": True,
            "sharedDecodedFramesSha256": report["sharedDecodedFramesSha256"],
            "masterQuality": report["masterQuality"],
            "languages": report["languages"],
        }
    validation_path = OUTPUT / "validation.json"
    write_json(validation_path, {"schemaVersion": 1, "revisionId": REVISION, "status": "PASS", "designs": checks,
                                "scope": "Annotation/language-only change. Original CAD, poses, camera, motion scale, frame count, timing and rendering settings retained. No new physics or qualification."})
    files.append(validation_path)
    result = {
        "schemaVersion": 1, "revisionId": REVISION,
        "baseManifest": {"path": str((BASE / "walking-manifest.json").relative_to(ROOT)), **fingerprint(BASE / "walking-manifest.json")},
        "artifactCommit": base["artifactCommit"], "inputCommit": base["inputCommit"],
        "sourceHash": base["sourceHash"], "manufacturingRelease": False, "physicalQualifiedCount": 0,
        "defaults": {"captionTrackMode": "disabled", "inputRpm": 120, "timeFactor": 16},
        "layout": catalog["layout"], "designs": designs,
        "files": {str(p.relative_to(ROOT)): fingerprint(p) for p in files},
    }
    write_json(OUTPUT / "manifest.json", result)
    print(json.dumps({"revision": REVISION, "movieBytes": sum(d["locales"][l]["video"]["bytes"] for d in designs.values() for l in ("ja", "en"))}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--preview", choices=list("ABC"))
    action.add_argument("--render-clean", choices=list("ABC"))
    action.add_argument("--compose-preview", choices=list("ABC"))
    action.add_argument("--compose", choices=list("ABC"))
    action.add_argument("--finalize", action="store_true")
    parser.add_argument("--master-dir", type=Path)
    parser.add_argument("--frame", type=int, default=39)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else None)
    if args.finalize:
        finalize()
        return
    if args.master_dir is None:
        parser.error("--master-dir is required; clean masters must remain private")
    folder = args.master_dir.resolve()
    if folder.is_relative_to(OUTPUT.resolve()) or folder.is_relative_to((ROOT / "site/dist/TeoJansen_Rhinoceros").resolve()):
        raise ValueError("Private masters must not be placed in a public media directory")
    if args.preview or args.render_clean:
        lock_path = ROOT / "site/dist/r7-blender-prep/render.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            render_clean(args.preview or args.render_clean, folder, args.frame if args.preview else None)
    elif args.compose_preview:
        preview(args.compose_preview, folder, args.frame)
    else:
        compose(args.compose, folder)


if __name__ == "__main__":
    main()
