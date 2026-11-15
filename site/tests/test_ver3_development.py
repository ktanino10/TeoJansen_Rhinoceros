from collections import Counter
import csv
import gzip
import hashlib
import json
from pathlib import Path
import sys
import unittest

from test_build import Sections

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/ver3/m3_a34"
OUTPUT = ROOT / "site/dist/TeoJansen_Rhinoceros"


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DevelopmentContractTests(unittest.TestCase):
    def test_retained_purchase_sources_keep_flat_and_nested_quotes(self):
        sys.path.insert(0, str(ROOT / "scripts/ver3"))
        from purchase_reference import retained_reference
        flat = retained_reference({"source": "https://supplier.example/item", "unitExTaxJpy": 31,
                                   "minimumOrder": 50, "checkedJst": "2026-09-27"})
        self.assertEqual(flat["urls"], ["https://supplier.example/item"])
        self.assertIn("31 JPY/piece", flat["price_text"])
        nested = retained_reference({"source": "https://supplier.example/catalog", "lots": [
            {"url": "https://supplier.example/item", "packSize": 100, "packPriceTaxIncludedJpy": 440, "packs": 1}]})
        self.assertEqual(nested["urls"], ["https://supplier.example/catalog", "https://supplier.example/item"])
        self.assertIn("100 pieces/pack", nested["sales_unit"])
        self.assertIn("440 JPY/pack", nested["price_text"])
        self.assertEqual(json.loads(nested["reference_lots"])[0]["packs"], 1)

    def test_purchase_list_preserves_old_urls_and_one_shared_stock_plan(self):
        with (DOC / "purchase-list.csv").open() as stream:
            rows = {r["part_id"]: r for r in csv.DictReader(stream)}
        self.assertIn("nejinejikun.com/products/detail/285470", rows["H_BOLT_M3_16"]["official_url"])
        self.assertIn("nejinejikun.com/products/detail/361377", rows["H_NUT_M3"]["official_url"])
        self.assertEqual(rows["H_NUT_M3"]["checked_date"], "2026-09-27")
        self.assertIn("AF5.5", rows["H_NUT_M3"]["specification"])
        self.assertIn("ID4.3 x OD9", rows["H_WASHER_4"]["specification"])
        stock = [rows["H_MAIN_HEX100"], rows["H_INTER_HEX58"]]
        self.assertEqual(stock[0]["purchase_group"], stock[1]["purchase_group"])
        self.assertIn("one500mm bar", stock[0]["shared_group_note"])
        self.assertEqual(stock[0]["reference_group_order"], "1")
        self.assertIn("100/100/100/58", stock[0]["shared_group_note"])
        panels = [r for r in rows.values() if r["purchase_group"] == "PAC34-05"]
        self.assertEqual(len(panels), 3)
        self.assertTrue(all(r["reference_group_order"] == "1" for r in panels))

    def test_english_root_readme_keeps_its_frozen_completed_ref(self):
        from localization import translated_link
        old = "18dd3f40fb811b3d50cfa527b6fafbfa55a6e781"
        current = "f" * 40
        root = f"https://github.com/ktanino10/TeoJansen_Rhinoceros/blob/{old}/README_ja.md"
        self.assertEqual(translated_link(root, current), root.replace("README_ja.md", "README.md"))
        development = f"https://github.com/ktanino10/TeoJansen_Rhinoceros/blob/{current}/docs/ver3/m3_a34/README_ja.md"
        self.assertTrue(translated_link(development, current).endswith("/m3_a34/README_en.md"))

    def test_completed_sources_and_readme_text_are_unchanged(self):
        baseline = load(DOC / "completed-baseline.json")
        for name, expected in baseline["protectedFiles"].items():
            self.assertEqual(sha(ROOT / name), expected, name)
        for name, sections in baseline["readme"].items():
            content = (ROOT / name).read_bytes()
            begin = content.index(b"\n## Ver.3.1")
            end = content.index(b"\n---", begin)
            self.assertEqual(hashlib.sha256(content[:begin]).hexdigest(), sections["prefix"])
            self.assertEqual(hashlib.sha256(content[end:]).hexdigest(), sections["legacy"])

    def test_completed_public_presentation_and_source_links_are_frozen(self):
        baseline = load(DOC / "completed-baseline.json")
        for name, expected in baseline["renderedProductionSha256"].items():
            self.assertEqual(sha(OUTPUT / name), expected, name)
        for name, expected in baseline["homeCompletedSections"].items():
            parser = Sections()
            parser.feed((OUTPUT / name).read_text())
            self.assertEqual({key: parser.sections[key] for key in expected}, expected, name)
        manifest = load(OUTPUT / "build-manifest.json")
        for name, before in baseline["publishedImageSources"].items():
            after = manifest["assets"][name]
            for key in ("source", "source_sha256", "crop", "width", "height", "sha256"):
                self.assertEqual(after.get(key), before.get(key), (name, key))

    def test_whole_a_bom_print_list_and_real_new_geometry_agree(self):
        assembly = load(DOC / "assembly.json")
        counts = Counter(i["part_id"] for i in assembly["instances"])
        with (DOC / "BOM.csv").open() as stream:
            bom = list(csv.DictReader(stream))
        self.assertEqual({r["part_id"]: int(r["quantity"]) for r in bom}, dict(counts))
        with (DOC / "print-list.csv").open() as stream:
            prints = list(csv.DictReader(stream))
        self.assertEqual(sum(int(r["needed"]) for r in prints), 115)
        self.assertEqual(len(prints), 45)
        for row in prints:
            self.assertTrue({"purpose", "support_plan", "material_and_machine", "nozzle_diameter_mm", "bed_fit"} <= row.keys())
            self.assertEqual(row["nozzle_diameter_mm"], "0.2")
            self.assertEqual(int(row["needed"]), counts[row["part_id"]])
            path = (ROOT / row["file"]).resolve()
            self.assertTrue(path.is_relative_to(ROOT))
            self.assertEqual(sha(path), row["sha256"])
            if row["change"] == "changed":
                self.assertIn("/m3_a34/", row["file"])
        self.assertEqual(len(assembly["instances"]), 754)
        self.assertEqual(assembly["m3Integration"]["convertedPinNodes"], ["A", "D"])
        self.assertGreater(assembly["m3Integration"]["toolChannelToHexCircumcircleGapMm"], 3.69)
        library = json.loads(gzip.decompress((ROOT / assembly["cadMeshes"]).read_bytes()))
        self.assertEqual(set(library), set(assembly["parts"]))
        for pid in assembly["m3Integration"]["changedParts"]:
            self.assertGreater(len(library[pid]["triangles"]), 0)
        self.assertNotEqual(sha(ROOT / "FreeCAD/Ver.3/m3_a34/Walker_A_3_4.FCStd"),
                            sha(ROOT / "FreeCAD/Ver.3/integrated_r7/A/Walker_A.FCStd"))

    def test_validation_and_slicing_are_bound_to_current_revision(self):
        assembly = load(DOC / "assembly.json")
        for relative, expected in {**assembly["sourceHashes"], **load(DOC/"files.json")}.items():
            self.assertEqual(sha(ROOT / relative), expected, relative)
        current = sha(ROOT / "FreeCAD/Ver.3/m3_a34/Walker_A_3_4.FCStd")
        for name in ("motion_check.json", "floor_check.json", "access_check.json"):
            report = load(DOC / name)
            self.assertEqual(report["revisionId"], assembly["revisionId"])
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["nativeSha256"], current)
        self.assertEqual(load(DOC/"motion_check.json")["poses"], 72)
        self.assertEqual(load(DOC/"floor_check.json")["phaseCount"], 720)
        self.assertEqual(len(load(DOC/"access_check.json")["locations"]), 14)
        summary = load(DOC/"summary.json")
        self.assertFalse(summary["manufacturingRelease"])
        self.assertFalse(summary["wholeToolSetReduced"])
        self.assertIsNone(summary["fullPurchaseCostJpy"])
        report = load(DOC/"slicing.json")
        self.assertEqual(len(report["parts"]), 3)
        self.assertFalse(report["printerContacted"])
        self.assertFalse(report["physicalPrintingPerformed"])
        for part in report["parts"]:
            self.assertEqual(sha(ROOT/part["stl"]), part["stlSha256"])
            for row in part["gearChecks"]:
                self.assertEqual(row["depositedEnvelopeTeeth"], 42)
                self.assertTrue(row["allDetectedTipsOnOneRootConnectedComponent"])

    def test_public_model_is_integrated_a_and_discovery_is_not_assembly_order(self):
        guide = load(OUTPUT / "assets/a34-assembly-A.json")
        assembly = load(DOC / "assembly.json")
        self.assertEqual(guide["revision"]["revisionId"], assembly["revisionId"])
        self.assertEqual(guide["model"]["instanceCount"], len(assembly["instances"]))
        self.assertEqual(set(guide["focusGroups"]["modified"]), set(assembly["m3Integration"]["changedInstances"]))
        self.assertEqual(guide["mapping"], "component-discovery-not-assembly-order")
        for prefix in ("", "en/"):
            page = (OUTPUT / prefix / "ver3-4.html").read_text()
            self.assertIn('data-public-version="3.4"', page)
            self.assertIn("manufacturingRelease=false", page)
            self.assertIn("assets/a34-", page)
            self.assertNotIn("assets/r7-comparison", page)
        manifest = load(OUTPUT / "build-manifest.json")
        self.assertFalse(any(name.endswith((".FCBak", ".FCStd1", ".gcode", ".3mf")) for name in manifest["assets"]))
        self.assertLessEqual(sum(r["bytes"] for r in manifest["assets"].values()
                                 if r.get("bundle_group") == "ver3-development"), 6_000_000)


if __name__ == "__main__":
    unittest.main()
