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
        self.assertTrue(url.startswith(verify_live.PUBLIC_URL))
        path = url.removeprefix(verify_live.PUBLIC_URL)
        return (self.output / path).read_bytes()

    def test_all_pages_assets_and_source_hashes_are_checked(self):
        with patch.object(verify_live, "fetch_bytes", side_effect=self.fixture_fetch) as fetch:
            report = verify_live.verify(self.manifest["source_commit"])
        self.assertEqual(report["pages"], 4)
        self.assertEqual(report["assets"], len(self.manifest["assets"]))
        self.assertEqual(report["all_gets"], 200)
        self.assertEqual(fetch.call_count, 1 + 4 + 5 + len(self.manifest["assets"]))

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


if __name__ == "__main__":
    unittest.main()
