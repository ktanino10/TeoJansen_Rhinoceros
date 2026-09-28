import json
from pathlib import Path
import sys
import unittest

SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))
from r7_render_plan import timeline, subtitle_vtt


class RenderPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        output = SITE / "dist/r7-preview/TeoJansen_Rhinoceros"
        cls.guides = {key: json.loads((output/f"assets/r7-assembly-{key}.json").read_text()) for key in "ABC"}

    def test_all_source_states_are_retained_in_both_explanation_directions(self):
        for guide in self.guides.values():
            plan = timeline(guide)
            reverse = timeline(guide, reverse=True)
            source = [state for stage in guide["steps"] for state in stage["frames"]]
            self.assertEqual([e["state"] for e in plan["entries"]], source)
            self.assertEqual([e["state"] for e in reverse["entries"]], list(reversed(source)))
            for sequence in (plan, reverse):
                self.assertEqual(sequence["frameEnd"], sum(e["durationFrames"] for e in sequence["entries"]))
                self.assertEqual(sequence["entries"][0]["timelineFrame"], 1)
                for a, b in zip(sequence["entries"], sequence["entries"][1:]):
                    self.assertEqual(a["lastFrame"]+1, b["timelineFrame"])
                for entry in sequence["entries"]:
                    self.assertEqual(entry["displayedIds"], guide["inventories"][entry["state"]["inventory"]])
                    self.assertEqual(entry["installedIds"], guide["inventories"][entry["state"]["installedInventory"]])
            self.assertEqual(plan["frameEnd"], reverse["frameEnd"])

    def test_timing_is_illustrative_and_subtitles_distinguish_support_and_reverse(self):
        plan = timeline(self.guides["B"])
        self.assertIn("No physical assembly speed", plan["timeMeaning"])
        self.assertIn("Constant-held", plan["motionMeaning"])
        for entry in plan["entries"]:
            self.assertEqual(entry["state"]["stopCrankDeg"], 0)
            if entry["stageIndex"] in (6, 7, 11):
                self.assertIn("HAND / TEMPORARY SUPPORT REQUIRED", entry["notes"])
            if entry["state"].get("pathId") == "front_basket_and_rotor_lower":
                self.assertIn("FIXED 276", " ".join(entry["notes"]))
        vtt = subtitle_vtt(plan)
        self.assertTrue(vtt.startswith("WEBVTT\n"))
        self.assertEqual(vtt.count(" --> "), len(plan["entries"]))
        self.assertIn("停止姿勢", vtt)
        self.assertIn("分解参照（逆順）", subtitle_vtt(timeline(self.guides["B"], reverse=True)))


if __name__ == "__main__":
    unittest.main()
