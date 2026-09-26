"""Build only the public showcase assets; never copy the repository wholesale."""

from __future__ import annotations

import argparse
import hashlib
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import quote, unquote, urlsplit

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
REPOSITORY = "ktanino10/TeoJansen_Rhinoceros"
SLUG = "TeoJansen_Rhinoceros"
DEFAULT_OUTPUT = SITE / "dist" / SLUG
MAX_BUNDLE_BYTES = 30_000_000
MAX_STATIC_BYTES = 12_000_000
PAGES = ("index.html", "production.html", "comparison.html", "viewer.html")
IMAGES = {
    "hero": ("docs/images/テオヤンセンver2完成3.jpg", (320, 0, 1240, 1100), 1100),
    "v1-photo": ("docs/images/テオヤンセンver1完成1.jpg", (70, 0, 1240, 1090), 1050),
    "v1-cg": ("docs/images/テオヤンセン2.png", None, 1050),
    "v2-photo": ("docs/images/テオヤンセンver2完成1.jpg", (330, 20, 1270, 1045), 1100),
    "comparison": ("docs/ver3/media/comparison.png", None, 1280),
    "frame-c": ("docs/ver3/media/frame_C.png", None, 1000),
    "drive": ("docs/ver3/media/drivetrain_detail.png", None, 1000),
    "exploded": ("docs/ver3/media/exploded_A.png", None, 1000),
    "rex-connection": ("docs/ver3/media/rex_connection.png", None, 1100),
    **{f"hero-{i}": (f"docs/ver3/media/hero_{i}.png", None, 900) for i in "ABC"},
    **{f"walking-{i}": (f"docs/ver3/media/walking_{i}.png", None, 1000) for i in "ABC"},
    "making-printer": ("docs/images/88187.jpg", (20, 0, 920, 1110), 700),
    "making-sanding": ("docs/images/88075_0.jpg", (190, 210, 1450, 1050), 850),
    "making-cleaning": ("docs/images/88073_0.jpg", (90, 170, 1080, 1380), 700),
    "making-booth": ("docs/images/88072.jpg", (130, 100, 1350, 1020), 800),
    "making-airbrush": ("docs/images/2339528.jpg", (400, 20, 3420, 2950), 800),
    "making-paint-prep": ("docs/images/88208_0.jpg", (290, 25, 1360, 1090), 800),
    "making-drying": ("docs/images/88089_0.jpg", (565, 30, 1310, 780), 700),
    "making-finish": ("docs/images/88209_0.jpg", (135, 100, 1410, 1070), 850),
    "making-decals": ("docs/images/88060_0.jpg", (210, 235, 1360, 1000), 800),
    "making-topcoat": ("docs/images/88061_0.jpg", (130, 130, 1440, 1080), 800),
    "making-finished-panels": ("docs/images/88059_0.jpg", (90, 270, 1400, 980), 800),
    "v1-concept-angle": ("docs/images/テオヤンセン1.png", None, 800),
    "v1-concept-side": ("docs/images/テオヤンセン3.png", None, 800),
    **{f"v1-view-{i}": (f"docs/images/テオヤンセンver1完成{i}.jpg", None, 800) for i in range(2, 7)},
    "v2-view-2": ("docs/images/テオヤンセンver2完成2.jpg", (285, 0, 1270, 1070), 800),
    "v2-view-4": ("docs/images/テオヤンセンver2完成4.jpg", (295, 0, 1250, 1090), 800),
    "v2-view-5": ("docs/images/テオヤンセンver2完成5.jpg", (395, 0, 1230, 1080), 800),
    "v2-view-6": ("docs/images/テオヤンセンver2完成6.jpg", (275, 0, 1270, 1080), 800),
    "gear-trial": ("docs/images/88476.jpg", (140, 100, 1000, 1240), 700),
    "gear-prototypes": ("docs/images/87813.jpg", (0, 130, 1370, 1110), 850),
    "turbines-real": ("docs/images/87816.jpg", (45, 205, 1215, 1090), 850),
    "turbines-angle": ("docs/images/Wheel2.jpg", None, 800),
    "turbines-top": ("docs/images/Wheel3.jpg", None, 650),
    "hook-front": ("docs/images/hook.jpg", None, 400),
    "hook-side": ("docs/images/hook2.jpg", None, 400),
    "v1-drive-front": ("docs/images/テオヤンセンv2joint v32.png", None, 800),
    "v1-drive-side": ("docs/images/テオヤンセンv2joint v322.png", None, 800),
    "v2-drive-front": ("docs/images/テオヤンセンv4joint v15.1.png", None, 800),
    "v2-drive-side": ("docs/images/テオヤンセンv4joint v15.png", None, 800),
}
COPIES = {
    **{f"walking_{i}.mp4": f"docs/ver3/media/walking_{i}.mp4" for i in "ABC"},
    "operation.mp4": "docs/ver3/media/operation.mp4",
    "exploded.mp4": "docs/ver3/media/exploded.mp4",
    "walk_preview.gif": "docs/ver3/media/walk_preview.gif",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_url(kind: str, path: str, ref: str) -> str:
    local = ROOT / path
    if not local.exists() or not local.resolve().is_relative_to(ROOT):
        raise ValueError(f"Invalid repository source link: {path}")
    route = {"source": "blob", "tree": "tree", "download": "raw"}[kind]
    return f"https://github.com/{REPOSITORY}/{route}/{ref}/{quote(path, safe='/')}"


def link(kind: str, path: str, label: str, ref: str, classes: str = "") -> str:
    href = source_url(kind, path, ref)
    return f'<a class="{classes}" href="{escape(href, quote=True)}">{escape(label)}</a>'


def display_image(name: str) -> Image.Image:
    source, crop, width = IMAGES[name]
    with Image.open(ROOT / source) as original:
        oriented = ImageOps.exif_transpose(original)
        if crop:
            oriented = oriented.crop(crop)
        oriented.thumbnail((width, width * 2), Image.Resampling.LANCZOS)
        clean = Image.new("RGB", oriented.size, "#eee9dd")
        if "A" in oriented.getbands():
            clean.paste(oriented.convert("RGB"), mask=oriented.getchannel("A"))
        else:
            clean.paste(oriented.convert("RGB"))
    return clean


def image(name: str, alt: str, eager: bool = False) -> str:
    loading = "eager" if eager else "lazy"
    priority = ' fetchpriority="high"' if eager else ""
    with display_image(name) as photo:
        width, height = photo.size
    return (f'<img src="assets/{name}.webp" alt="{escape(alt, quote=True)}" '
            f'width="{width}" height="{height}" loading="{loading}" decoding="async"{priority}>')


def figure(name: str, alt: str, caption: str, ref: str, eager: bool = False) -> str:
    return (f'<figure class="media">{image(name, alt, eager)}'
            '<p class="media-error" role="status" hidden>画像を読み込めませんでした。原典リンクから確認できます。</p>'
            f'<figcaption>{escape(caption)} '
            f'{link("source", IMAGES[name][0], "原典画像 ↗", ref)}</figcaption></figure>')


def video(name: str, poster: str, label: str, description: str, ref: str) -> str:
    filename = f"{name}.mp4"
    return f'''<div class="video-card media">
      <video id="{name}" controls playsinline preload="none" poster="assets/{poster}.webp"
        width="960" height="540" aria-label="{escape(label, quote=True)}" aria-describedby="{name}-note">
        <source src="assets/{filename}" type="video/mp4">
        お使いのブラウザーでは動画を表示できません。下のMP4リンクをご利用ください。
      </video>
      <div class="video-caption">
        <button type="button" class="button video-toggle" data-video="{name}"
          data-label="{escape(label, quote=True)}" aria-controls="{name}" hidden>{escape(label)}を再生</button>
        <p id="{name}-note">{description}</p>
        <p class="media-error" role="status" hidden>動画を再生できませんでした。MP4をGitHubで開いてください。</p>
        {link("source", COPIES[filename], "MP4をGitHubで開く ↗", ref)}
      </div>
    </div>'''


def design_cards(records: list[dict], ref: str) -> str:
    titles = {"A": "大風車・少段減速", "B": "小風車・高減速", "C": "中間風車・生成軽量"}
    explanations = {
        "A": "受風面積を広げ、HTD5M歯付きベルト2:1と平歯車3:1を組み合わせる。風荷重と張力調整が代償。",
        "B": "90 mmの風車を維持し、4:1の平歯車を三段に。低速化に加え、段数と軸受の始動抵抗が増える。",
        "C": "4:1の平歯車を二段にし、リブ形状を制約付きで探索。組立・接合・抵抗測定の最初の候補。",
    }
    result = []
    for record in records:
        row = record["comparison"]
        ident = row["prototype"]
        residual = row["maximum_single_episode_material_anchor_drift_mm"]
        note = (f'<strong>実機未検証・3 mm目標未達。</strong> 規定入力 {row["input_rpm"]:g} rpm、'
                f'3周期。動画 {row["video_seconds"]:g} 秒／モデル時間 {row["physical_seconds"]:g} 秒、'
                f'<strong>{row["time_scale"]:g}倍表示</strong>。材料点の最大水平残差は '
                f'{residual:.2f} mm。風・接触動力学の実証ではありません。')
        if ident == "B":
            note += '<strong> Bは名目トルク入力も不足しています。</strong>'
        result.append(f'''<article class="prototype" id="prototype-{ident}" aria-labelledby="title-{ident}">
          <div class="prototype-heading"><span class="prototype-letter">{ident}</span>
            <div><p class="eyebrow">ENGINEERING CONCEPT</p><h3 id="title-{ident}">{titles[ident]}</h3></div></div>
          {figure(f"hero-{ident}", f"Ver.3 {ident}案の実CADに基づく完成予想CG。実物ではない。", "Ver.3 · 設計CG／実物ではありません", ref)}
          <dl class="specs">
            <div><dt>風車径 × 幅</dt><dd>{row["rotor_diameter_mm"]:g} × {row["rotor_span_mm"]:g} mm</dd></div>
            <div><dt>総減速比</dt><dd>{row["reduction"]:g} : 1</dd></div>
            <div><dt>名目質量</dt><dd>{row["nominal_solid_and_hardware_mass_g"]/1000:.2f} kg</dd></div>
            <div><dt>材料点残差</dt><dd>{residual:.2f} mm <small>目標未達</small></dd></div>
          </dl>
          <p>{explanations[ident]}</p>
          {video(f"walking_{ident}", f"walking-{ident}", f"{ident}案の歩行", note, ref)}
        </article>''')
    return "\n".join(result)


def download_cards(records: list[dict], ref: str) -> str:
    result = []
    for record in records:
        ident = record["comparison"]["prototype"]
        links = [
            ("download", f"FreeCAD/Ver.3/{ident}/Ver3_{ident}.FCStd", "FreeCAD · FCStd"),
            ("download", f"FreeCAD/Ver.3/{ident}/Ver3_{ident}.step", "交換用 · STEP"),
            ("tree", f"STL/Ver.3/{ident}", "印刷部品 · STL一覧"),
            ("download", f"docs/ver3/BOM_{ident}.csv", "部品表 · CSV"),
            ("source", f"docs/ver3/assembly_{ident}.json", "正規組立データ · JSON"),
        ]
        items = []
        for kind, path, label in links:
            if (ROOT / path).is_file() and kind == "download":
                size = (ROOT / path).stat().st_size
                label += f" ({size/1e6:.1f} MB)" if size >= 1_000_000 else f" ({size/1000:.0f} KB)"
            items.append(f"<li>{link(kind, path, label, ref)}</li>")
        result.append(f'<article class="download-card"><h4>Ver.3 {ident}案</h4><ul>{"".join(items)}</ul></article>')
    return "".join(result)


class DocumentLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids: set[str] = set()
        self.links: list[str] = []
        self.elements: list[tuple[str, dict]] = []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if attrs.get("id"):
            if attrs["id"] in self.ids:
                raise ValueError(f"Duplicate page id: {attrs['id']}")
            self.ids.add(attrs["id"])
        for key in ("href", "src", "poster", "data-animation"):
            if attrs.get(key):
                self.links.append(attrs[key])
        self.elements.append((tag, attrs))


def validate(output: Path, manifest: dict) -> None:
    output = output.resolve()
    documents = {}
    for name in PAGES:
        text = (output / name).read_text()
        if "{{" in text or "/Users/" in text or "file://" in text:
            raise ValueError(f"Unresolved template or private path in {name}")
        parser = DocumentLinks()
        parser.feed(text)
        documents[name] = parser
    for name, parser in documents.items():
        for url in parser.links:
            split = urlsplit(url)
            if split.scheme or split.netloc:
                if split.scheme != "https":
                    raise ValueError(f"Insecure or unsupported external link: {url}")
                continue
            target = (output / unquote(split.path or name)).resolve()
            if split.path.startswith("/") or not target.is_relative_to(output):
                raise ValueError(f"Repository-subpath unsafe link: {url}")
            if not target.is_file():
                raise ValueError(f"Missing bundled asset: {url}")
            if split.fragment and target.suffix == ".html":
                target_page = documents[str(target.relative_to(output))]
                if unquote(split.fragment) not in target_page.ids:
                    raise ValueError(f"Missing anchor in {name}: {url}")
        for tag, attrs in parser.elements:
            if tag == "video" and not ({"controls", "playsinline"} <= attrs.keys()
                                        and attrs.get("preload") == "none" and "autoplay" not in attrs):
                raise ValueError("Video must be opt-in, accessible and not preload payloads")
            if tag == "img" and not (attrs.get("alt") and attrs.get("width") and attrs.get("height")):
                raise ValueError("Every content image needs alt text and dimensions")
    actual = {str(path.relative_to(output)) for path in output.rglob("*") if path.is_file()}
    expected = {*PAGES, "styles.css", "viewer.css", "app.js", "viewer-loader.js", "favicon.svg", ".nojekyll", "build-manifest.json",
                *manifest["assets"].keys()}
    if actual != expected:
        raise ValueError(f"Unexpected output files: {actual ^ expected}")
    total = sum(path.stat().st_size for path in output.rglob("*") if path.is_file())
    display = sum(entry["bytes"] for entry in manifest["assets"].values() if entry.get("loading") == "on-demand")
    if total > MAX_BUNDLE_BYTES or total - display > MAX_STATIC_BYTES or display > 18_000_000:
        raise ValueError("Public bundle exceeded the 12 MB static / 18 MB opt-in 3D budgets")
    for name in manifest["assets"]:
        path = output / name
        if path.suffix == ".webp":
            with Image.open(path) as photo:
                if photo.getexif() or any(key in photo.info for key in ("exif", "xmp", "icc_profile")):
                    raise ValueError(f"Display derivative retained metadata: {name}")


def build(output: Path, ref: str) -> dict:
    from viewer_data import build_viewer, static_guides

    if not re.fullmatch(r"[0-9a-f]{40}", ref):
        raise ValueError("Use an immutable, full 40-character Git commit for source links")
    output = output.resolve()
    if not output.is_relative_to((SITE / "dist").resolve()) or output == (SITE / "dist").resolve():
        raise ValueError("Build output must be a named child of site/dist")
    if output.exists():
        if output.is_symlink():
            raise ValueError("Build output must not be a symlink")
        shutil.rmtree(output)
    (output / "assets").mkdir(parents=True)
    assets = {}
    for name, (source, crop, _) in IMAGES.items():
        with display_image(name) as clean:
            destination = output / "assets" / f"{name}.webp"
            clean.save(destination, "WEBP", quality=88, method=6)
            assets[f"assets/{name}.webp"] = {"source": source, "source_sha256": sha256(ROOT / source),
                                           "crop": crop, "metadata_removed": True,
                                           "width": clean.width, "height": clean.height,
                                           "bytes": destination.stat().st_size, "sha256": sha256(destination)}
    for name, source in COPIES.items():
        destination = output / "assets" / name
        shutil.copyfile(ROOT / source, destination)
        assets[f"assets/{name}"] = {"source": source, "bytes": destination.stat().st_size,
                                   "sha256": sha256(destination), "source_sha256": sha256(ROOT / source)}
    guides, viewer_assets, viewer_source = build_viewer(output)
    assets.update(viewer_assets)
    subprocess.run(["node", str(SITE / "build-viewer.mjs"), str(output)], cwd=ROOT, check=True)
    for name, original in (("viewer-engine.js", "site/viewer.js"),
                           ("three-LICENSE.txt", "site/node_modules/three/LICENSE")):
        destination = output / "assets" / name
        assets[f"assets/{name}"] = {"source": original, "source_sha256": sha256(ROOT / original),
                                   "sha256": sha256(destination), "bytes": destination.stat().st_size}
    comparison = json.loads((ROOT / "docs/ver3/comparison.json").read_text())
    records = comparison["designs"]
    if [r["comparison"]["prototype"] for r in records] != list("ABC"):
        raise ValueError("Expected exactly the three canonical Ver.3 concepts")
    trials = json.loads((ROOT / "docs/ver3/structure_search_C.json").read_text())
    selected = records[2]["design"]["structure"]
    baseline = next(t for t in trials if t["plate_thickness_mm"] == 8 and t["rib_width_mm"] == 14)
    reduction = 100 * (1 - selected["volume_proxy_mm3"] / baseline["volume_proxy_mm3"])
    replacements = {
        "{{hero}}": figure("hero", "サボニウス型風車を備えたVer.2の実物。白いフレームと黒い足を持つ歩行模型。", "Ver.2 · 実物の制作記録（表示用トリミング）", ref, True),
        "{{v1_photo}}": figure("v1-photo", "六枚羽の風車を備えたVer.1実物の斜めからの写真。", "Ver.1 · 実物の完成写真", ref),
        "{{v1_cg}}": figure("v1-cg", "Ver.1設計CG。屋外の背景を使ったレンダリングで、実物の屋外撮影ではない。", "Ver.1 · Fusion 360設計CG／実物写真ではありません", ref),
        "{{v2_photo}}": figure("v2-photo", "Ver.2の実物。カップ状の風車と脚・歯車の構成が見える。", "Ver.2 · 実物の完成写真（表示用トリミング）", ref),
        "{{comparison}}": figure("comparison", "Ver.3のA・B・Cを同じ尺度で比較した設計CG。風車径は300・90・180mm。", "Ver.3 · 同一実寸スケールの設計CG／実機未検証", ref),
        "{{frame_c}}": figure("frame-c", "Ver.3 C案の制約付き生成リブ構造を示すCAD由来のCG。", "Ver.3 C · 生成したフレームの設計CG", ref),
        "{{design_cards}}": design_cards(records, ref),
        "{{download_cards}}": download_cards(records, ref),
        "{{operation}}": video("operation", "drive", "駆動機構", "<strong>規定運動・実機未検証。</strong> CADと同じ軸・歯車比を表示。風や接触動力学の実証ではありません。", ref),
        "{{exploded}}": video("exploded", "exploded", "分解説明", "<strong>説明用の分解オフセット。</strong> 同時に動かす映像だけでは組立経路を証明しません。実際の順序は組立資料を参照してください。", ref),
        "{{generation_reduction}}": f"{reduction:.2f}",
        "{{source_commit}}": ref[:7],
        "{{repository_url}}": f"https://github.com/{REPOSITORY}",
        "{{source_tree}}": f"https://github.com/{REPOSITORY}/tree/{ref}",
        "{{assembly_guides}}": static_guides(guides, viewer_source),
        "{{viewer_revision}}": escape(viewer_source["label"]),
        "{{viewer_revision_id}}": escape(viewer_source["revisionId"]),
        "{{viewer_source}}": f"https://github.com/{REPOSITORY}/tree/{viewer_source['canonicalCommit']}",
        "{{matrix_specs}}": '<div class="matrix-summary">' + "".join(
            f'<article><h3>Ver.3 {r["comparison"]["prototype"]}案</h3>'
            f'<p>風車 {r["comparison"]["rotor_diameter_mm"]:g} × {r["comparison"]["rotor_span_mm"]:g} mm<br>'
            f'総減速比 {r["comparison"]["reduction"]:g} : 1<br>'
            f'名目質量 {r["comparison"]["nominal_solid_and_hardware_mass_g"]/1000:.2f} kg</p>'
            f'<p><strong>材料点残差 {r["comparison"]["maximum_single_episode_material_anchor_drift_mm"]:.2f} mm · 3 mm目標未達</strong></p>'
            f'<a href="viewer.html?design={r["comparison"]["prototype"]}">{r["comparison"]["prototype"]}の360°と組立へ →</a></article>'
            for r in records) + "</div>",
    }
    for name in PAGES:
        html = (SITE / name).read_text()
        for token, value in replacements.items():
            html = html.replace(token, value)
        html = re.sub(r"\{\{figure:([\w-]+)\|([^|{}]+)\|([^|{}]+)\}\}",
                      lambda match: figure(match[1], match[2], match[3], ref), html)
        html = re.sub(r"\{\{(source|tree|download):([^}]+)\}\}",
                      lambda match: escape(source_url(match[1], match[2], ref), quote=True), html)
        (output / name).write_text(html)
    for name in ("styles.css", "viewer.css", "app.js", "viewer-loader.js", "favicon.svg"):
        shutil.copyfile(SITE / name, output / name)
    (output / ".nojekyll").write_text("")
    manifest = {"schema": 1, "repository": REPOSITORY, "source_commit": ref, "pages": list(PAGES),
                "repository_subpath": f"/{SLUG}/",
                "comparison_sha256": sha256(ROOT / "docs/ver3/comparison.json"),
                "assets": assets, "bundle_budget_bytes": MAX_BUNDLE_BYTES,
                "static_budget_bytes": MAX_STATIC_BYTES, "on_demand_3d_budget_bytes": 18_000_000,
                "engineering_source": viewer_source,
                "note": "Only selected display derivatives and existing media are deployed. Exact-mesh GLBs are opt-in display data; native CAD/STL/BOM downloads remain on GitHub."}
    (output / "build-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    validate(output, manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--ref", default=None)
    args = parser.parse_args()
    commit = args.ref or subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    result = build(args.output, commit)
    print(f"Built {args.output.relative_to(ROOT) if args.output.is_absolute() else args.output}: "
          f"{len(result['assets'])} selected display assets; validated subpath, privacy and bundle budget.")
