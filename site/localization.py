"""Strict presentation-only translations, with source-bound document derivatives."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
from html import escape
from html.parser import HTMLParser
import json
import posixpath
from pathlib import Path
import re
from urllib.parse import quote, unquote, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
LOCALES = SITE / "locales"
PUBLIC_URL = "https://ktanino10.github.io/TeoJansen_Rhinoceros/"
REPOSITORY = "https://github.com/ktanino10/TeoJansen_Rhinoceros"
JAPANESE = re.compile(r"[ぁ-ヿ㐀-鿿]")
VALUES = re.compile(r"`[^`]+`|https?://[^\s<>)]*|(?<![A-Za-z_])[ABC](?![A-Za-z_])|[+−-]?\d+(?:[.,]\d+)*")
SLOTS = re.compile(r"\{(\d+)\}")
TEXT_ATTRIBUTES = {"alt", "title", "aria-label", "data-label", "data-title", "placeholder", "label"}
DOCUMENTS = (
    "docs/ver3/DESIGN_ja.md",
    "docs/ver3/ASSEMBLY_ja.md",
    "docs/ver3/REVIEW_ja.md",
    "docs/ver3/commercial_basis_r3/DESIGN_GATE_ja.md",
    "docs/ver3/commercial_basis_r3/V2_CHECK_ja.md",
    "docs/ver3/common_input_r4/README_ja.md",
    "docs/ver3/common_input_r4/ASSEMBLY_ja.md",
    "docs/ver3/integrated_r7/README_ja.md",
    "docs/ver3/integrated_r7/ASSEMBLY_ja.md",
    "docs/ver3/integrated_r7/REVIEW_ja.md",
    "docs/ver3/integrated_r7/FLOOR_CORRECTION_ja.md",
    "docs/ver3/integrated_r7/CONTACT_FRAMES_ja.md",
    "docs/ver3/integrated_r7/SLICING_ja.md",
    "docs/ver3/integrated_r7/A/README_ja.md",
    "docs/ver3/integrated_r7/B/README_ja.md",
    "docs/ver3/integrated_r7/C/README_ja.md",
    "docs/ver3/integrated_r7/C/SLICING_ja.md",
    "docs/ver3/r7_walking_v1/MODEL_ja.md",
)
CSV_DOCUMENTS = (
    *(f"docs/ver3/BOM_{d}.csv" for d in "ABC"),
    "docs/ver3/common_input_r4/BOM.csv",
    *(f"docs/ver3/integrated_r7/{d}/BOM.csv" for d in "ABC"),
)
ORIGINAL_DRAWINGS = ("docs/テオヤンセン2Dv1.pdf", "docs/テオヤンセン2D図面最新.pdf")
CAPTIONS = tuple(
    f"docs/ver3/r7_display_floor2/{mode}_{d}.vtt"
    for mode in ("assembly", "disassembly") for d in "ABC"
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def shape(text: str) -> tuple[str, list[str]]:
    values = []

    def parameter(match):
        values.append(match[0])
        return "{" + str(len(values) - 1) + "}"

    return VALUES.sub(parameter, " ".join(text.split())), values


def message_id(key: str) -> str:
    return digest(key.encode())[:16]


def source_markup(html: str) -> str:
    return re.sub(r"確定コミット ([0-9a-f]{7})", r"確定コミット <code>\1</code>", html)


class Catalog:
    def __init__(self, *, collecting=False):
        self.collecting = collecting
        self.sources = {}
        self.translations = {}
        for path in (LOCALES / "en.json", LOCALES / "documents.en.json"):
            if not path.exists():
                continue
            entries = json.loads(path.read_text())
            if self.translations.keys() & entries.keys():
                raise ValueError("Duplicate translation message across catalogs")
            self.translations.update(entries)
        self.used = set()
        if not collecting:
            registry = json.loads((LOCALES / "sources.json").read_text())
            if registry.keys() != self.translations.keys():
                raise ValueError(f"Incomplete/stale translation catalog: {registry.keys() ^ self.translations.keys()}")

    def text(self, text: str, origin: str = "") -> str:
        if not JAPANESE.search(text) or text.startswith(("https://", "http://")):
            return text
        key, values = shape(text)
        ident = message_id(key)
        entry = self.sources.setdefault(ident, {"source": key, "example": " ".join(text.split()), "origins": []})
        if entry["source"] != key:
            raise ValueError("Translation message ID collision")
        if origin and origin not in entry["origins"]:
            entry["origins"].append(origin)
        self.used.add(ident)
        if self.collecting:
            return text
        if ident not in self.translations:
            raise ValueError(f"Missing English translation {ident}: {key} ({origin})")
        translated = self.translations[ident]
        if JAPANESE.search(translated) or Counter(SLOTS.findall(translated)) != Counter(SLOTS.findall(key)):
            raise ValueError(f"Translation changes parameters or retains Japanese: {ident}")
        result = SLOTS.sub(lambda match: values[int(match[1])], translated)
        return text[:len(text) - len(text.lstrip())] + result + text[len(text.rstrip()):]

    def data(self, value, origin=""):
        if isinstance(value, str):
            return self.text(value, origin)
        if isinstance(value, list):
            return [self.data(item, origin) for item in value]
        if isinstance(value, dict):
            return {key: self.data(item, origin) for key, item in value.items()}
        return value


def english_path(path: str) -> str:
    if path == "README_ja.md":
        return "README.md"
    if path in DOCUMENTS:
        return path.replace("_ja.md", "_en.md")
    if path in CSV_DOCUMENTS and JAPANESE.search((ROOT / path).read_text()):
        return path[:-4] + "_en.csv"
    return path


def translated_link(href: str, ref: str) -> str:
    parsed = urlsplit(href)
    if not href.startswith(REPOSITORY + "/"):
        return href
    pieces = unquote(parsed.path).split("/")
    if len(pieces) < 6 or pieces[3] not in {"blob", "raw"}:
        return href
    original = "/".join(pieces[5:])
    target = english_path(original)
    if target == original:
        return href
    return urlunsplit((parsed.scheme, parsed.netloc,
                      f"/ktanino10/TeoJansen_Rhinoceros/{pieces[3]}/{ref}/{quote(target, safe='/')}",
                      parsed.query, parsed.fragment))


class LocalizedHTML(HTMLParser):
    def __init__(self, catalog: Catalog, page: str, ref: str):
        super().__init__(convert_charrefs=False)
        self.catalog, self.page, self.ref = catalog, page, ref
        self.output = []
        media = json.loads((ROOT / "docs/ver3/r7_walking_locales_v1/manifest.json").read_text())
        self.media_copy = {}
        for entry in media["designs"].values():
            ja, en = entry["locales"]["ja"], entry["locales"]["en"]
            for japanese, english in ((ja["title"], en["title"]), (ja["description"], en["description"]),
                                      (ja["captions"]["label"], en["captions"]["label"])):
                self.media_copy[" ".join(japanese.split())] = english

    def translate(self, value):
        paired = self.media_copy.get(" ".join(value.split()))
        if paired is not None:
            return value if self.catalog.collecting else paired
        return self.catalog.text(value, self.page)

    def handle_starttag(self, tag, attrs):
        if tag in {"a", "strong", "em", "code", "small", "span"}:
            self.output.append(" ")
        result = []
        original_language = dict(attrs).get("data-original-language")
        for key, value in attrs:
            if value is None:
                result.append(key)
                continue
            if tag == "html" and key == "lang":
                value = "en"
            if tag == "track" and dict(attrs).get("src", "").startswith(("assets/r7-assembly-", "assets/r7-disassembly-")):
                if key == "src":
                    value = value.replace(".vtt", "-en.vtt")
                elif key == "srclang":
                    value = "en"
                elif key == "label":
                    value = "English stage descriptions"
            if tag == "track" and dict(attrs).get("src", "").startswith("assets/r7-walking-") and key == "srclang":
                value = "en"
            if key in TEXT_ATTRIBUTES or (tag == "meta" and key == "content" and JAPANESE.search(value)):
                value = self.translate(value)
            if key in {"href", "src", "poster"} and re.fullmatch(r"assets/r7-walking-[ABC]\.(mp4|webp|vtt)", value):
                value = re.sub(r"(\.[a-z0-9]+)$", r"-en\1", value)
            if key == "href" and not original_language:
                value = translated_link(value, self.ref)
            if key == "href" and value.startswith("assets/"):
                value = "../" + value
            if key in {"src", "poster", "data-animation"} or (key == "href" and tag == "link"):
                if value and not value.startswith(("#", "https://", "http://", "../")):
                    value = "../" + value
            result.append(f'{key}="{escape(value, quote=True)}"')
        self.output.append("<" + tag + (" " + " ".join(result) if result else "") + ">")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.output[-1] = self.output[-1][:-1] + "/>"

    def handle_endtag(self, tag):
        self.output.append(f"</{tag}>")
        if tag in {"a", "strong", "em", "code", "small", "span"}:
            self.output.append(" ")

    def handle_data(self, data):
        translated = self.translate(data)
        if not self.catalog.collecting:
            translated = translated.translate(str.maketrans({"。": ".", "／": "/", "（": "(", "）": ")"}))
        self.output.append(escape(translated, quote=False))

    def handle_entityref(self, name):
        self.output.append(f"&{name};")

    def handle_charref(self, name):
        self.output.append(f"&#{name};")

    def handle_decl(self, decl):
        self.output.append(f"<!{decl}>")

    def handle_comment(self, data):
        self.output.append(f"<!--{data}-->")


def metadata(html: str, page: str, locale: str) -> str:
    prefix = "../" if locale == "en" else ""
    canonical = PUBLIC_URL + ("en/" if locale == "en" else "") + page
    links = (f'<link rel="canonical" href="{canonical}">\n'
             f'<link rel="alternate" hreflang="ja" href="{PUBLIC_URL}{page}">\n'
             f'<link rel="alternate" hreflang="en" href="{PUBLIC_URL}en/{page}">\n'
             f'<link rel="alternate" hreflang="x-default" href="{PUBLIC_URL}{page}">\n'
             f'<meta property="og:locale" content="{"en_US" if locale == "en" else "ja_JP"}">\n')
    if 'name="description"' not in html:
        title = re.search(r"<title>([^<]+)</title>", html)[1]
        links += f'<meta name="description" content="{escape(title, quote=True)}">\n'
    scripts = (f'<script src="{prefix}assets/locale-en.js" defer></script>\n' if locale == "en" else "")
    if f'src="{prefix}i18n.js"' not in html:
        scripts += f'<script src="{prefix}i18n.js" defer></script>\n'
    html = html.replace("<head>", "<head>\n" + links + scripts)
    nav = ('<nav class="language-switch" aria-label="' + ("Language" if locale == "en" else "言語") + '">'
           f'<a lang="ja" hreflang="ja" href="{prefix}{page}"'
           + (' aria-current="page"' if locale == "ja" else ' data-language-link')
           + '>日本語</a><span aria-hidden="true"> / </span>'
           f'<a lang="en" hreflang="en" href="{"en/" if locale == "ja" else ""}{page}"'
           + (' aria-current="page"' if locale == "en" else ' data-language-link')
           + '>English</a></nav>')
    return html.replace("</header>", nav + "</header>", 1)


def build_locales(output: Path, pages: tuple[str, ...], ref: str) -> dict:
    catalog = Catalog()
    for name, expected in document_outputs().items():
        if not (ROOT / name).is_file() or (ROOT / name).read_text() != expected:
            raise ValueError(f"Stale document derivative; run localization.py --documents: {name}")
    (output / "en").mkdir()
    for page in pages:
        source = source_markup((output / page).read_text())
        source = re.sub(r'<a href="([^"]+)">((?:日本語の原典README|日本語README)[^<]*)</a>',
                        r'<a data-original-language="ja" href="\1">\2</a>', source)
        translated = LocalizedHTML(catalog, page, ref)
        translated.feed(source)
        (output / "en" / page).write_text(resource_notice(metadata("".join(translated.output), page, "en"), ref, "en"))
        (output / page).write_text(resource_notice(metadata(source, page, "ja"), ref, "ja"))
    registry = json.loads((LOCALES / "sources.json").read_text())
    messages = {entry["source"]: catalog.translations[ident] for ident, entry in registry.items()
                if ident in catalog.translations and any(not origin.startswith("docs/") for origin in entry["origins"])}
    for ident, entry in registry.items():
        if ident in catalog.translations:
            catalog.text(entry["example"], entry["origins"][0])
    path = output / "assets/locale-en.js"
    path.write_text("globalThis.RHINO_EN = " + json.dumps(messages, ensure_ascii=False, separators=(",", ":")) + ";\n")
    assets = {"assets/locale-en.js": {
        "source": "site/locales/en.json", "source_sha256": digest((LOCALES / "en.json").read_bytes()),
        "sha256": digest(path.read_bytes()), "bytes": path.stat().st_size, "locale": "en",
        "bundle_group": "localization",
    }}
    for source in CAPTIONS:
        target = source.replace(".vtt", "_en.vtt")
        name = "assets/r7-" + Path(target).name.replace("_", "-")
        raw = (ROOT / target).read_bytes()
        (output / name).write_bytes(raw)
        assets[name] = {"source": target, "source_sha256": digest(raw), "sha256": digest(raw),
                        "bytes": len(raw), "locale": "en", "bundle_group": "localization", "loading": "on-demand"}
    manifest = ROOT / "docs/translation-manifest.json"
    if not manifest.is_file():
        raise ValueError("Generate source-bound document translations before building the public site")
    raw = manifest.read_bytes()
    (output / "assets/translation-manifest.json").write_bytes(raw)
    assets["assets/translation-manifest.json"] = {
        "source": "docs/translation-manifest.json", "source_sha256": digest(raw), "sha256": digest(raw),
        "bytes": len(raw), "bundle_group": "localization",
    }
    return assets


def resource_notice(html: str, ref: str, locale: str) -> str:
    url = f"{REPOSITORY}/blob/{ref}/docs/README_{locale}.md"
    if locale == "en":
        text = (f'<h2>Documents by language</h2><p><a href="{url}">English documents and Japanese counterparts</a> · '
                '<a href="../assets/translation-manifest.json">Translation sources and coverage</a></p>'
                '<p>CAD, STEP, STL, GLB and numerical data are shared, not remodeled for language. '
                'BOMs already use English/neutral fields. Original Ver.1 PDF drawings remain Japanese. '
                'Historical external videos keep their original language; no reuploads or new performance claims.</p>')
    else:
        text = (f'<h2>資料の言語を選ぶ</h2><p><a href="{url}">日本語資料と英語版の対応一覧</a> · '
                '<a href="assets/translation-manifest.json">翻訳の出典・対応範囲</a></p>'
                '<p>CAD・STEP・STL・GLB・数値データは共通で、言語のための再設計はしていません。'
                'BOMは英語・共通の項目です。Ver.1の原図PDFは日本語のまま保持しています。'
                '過去の外部動画は元の言語で、新規投稿や性能の再認定は行っていません。</p>')
    return html.replace("</main>", f'<section class="section localization-resources">{text}</section></main>', 1)


def document_destination(destination: str, source: str) -> tuple[str, bool]:
    if destination.startswith(PUBLIC_URL) and not destination.startswith(PUBLIC_URL + "en/"):
        return PUBLIC_URL + "en/" + destination[len(PUBLIC_URL):], False
    parsed = urlsplit(destination)
    if parsed.scheme or parsed.netloc:
        return destination, False
    path = posixpath.normpath(posixpath.join(posixpath.dirname(source), unquote(parsed.path))) if parsed.path else source
    target = english_path(path)
    relative = posixpath.relpath(target, posixpath.dirname(source)) if parsed.path else ""
    fragment = parsed.fragment
    if fragment and target != path and path in DOCUMENTS:
        for line in (ROOT / path).read_text().splitlines():
            if line.startswith("#"):
                old = heading_slug(line)
                if old == unquote(fragment):
                    fragment = heading_slug(Catalog().text(line, path))
                    break
        else:
            raise ValueError(f"Unresolved translated document anchor: {source} -> {destination}")
    return urlunsplit(("", "", relative, parsed.query, fragment)), path.endswith("_ja.md") and target == path


def heading_slug(line: str) -> str:
    text = re.sub(r"^#+\s*", "", line).strip().lower()
    text = re.sub(r"<[^>]*>", "", text)
    text = re.sub(r"[^\w\s-]", "", text)
    return text.replace(" ", "-")


def markdown(source: str, catalog: Catalog) -> str:
    lines = []
    in_code = False
    for line in (ROOT / source).read_text().splitlines():
        if line.startswith("```"):
            in_code = not in_code
        if in_code:
            lines.append(line)
            continue
        # Link destinations are paths, not prose; translating them would break citations.
        destinations = []

        def stash(match):
            destinations.append(match[1])
            return "](`LINK" + str(len(destinations) - 1) + "`)"

        protected = re.sub(r"\]\(([^)]+)\)", stash, line)
        if protected.lstrip().startswith("|"):
            translated = "|".join(catalog.text(cell, source) for cell in protected.split("|"))
        else:
            translated = catalog.text(protected, source)
        for index, destination in enumerate(destinations):
            destination, original_only = (destination, False) if catalog.collecting else document_destination(destination, source)
            translated = translated.replace(f"`LINK{index}`", destination)
            if original_only:
                translated = translated.replace(f"]({destination})", f"]({destination}) (Japanese archival original)")
        lines.append(translated)
    return "\n".join(lines) + "\n"


def document_outputs() -> dict[str, str]:
    catalog = Catalog()
    outputs = {}
    entries = []
    for source in DOCUMENTS:
        target = english_path(source)
        source_hash = digest((ROOT / source).read_bytes())
        guide = posixpath.relpath("docs/README_en.md", posixpath.dirname(target))
        original = Path(source).name
        body = markdown(source, catalog)
        first, rest = body.split("\n", 1)
        text = (first + f"\n\n[日本語 (original)]({original}) | **English** | [Document languages]({guide})\n\n"
                f"> Presentation-only translation of the unchanged Japanese source. Source SHA256: `{source_hash}`. "
                "Numbers, part IDs, equations, code and qualification limits are retained; this is not a new engineering revision.\n\n")
        if source == "docs/ver3/r7_walking_v1/MODEL_ja.md":
            text += ("> This frozen base-model record describes its original annotation pipeline and media budget. "
                     "The separate [Japanese/English media revision](../r7_walking_locales_v1/manifest.json) reuses the same motion and timing. "
                     "See the [current website guide](../../USER_GUIDE_en.md); historical pipeline/budget statements below are not silently rewritten.\n\n")
        text += rest.lstrip()
        outputs[target] = text
        entries.append({"source": source, "sourceLanguage": "ja", "sourceSha256": source_hash,
                        "target": target, "targetLanguage": "en", "targetSha256": digest(text.encode()),
                        "coverage": "full-source-prose; equations/code/data preserved"})
    for source in CSV_DOCUMENTS:
        with (ROOT / source).open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        if JAPANESE.search((ROOT / source).read_text()):
            raise ValueError(f"New Japanese BOM fields require a reviewed description-only derivative: {source}")
        entries.append({"source": source, "sourceLanguage": "en-neutral", "sourceSha256": digest((ROOT / source).read_bytes()),
                        "target": source, "targetLanguage": "shared", "coverage": "unchanged shared BOM",
                        "rowIdentity": "part_id", "rows": len(rows), "columns": list(rows[0])})
    for source in CAPTIONS:
        target = source.replace(".vtt", "_en.vtt")
        text = "\n".join(catalog.text(line, source) for line in (ROOT / source).read_text().splitlines()) + "\n"
        outputs[target] = text
        entries.append({"source": source, "sourceLanguage": "ja", "sourceSha256": digest((ROOT / source).read_bytes()),
                        "target": target, "targetLanguage": "en", "targetSha256": digest(text.encode()),
                        "coverage": "complete captions; cue timing unchanged"})
    for source in ORIGINAL_DRAWINGS:
        entries.append({"source": source, "sourceLanguage": "ja", "sourceSha256": digest((ROOT / source).read_bytes()),
                        "target": source, "targetLanguage": "ja-original", "coverage": "unchanged original drawing; not an English drawing"})
    archives = sorted(path.relative_to(ROOT).as_posix() for path in (ROOT / "docs/ver3").rglob("*_ja.md")
                      if path.relative_to(ROOT).as_posix() not in DOCUMENTS)
    manifest = {
        "schemaVersion": 1, "defaultLanguage": "ja", "englishSitePrefix": "en/",
        "pagePairs": [{"ja": page, "en": "en/" + page} for page in (
            "index.html", "production.html", "comparison.html", "viewer.html", "calculations.html", "r7.html", "walking.html")],
        "engineeringInvariant": "Translation only: no CAD, kinematics, physics, quantities, prices, release status or qualification changes.",
        "entries": entries,
        "existingPairs": [
            {"source": ja, "sourceLanguage": "ja", "sourceSha256": digest((ROOT / ja).read_bytes()),
             "target": en, "targetLanguage": "en", "targetSha256": digest((ROOT / en).read_bytes()), "coverage": coverage}
            for ja, en, coverage in (
                ("README_ja.md", "README.md", "existing historical V1/V2 production records"),
                ("docs/USER_GUIDE_ja.md", "docs/USER_GUIDE_en.md", "website and document use; shared-resource legend"),
            )
        ],
        "archivalOriginals": [{"path": path, "language": "ja", "sourceSha256": digest((ROOT / path).read_bytes()),
                              "coverage": "linked archival source, explicitly labeled Japanese"}
                              for path in archives],
        "sharedResources": ["Native CAD", "STEP", "STL", "GLB", "math JSON/CSV", "original photographs", "English-labeled analysis SVG"],
        "sharedDataNotice": "Machine-readable numerical sources are shared; original source annotations can be Japanese. Use paired prose for interpretation.",
        "walkingMedia": {
            "manifest": "docs/ver3/r7_walking_locales_v1/manifest.json",
            "sha256": digest((ROOT / "docs/ver3/r7_walking_locales_v1/manifest.json").read_bytes()),
            "languages": ["ja", "en"], "coverage": "separate burned notes, posters and optional captions; same source motion and timing",
        },
    }
    outputs["docs/translation-manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    for locale in ("ja", "en"):
        english = locale == "en"
        title = "# Documents in English" if english else "# 日本語の資料"
        intro = ("Full English counterparts of the major public documents. Frozen Japanese engineering originals remain unchanged; "
                 "each translation identifies its source SHA256. The language switch on every website page retains the page, query and anchor."
                 if english else "公開ページから参照する主要資料の日本語・英語対応表です。固定された日本語の機械資料は変更せず、英語版に原本SHA256を記録しています。サイトの言語切替は同じページ・クエリ・アンカーを保持します。")
        lines = [title, "", "[日本語](README_ja.md) | [English](README_en.md)", "", intro, "",
                 f"[{'English website' if english else '日本語サイト'}]({PUBLIC_URL}{'en/' if english else ''}) · "
                 f"[{'How to use / resource legend' if english else '使い方・資料の凡例'}](USER_GUIDE_{locale}.md) · "
                 f"[{'Source and coverage manifest' if english else '出典・対応範囲manifest'}](translation-manifest.json)", "",
                 "| Document | 日本語 | English |" if english else "| 資料 | 日本語 | English |",
                 "|---|---|---|"]
        for source in DOCUMENTS:
            target = english_path(source)
            heading = (outputs[target] if english else (ROOT / source).read_text()).splitlines()[0].lstrip("# ")
            lines.append(f"| {heading} | [日本語]({source.removeprefix('docs/')}) | [English]({target.removeprefix('docs/')}) |")
        lines += ["", "## Shared and original-language resources" if english else "## 共通データと原本の言語", "",
                  ("The seven BOMs already use English/neutral fields and are shared byte-for-byte: part IDs, quantities, SKUs, prices and URLs are unchanged. "
                   "CAD/STEP/STL/GLB and numerical sources are shared, not remodeled. Source JSON annotations may be Japanese; paired prose supplies the English explanation. "
                   "Original Ver.1 PDFs are **Original drawing (Japanese)**, not translated English drawings. Photos are unchanged and external videos retain their actual original language."
                   if english else "7つのBOMは英語・共通の項目で、バイト単位で同じ原本を参照します。部品ID・数量・SKU・価格・URLは不変です。CAD・STEP・STL・GLB・数値原本は共通で、再設計していません。JSONの原注記には日本語が含まれる場合があり、解説は対訳資料を使用します。Ver.1のPDFは**原図（日本語）**で、英訳図面とは表示しません。原写真と外部動画の言語は変更しません。"), "",
                  "## Archival Japanese originals" if english else "## 日本語のまま保持する補助的な履歴", "",
                  ("The earlier feasibility/wind-module studies and detailed archived reviewer logs below remain Japanese source records. "
                   "They are explicitly labeled when cited, not substituted for English major-document downloads."
                   if english else "以前の成立性・風車モジュールの研究と、保存した詳細レビュー原本は以下の日本語資料です。英語の主要資料ダウンロードの代わりにはせず、引用時に原本の言語を明示します。")]
        lines += [f"- [{path.removeprefix('docs/')} — {'Japanese original' if english else '日本語原本'}]({path.removeprefix('docs/')})" for path in archives]
        outputs[f"docs/README_{locale}.md"] = "\n".join(lines) + "\n"
    return outputs


def collect(output: Path) -> Catalog:
    catalog = Catalog(collecting=True)
    for page in sorted(output.glob("*.html")):
        parser = LocalizedHTML(catalog, page.name, "0" * 40)
        text = re.sub(r'<nav class="language-switch".*?</nav>', "", page.read_text(), flags=re.S)
        text = re.sub(r'<section class="section localization-resources".*?</section>', "", text, flags=re.S)
        parser.feed(source_markup(text))
    for name in ("assembly-A.json", "assembly-B.json", "assembly-C.json",
                 "r7-assembly-A.json", "r7-assembly-B.json", "r7-assembly-C.json",
                 "viewer-index.json", "r7-viewer-index.json"):
        path = output / "assets" / name
        if path.exists():
            catalog.data(json.loads(path.read_text()), name)
    for source in DOCUMENTS:
        markdown(source, catalog)
    for source in CSV_DOCUMENTS:
        with (ROOT / source).open(newline="") as stream:
            for row in csv.reader(stream):
                for cell in row:
                    catalog.text(cell, source)
    for source in CAPTIONS:
        for line in (ROOT / source).read_text().splitlines():
            catalog.text(line, source)
    for source in ("viewer.js", "r7-player.js", "walking.js"):
        for message in re.findall(r'new Error\("([^"]+)"', (SITE / source).read_text()):
            catalog.text(message, source)
    for message in ("このサイトが参照する確定コミット", "参照する確定コミット"):
        catalog.text(message, "site provenance")
    return catalog


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inventory", action="store_true")
    mode.add_argument("--documents", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=SITE / "dist/TeoJansen_Rhinoceros")
    args = parser.parse_args()
    if args.inventory:
        catalog = collect(args.output)
        LOCALES.mkdir(exist_ok=True)
        (LOCALES / "sources.json").write_text(json.dumps(catalog.sources, ensure_ascii=False, indent=2) + "\n")
        print(f"Inventoried {len(catalog.sources)} parameter-preserving messages.")
    else:
        outputs = document_outputs()
        if args.check:
            stale = [path for path, text in outputs.items() if not (ROOT / path).is_file() or (ROOT / path).read_text() != text]
            if stale:
                raise ValueError(f"Stale/missing translated derivatives: {stale}")
            print(f"Verified {len(outputs)} source-bound translated document/index/caption artifacts.")
        else:
            for path, text in outputs.items():
                (ROOT / path).write_text(text)
            print(f"Generated {len(outputs)} source-bound translated document/index/caption artifacts.")
