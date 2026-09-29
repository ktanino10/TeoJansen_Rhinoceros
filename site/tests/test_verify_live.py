import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "site"))
import verify_live


class LiveVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = verify_live.OUTPUT
        cls.manifest = json.loads((cls.output / "build-manifest.json").read_text())

    def fixture_fetch(self, url):
        if url in self.manifest.get("external_images", {}):
            return (ROOT / self.manifest["external_images"][url]["source"]).read_bytes()
        raw_prefix = f"https://raw.githubusercontent.com/ktanino10/TeoJansen_Rhinoceros/{self.manifest['source_commit']}/"
        if url.startswith(raw_prefix):
            path = url.removeprefix(raw_prefix)
            self.assertIn(path, verify_live.DOCUMENT_EXAMPLES)
            return (ROOT / path).read_bytes()
        engineering_prefix = f"https://raw.githubusercontent.com/ktanino10/TeoJansen_Rhinoceros/{self.manifest['r7_source']['publicSourceCommit']}/"
        if url.startswith(engineering_prefix):
            path = url.removeprefix(engineering_prefix)
            self.assertIn(path, verify_live.engineering_examples(self.manifest))
            return (ROOT / path).read_bytes()
        self.assertTrue(url.startswith(verify_live.PUBLIC_URL))
        path = url.removeprefix(verify_live.PUBLIC_URL)
        return (self.output / path).read_bytes()

    def test_all_pages_assets_and_source_hashes_are_checked(self):
        with patch.object(verify_live, "fetch_bytes", side_effect=self.fixture_fetch) as fetch:
            report = verify_live.verify(self.manifest["source_commit"])
        self.assertEqual(report["pages"], 14)
        self.assertEqual(report["assets"], len(self.manifest["assets"]))
        self.assertEqual(report["all_gets"], 200)
        self.assertEqual(report["external_images"], 1)
        self.assertEqual(report["english_documents"], 3)
        self.assertEqual(report["current_version"], "3.1")
        self.assertEqual(report["engineering_downloads"], 3)
        self.assertEqual(fetch.call_count, 1 + 14 + len(verify_live.STATIC_FILES) + len(self.manifest["assets"]) + 1 + 3 + 3)

    def test_stale_commit_and_external_paths_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Published commit differs"):
            verify_live.validate_manifest(self.manifest, "0" * 40)
        modified = copy.deepcopy(self.manifest)
        modified["assets"]["https://example.com/untrusted"] = {}
        with self.assertRaisesRegex(ValueError, "Unsafe public asset path"):
            verify_live.validate_manifest(modified, modified["source_commit"])

    def test_corrupt_live_payload_cannot_pass(self):
        def corrupt(url):
            data = self.fixture_fetch(url)
            return data + b"corrupt" if url.endswith("assets/ver3-C.glb") else data
        with patch.object(verify_live, "fetch_bytes", side_effect=corrupt):
            with self.assertRaisesRegex(ValueError, "size/hash differs"):
                verify_live.verify(self.manifest["source_commit"])

    def test_wrong_public_version_and_corrupt_current_native_cannot_pass(self):
        def wrong_version(url):
            if url.endswith("build-manifest.json"):
                manifest = copy.deepcopy(self.manifest)
                manifest["public_versions"]["3.1"]["data"] = "docs/ver3/comparison.json"
                return json.dumps(manifest).encode()
            return self.fixture_fetch(url)
        with patch.object(verify_live, "fetch_bytes", side_effect=wrong_version):
            with self.assertRaisesRegex(ValueError, "public-version mapping"):
                verify_live.verify(self.manifest["source_commit"])

        def corrupt_native(url):
            data = self.fixture_fetch(url)
            return data + b"corrupt" if url.endswith("Walker_A.FCStd") else data
        with patch.object(verify_live, "fetch_bytes", side_effect=corrupt_native):
            with self.assertRaisesRegex(ValueError, "engineering download differs"):
                verify_live.verify(self.manifest["source_commit"])


if __name__ == "__main__":
    unittest.main()
