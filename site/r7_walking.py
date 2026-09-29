"""Publish only the separately versioned, source-pinned walking visualization."""

import argparse
from html import escape
import json
import math
from pathlib import Path
import re
import shutil
import subprocess

from PIL import Image

from r7_data import ROOT, Snapshot, digest

WALK = ROOT / "docs/ver3/r7_walking_v1"
REVISION = "r7-floor2-walking-kinematic-v1"
NATIVE = "Blender/Ver.3/integrated_r7/r7_walking_v1.blend"
LOCALIZED = ROOT / "docs/ver3/r7_walking_locales_v1"
LOCALIZED_REVISION = "r7-floor2-walking-localized-v1"


def validate_localized_media(media, base, source):
    prefix = "docs/ver3/r7_walking_locales_v1/"
    allowed = {"site/r7_video_locales.py", "site/r7_video_texts.json", prefix + "validation.json"}
    allowed.update(prefix + f"render_{design}.json" for design in "ABC")
    allowed.update(prefix + f"{locale}/walking_{design}.{extension}"
                   for locale in ("ja", "en") for design in "ABC" for extension in ("mp4", "png", "vtt"))
    base_bytes = (WALK / "walking-manifest.json").read_bytes()
    if (media["schemaVersion"] != 1 or media["revisionId"] != LOCALIZED_REVISION
            or media["manufacturingRelease"] is not False or media["physicalQualifiedCount"] != 0
            or media["baseManifest"] != {"path": "docs/ver3/r7_walking_v1/walking-manifest.json",
                                        "sha256": digest(base_bytes), "bytes": len(base_bytes)}
            or any(media[key] != source.source[key] for key in ("artifactCommit", "inputCommit", "sourceHash"))
            or media["defaults"] != {"captionTrackMode": "disabled", "inputRpm": 120, "timeFactor": 16}
            or set(media["designs"]) != set("ABC") or set(media["files"]) != allowed):
        raise ValueError("Localized walking source, qualification, defaults or allowlist differs")
    for name, expected in media["files"].items():
        path = ROOT / name
        if (not path.resolve().is_relative_to(ROOT) or path.is_symlink() or not path.is_file()
                or path.stat().st_size != expected["bytes"] or digest(path.read_bytes()) != expected["sha256"]):
            raise ValueError(f"Localized walking artifact fingerprint differs: {name}")
    validation = json.loads((LOCALIZED / "validation.json").read_text())
    text_catalog = json.loads((ROOT / "site/r7_video_texts.json").read_text())
    texts = text_catalog["locales"]
    if media["layout"] != text_catalog["layout"] or text_catalog["revisionId"] != LOCALIZED_REVISION:
        raise ValueError("Localized walking annotation layout differs from its pinned catalog")
    if validation["status"] != "PASS" or validation["revisionId"] != LOCALIZED_REVISION:
        raise ValueError("Localized walking media validation is incomplete")
    for design, entry in media["designs"].items():
        original = json.loads((WALK / f"render_{design}.json").read_text())
        render = json.loads((LOCALIZED / f"render_{design}.json").read_text())
        checks = validation["designs"][design]
        for field in ("fps", "frameCount", "width", "height", "prescribedSeconds", "timeFactor", "cycles", "motionSha256"):
            if entry[field] != original[field]:
                raise ValueError(f"{design}: localization changed the original {field}")
        if (not math.isclose(entry["durationSeconds"], original["durationSeconds"], abs_tol=1e-6)
                or entry["forwardMm"] != base["movies"][design]["forwardMm"]
                or set(entry["locales"]) != {"ja", "en"}
                or checks["sameCleanFramesForBothLanguages"] is not True
                or checks["modelPixelsUnchangedBeforeDeliveryEncoding"] is not True
                or checks["sourceNativeSha256"] != base["files"][NATIVE]["sha256"]
                or checks["motionSha256"] != entry["motionSha256"]
                or render["evaluatorSha256"] != original["evaluatorSha256"]
                or render["privateMaster"]["cameraAndMechanicalTransformsUnchanged"] is not True
                or render["privateMaster"]["mechanicalInstanceCount"] != source.source["expectedInstances"][design]
                or render["captionCatalog"] != media["files"]["site/r7_video_texts.json"]
                or render["maximumChangedPixelOutsideAnnotationRegions"] != 0
                or render["sharedDecodedFramesSha256"] != checks["sharedDecodedFramesSha256"]
                or checks["masterQuality"]["minimumPsnrDb"] < checks["masterQuality"]["thresholdPsnrDb"]):
            raise ValueError(f"{design}: localized media changed motion, source or model pixels")
        original_cues = re.findall(r"^.* --> .*$", (WALK / f"walking_{design}.vtt").read_text(), re.M)
        for locale, variant in entry["locales"].items():
            for kind, extension in (("video", "mp4"), ("poster", "png"), ("captions", "vtt")):
                expected_path = prefix + f"{locale}/walking_{design}.{extension}"
                record = variant[kind]
                if (record["path"] != expected_path
                        or any(record[field] != media["files"][expected_path][field] for field in ("sha256", "bytes"))):
                    raise ValueError(f"{design}/{locale}: localized {kind} does not match its pinned file")
            captions = variant["captions"]
            if (captions["lang"] != locale or captions["default"] is not False
                    or variant["title"] != texts[locale]["accessibleTitle"].format(design=design)
                    or variant["description"] != texts[locale]["description"].format(design=design, forward=entry["forwardMm"])
                    or captions["label"] != texts[locale]["captionLabel"]
                    or (variant["poster"]["width"], variant["poster"]["height"]) != (960, 720)):
                raise ValueError(f"{design}/{locale}: caption language, description or poster differs")
            cues = (ROOT / captions["path"]).read_text()
            if re.findall(r"^.* --> .*$", cues, re.M) != original_cues:
                raise ValueError(f"{design}/{locale}: caption timing changed")
            if locale == "en" and re.search(r"[ぁ-ゖァ-ヺ一-龯]", cues + variant["title"] + variant["description"]):
                raise ValueError(f"{design}: English walking media retains Japanese captions")
            decoded = checks["languages"][locale]
            if (decoded["frameCount"] != entry["frameCount"] or decoded["fps"] != "24/1"
                    or (decoded["width"], decoded["height"]) != (960, 720)
                    or not math.isclose(decoded["durationSeconds"], entry["durationSeconds"], abs_tol=1e-6)
                    or decoded["bytes"] != variant["video"]["bytes"]):
                raise ValueError(f"{design}/{locale}: decoded media no longer matches its delivery record")
    return media


