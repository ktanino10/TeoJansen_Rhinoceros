from collections import Counter
import copy
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import unittest
import zipfile

SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))
from build_r7_preview import OUTPUT, validate_preview
from r7_data import Snapshot, replay_contract, display_sequence, path_point, json_digest


def read_glb(path):
    compressed = path.read_bytes()
    raw = gzip.decompress(compressed)
    magic, version, length = struct.unpack_from("<4sII", raw)
    if magic != b"glTF" or version != 2 or length != len(raw):
        raise AssertionError("Invalid local r7 GLB")
    size, kind = struct.unpack_from("<I4s", raw, 12)
    if kind != b"JSON":
        raise AssertionError("Missing JSON chunk")
    return json.loads(raw[20:20+size]), raw[28+size:], raw, compressed


class R7DisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = Snapshot()
        cls.guides = {key: json.loads((OUTPUT / f"assets/r7-assembly-{key}.json").read_text()) for key in "ABC"}
        cls.inputs = {}
        for design in cls.snapshot.contract["designs"]:
            cls.inputs[design["id"]] = (
                cls.snapshot.json(design["assembly"]["path"]),
                cls.snapshot.json(design["stages"]["path"]),
                cls.snapshot.json(f"docs/ver3/integrated_r7/{design['id']}/assembly_access.json"),
                json.loads(gzip.decompress(cls.snapshot.read(design["mesh"]["path"]))),
                list(csv.DictReader(io.StringIO(cls.snapshot.read(design["bom"]["path"]).decode()))),
            )

    def test_exact_geometry_placements_and_all_2285_instances(self):
        total = 0
        for key, guide in self.guides.items():
            with self.subTest(design=key):
                assembly, _, _, library, bom = self.inputs[key]
                gltf, binary, raw, compressed = read_glb(OUTPUT / guide["modelUrl"])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), guide["model"]["sha256"])
                self.assertEqual(hashlib.sha256(compressed).hexdigest(), guide["model"]["transportSha256"])
                self.assertEqual(len(raw), guide["model"]["bytes"])
                self.assertEqual(len(compressed), guide["model"]["transportBytes"])
                for mesh in gltf["meshes"]:
                    part = mesh["name"]
                    primitive = mesh["primitives"][0]
                    positions = gltf["accessors"][primitive["attributes"]["POSITION"]]
                    view = gltf["bufferViews"][positions["bufferView"]]
                    payload = binary[view["byteOffset"]:view["byteOffset"]+view["byteLength"]]
                    values = [v * 0.001 for vertex in library[part]["vertices"] for v in vertex]
                    self.assertEqual(payload, struct.pack(f"<{len(values)}f", *values), part)
                    restored = struct.unpack(f"<{len(values)}f", payload)
                    self.assertLess(max(abs(a-b) for a, b in zip(values, restored))*1000, 0.001)
                    indices = gltf["accessors"][primitive["indices"]]
                    index_view = gltf["bufferViews"][indices["bufferView"]]
                    values = [i for triangle in library[part]["triangles"] for i in triangle]
                    self.assertEqual(binary[index_view["byteOffset"]:index_view["byteOffset"]+index_view["byteLength"]],
                                     struct.pack(f"<{len(values)}I", *values))
                nodes = {node["extras"]["instanceId"]: node for node in gltf["nodes"] if node.get("extras", {}).get("role") == "assembly"}
                self.assertEqual(set(nodes), set(guide["instances"]))
                self.assertEqual(len(nodes), {"A": 750, "B": 785, "C": 750}[key])
                for item in assembly["instances"]:
                    expected = [item["transform"][r][c] * (0.001 if c == 3 and r < 3 else 1) for c in range(4) for r in range(4)]
                    self.assertEqual(nodes[item["name"]]["matrix"], expected)
                counts = Counter(node["extras"]["partId"] for node in nodes.values())
                self.assertEqual(counts, Counter({row["part_id"]: int(row["quantity"]) for row in bom}))
                self.assertFalse(any(node.get("extras", {}).get("role") == "coupon" for node in gltf["nodes"]))
                total += len(nodes)
        self.assertEqual(total, 2285)

    def test_all_12_stages_replay_operations_and_final_inventory(self):
        for key, guide in self.guides.items():
            assembly, workflow, access, _, _ = self.inputs[key]
            states, paths = replay_contract(assembly, workflow, access)
            self.assertEqual(len(guide["steps"]), 13)
            self.assertEqual(guide["canonicalStageCount"], 12)
            self.assertEqual(guide["inventories"][guide["steps"][0]["frames"][0]["inventory"]], [])
            self.assertEqual(guide["paths"], paths)
            ever, visible = set(), set()
            for source, stage in zip(workflow["stages"], guide["steps"][1:]):
                self.assertEqual(stage["id"], source["id"])
                self.assertEqual(stage["title"], source["titleJa"])
                self.assertEqual(stage["orderedOperations"], source["orderedOperations"])
                for index, operation in enumerate(source["orderedOperations"]):
                    names = set(operation["instances"])
                    if operation["operation"] == "remove":
                        self.assertTrue(names <= visible)
                        visible -= names
                    elif operation["operation"] == "reinsert":
                        self.assertTrue(names <= ever)
                        self.assertFalse(names & visible)
                        visible |= names
                    else:
                        self.assertFalse(names & ever)
                        ever |= names
                        visible |= names
                    self.assertEqual(visible, states[source["id"]][index])
                end = stage["frames"][-1]
                self.assertEqual(set(guide["inventories"][end["inventory"]]), visible)
                self.assertEqual(set(guide["inventories"][end["installedInventory"]]), visible)
                self.assertEqual(end["offsets"], {})
            self.assertEqual(visible, set(guide["instances"]))

    def test_path_frames_keep_all_fixed_parts_and_exact_translations(self):
        for key, guide in self.guides.items():
            for stage in guide["steps"]:
                for frame in stage["frames"]:
                    if frame["kind"] != "path-sample":
                        continue
                    p = guide["paths"][frame["pathId"]]
                    self.assertEqual(guide["inventories"][frame["inventory"]], p["sceneInventoryNames"])
                    self.assertEqual(frame["inventorySha256"], json_digest(p["sceneInventoryNames"]))
                    delta = [p["sceneOffsetMm"][n] + path_point(p, frame["distanceMm"])[n] for n in range(3)]
                    for name in p["movingNames"]:
                        self.assertEqual(frame["offsets"].get(name, [0, 0, 0]), delta)
                    for name in p["fixedNames"]:
                        expected = [p["sceneOffsetMm"][n] + p["fixedPoseOverridesByName"].get(name, [0, 0, 0])[n] for n in range(3)]
                        self.assertEqual(frame["offsets"].get(name, [0, 0, 0]), expected)
                    self.assertEqual(frame["stopCrankDeg"], 0)
        guide = self.guides["B"]
        first, second = (guide["paths"][key] for key in ("front_basket_and_rotor_lower", "front_basket_axial_seat"))
        self.assertEqual(len(first["fixedNames"]), 276)
        for name in ("S_GUARD_UPPER_RIGHT_2_001", "H_BOLT_M3_20_011", "H_BOLT_M3_20_012"):
            self.assertIn(name, first["fixedNames"])
            self.assertIn(name, second["fixedNames"])
        self.assertEqual(first["fixedNames"], second["fixedNames"])
        self.assertEqual(first["movingNames"], second["movingNames"])
        self.assertEqual(path_point(first, first["distancesMm"][-1]), [4, 0, 0])
        self.assertEqual(path_point(second, second["distancesMm"][0]), [4, 0, 0])
        self.assertEqual(path_point(second, second["distancesMm"][-1]), [0, 0, 0])
        upper = guide["paths"]["upper_pet_from_below"]
        self.assertEqual(upper["constantOffsetMm"], [0, -4, 0])
        for name, offset in upper["fixedPoseOverridesByName"].items():
            self.assertIn(name, upper["fixedNames"])
            self.assertEqual(offset, [-53, 0, 0])

    def test_preparation_hand_support_and_reinsert_are_not_omitted(self):
        for guide in self.guides.values():
            for stage in (guide["steps"][6], guide["steps"][11]):
                self.assertTrue(stage["prepareOnly"])
                frame = stage["frames"][stage["defaultFrame"]]
                shown = set(guide["inventories"][frame["inventory"]])
                installed = set(guide["inventories"][frame["installedInventory"]])
                self.assertEqual(shown, set(stage["prepareOnly"]))
                self.assertFalse(shown & installed)
            self.assertEqual(guide["steps"][6]["orderedOperations"][0]["instances"], ["P_INPUT_PINION_001"])
            restored = [name for op in guide["steps"][7]["orderedOperations"] if op["operation"] == "reinsert" for name in op["instances"]]
            self.assertEqual(restored, ["P_INPUT_PINION_001"])
            self.assertEqual(len(guide["steps"][7]["temporarilyHandSupported"]), 16)
            self.assertTrue(guide["steps"][8]["clockingAlreadyIncludedInCadTransforms"])

    def test_negative_controls_reject_inventory_drops_reinsert_and_path_changes(self):
        assembly, workflow, access, _, _ = self.inputs["B"]
        modified = copy.deepcopy(access)
        path = next(p for p in modified["stages"] if p["id"] == "front_basket_and_rotor_lower")
        name = "S_GUARD_UPPER_RIGHT_2_001"
        path["fixedNames"].remove(name)
        path["sceneInventoryNames"].remove(name)
        path["inventorySha256"] = json_digest(path["sceneInventoryNames"])
        with self.assertRaisesRegex(ValueError, "inventory"):
            replay_contract(assembly, workflow, modified)
        modified = copy.deepcopy(workflow)
        modified["stages"][6]["orderedOperations"][1]["operation"] = "add"
        with self.assertRaisesRegex(ValueError, "require reinsert"):
            replay_contract(assembly, modified, access)
        modified = copy.deepcopy(workflow)
        modified["stages"][3]["pathChecks"][0]["fixedPoseOverrides"][0]["translationFromCadMm"] = [0, 0, 0]
        with self.assertRaisesRegex(ValueError, "inventory"):
            replay_contract(assembly, modified, access)
        modified = copy.deepcopy(workflow)
        modified["stages"][6]["pathChecks"][0]["constantOffsetMm"] = [0, 0, 0]
        with self.assertRaises(ValueError):
            replay_contract(assembly, modified, access)
        modified = copy.deepcopy(workflow)
        modified["stages"][0]["stopCrankDeg"] = 15
        with self.assertRaisesRegex(ValueError, "stop-angle0"):
            replay_contract(assembly, modified, access)

    def test_local_downloads_and_nonpublication_guards(self):
        manifest = json.loads((OUTPUT / "r7-preview-manifest.json").read_text())
        validate_preview(OUTPUT, manifest)
        self.assertFalse(manifest["publicationAuthorized"])
        self.assertTrue((OUTPUT / "LOCAL_ONLY_DO_NOT_DEPLOY").exists())
        self.assertIn("rocker angles", manifest["motionStatus"])
        for ident, guide in self.guides.items():
            for kind in ("cad", "native", "bom"):
                path = guide["links"][kind]
                self.assertFalse(path.startswith("http"))
                entry = manifest["localDownloads"][path]
                self.assertEqual(hashlib.sha256((OUTPUT/path).read_bytes()).hexdigest(), entry["sha256"])
            with zipfile.ZipFile(OUTPUT / guide["links"]["stl"]) as archive:
                for name in archive.namelist():
                    original = f"STL/Ver.3/integrated_r7/{ident}/{name}"
                    self.assertEqual(archive.read(name), self.snapshot.checked(original))
        html = (OUTPUT / "r7.html").read_text()
        for value in ("23,305.13", "23,735.37", "23,154.43", "24,000", "約396円"):
            self.assertIn(value, html)
        self.assertNotIn("<video", html)
        self.assertNotIn("https://github.com/", html)
        self.assertEqual((OUTPUT / "assets/assembly-A.json").read_bytes(),
                         (SITE / "dist/TeoJansen_Rhinoceros/assets/assembly-A.json").read_bytes())

    def test_blender_handoff_reuses_exact_ui_sources_without_walking_fabrication(self):
        from r7_blender import read_handoff, accessor_values
        handoff, models = read_handoff()
        self.assertEqual(handoff["candidateCommit"], self.snapshot.commit)
        self.assertEqual(handoff["walkingMotion"]["status"], "partial_canonical_states_received")
        self.assertTrue(handoff["localOnly"])
        self.assertEqual(sum(len(model["guide"]["instances"]) for model in models.values()), 2285)
        for ident, model in models.items():
            self.assertEqual(model["guide"], self.guides[ident])
            mesh = model["gltf"]["meshes"][0]
            original = self.inputs[ident][3][mesh["name"]]
            accessor = mesh["primitives"][0]["attributes"]["POSITION"]
            points = accessor_values(model, accessor)
            self.assertEqual(len(points), len(original["vertices"]))
            for a, b in zip(points[0], original["vertices"][0]):
                self.assertAlmostEqual(a * 1000, b, places=5)
            self.assertEqual(handoff["designs"][ident]["signedInputRevolutionsPerCrank"],
                             self.guides[ident]["signedInputRevolutionsPerCrank"])


if __name__ == "__main__":
    unittest.main()
