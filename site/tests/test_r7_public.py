from collections import Counter
import copy
import gzip
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest

SITE = Path(__file__).resolve().parents[1]
ROOT = SITE.parent
OUTPUT = SITE / "dist/TeoJansen_Rhinoceros"
sys.path.insert(0, str(SITE))
from r7_data import Snapshot, replay_contract
from test_build import Tags


class PublishedR7Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Snapshot(use_git=False)
        cls.guides = {key: json.loads((OUTPUT/f"assets/r7-assembly-{key}.json").read_text()) for key in "ABC"}
        cls.html = (OUTPUT/"r7.html").read_text()
        tags = Tags()
        tags.feed(cls.html)
        cls.tags = tags.items
        cls.media = json.loads((ROOT/"docs/ver3/r7_display_floor2/display-manifest.json").read_text())

    def test_corrected_instance_identity_and_every_schema2_operation(self):
        self.assertEqual(sum(g["model"]["instanceCount"] for g in self.guides.values()), 2285)
        for design in self.source.contract["designs"]:
            key = design["id"]
            guide = self.guides[key]
            assembly = self.source.json(design["assembly"]["path"])
            workflow = self.source.json(design["stages"]["path"])
            access = self.source.json(f"docs/ver3/integrated_r7/{key}/assembly_access.json")
            states, paths = replay_contract(assembly, workflow, access)
            self.assertEqual(guide["paths"], paths)
            self.assertEqual(guide["canonicalStageCount"], 12)
            self.assertFalse(guide["revision"]["localOnly"])
            self.assertEqual(guide["revision"]["candidateRevision"], self.source.source["candidateRevision"])
            self.assertEqual(set(guide["instances"]), {i["name"] for i in assembly["instances"]})
            for step, original in zip(guide["steps"][1:], workflow["stages"]):
                self.assertEqual(step["orderedOperations"], original["orderedOperations"])
                end = step["frames"][-1]
                self.assertEqual(set(guide["inventories"][end["inventory"]]), set(original["visibleAfter"]))
            benches = guide["steps"][11]["footFirstBenchSubassemblies"]
            self.assertEqual(len(benches), 6)
            self.assertEqual(len([f for f in guide["steps"][11]["frames"] if f["kind"] == "foot-bench"]), 6)
            self.assertEqual(guide["parts"]["H_LOCK_NUT_M2"]["quantity"], 6)
            self.assertIn("NUT_DRIVER_4P5", guide["steps"][11]["tools"])
            for name, label in assembly.get("nativeLabelOverrides", {}).items():
                self.assertEqual(guide["instances"][name]["displayLabel"], label)

    def test_glb_is_exact_mesh_and_placement_for_corrected_parts(self):
        for design in self.source.contract["designs"]:
            guide = self.guides[design["id"]]
            transfer = (OUTPUT/guide["modelUrl"]).read_bytes()
            self.assertEqual(hashlib.sha256(transfer).hexdigest(), guide["model"]["transportSha256"])
            raw = gzip.decompress(transfer)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), guide["model"]["sha256"])
            size = struct.unpack_from("<I", raw, 12)[0]
            document = json.loads(raw[20:20+size])
            binary = raw[28+size:]
            library = json.loads(gzip.decompress(self.source.read(design["mesh"]["path"])))
            for mesh in document["meshes"]:
                original = library[mesh["name"]]
                primitive = mesh["primitives"][0]
                for accessor_id, values, code in (
                    (primitive["attributes"]["POSITION"], [x*0.001 for v in original["vertices"] for x in v], "f"),
                    (primitive["indices"], [x for t in original["triangles"] for x in t], "I"),
                ):
                    view = document["bufferViews"][document["accessors"][accessor_id]["bufferView"]]
                    self.assertEqual(binary[view["byteOffset"]:view["byteOffset"]+view["byteLength"]],
                                     struct.pack(f"<{len(values)}{code}", *values))
            nodes = {n["extras"]["instanceId"]: n for n in document["nodes"] if n.get("extras", {}).get("role") == "assembly"}
            assembly = self.source.json(design["assembly"]["path"])
            for item in assembly["instances"]:
                self.assertEqual(nodes[item["name"]]["extras"]["partId"], item["part_id"])
                self.assertEqual(nodes[item["name"]]["matrix"],
                                 [item["transform"][r][c]*(0.001 if c == 3 and r < 3 else 1) for c in range(4) for r in range(4)])

    def test_saved_frame_floor_and_media_provenance_match_the_corrected_revision(self):
        self.assertEqual(self.media["artifactCommit"], self.source.commit)
        self.assertEqual(self.media["contractSha256"], self.source.source["contractSha256"])
        self.assertEqual(self.media["allSavedDisplayFramesFloorGate"], "PASS")
        self.assertFalse(self.media["completeWalkingVideoGenerated"])
        for name, entry in self.media["files"].items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(), entry["sha256"])
        floor = json.loads((ROOT/"docs/ver3/r7_display_floor2/display-floor-gate.json").read_text())
        self.assertEqual(floor["artifactCommit"], self.source.commit)
        self.assertFalse(floor["floorOrMeshShifted"])
        for key, guide in self.guides.items():
            self.assertEqual(len(floor["designs"][key]["orthogonalDisplayFrames"]), 73)
            self.assertEqual(floor["designs"][key]["instanceCount"], guide["model"]["instanceCount"])
            self.assertGreaterEqual(floor["designs"][key]["minimumDisplayNoncontactZMm"], 0)
            diag = json.loads((ROOT/f"docs/ver3/r7_display_floor2/diagnostic_{key}.json").read_text())
            self.assertTrue(diag["canonicalRockerNullPreserved"])
            for frame in diag["frames"]:
                self.assertFalse(frame["floorCorrectionApplied"])
                self.assertFalse(frame["interpolationUsed"])
                self.assertEqual(frame["belowReferencePlaneParts"], {})
                for foot in frame["feet"]:
                    self.assertIsNone(foot["canonicalIndependentRockerAngleRad"])

    def test_public_page_is_not_an_old_model_or_a_claimed_walking_movie(self):
        for text in ("全2285点", "24,000", "23,305.13", "23,735.37", "23,154.43", "396円",
                     "未計算の足部品は省略", "完全なCAD歩行映像ではありません", "0.2 mm", "2点",
                     "第一カット", "実自己始動・30 cm歩行はUNKNOWN"):
            self.assertIn(text, self.html)
        self.assertNotIn("全2303点", self.html)
        self.assertNotIn("ローカル未公開", self.html)
        videos = [a for tag, a in self.tags if tag == "video"]
        self.assertEqual(len(videos), 6)
        self.assertTrue(all("r7-" in v["id"] and "walking" not in v["id"] for v in videos))
        for guide in self.guides.values():
            for key, url in guide["links"].items():
                self.assertIn(self.source.source["publicSourceCommit"], url)
                self.assertTrue(url.startswith("https://github.com/"))
        self.assertNotIn("r7-files/", self.html)

    def test_current_part_labels_not_historical_dimension_names(self):
        for guide in self.guides.values():
            for item in guide["instances"].values():
                self.assertIn(item["partId"], guide["parts"])
            self.assertIn("H_BOLT_M2_12", guide["parts"])
            self.assertIn("H_LOCK_NUT_M2", guide["parts"])
        sample = self.guides["A"]["instances"]["H_NUT_M2_019"]
        self.assertEqual(sample["partId"], "H_LOCK_NUT_M2")
        self.assertEqual(sample["displayLabel"], "H_LOCK_NUT_M2_019")


if __name__ == "__main__":
    unittest.main()
