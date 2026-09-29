"""Seal verified walking media and source files; never promote a failed mechanical release."""

import hashlib
import json
from pathlib import Path
import subprocess

from PIL import Image

from r7_data import Snapshot
from r7_walking import WALK, NATIVE, REVISION

ROOT = Path(__file__).resolve().parents[1]


def record(path):
    data = path.read_bytes()
    if len(data) >= 100_000_000:
        raise ValueError("Walking delivery exceeds the per-file ceiling")
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def vtt_time(seconds):
    ms = round(seconds * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02}.{ms % 1000:03}"


def main():
    source = Snapshot(use_git=False)
    native = json.loads((WALK / "native-validation.json").read_text())
    if native["status"] != "PASS" or native["nativeSha256"] != record(ROOT / NATIVE)["sha256"]:
        raise ValueError("The saved native scene has not passed verification")
    files = [ROOT / NATIVE, WALK / "native-validation.json", WALK / "MODEL_ja.md"]
    files += [ROOT / "site" / name for name in (
        "r7-walk-math.js", "r7-walk-export.mjs", "r7_walk_model.py",
        "r7_walk_render.py", "r7_walk_verify_native.py", "r7_walk_finalize.py")]
    movies = {}
    evaluator_sha = record(ROOT / "site/r7-walk-math.js")["sha256"]
    for design in "ABC":
        motion_path = WALK / f"motion_{design}.json"
        motion = json.loads(motion_path.read_text())
        validation = json.loads((WALK / f"validation_{design}.json").read_text())
        render = json.loads((WALK / f"render_{design}.json").read_text())
        if (validation["status"] != "PASS" or motion["source"]["artifactCommit"] != source.commit
                or render["motionSha256"] != record(motion_path)["sha256"]
                or render["evaluatorSha256"] != evaluator_sha
                or native["designs"][design]["motionSha256"] != render["motionSha256"]):
            raise ValueError("Walking source, numeric evidence and film differ")
        movie = WALK / f"walking_{design}.mp4"
        info = json.loads(subprocess.check_output([
            "ffprobe", "-v", "error", "-count_frames", "-show_streams", "-of", "json", str(movie)], text=True))
        if len(info["streams"]) != 1:
            raise ValueError("Only a silent, opt-in video stream is allowed")
        stream = info["streams"][0]
        if ((stream["width"], stream["height"], stream["codec_name"], stream["pix_fmt"]) != (960, 720, "h264", "yuv420p")
                or int(stream["nb_read_frames"]) != render["frameCount"]
                or stream["r_frame_rate"] != f'{render["fps"]}/1'
                or abs(float(stream["duration"]) - render["frameCount"] / render["fps"]) > .002):
            raise ValueError("Movie dimensions, frame count or prescribed timing differ")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(movie), "-f", "null", "-"], check=True)
        sampled = subprocess.check_output(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(movie),
            "-vf", "fps=2,crop=iw/2:ih/3:iw/4:ih/2,scale=48:32", "-f", "framemd5", "-"], text=True)
        hashes = [line.rsplit(",", 1)[-1].strip() for line in sampled.splitlines() if line and not line.startswith("#")]
        if len(set(hashes)) < len(hashes) * .9:
            raise ValueError("Walking film does not contain sufficiently distinct rendered leg-region frames")
        duration = float(stream["duration"])
        captions = [
            f"{design}案・r7床是正版の連続歩行計算です。実機の映像ではありません。\n入力120 rpmを規定し、16倍の時間圧縮で表示しています。",
            "実寸の歯車・クランク・リンクがつながり、六脚の荷重足と戻り足が交代します。\n同じ入力条件では512:1のB案はA・C案より遅く進みます。",
            "空中ロッカーは中立復帰の表示仮定、12本のばねは座・線径・巻数を保持する手続き形状です。\n元解析の独立ロッカー角nullは変更していません。",
            f"4周期の計算上の前進は{4 * motion['forwardPerCycleMm']:.1f} mmです。実測距離ではありません。\n風・実自己始動・実30 cm歩行は未確認、実機合格0のままです。",
        ]
        (WALK / f"walking_{design}.vtt").write_text("WEBVTT\n\n" + "\n\n".join(
            f"{vtt_time(i * duration / 4)} --> {vtt_time((i + 1) * duration / 4)}\n{text}"
            for i, text in enumerate(captions)) + "\n")
        poster = WALK / f"walking_{design}.png"
        with Image.open(poster) as image:
            clean = Image.new("RGB", image.size)
            clean.paste(image.convert("RGB"))
            clean.save(poster, "PNG", optimize=True)
        movies[design] = {"width": stream["width"], "height": stream["height"],
                          "fps": render["fps"], "frameCount": render["frameCount"], "durationSeconds": duration,
                          "prescribedSeconds": render["prescribedSeconds"], "timeFactor": 16, "cycles": 4,
                          "forwardMm": 4 * motion["forwardPerCycleMm"], "decoded": True,
                          "sampledLegRegionFrames": len(hashes), "distinctSampledLegRegionFrames": len(set(hashes))}
        files += [WALK / f"{stem}_{design}.{extension}" for stem, extension in (
            ("motion", "json"), ("validation", "json"), ("reference", "json"), ("render", "json"),
            ("walking", "mp4"), ("walking", "png"), ("walking", "vtt"))]
    manifest = {
        "schemaVersion": 1, "revisionId": REVISION, "status": "PASS", "artifactCommit": source.commit,
        "inputCommit": source.source["inputCommit"], "sourceHash": source.source["sourceHash"],
        "contractSha256": source.source["contractSha256"],
        "manufacturingRelease": False, "physicalQualifiedCount": 0, "physicalTestsPerformed": False,
        "newMotionStatesAreVisualizationExtension": True, "canonicalRockerNullsUnmodified": True,
        "movies": movies, "native": native,
        "files": {str(path.relative_to(ROOT)): record(path) for path in files},
    }
    (WALK / "walking-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": "PASS", "movies": movies, "nativeBytes": record(ROOT / NATIVE)["bytes"]}, indent=2))


if __name__ == "__main__":
    main()
