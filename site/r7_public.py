"""Allowlisted r7 page, media and exact display models for the ordinary Pages build."""

from html import escape
import json
from pathlib import Path
import shutil

from PIL import Image

from r7_data import ROOT, BASE, Snapshot, build_candidate, digest
from build_r7_preview import comparison_html, overview_html, static_guides

MEDIA_ROOT = ROOT / "docs/ver3/r7_display_floor2"
NATIVE_PATH = "Blender/Ver.3/integrated_r7/r7_floor2.blend"


def build_public_r7(output, ref):
    from build import source_url
    source = Snapshot(use_git=False)
    if not source.source["publicationAuthorized"] or source.source.get("publicationHold"):
        raise ValueError("r7 publication is held until the corrected source and display gate are accepted")
    manifest = json.loads((MEDIA_ROOT / "display-manifest.json").read_text())
    if (manifest["artifactCommit"] != source.commit or manifest["contractSha256"] != source.source["contractSha256"]
            or manifest["allSavedDisplayFramesFloorGate"] != "PASS" or manifest["completeWalkingVideoGenerated"] is not False):
        raise ValueError("The source-bound r7 media or floor gate is stale")
    for name, entry in manifest["files"].items():
        path = ROOT / name
        if not path.is_file() or path.stat().st_size != entry["bytes"] or digest(path.read_bytes()) != entry["sha256"]:
            raise ValueError(f"r7 display artifact fingerprint differs: {name}")
    guides, catalog, assets, _ = build_candidate(output, source, public_links=True)
    for asset in assets.values():
        asset["source_sha256"] = digest((ROOT / asset["source"]).read_bytes())
        asset["bundle_group"] = "r7"
    displays = {}
    for name, entry in manifest["files"].items():
        path = ROOT / name
        if path.suffix == ".blend" or path.name in {"diagnostic_A.json", "diagnostic_B.json", "diagnostic_C.json"}:
            continue
        if path.suffix == ".png":
            filename = "assets/r7-" + path.stem.replace("_", "-") + ".webp"
            with Image.open(path) as original:
                clean = Image.new("RGB", original.size)
                clean.paste(original.convert("RGB"))
                clean.save(output / filename, "WEBP", quality=88, method=6)
                dimensions = clean.size
        elif path.suffix in {".mp4", ".vtt", ".json"}:
            filename = ("assets/r7-media-" if path.suffix == ".json" else "assets/r7-") + path.name.replace("_", "-")
            if filename in assets:
                raise ValueError(f"Media would overwrite a canonical viewer asset: {filename}")
            shutil.copyfile(path, output / filename)
            dimensions = None
        else:
            raise ValueError(f"Unexpected r7 display media type: {name}")
        data = (output / filename).read_bytes()
        assets[filename] = {"source": name, "source_sha256": entry["sha256"], "sha256": digest(data),
                            "bytes": len(data), "bundle_group": "r7", "display_revision": source.source["revisionId"]}
        if dimensions:
            assets[filename].update(width=dimensions[0], height=dimensions[1], metadata_removed=True)
            displays[path.stem] = (filename, dimensions)

    def image(stem, caption, *, eager=False):
        filename, (width, height) = displays[stem]
        loading = 'loading="eager" fetchpriority="high"' if eager else 'loading="lazy"'
        return (f'<figure class="media"><img src="{filename}" width="{width}" height="{height}" {loading} decoding="async" '
                f'alt="{escape(caption)}"><p class="media-error" role="status" hidden>画像を読み込めませんでした。原本リンクをご利用ください。</p>'
                f'<figcaption>{escape(caption)} <a href="{source_url("source", str((MEDIA_ROOT/(stem+".png")).relative_to(ROOT)), ref)}">'
                '原寸画像 ↗</a></figcaption></figure>')

    media_sections = []
    for ident, guide in guides.items():
        clips = []
        for mode, label in (("assembly", "組立"), ("disassembly", "取外しの逆順参照")):
            source_name = f"{mode}_{ident}.mp4"
            video_id = f"r7-{mode}-{ident}"
            name = f"{ident}案の{label}"
            clips.append(f'''<div class="video-card media">
              <video id="{video_id}" controls playsinline preload="none" width="1280" height="720"
                poster="assets/r7-hero-{ident}.webp" aria-label="{name}" aria-describedby="{video_id}-note">
                <source src="assets/r7-{mode}-{ident}.mp4" type="video/mp4">
                <track kind="captions" src="assets/r7-{mode}-{ident}.vtt" srclang="ja" label="日本語の工程説明" default>
                MP4の原本リンクをご利用ください。</video>
              <div class="video-caption"><button class="button video-toggle" data-video="{video_id}" data-label="{name}" aria-controls="{video_id}" type="button" hidden>{name}を再生</button>
              <p id="{video_id}-note"><strong>{label}の説明用時間・停止角0°。</strong>原典の操作境界と有限経路標本を順に表示します。
              灰色は装着済みで残る部品、透明なPETも存在します。非表示は取外し／未配置であり、透明化と区別しています。
              手による仮支持・別作業台・同ID再挿入を省略しません。実際の作業時間・連続経路・現物組立の保証ではありません。</p>
              <p class="media-error" role="status" hidden>動画を再生できませんでした。原本MP4をご利用ください。</p>
              <a href="{source_url("source", str((MEDIA_ROOT/source_name).relative_to(ROOT)), ref)}">原本MP4 ↗</a></div></div>''')
        media_sections.append(f'<article class="r7-film" id="r7-media-{ident}"><h3>{ident}案 · 同版の組立・取外し参照</h3>'
                              f'<div class="two-column">{"".join(clips)}</div></article>')
    media_html = ('<section class="section" id="r7-media"><p class="eyebrow">SAME-SOURCE ASSEMBLY EXPLANATIONS</p>'
                  '<h2>12工程を、映像と編集可能なシーンで。</h2><p>全体を一斉に爆発させる映像ではありません。'
                  '表示時間は説明用で、風入力・歩行を動かした映像ではありません。取外し映像は同じ有限状態を逆順で辿る参照です。</p>'
                  + "".join(media_sections) + f'<div class="document-strip"><a href="{source_url("download", NATIVE_PATH, ref)}">'
                  '編集可能なBlender原本（全三案・工程・診断シーン）</a>'
                  f'<a href="{source_url("source", str((MEDIA_ROOT/"display-manifest.json").relative_to(ROOT)), ref)}">媒体の版・出典・検証記録</a></div></section>')

    diagnostic_groups = []
    for ident in "ABC":
        record = json.loads((MEDIA_ROOT/f"diagnostic_{ident}.json").read_text())
        max_difference = max(f["maximumFootCenterRepresentationDifferenceMm"] for f in record["frames"])
        frames = "".join(image(f"diagnostic_{ident}_{phase:03}",
                         f"{ident}案・クランク{phase}°の診断図。計算された位置を確認する表示で、未計算の足部品とばね線材は省略。")
                         for phase in (0, 120, 240))
        diagnostic_groups.append(f'<details class="image-detail r7-diagnostic" id="diagnostic-{ident}"><summary>{ident}案 · 0／120／240°を確認する</summary>'
                                 '<p>緑は保存された計算点、青はCADを伸縮させない直交表示フレームの代表点です。'
                                 f'本案の代表点の表示差は最大{max_difference:.6f} mm。床や部材を動かして差を隠していません。</p>'
                                 '<p>荷重足の左右パッド中心を等高にする角は、機械範囲内で一意な場合だけ「幾何による表示角」として使用。'
                                 '元solverの独立ロッカー角はnullのままです。空中足など未解決の角は省略し、ばね線材を伸縮して補完していません。</p>'
                                 f'<div class="r7-diagnostic-grid">{frames}</div>'
                                 f'<a href="{source_url("source", str((MEDIA_ROOT/f"diagnostic_{ident}.json").relative_to(ROOT)), ref)}">姿勢・省略ID・位置差の正本</a></details>')
    diagnostic_html = ('<section class="chapter-tinted" id="r7-diagnostics"><div class="section"><p class="eyebrow">SAVED CONTACT DATA / LIMITED VISUALIZATION</p>'
                       '<h2>以前の3位相診断：計算された位置を確認する。</h2><p><strong>この歴史資料では未計算の足部品は省略しています。完全なCAD歩行映像ではありません。</strong>'
                       '73保存フレームの前進・高さ・勾配・足圧縮を使い、0／120／240°だけを表示しました。独立ロッカー角と完全な剛体姿勢は未解決です。'
                       '正規の小角写像を全頂点へ掛けてせん断せず、表示専用の直交フレームと計算点の差を記録しています。'
                       '当時の診断結果と省略は保持し、後から別モデルで計算した連続歩行と混同しません。'
                       '<a href="walking.html">新しい連続歩行3D・動画と、その追加仮定はこちら</a>。</p>'
                       + "".join(diagnostic_groups) + '</div></section>')
    comparison, baseline = comparison_html(guides, source)
    links = catalog["links"]
    replacements = {
        "{{r7_robots}}": "", "{{r7_page_title}}": "Ver.3.1 現行設計 — 三案の連続歩行・360°・組立",
        "{{r7_local_only}}": "false", "{{r7_brand_note}}": "Ver.3.1 現行設計 · 実機未検証",
        "{{r7_scope_label}}": "SOURCE-BOUND DESIGN CANDIDATES",
        "{{r7_status_title}}": "Ver.3.1 床是正版 · 比較設計候補であり、実機の合格ではありません",
        "{{r7_resource_notice}}": "機械資料は床是正版の確定コミットへ、媒体は同じ形状・工程に基づく原本へリンクしています。大きなCAD／STL／BlenderはGitHubで必要なものだけ開けます。",
        "{{r7_scope_short}}": "床是正版", "{{r7_footer_note}}": "Ver.3.1 · 実風・実始動・実30cm歩行は未確認。",
        "{{r7_revision}}": source.source["revisionId"], "{{r7_candidate_revision}}": source.source["candidateRevision"],
        "{{r7_commit}}": source.source["publicSourceCommit"],
        "{{r7_slice_notice}}": "従来5点＋Cの新しい相手歯車2点を実層確認。Z0.2 mmの支持薄膜除去、支持面／歯下縁の仕上げ、実はめあいは未確認です。",
        "{{r7_comparison_image}}": image("comparison", "Ver.3.1床是正版のA・B・Cを同一尺度で並べた実CAD由来CG。無圧縮の組立基準姿勢で、実物ではありません。"),
        "{{r7_comparison}}": comparison, "{{r7_baseline}}": baseline,
        "{{r7_payload}}": "転送サイズ " + "／".join(f"{ident} {g['model']['transportBytes']/1e6:.2f} MB" for ident, g in guides.items()),
        "{{r7_fallback}}": '<div class="r7-fallback">' + "".join(image(f"hero_{d}", f"Ver.3.1 {d}案の床是正版・実CAD由来CG。") for d in "ABC") + "</div>",
        "{{r7_guides}}": static_guides(guides), "{{r7_media}}": media_html, "{{r7_diagnostics}}": diagnostic_html,
        "{{r7_sources}}": "".join(f'<a href="{links[key]}">{label}</a>' for key, label in (
            ("contract", "schema2統合契約"), ("manifest", "正規manifest"), ("readme", "全体設計資料"),
            ("floorCorrection", "床是正と有限検査の範囲"), ("stockTools", "市販締結品とDN-03"),
            ("slicingReport", "従来5点の層確認"), ("cSlicing", "C追加2点の層確認"),
            ("contactFrames", "保存接地フレームの近似"), ("comparisonCsv", "比較CSV"),
            ("accessories", "試験片・組立台"), ("sharedLots", "共同購入lot（個別費用とは別）"))),
    }
    for entry in assets.values():
        entry.setdefault("source_sha256", digest((ROOT/entry["source"]).read_bytes()))
        entry["bundle_group"] = "r7"
    from r7_walking import build_walking
    walking_html, walking_assets = build_walking(output, guides, ref)
    replacements.update(walking_html)
    replacements.update(overview_html(guides, image, links))
    replacements["{{current_sources}}"] += walking_html["{{walk_sources}}"]
    replacements["{{current_sources}}"] += '<a href="build-manifest.json">公開版と内部設計IDの対応</a>'
    assets.update(walking_assets)
    return replacements, assets, source.source
