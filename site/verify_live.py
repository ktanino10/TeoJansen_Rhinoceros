"""Verify the actual public Pages response, independently of deployment success."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "site/dist/TeoJansen_Rhinoceros"
PUBLIC_URL = "https://ktanino10.github.io/TeoJansen_Rhinoceros/"
PAGES = {"index.html", "production.html", "comparison.html", "viewer.html", "calculations.html"}


def fetch_bytes(url):
    with urlopen(Request(url, headers={"User-Agent": "Rhinoceros-Pages-verification"}), timeout=45) as response:
        if response.status != 200:
            raise ValueError(f"Expected GET 200: {url}")
        return response.read()


def validate_manifest(manifest, expected_commit):
    if not re.fullmatch(r"[0-9a-f]{40}", expected_commit):
        raise ValueError("Expected a full immutable commit SHA")
    if manifest.get("source_commit") != expected_commit:
        raise ValueError(f"Published commit differs: expected {expected_commit}, received {manifest.get('source_commit')}")
    if set(manifest.get("pages", [])) != PAGES:
        raise ValueError("Published page allowlist differs")
    if not manifest.get("assets"):
        raise ValueError("Published asset manifest is empty")
    for name in manifest["assets"]:
        if not re.fullmatch(r"assets/[A-Za-z0-9][A-Za-z0-9_.-]*\.(webp|mp4|gif|glb|json|js|txt|svg|csv)", name):
            raise ValueError(f"Unsafe public asset path: {name}")


def verify(expected_commit):
    local = json.loads((OUTPUT / "build-manifest.json").read_text())
    remote = json.loads(fetch_bytes(PUBLIC_URL + "build-manifest.json"))
    validate_manifest(remote, expected_commit)
    if set(remote["assets"]) != set(local["assets"]):
        raise ValueError("Published assets differ from the local build allowlist")
    if remote.get("external_images", {}) != local.get("external_images", {}):
        raise ValueError("Published external image references differ from the fixed local source")
    for page in sorted(PAGES):
        text = fetch_bytes(PUBLIC_URL + page).decode("utf-8")
        if '<html lang="ja">' not in text or "{{" in text or "/Users/" in text:
            raise ValueError(f"Invalid deployed HTML: {page}")
    for filename in ("styles.css", "viewer.css", "calculations.css", "app.js", "viewer-loader.js", "calculations.js", "favicon.svg"):
        if fetch_bytes(PUBLIC_URL + filename) != (ROOT / "site" / filename).read_bytes():
            raise ValueError(f"Deployed static source differs: {filename}")

    def check_asset(item):
        name, entry = item
        expected = local["assets"][name]
        if (entry["source"], entry["source_sha256"]) != (expected["source"], expected["source_sha256"]):
            raise ValueError(f"Published asset has a different source: {name}")
        data = fetch_bytes(PUBLIC_URL + name)
        if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError(f"Published asset size/hash differs: {name}")
        if name.endswith(".webp"):
            with Image.open(BytesIO(data)) as image:
                if image.getexif() or any(key in image.info for key in ("exif", "xmp", "icc_profile")):
                    raise ValueError(f"Public derivative retained metadata: {name}")
        if name.endswith(".svg"):
            from calculation_data import svg_dimensions
            svg_dimensions(data)
        if entry.get("unchanged_original") and entry["sha256"] != entry["source_sha256"]:
            raise ValueError(f"Calculation original was modified: {name}")
        return len(data)

    with ThreadPoolExecutor(max_workers=4) as pool:
        sizes = list(pool.map(check_asset, remote["assets"].items()))
    for url, entry in local.get("external_images", {}).items():
        data = fetch_bytes(url)
        if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["source_sha256"]:
            raise ValueError(f"External reference size/hash differs: {url}")
        from calculation_data import svg_dimensions
        svg_dimensions(data)
    return {"url": PUBLIC_URL, "source_commit": expected_commit, "pages": len(PAGES),
            "assets": len(sizes), "asset_bytes": sum(sizes), "all_gets": 200,
            "external_images": len(local.get("external_images", {})),
            "asset_hashes": "matched", "display_metadata": "removed"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.expected_commit), ensure_ascii=False, indent=2))
