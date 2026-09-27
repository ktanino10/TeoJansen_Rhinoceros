import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "site"))
import calculation_data as calculation
from test_build import Sections, Tags

OUTPUT = ROOT / "site/dist/TeoJansen_Rhinoceros"


class CalculationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source, cls.manifest, cls.figures, cls.comparison, cls.candidates, cls.decomposition = calculation.read_study()
        cls.html = (OUTPUT / "calculations.html").read_text()
        sections, tags = Sections(), Tags()
        sections.feed(cls.html)
        tags.feed(cls.html)
        cls.sections, cls.tags = sections.sections, tags.items

    def test_sixteen_original_svgs_and_four_data_files_keep_hashes(self):
        build = json.loads((OUTPUT / "build-manifest.json").read_text())
        assets = {name: entry for name, entry in build["assets"].items() if entry.get("calculation_revision")}
        self.assertEqual(len(assets), 20)
        self.assertEqual(len([name for name in assets if name.endswith(".svg")]), 16)
        self.assertEqual(build["calculation_source"], self.source)
        self.assertNotEqual(build["engineering_source"]["revisionId"], self.source["revisionId"])
        self.assertEqual(build["engineering_source"]["revisionId"], "ver3-first-cut-2026-09-26")
        for name, entry in assets.items():
            original = (ROOT / entry["source"]).read_bytes()
            self.assertEqual((OUTPUT / name).read_bytes(), original, name)
            self.assertEqual(entry["sha256"], entry["source_sha256"])
            self.assertEqual(entry["sha256"], hashlib.sha256(original).hexdigest())
            self.assertTrue(entry["unchanged_original"])

    def test_every_figure_exposes_its_exact_contract_and_source(self):
        images = [attrs for tag, attrs in self.tags if tag == "img"]
        self.assertEqual(len(images), 16)
        self.assertEqual(len({attrs["src"] for attrs in images}), 16)
        for stem, contract in self.figures.items():
            section = self.sections[f"figure-{stem}"]
            for field in ("revisionId", "loadcaseId", "method", "units", "resultStatus"):
                self.assertIn(contract[field], section["text"])
            self.assertTrue(any(self.source["artifactCommit"] in href for href in section["links"]))
            self.assertIn(calculation.asset_name(contract["file"]), section["links"])
            self.assertEqual(section["images"][0]["loading"], "lazy")
            if isinstance(contract["displayAmplification"], dict):
                for part, multiplier in contract["displayAmplification"].items():
                    self.assertIn(f"{part}：{multiplier:g}倍", section["text"])
        self.assertIn("共通の応力尺度ではありません", self.html)

    def test_abc_results_tables_and_five_topics_match_evidence(self):
        for ident, candidate in self.candidates.items():
            nominal = next(row for row in candidate["startup"] if row["id"] == "nominal")
            row = next(row for row in self.decomposition if row["design"] == ident and row["case"] == "nominal")
            section = self.sections[f"analysis-{ident}"]
            for kind in ("structure", "linkage", "fluid", "interface", "procurement"):
                self.assertGreater(len(self.sections[f"{kind}-{ident}"]["text"]), 150)
            for text in ("0/27", "FAIL", "UNKNOWN", f'{nominal["proxy_min_raw_nm"] * 500:.3f} mN·m',
                         f'{float(row["gross_target_nm"]) * 1000:.3f} mN·m',
                         f'{float(row["peak_crank_deg"]):g}°'):
                self.assertIn(text, section["text"])
            for member in candidate["structure"]["members"]:
                self.assertIn(f'{member["max_deflection_mm"]:.6f}', section["text"])
            self.assertEqual(len(section["images"]), 5 if ident == "C" else 4)
        for text in ("qualifiedPrototypeCount = 0", "最終mesh・組立・全BOMはありません", "下流だけ2倍",
                     "総要求の単純2倍", "6.4 m/s", "別機種", "CFD", "未校正", "2万円",
                     "旧解析 v3-r2-feasibility-02", "Ver.2実物", "三案とも未合格"):
            self.assertIn(text, self.html)
        self.assertIn("A300／B90／C180", self.html)

    def test_page_links_are_scoped_and_both_revisions_remain_separate(self):
        for page in ("index.html", "production.html", "comparison.html", "viewer.html"):
            content = (OUTPUT / page).read_text()
            self.assertIn('href="calculations.html"', content)
        for tag, attrs in self.tags:
            if tag in ("script", "img"):
                self.assertFalse(attrs["src"].startswith(("http", "/", "//")))
        for ident in "ABC":
            guide = json.loads((OUTPUT / f"assets/assembly-{ident}.json").read_text())
            self.assertEqual(guide["revision"]["revisionId"], "ver3-first-cut-2026-09-26")
            self.assertNotIn("calculation", guide["modelUrl"])

    def test_revision_mismatch_and_unsafe_svg_fail_closed(self):
        real_digest = calculation.digest
        manifest_path = ROOT / self.source["manifest"]
        with patch.object(calculation, "digest", side_effect=lambda path: "0" * 64 if path == manifest_path else real_digest(path)):
            with self.assertRaisesRegex(ValueError, "manifest changed"):
                calculation.read_study()
        original = (ROOT / next(iter(self.figures.values()))["file"]).read_bytes()
        calculation.svg_dimensions(original)
        for inserted in (b"<script>alert(1)</script>", b"<metadata>private data</metadata>",
                         b'<image href="https://example.com/tracker"/>', b'<rect onload="alert(1)"/>'):
            with self.subTest(inserted=inserted):
                modified = original.replace(b"</svg>", inserted + b"</svg>")
                with self.assertRaises(ValueError):
                    calculation.svg_dimensions(modified)
        tree = ET.fromstring(original)
        self.assertEqual(calculation.svg_dimensions(original), (int(tree.attrib["width"]), int(tree.attrib["height"])))


if __name__ == "__main__":
    unittest.main()
