from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import unittest
from urllib.parse import urlsplit

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "site/dist/TeoJansen_Rhinoceros"


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []

    def handle_starttag(self, name, attrs):
        self.items.append((name, dict(attrs)))


class PublicBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((OUTPUT / "build-manifest.json").read_text())
        cls.document = (OUTPUT / "index.html").read_text()
        cls.tags = Tags()
        cls.tags.feed(cls.document)

    def test_asset_allowlist_and_budget(self):
        forbidden = {".fcstd", ".step", ".stl", ".blend", ".py", ".log", ".tgz"}
        files = [p for p in OUTPUT.rglob("*") if p.is_file()]
        self.assertFalse(any(p.suffix.lower() in forbidden for p in files))
        self.assertLess(sum(p.stat().st_size for p in files), 12_000_000)
        self.assertEqual(len(self.manifest["assets"]), 20)
        for asset, data in self.manifest["assets"].items():
            self.assertEqual(hashlib.sha256((OUTPUT / asset).read_bytes()).hexdigest(), data["sha256"])
            self.assertEqual(hashlib.sha256((ROOT / data["source"]).read_bytes()).hexdigest(), data["source_sha256"])

    def test_no_private_metadata(self):
        self.assertNotIn("/Users/", self.document)
        self.assertNotIn("file://", self.document)
        for path in (OUTPUT / "assets").glob("*.webp"):
            with Image.open(path) as image:
                self.assertFalse(image.getexif())
                self.assertNotIn("xmp", image.info)
                self.assertNotIn("icc_profile", image.info)

    def test_safe_subpath_and_opt_in_media(self):
        videos = []
        for name, attrs in self.tags.items:
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


if __name__ == "__main__":
    unittest.main()
