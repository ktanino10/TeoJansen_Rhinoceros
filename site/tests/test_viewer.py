from collections import Counter
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "site"))
import viewer_data
from test_build import Sections

OUTPUT = ROOT / "site/dist/TeoJansen_Rhinoceros"


def glb(path):
    data = path.read_bytes()
    magic, version, length = struct.unpack_from("<4sII", data)
    if magic != b"glTF" or version != 2 or length != len(data):
        raise AssertionError("Not a complete GLB 2.0")
    json_length, kind = struct.unpack_from("<I4s", data, 12)
    if kind != b"JSON":
        raise AssertionError("Missing GLB JSON chunk")
    document = json.loads(data[20:20+json_length])
    binary_length, kind = struct.unpack_from("<I4s", data, 20+json_length)
    if kind != b"BIN\0":
        raise AssertionError("Missing GLB binary chunk")
    binary = data[28+json_length:]
    if binary_length != len(binary):
        raise AssertionError("Truncated binary")
    return document, binary


def payload(document, binary, index):
    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    offset = view.get("byteOffset", 0)
    return binary[offset:offset+view["byteLength"]], accessor


def visible_at(guide, step_index):
    step = guide["steps"][step_index]
    introduced = set().union(*(set(s["add"]) for s in guide["steps"][:step_index+1]))
    return (introduced - set(step["hidden"])) | set(step["preview"])


class ViewerDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = viewer_data.read_source()
        cls.guides = {key: json.loads((OUTPUT / f"assets/assembly-{key}.json").read_text()) for key in "ABC"}
        cls.inputs = {key: viewer_data.read_inputs(key) for key in "ABC"}
        cls.static = (OUTPUT / "viewer.html").read_text()
        parser = Sections()
        parser.feed(cls.static)
        cls.sections = parser.sections

    def test_exact_cad_vertices_triangles_instances_and_units(self):
        for key in "ABC":
            with self.subTest(design=key):
                manifest, library, bom, _ = self.inputs[key]
                document, binary = glb(OUTPUT / f"assets/ver3-{key}.glb")
                self.assertEqual(document["asset"]["extras"]["sourceUnits"], "mm")
                self.assertEqual(document["asset"]["extras"]["units"], "metres")
                self.assertFalse(document["asset"]["extras"]["simplifiedByAdapter"])
                for mesh in document["meshes"]:
                    part = mesh["name"]
                    original = library[part]
                    primitive = mesh["primitives"][0]
                    actual, accessor = payload(document, binary, primitive["attributes"]["POSITION"])
                    flat = [value * 0.001 for vertex in original["vertices"] for value in vertex]
                    self.assertEqual(actual, struct.pack(f"<{len(flat)}f", *flat), part)
                    self.assertEqual(accessor["count"], len(original["vertices"]))
                    converted = struct.unpack(f"<{len(flat)}f", actual)
                    self.assertLess(max(abs(x-y) for x, y in zip(flat, converted))*1000, 0.001, part)
                    actual, accessor = payload(document, binary, primitive["indices"])
                    flat = [value for triangle in original["triangles"] for value in triangle]
                    self.assertEqual(actual, struct.pack(f"<{len(flat)}I", *flat), part)
                    self.assertEqual(accessor["count"], len(flat))
                instances = {node["extras"]["instanceId"]: node for node in document["nodes"]
                             if node.get("extras", {}).get("role") == "assembly"}
                self.assertEqual(set(instances), {item["name"] for item in manifest["instances"]})
                counts = Counter(node["extras"]["partId"] for node in instances.values())
                self.assertEqual({p: counts[p] for p in bom}, {p: int(r["quantity"]) for p, r in bom.items()})
                for item in manifest["instances"]:
                    node = instances[item["name"]]
                    expected = [item["transform"][row][col] * (0.001 if col == 3 and row < 3 else 1)
                                for col in range(4) for row in range(4)]
                    self.assertEqual(node["matrix"], expected)
                root = document["nodes"][document["scenes"][0]["nodes"][0]]
                self.assertEqual(root["rotation"], [-math.sqrt(0.5), 0, 0, math.sqrt(0.5)])
                coupons = [n for n in document["nodes"] if n.get("extras", {}).get("role") == "coupon"]
                self.assertEqual({n["extras"]["partId"] for n in coupons}, {"Q_BEARING_FIT", "Q_JOINT_FIT"})
                self.assertTrue(all(int(bom[n["extras"]["partId"]]["quantity"]) == 0 for n in coupons))

    def test_every_instance_is_mapped_once_and_empty_is_not_first_part(self):
        for key, guide in self.guides.items():
            self.assertEqual(guide["model"]["instanceCount"], {"A": 791, "B": 796, "C": 755}[key])
            self.assertEqual(guide["revision"], self.source)
            added = [name for step in guide["steps"] for name in step["add"]]
            self.assertEqual(len(added), len(set(added)))
            self.assertEqual(set(added), set(guide["instances"]))
            self.assertEqual(visible_at(guide, 0), set())
            self.assertEqual(guide["steps"][0]["coupons"], [])
            self.assertEqual(guide["steps"][1]["coupons"], ["Q_BEARING_FIT", "Q_JOINT_FIT"])
            self.assertEqual(visible_at(guide, 1), set())
            self.assertTrue(guide["steps"][2]["preview"])
            self.assertEqual(guide["steps"][2]["add"], [])
            self.assertEqual(visible_at(guide, guide["completeStep"]), set(guide["instances"]))
            for step in guide["steps"]:
                if step["referenceStep"]:
                    self.assertEqual(step["title"], viewer_data.instructions()[step["referenceStep"]]["title"])
                    self.assertIn(step["title"], self.sections[f"guide-{key}-{step['id']}"]["text"])
                for ident in step["hidden"] + step["preview"]:
                    self.assertIn(ident, guide["instances"])

    def test_windows_respect_recorded_partial_states_and_variant_order(self):
        for key, guide in self.guides.items():
            by_id = {step["id"]: n for n, step in enumerate(guide["steps"])}
            _, _, _, access = self.inputs[key]
            for inspection in guide["inspections"]:
                checks = [c for c in access["checks"] if c.get("screw") in inspection["highlight"]
                          and c["check"] == "Window screw straight-tool path after carrier-first disassembly"]
                self.assertEqual(len(checks), 4)
                self.assertTrue(all(c["passed"] for c in checks))
                self.assertEqual(inspection["hidden"], sorted(checks[0]["removed_parts"]))
                window_step = "12-window" if key == "A" and inspection["id"] == "S1" else f"11-{inspection['id']}-window"
                shown = visible_at(guide, by_id[window_step])
                self.assertFalse(shown & set(inspection["hidden"]))
                self.assertTrue(set(inspection["highlight"]) <= shown)
            if key == "B":
                self.assertLess(by_id["11-S1-window"], by_id["11-S3"])
                self.assertLess(by_id["11-S3"], by_id["11-S3-window"])
            elif key == "A":
                self.assertLess(by_id["4"], by_id["12-belt"])
                self.assertLess(by_id["12-belt"], by_id["12-window"])
                self.assertLess(by_id["12-window"], by_id["13"])
                carriage_parts = [guide["instances"][n]["partId"] for n in guide["steps"][by_id["4"]]["add"]]
                self.assertEqual(sum(p.startswith("P_INPUT_CARRIAGE_") for p in carriage_parts), 3)

    def test_glb_fingerprints_and_private_metadata(self):
        for key, guide in self.guides.items():
            path = OUTPUT / f"assets/ver3-{key}.glb"
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), guide["model"]["sha256"])
            self.assertLess(path.stat().st_size, viewer_data.MAX_MODEL_BYTES)
            document, _ = glb(path)
            metadata = json.dumps(document)
            for private in ("/Users/", "file://", "EXIF", "XMP"):
                self.assertNotIn(private, metadata)
            self.assertNotIn("images", document)
            self.assertNotIn("animations", document)

    def test_changed_engineering_sources_and_missing_parts_fail_closed(self):
        modified = copy.deepcopy(self.source)
        modified["sourceHashes"]["docs/ver3/ASSEMBLY_ja.md"] = "0" * 64
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.json"
            path.write_text(json.dumps(modified))
            with patch.object(viewer_data, "SOURCE", path):
                with self.assertRaisesRegex(ValueError, "Engineering revision changed"):
                    viewer_data.read_source()
        manifest, _, _, access = self.inputs["C"]
        modified = copy.deepcopy(manifest)
        modified["instances"].append({"name": "UNMAPPED_001", "part_id": "UNMAPPED", "group": "unknown",
                                      "transform": manifest["instances"][0]["transform"]})
        with self.assertRaisesRegex(ValueError, "missing assembly-stage mapping"):
            viewer_data.make_guide(modified, access)

    def test_matrix_has_all_eight_rows_media_sources_and_limits(self):
        matrix = (OUTPUT / "comparison.html").read_text()
        parser = Sections()
        parser.feed(matrix)
        for name in ("connection", "retention", "bearings", "input", "support", "mass", "assembly", "procurement"):
            row = parser.sections[f"matrix-{name}"]
            self.assertGreaterEqual(len(row["images"]), 2)
            self.assertGreater(len(row["text"]), 250)
            self.assertTrue(any("viewer.html" in link for link in row["links"]))
        for text in ("3 mm目標は未達", "Bは名目トルク入力も不足", "調達完了ではない",
                     "装置全体がその割合で軽くなった", "第一カット", "同じ実測値"):
            self.assertIn(text, matrix)


if __name__ == "__main__":
    unittest.main()