def build_walking(output, guides, ref, *, preview=False):
    from build import source_url
    source = Snapshot(use_git=False)
    media = None
    localized = None
    if not preview:
        media = json.loads((WALK / "walking-manifest.json").read_text())
        if (media["revisionId"] != REVISION or media["artifactCommit"] != source.commit
                or media["contractSha256"] != source.source["contractSha256"]
                or media["status"] != "PASS" or media["manufacturingRelease"] is not False
                or media["physicalQualifiedCount"] != 0):
            raise ValueError("Walking artifacts belong to another source or qualification status")
        base = "docs/ver3/r7_walking_v1/"
        allowed = {NATIVE, base + "MODEL_ja.md", base + "native-validation.json"}
        allowed.update("site/" + name for name in (
            "r7-walk-math.js", "r7-walk-export.mjs", "r7_walk_model.py",
            "r7_walk_render.py", "r7_walk_verify_native.py", "r7_walk_finalize.py"))
        allowed.update(base + f"{stem}_{d}.{extension}" for d in "ABC" for stem, extension in (
            ("motion", "json"), ("validation", "json"), ("reference", "json"), ("render", "json"),
            ("walking", "mp4"), ("walking", "png"), ("walking", "vtt")))
        if set(media["files"]) != allowed:
            raise ValueError("Walking source/media file allowlist differs")
        for name, entry in media["files"].items():
            path = ROOT / name
            if path.is_symlink() or not path.is_file() or path.stat().st_size != entry["bytes"] or digest(path.read_bytes()) != entry["sha256"]:
                raise ValueError(f"Walking artifact fingerprint differs: {name}")
        localized = validate_localized_media(json.loads((LOCALIZED / "manifest.json").read_text()), media, source)
    assets, entries, reports, films = {}, {}, {}, []

    def copy(path, filename):
        original = path.read_bytes()
        dimensions = None
        if path.suffix == ".png":
            filename = str(Path(filename).with_suffix(".webp"))
            with Image.open(path) as image:
                clean = Image.new("RGB", image.size)
                clean.paste(image.convert("RGB"))
                clean.save(output / filename, "WEBP", quality=88, method=6)
                dimensions = clean.size
        else:
            shutil.copyfile(path, output / filename)
        data = (output / filename).read_bytes()
        assets[filename] = {"source": str(path.relative_to(ROOT)), "source_sha256": digest(original),
                            "sha256": digest(data), "bytes": len(data), "bundle_group": "walking",
                            "loading": "on-demand", "display_revision": REVISION}
        if dimensions:
            assets[filename].update(width=dimensions[0], height=dimensions[1], metadata_removed=True, loading="poster")
        return filename

    for design in ("C", "A", "B"):
        path = WALK / f"motion_{design}.json"
        if preview and not path.exists():
            continue
        motion = json.loads(path.read_text())
        report = json.loads((WALK / f"validation_{design}.json").read_text())
        original = next(d for d in source.contract["designs"] if d["id"] == design)
        if (motion["revisionId"] != REVISION or motion["source"]["artifactCommit"] != source.commit
                or motion["source"]["assemblySha256"] != original["assembly"]["sha256"]
                or motion["source"]["contactFramesSha256"] != original["contactFrames"]["sha256"]
                or motion["source"]["meshSha256"] != original["mesh"]["sha256"]
                or motion["instanceCount"] != guides[design]["model"]["instanceCount"]
                or motion["canonicalIndependentRockerAngleRad"] is not None
                or motion["manufacturingRelease"] is not False or motion["physicalQualifiedCount"] != 0
                or report["status"] != "PASS" or not all(report["checks"].values())
                or report["nativeNoncontactFloorSamples"] < 720 or report["samples"] < 5760):
            raise ValueError(f"{design}: stale or failed continuous walking model")
        filename = copy(path, f"assets/r7-walk-{design}.json")
        copy(WALK / f"validation_{design}.json", f"assets/r7-walk-validation-{design}.json")
        model = guides[design]["model"]
        entries[design] = {
            "motionUrl": filename, "motionSha256": assets[filename]["sha256"],
            "modelUrl": guides[design]["modelUrl"], "modelSha256": model["sha256"],
            "transportSha256": model["transportSha256"],
            "assemblySha256": original["assembly"]["sha256"], "meshSha256": original["mesh"]["sha256"],
            "inputTurnsPerCrank": motion["inputTurnsPerCrank"],
        }
        reports[design] = report
        if media:
            for locale, variant in localized["designs"][design]["locales"].items():
                suffix = "" if locale == "ja" else "-en"
                for kind, extension in (("video", "mp4"), ("captions", "vtt"), ("poster", "png")):
                    filename = copy(ROOT / variant[kind]["path"], f"assets/r7-walking-{design}{suffix}.{extension}")
                    assets[filename].update(locale=locale, media_revision=LOCALIZED_REVISION)
            variant = localized["designs"][design]["locales"]["ja"]
            title = escape(variant["title"], quote=True)
            caption = variant["captions"]
            films.append(f'''<article class="walk-film media" id="walking-film-{design}"><h3>Ver.3.1 · {title} · {abs(motion["inputTurnsPerCrank"]):g}:1</h3>
              <video id="r7-walking-{design}" controls playsinline preload="none" width="960" height="720"
                poster="assets/r7-walking-{design}.webp" aria-label="Ver.3.1 · {title}" title="{escape(variant["description"], quote=True)}" aria-describedby="walking-version-note walking-note-{design}">
                <source src="assets/r7-walking-{design}.mp4" type="video/mp4">
                <track kind="captions" src="assets/r7-walking-{design}.vtt" srclang="{caption["lang"]}" label="{escape(caption["label"], quote=True)}">
                MP4のダウンロードをご利用ください。</video>
              <div class="video-caption"><button type="button" class="button video-toggle" data-video="r7-walking-{design}"
                data-label="{title}" aria-controls="r7-walking-{design}" hidden>{title}を再生</button>
              <p id="walking-note-{design}"><strong>規定入力120 rpm／時間圧縮16×／実機未検証。</strong>
                {4 * motion["forwardPerCycleMm"]:.1f} mmの計算上の前進（4周期）。ばね・空中ロッカーは明示した表示モデルです。</p>
              <p class="media-error" role="status" hidden>動画を再生できませんでした。MP4をダウンロードしてご覧ください。</p>
              <a href="assets/r7-walking-{design}.mp4" download>歩行MP4をダウンロード</a></div></article>''')
    if not entries or (not preview and set(entries) != set("ABC")):
        raise ValueError("Walking delivery requires all three designs")
    if localized:
        copy(LOCALIZED / "manifest.json", "assets/r7-walking-locales-manifest.json")
        copy(LOCALIZED / "validation.json", "assets/r7-walking-locales-validation.json")
    catalog = {"schemaVersion": 1, "revisionId": REVISION, "artifactCommit": source.commit, "designs": entries}
    filename = "assets/r7-walking-index.json"
    data = (json.dumps(catalog, separators=(",", ":")) + "\n").encode()
    (output / filename).write_bytes(data)
    assets[filename] = {"source": "site/r7_walking.py", "source_sha256": digest(Path(__file__).read_bytes()),
                        "sha256": digest(data), "bytes": len(data), "bundle_group": "walking", "loading": "on-demand"}
    ratios = {"A": "220 mm／144:1", "B": "160 mm／512:1", "C": "200 mm／156:1"}
    validation = "".join(
        f'<p><strong>{d}案</strong>：{r["samples"]}位相、{r["instanceCount"]}点。'
        f'非接地部の最小床隙間 {r["minimumNativeNoncontactEnvelopeZMm"]:.3f} mm（0.5°標本）、'
        f'最大ばね圧縮 {r["maximumGuideCompressionMm"]:.3f} mm／上限6 mm、'
        f'ロッカー最大 {r["maximumRockerAngleDeg"]:.3f}°／範囲±5°。'
        f'<a href="assets/r7-walk-validation-{d}.json">数値検証JSON</a> · '
        f'<a href="assets/r7-walk-{d}.json">版付き運動データ</a></p>' for d, r in reports.items())
    sources = "" if preview else (
        f'<a href="{source_url("source", "docs/ver3/r7_walking_v1/MODEL_ja.md", ref)}">モデル・仮定・再現方法</a>'
        f'<a href="{source_url("source", "docs/ver3/r7_walking_v1/walking-manifest.json", ref)}">媒体・ソースのハッシュ</a>'
        '<a href="assets/r7-walking-locales-manifest.json">日英動画・字幕の来歴</a>'
        f'<a href="{source_url("download", NATIVE, ref)}">編集可能な歩行Blender原本</a>'
        f'<a href="{source_url("source", "site/r7_walk_render.py", ref)}">同じ運動データからの再生成スクリプト</a>')
    replacements = {
        "{{walk_preview_notice}}": "初回ローカルプレビュー。動画は未生成です。" if preview else "",
        "{{walk_design_options}}": "".join(f'<option value="{d}">{d} · {ratios[d]}</option>' for d in entries),
        "{{walk_movies}}": ('<p class="small-note" id="walking-caption-help">注記はページと同じ言語です。CCは任意に表示できます。小さい画面では全画面表示・CC・この本文をご利用ください。</p>'
                            + "".join(films)) if media else '<p class="record-scope">まず上の操作可能な連続歩行をご覧ください。このローカルプレビューの動画は次工程で生成します。</p>',
        "{{walk_validation}}": '<div class="walk-validation"><h3>この表示モデルの有限標本確認</h3>' + validation + "</div>",
        "{{walk_sources}}": sources,
        "{{r7_walking}}": '''<section class="section" id="r7-walking"><p class="eyebrow">NEW / CONTINUOUS WALKING</p>
          <h2>Ver.3.1 六脚の連続歩行へ。</h2><p>床是正版の全体が地面を進む3Dと、A/B/Cそれぞれの新しい歩行MP4を用意しました。
          入力120 rpmの規定運動に、別版の接地再整合・空中ロッカー・ばね表示を追加。実機の自己始動・歩行実証ではありません。</p>
          <a class="button primary" href="walking.html">Ver.3.1 連続歩行シミュレーションを開く →</a></section>''',
    }
    return replacements, assets


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true", required=True)
    args = parser.parse_args()
    output = ROOT / "site/dist/TeoJansen_Rhinoceros"
    guides = {d: json.loads((output / f"assets/r7-assembly-{d}.json").read_text()) for d in "ABC"}
    ref = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    replacements, _ = build_walking(output, guides, ref, preview=True)
    html = (ROOT / "site/walking.html").read_text()
    for key, value in replacements.items():
        html = html.replace(key, value)
    (output / "walking.html").write_text(html)
    for name in ("walking.css", "walking-loader.js"):
        shutil.copyfile(ROOT / "site" / name, output / name)
    subprocess.run(["node", str(ROOT / "site/build-viewer.mjs"), str(output), "--walking"], cwd=ROOT, check=True)
    print("First local continuous preview: /TeoJansen_Rhinoceros/walking.html")
