from html.parser import HTMLParser
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from urllib.parse import unquote, urlsplit

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "site/dist/TeoJansen_Rhinoceros"


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []

    def handle_starttag(self, name, attrs):
        self.items.append((name, dict(attrs)))


class Sections(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.sections = {}

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        ident = attrs.get("id")
        if ident:
            self.sections[ident] = {"text": "", "images": [], "links": []}
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input",
                       "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append((tag, ident))
        for _, active in self.stack:
            if active and tag == "img":
                self.sections[active]["images"].append(attrs)
            if active and tag == "a":
                self.sections[active]["links"].append(attrs["href"])

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        for _, ident in self.stack:
            if ident:
                self.sections[ident]["text"] += data


class PublicBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((OUTPUT / "build-manifest.json").read_text())
        cls.document = (OUTPUT / "index.html").read_text()
        cls.tags = Tags()
        cls.tags.feed(cls.document)
        cls.production = (OUTPUT / "production.html").read_text()
        cls.production_tags = Tags()
        cls.production_tags.feed(cls.production)
        sections = Sections()
        sections.feed(cls.production)
        cls.sections = sections.sections

    def test_asset_allowlist_and_budget(self):
        forbidden = {".fcstd", ".step", ".stl", ".blend", ".py", ".log", ".tgz"}
        files = [p for p in OUTPUT.rglob("*") if p.is_file()]
        self.assertFalse(any(p.suffix.lower() in forbidden for p in files))
        self.assertLess(sum(p.stat().st_size for p in files), 12_000_000)
        self.assertEqual(len(self.manifest["assets"]), 53)
        self.assertEqual(self.manifest["pages"], ["index.html", "production.html"])
        for asset, data in self.manifest["assets"].items():
            self.assertEqual(hashlib.sha256((OUTPUT / asset).read_bytes()).hexdigest(), data["sha256"])
            self.assertEqual(hashlib.sha256((ROOT / data["source"]).read_bytes()).hexdigest(), data["source_sha256"])

    def test_no_private_metadata(self):
        for document in (self.document, self.production):
            self.assertNotIn("/Users/", document)
            self.assertNotIn("file://", document)
        for path in (OUTPUT / "assets").glob("*.webp"):
            with Image.open(path) as image:
                self.assertFalse(image.getexif())
                self.assertNotIn("xmp", image.info)
                self.assertNotIn("icc_profile", image.info)

    def test_safe_subpath_and_opt_in_media(self):
        videos = []
        for name, attrs in self.tags.items + self.production_tags.items:
            for key in ("src", "href", "poster"):
                if key in attrs:
                    url = urlsplit(attrs[key])
                    if not url.scheme:
                        self.assertFalse(url.path.startswith("/"), attrs[key])
            if name == "video":
                videos.append(attrs)
                self.assertIn("controls", attrs)
                self.assertIn("playsinline", attrs)
                self.assertNotIn("autoplay", attrs)
                self.assertEqual(attrs.get("preload"), "none")
            if name == "img":
                self.assertTrue(attrs.get("alt"))
                self.assertFalse(attrs["src"].endswith(".gif"))
                with Image.open(OUTPUT / attrs["src"]) as image:
                    self.assertEqual(int(attrs["width"]), image.width)
                    self.assertEqual(int(attrs["height"]), image.height)
            self.assertNotEqual(name, "iframe")
        self.assertEqual(len(videos), 5)

    def test_canonical_source_and_limits_are_visible(self):
        data = ROOT / "docs/ver3/comparison.json"
        self.assertEqual(hashlib.sha256(data.read_bytes()).hexdigest(), self.manifest["comparison_sha256"])
        for text in ("3 mm目標未達", "名目トルク入力も不足", "規定入力 120 rpm",
                     "8倍表示", "2倍表示", "パラメトリック生成設計", "装置全体の質量"):
            self.assertIn(text, self.document)
        self.assertIn("専用の組立PDF・詳細な手順書は未整備", self.document)
        self.assertIn("新しいVer.3のSTLはmm・100%", self.document)

    def test_substantive_production_stages_and_media(self):
        stages = ("research", "design", "printing", "sanding", "cleaning",
                  "painting", "decals", "assembly", "ver1-test")
        for stage in stages:
            with self.subTest(stage=stage):
                section = self.sections[stage]
                self.assertGreater(len(section["text"].strip()), 200)
                self.assertTrue(section["links"] or section["images"])
        for stage in ("design", "printing", "sanding", "cleaning", "painting", "decals"):
            self.assertTrue(self.sections[stage]["images"], stage)
        for text in ("Fusion 360", "ABS", "150%", "160%", "#400 → #600 → #800",
                     "超音波洗浄", "品番87137", "エアブラシ", "防毒マスク",
                     "デカール", "トップコート", "ステンレス丸棒", "金切りばさみ"):
            self.assertIn(text, self.production)
        self.assertNotIn("30分", self.production)
        self.assertIn("各製品の表示・取扱説明を優先", self.production)
        self.assertIn("接着作業そのものの写真は原典にない", self.production)

    def test_version_identity_and_source_gaps(self):
        for version in (1, 2):
            images = self.sections[f"ver{version}-gallery"]["images"]
            self.assertEqual(len(images), 6)
            sources = {self.manifest["assets"][image["src"]]["source"] for image in images}
            self.assertEqual(sources, {f"docs/images/テオヤンセンver{version}完成{i}.jpg" for i in range(1, 7)})
        for stage in ("v2-gears", "v2-turbine", "v2-support", "v2-hooks"):
            section = self.sections[stage]
            for label in ("観察", "作者の考察", "実際の変更"):
                self.assertIn(label, section["text"])
            self.assertGreaterEqual(len(section["images"]), 2)
        self.assertEqual(self.manifest["assets"]["assets/v1-drive-front.webp"]["source"],
                         "docs/images/テオヤンセンv2joint v32.png")
        self.assertEqual(self.manifest["assets"]["assets/v2-drive-front.webp"]["source"],
                         "docs/images/テオヤンセンv4joint v15.1.png")
        turbine_sources = {self.manifest["assets"][image["src"]]["source"]
                           for image in self.sections["v2-turbine"]["images"]}
        self.assertEqual(turbine_sources, {"docs/images/87816.jpg", "docs/images/Wheel2.jpg", "docs/images/Wheel3.jpg"})
        for text in ("独立したVer.2の全工程ログ", "専用の組立PDF・詳細な手順書は未整備",
                     "元の.f3dは公開されていません", "Ver.3のmm・100%とは別",
                     "Crankshaft_Part1〜3", "軸受の焼付きが確認された、と原因を置き換えてはいません"):
            self.assertIn(text, self.production)
        self.assertIn("接合が滑って一体で回らなくなる", self.sections["remaining"]["text"])
        self.assertIn("始動の難しさ", self.sections["remaining"]["text"])

    def test_source_links_and_no_external_media(self):
        readmes = (ROOT / "README.md").read_text() + (ROOT / "README_ja.md").read_text()
        downloads = []
        for tag, attrs in self.production_tags.items:
            if tag in {"img", "script", "link"}:
                url = attrs.get("src", attrs.get("href", ""))
                self.assertFalse(urlsplit(url).scheme, url)
            if tag != "a":
                continue
            href = attrs["href"]
            url = urlsplit(href)
            if url.netloc in {"youtu.be", "www.youtube.com", "youtube.com", "makerworld.com", "www.tamiya.com"}:
                self.assertIn(href, readmes)
            if url.netloc == "github.com" and f"/{self.manifest['source_commit']}/" in url.path:
                local = unquote(url.path.split(f"/{self.manifest['source_commit']}/")[1])
                self.assertTrue((ROOT / local).exists(), href)
                downloads.append(local)
        for source in ("docs/テオヤンセン2Dv1.pdf", "docs/テオヤンセン2D図面最新.pdf",
                       "STL/Ver.1", "STL/Ver.2", "README.md", "README_ja.md", "Fusion360"):
            self.assertIn(source, downloads)

    def test_cross_page_validation_rejects_missing_anchor(self):
        spec = importlib.util.spec_from_file_location("showcase_build", ROOT / "site/build.py")
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "public"
            shutil.copytree(OUTPUT, output)
            index = output / "index.html"
            index.write_text(self.document.replace("production.html#ver1", "production.html#missing-stage"))
            with self.assertRaisesRegex(ValueError, "Missing anchor"):
                builder.validate(output, self.manifest)


if __name__ == "__main__":
    unittest.main()
