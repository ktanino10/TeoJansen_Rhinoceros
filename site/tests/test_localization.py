from collections import Counter
import copy
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import unittest
from urllib.parse import unquote, urlsplit

SITE = Path(__file__).resolve().parents[1]
ROOT = SITE.parent
OUTPUT = SITE / "dist/TeoJansen_Rhinoceros"
sys.path.insert(0, str(SITE))
from localization import Catalog, DOCUMENTS, CSV_DOCUMENTS, CAPTIONS, document_outputs, english_path, SLOTS
from test_build import Tags


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.links, self.visible = set(), [], []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if "id" in attributes:
            self.ids.add(attributes["id"])
        if tag == "a":
            self.links.append(attributes)

    def handle_data(self, text):
        self.visible.append(text)


class LocalizationTests(unittest.TestCase):
    def test_catalog_preserves_every_source_parameter_and_rejects_missing_translation(self):
        catalog = Catalog()
        sources = json.loads((SITE / "locales/sources.json").read_text())
        self.assertEqual(set(catalog.translations), set(sources))
        for ident, entry in sources.items():
            self.assertEqual(Counter(SLOTS.findall(entry["source"])),
                             Counter(SLOTS.findall(catalog.translations[ident])), ident)
            self.assertNotRegex(catalog.translations[ident], r"[ぁ-ゖァ-ヺ一-龯]", ident)
            catalog.text(entry["example"], entry["origins"][0])
        with self.assertRaisesRegex(ValueError, "Missing English translation"):
            catalog.text("未登録の新しい検証条件")

    def test_page_pairs_keep_every_anchor_and_have_correct_metadata_and_english_downloads(self):
        manifest = json.loads((OUTPUT / "build-manifest.json").read_text())
        self.assertEqual(len(manifest["pages"]), 14)
        for filename in [name for name in manifest["pages"] if "/" not in name]:
            parsers = []
            for locale, prefix in (("ja", ""), ("en", "en/")):
                html = (OUTPUT / prefix / filename).read_text()
                self.assertIn(f'<html lang="{locale}">', html)
                self.assertIn('hreflang="ja"', html)
                self.assertIn('hreflang="en"', html)
                self.assertIn('rel="canonical"', html)
                parser = Page()
                parser.feed(html)
                parsers.append(parser)
                switches = [a for a in parser.links if "data-language-link" in a]
                self.assertEqual(len(switches), 1)
                expected = "../" + filename if locale == "en" else "en/" + filename
                self.assertEqual(switches[0]["href"], expected)
                if locale == "en":
                    text = "".join(parser.visible).replace("日本語", "")
                    self.assertNotRegex(text, r"[ぁ-ゖァ-ヺ一-龯]", filename)
                    for link in parser.links:
                        if "data-original-language" not in link:
                            self.assertNotIn("_ja.md", link["href"], (filename, link))
                    self.assertIn("Original drawing (Japanese)" if filename in {"index.html", "production.html"}
                                  else "Original Ver.1 PDF drawings remain Japanese", html)
            self.assertEqual(parsers[0].ids, parsers[1].ids, filename)

    def test_localized_guide_data_keeps_ids_counts_coordinates_hashes_and_all_nonprose(self):
        catalog = Catalog()

        def compare(original, translated, path=""):
            if isinstance(original, dict):
                self.assertEqual(original.keys(), translated.keys(), path)
                for key, value in original.items():
                    compare(value, translated[key], path + "/" + key)
            elif isinstance(original, list):
                self.assertEqual(len(original), len(translated), path)
                for index, value in enumerate(original):
                    compare(value, translated[index], path + f"/{index}")
            elif not isinstance(original, str) or not re.search(r"[ぁ-ゖァ-ヺ一-龯]", original):
                self.assertEqual(original, translated, path)
            else:
                self.assertNotRegex(translated, r"[ぁ-ゖァ-ヺ一-龯]", path)

        for stem in ("assembly", "r7-assembly"):
            for design in "ABC":
                original = json.loads((OUTPUT / f"assets/{stem}-{design}.json").read_text())
                before = copy.deepcopy(original)
                translated = catalog.data(original)
                compare(original, translated)
                self.assertEqual(original, before)
                self.assertEqual(translated["model"]["instanceCount"], original["model"]["instanceCount"])
                self.assertEqual(translated["model"]["sha256"], original["model"]["sha256"])

    def test_document_derivatives_sources_links_and_caption_timing(self):
        outputs = document_outputs()
        for name, expected in outputs.items():
            self.assertEqual((ROOT / name).read_text(), expected, name)
        manifest = json.loads(outputs["docs/translation-manifest.json"])
        self.assertEqual(len(DOCUMENTS), 18)
        for entry in manifest["entries"] + manifest["existingPairs"]:
            self.assertEqual(hashlib.sha256((ROOT / entry["source"]).read_bytes()).hexdigest(), entry["sourceSha256"])
            if "targetSha256" in entry:
                self.assertEqual(hashlib.sha256((ROOT / entry["target"]).read_bytes()).hexdigest(), entry["targetSha256"])
        for source in DOCUMENTS:
            target = ROOT / english_path(source)
            text = target.read_text()
            self.assertIn("Source SHA256:", text)
            self.assertIn("日本語 (original)", text)
            for href in re.findall(r"\]\(([^)]+)\)", text):
                parsed = urlsplit(href)
                if not parsed.scheme and parsed.path:
                    path = (target.parent / unquote(parsed.path)).resolve()
                    self.assertTrue(path.is_relative_to(ROOT), (target, href))
                    self.assertTrue(path.exists(), (target, href))
            original = (ROOT / source).read_text()
            self.assertEqual(re.findall(r"```.*?```", original, re.S), re.findall(r"```.*?```", text, re.S))
            self.assertEqual(re.findall(r"^\$\$.*?^\$\$", original, re.M | re.S), re.findall(r"^\$\$.*?^\$\$", text, re.M | re.S))
        for source in CSV_DOCUMENTS:
            self.assertEqual(source, english_path(source))
            self.assertNotRegex((ROOT / source).read_text(), r"[ぁ-ゖァ-ヺ一-龯]")
        for source in CAPTIONS:
            original = (ROOT / source).read_text()
            translated = (ROOT / source.replace(".vtt", "_en.vtt")).read_text()
            self.assertEqual(re.findall(r"^.* --> .*$", original, re.M), re.findall(r"^.* --> .*$", translated, re.M))
            self.assertNotRegex(translated, r"[ぁ-ゖァ-ヺ一-龯]")
        tags = Tags()
        tags.feed((OUTPUT / "en/r7.html").read_text())
        tracks = [attrs for tag, attrs in tags.items if tag == "track"]
        self.assertEqual(len(tracks), 6)
        for track in tracks:
            self.assertEqual(track["srclang"], "en")
            self.assertIn("English", track["label"])
            self.assertTrue((OUTPUT / "en" / track["src"]).resolve().is_file())


if __name__ == "__main__":
    unittest.main()
