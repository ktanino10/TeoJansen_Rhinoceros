import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

SITE = Path(__file__).resolve().parents[1]
ROOT = SITE.parent
WALK = ROOT / "docs/ver3/r7_walking_v1"
OUTPUT = SITE / "dist/TeoJansen_Rhinoceros"
sys.path.insert(0, str(SITE))
from r7_data import Snapshot
from test_build import Tags


class ContinuousWalkingTests(unittest.TestCase):
    def test_analytical_cross_language_constraints_and_continuity(self):
        result = subprocess.run(["node", "--test", str(SITE / "tests/walking-math.test.mjs")],
                                cwd=ROOT, text=True, capture_output=True, timeout=150)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_source_pins_and_original_nulls_are_not_replaced(self):
        source = Snapshot(use_git=False)
        for entry in source.contract["designs"]:
            d = entry["id"]
            motion = json.loads((WALK / f"motion_{d}.json").read_text())
            report = json.loads((WALK / f"validation_{d}.json").read_text())
            assembly = json.loads(source.verify(entry["assembly"]))
            frames = json.loads(source.verify(entry["contactFrames"]))
            self.assertEqual(motion["source"]["assemblySha256"], entry["assembly"]["sha256"])
            self.assertEqual(motion["source"]["contactFramesSha256"], entry["contactFrames"]["sha256"])
            self.assertEqual(motion["source"]["meshSha256"], entry["mesh"]["sha256"])
            self.assertEqual(motion["instanceCount"], len(assembly["instances"]))
            self.assertIsNone(motion["canonicalIndependentRockerAngleRad"])
            self.assertTrue(all(f["independentRockerAngleRad"] is None for f in frames["frames"]))
            self.assertFalse(motion["manufacturingRelease"])
            self.assertEqual(motion["physicalQualifiedCount"], 0)
            for item in assembly["instances"]:
                part, group = motion["instances"][item["name"]]
                self.assertEqual(part, item["part_id"])
                self.assertEqual(motion["motionGroups"][group], item["motion"])
            self.assertEqual(report["status"], "PASS")
            self.assertTrue(all(report["checks"].values()))
            self.assertEqual(report["nativeNoncontactFloorSamples"], 720)
            self.assertGreater(report["minimumNativeNoncontactEnvelopeZMm"], 1)
            self.assertGreaterEqual(report["minimumAnalyticalPadZMm"], -1e-8)
            self.assertLess(report["maximumRotationGramError"], 1e-9)
            self.assertLess(report["maximumLinkLengthErrorMm"], 1e-8)
            self.assertLess(report["maximumSpringTopAnchorErrorMm"], 1e-8)
            self.assertLess(report["maximumInterpolatedBalanceErrorNAndNmmPer100"], .01)
            self.assertEqual(report["floorTranslationMm"], 0)

    def test_published_walking_has_new_movies_lazy_controls_and_model_notes(self):
        html = (OUTPUT / "walking.html").read_text()
        tags = Tags()
        tags.feed(html)
        videos = [attrs for tag, attrs in tags.items if tag == "video"]
        self.assertEqual({v["id"] for v in videos}, {f"r7-walking-{d}" for d in "ABC"})
        for video in videos:
            self.assertEqual(video["preload"], "none")
            self.assertNotIn("autoplay", video)
        for term in ("manufacturingRelease=false", "実機合格0", "原解析の独立ロッカー角nullは変更せず",
                     "空中", "中立", "時間圧縮16×", "実自己始動・実30 cm歩行はUNKNOWN"):
            self.assertIn(term, html)
        for ident in ("walk-load", "walk-design", "walk-play", "walk-reset", "walk-speed", "walk-phase",
                      "walk-distance", "walk-guards", "walk-forces", "walk-paths"):
            self.assertTrue(any(attrs.get("id") == ident for _, attrs in tags.items))
        r7 = (OUTPUT / "r7.html").read_text()
        self.assertIn('href="walking.html"', r7)
        self.assertIn("以前の3位相診断", r7)
        self.assertNotIn("歩行動画は未生成で", r7)

    def test_movie_native_and_numeric_evidence_share_the_evaluator_and_source(self):
        manifest = json.loads((WALK / "walking-manifest.json").read_text())
        self.assertEqual(manifest["revisionId"], "r7-floor2-walking-kinematic-v1")
        self.assertEqual(manifest["status"], "PASS")
        self.assertFalse(manifest["manufacturingRelease"])
        for name, record in manifest["files"].items():
            raw = (ROOT / name).read_bytes()
            self.assertEqual(len(raw), record["bytes"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), record["sha256"])
            self.assertLess(len(raw), 100_000_000)
        self.assertEqual(manifest["native"]["instanceCounts"], {"A": 750, "B": 785, "C": 750})
        self.assertEqual(manifest["native"]["proceduralSpringsPerDesign"], 12)
        for report in manifest["native"]["designs"].values():
            self.assertEqual(report["maximumNativeBaseVertexDifferenceMm"], 0)
            self.assertLess(report["maximumSampledWorldCornerDifferenceMm"], .15)
            self.assertLess(report["maximumNativeRotationGramError"], 2e-6)
            self.assertGreaterEqual(report["minimumSampledRockerVertexZMm"], -.001)
        for d, seconds in (("A", 288), ("B", 1024), ("C", 312)):
            record = json.loads((WALK / f"render_{d}.json").read_text())
            motion = (WALK / f"motion_{d}.json").read_bytes()
            self.assertEqual(record["motionSha256"], hashlib.sha256(motion).hexdigest())
            self.assertEqual(record["evaluatorSha256"], hashlib.sha256((SITE / "r7-walk-math.js").read_bytes()).hexdigest())
            self.assertEqual(record["cycles"], 4)
            self.assertEqual(record["prescribedSeconds"], seconds)
            self.assertEqual(record["timeFactor"], 16)
            self.assertEqual(manifest["movies"][d]["frameCount"], record["frameCount"])
            self.assertTrue(manifest["movies"][d]["decoded"])


if __name__ == "__main__":
    unittest.main()
