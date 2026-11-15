"""Publish exact trial quantities and separately labelled 3.1 A source lists."""

from collections import Counter
import csv
import json
import math
from pathlib import Path

from build_m3_trial import ROOT, DOC, CAD, PRINT, REVISION, BASE, sha, write_json
from purchase_reference import retained_reference

CHECKED = "2026-11-15"
PURCHASES = [
    ("H_M3_20", "千石電商", "EEHD-6D5E", "M3 x 20 socket head; nominal pitch 0.5; 2.5mm key",
     "stainless; grade/finish not stated", 10, 330, "https://www.sengoku.co.jp/mod/sgk_cart/detail.php?code=EEHD-6D5E",
     "listed; exact online/store quantity UNKNOWN"),
    ("H_M3_NUT", "秋月電子通商", "114372", "M3 x 0.5 hex nut; AF5.5/H2.4 are fit-acceptance assumptions",
     "brass", 10, 120, "https://akizukidenshi.com/catalog/g/g114372/",
     "online in stock; store table is a dated indication, not a reservation"),
    ("H_M3_WASHER", "千石電商", "EEHD-6EC4 / BSW3mm", "M3 x OD8 x 0.5; actual bore/tolerances to measure",
     "nickel-plated brass", 10, 250, "https://www.sengoku.co.jp/mod/sgk_cart/detail.php?code=EEHD-6EC4",
     "listed; Akihabara handling floor shown; exact online/store quantity UNKNOWN"),
    ("H_M3_SLEEVE12", "千石電商", "EEHD-6CJH / BSカラー 3x12", "M3 through / approx OD6 x 12; end groove, ID and tolerances to inspect",
     "brass", 4, 200, "https://www.sengoku.co.jp/mod/sgk_cart/detail.php?code=EEHD-6CJH",
     "listed; Akihabara stock location shown; exact online/store quantity UNKNOWN"),
]


def csv_write(path, headers, rows):
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(rows)


def main():
    assembly = json.loads((DOC / "assembly.json").read_text())
    checks = json.loads((DOC / "checks.json").read_text())
    if assembly["revisionId"] != REVISION or checks["status"] != "PASS_WITH_SCOPE":
        raise ValueError("Only a matching, checked bench revision can be reported")
    parts = assembly["parts"]
    rows = []
    for pid, shop, sku, spec, material, pack, price, url, stock in PURCHASES:
        needed = parts[pid]["quantity"]
        packs = math.ceil(needed / pack)
        rows.append((REVISION, pid, needed, "UNKNOWN", "UNKNOWN; subtract verified on-hand count",
                     shop, sku, spec, material, pack, price, packs * pack, packs * price, "JPY tax included",
                     url, CHECKED, stock, "bench only; not a complete walker purchase list"))
    rows.append((REVISION, "H_HEX5_30", 2, "UNKNOWN", "UNKNOWN; use spare stock if available",
                 "横山テクノ (existing 3.1 non-fastener stock family)", "HEX5",
                 "5mm-AF C3604B; cut two 30mm pieces from one 100mm stock bar; no end tapping",
                 "brass C3604B", 1, "UNKNOWN", "1 x 100mm stock if none on hand", "UNKNOWN",
                 "current price not transcribed from image table",
                 "https://www.yokoyama-techno.net/detail/596.html", CHECKED,
                 "listing confirmed; price, exact stock and shipping UNKNOWN",
                 "Do not cut shafts from the completed Ver.2; no plastic substitute for loaded torque testing"))
    csv_write(DOC / "purchase-list.csv",
              ("revision", "part_id", "trial_needed", "verified_on_hand", "additional_purchase_quantity",
               "shop", "sku", "specification", "material", "pack_quantity", "pack_price_jpy",
               "minimum_order_if_none_owned", "minimum_cost_if_none_owned_jpy", "tax",
               "official_url", "checked_date", "stock_status", "scope"), rows)
    csv_write(DOC / "BOM.csv", ("revision", "part_id", "category", "bench_quantity", "print_trial_quantity",
                              "nominal_unit_mass_g", "description"), [
        (REVISION, pid, part["category"], part["quantity"],
         max(1, part["quantity"]) if part["category"] == "printed" else 0,
         part["nominalMassG"], part["description"]) for pid, part in parts.items()])

    original = ROOT / "docs/ver3/integrated_r7/A"
    with (original / "BOM.csv").open() as stream:
        old_bom = list(csv.DictReader(stream))
    old_parts = {r["part_id"]: r for r in old_bom}
    geometry = json.loads((original / "print_geometry.json").read_text())
    print_rows = []
    for part in geometry["printedParts"]:
        row = old_parts[part["partId"]]
        print_rows.append(("3.1 / floor2 / A", part["partId"], part["stl"], row["quantity"], row["spec"],
                           json.dumps(part["rigidBedTransforms"]), "already baked into this STL; do not apply twice",
                           "may be required" if part["supportsMayBeRequired"] else "none planned; inspect",
                           "historical 0.4mm representatives only; NOT the 0.2mm M3 revision",
                           part["sha256"], "physical fit/strength UNKNOWN"))
    csv_write(DOC / "print-list-3.1-A.csv",
              ("revision", "part_id", "file", "needed", "purpose", "native_to_print_transform",
               "orientation", "support", "slicing_scope", "sha256", "qualification"), print_rows)
    lots = json.loads((original / "purchase_lots.json").read_text())
    purchase_rows = []
    for lot in lots["rows"]:
        reference = retained_reference(lot)
        related = [r for r in old_bom if r["sku"] == lot["sku"]]
        purchase_rows.append(("3.1 / floor2 / A", lot["sku"],
                              " | ".join(r["part_id"] for r in related),
                              " | ".join(r["spec"] for r in related),
                              lot.get("neededQuantity", "see source"), lot.get("purchaseQuantity", "see source"),
                              lot.get("costJpy", "UNKNOWN"), reference["url_text"],
                              lot.get("checkedJst", "UNKNOWN"), lot.get("tax", "UNKNOWN"),
                              "historical source, not current stock; NOT an M3 conversion",
                              "UNKNOWN"))
    csv_write(DOC / "purchase-list-3.1-A.csv",
              ("revision", "sku", "part_ids", "specification", "needed", "historical_purchase_quantity",
               "historical_cost_jpy", "source_url", "original_check_date", "tax_basis", "status", "verified_on_hand"), purchase_rows)
    old_gears = float(old_parts["P_SYNC_DRIVE"]["unit_nominal_mass_g"]) * 2
    new_gears = parts["P_M3_GEAR42"]["nominalMassG"] * 2
    comparison = {
        "revisionId": REVISION, "baseCommit": BASE,
        "unchangedFull31A": {"printedTypes": sum(r["category"] == "printed" for r in old_bom),
                            "printedQuantity": sum(int(r["quantity"]) for r in old_bom if r["category"] == "printed"),
                            "boltsById": {r["part_id"]: int(r["quantity"]) for r in old_bom if "BOLT" in r["part_id"]},
                            "physicalQualification": "UNKNOWN"},
        "matchedFastenerComparison": {
            "scope": "two 42T drive clamps plus one free pivot only, NOT two whole machines",
            "oldBolts": {"M3x16": 2, "M2x16": 1}, "newBolts": {"M3x20": 3},
            "oldNutCount": 6, "newNutCount": 6, "oldWasherCount": 2, "newWasherCount": 6,
            "oldToolSizes": ["hex1.5", "hex2.5", "spanner4", "spanner5.5"],
            "newToolSizes": ["hex2.5", "spanner5.5"],
            "oldTwoGearPlasticMassG": old_gears, "newTwoGearPlasticMassG": new_gears,
            "twoGearPlasticMassDifferenceG": new_gears - old_gears,
            "massBasis": "same assumed 1.27 g/cm3 solid density; not slicer or measured masses",
        },
        "benchInstanceCount": len(assembly["instances"]),
        "trialPrintedTypes": 5, "trialPrintedQuantity": 6, "full32MachineQuantity": None,
        "full32MassAndBudget": None, "fastenerMinimumOrderJpyIfNoneOwned": 900,
        "excludedCosts": ["metal shaft stock/cutting", "tools", "filament", "shipping", "travel"],
        "tools": [
            {"name": "2.5mm hex key", "source": "https://www.sengoku.co.jp/mod/sgk_cart/detail.php?code=EEHD-6TMA",
             "checkedDate": CHECKED, "priceJpy": 110, "onHand": None},
            {"name": "5.5mm spanner; inspect 2mm-thick jaw/10mm width envelope", "source": None,
             "priceJpy": None, "onHand": None},
            {"name": "caliper; saw/file only if cutting spare metal stock", "source": None, "onHand": None},
        ],
    }
    write_json(DOC / "comparison.json", comparison)
    expected_categories = Counter(r["part_id"] for r in assembly["instances"])
    if any(expected_categories[pid] != row["quantity"] for pid, row in parts.items()):
        raise ValueError("Reported quantity differs from the native-instance contract")
    artifacts = {}
    for folder in (CAD, PRINT, DOC):
        for path in sorted(folder.rglob("*")):
            if path.is_file() and path.name != "files.json" and path.suffix not in {".FCBak", ".FCStd1"}:
                artifacts[str(path.relative_to(ROOT))] = sha(path)
    write_json(DOC / "files.json", artifacts)
    print(f"Reported 22 bench instances / 6 trial prints; historical A has {len(print_rows)} print definitions.")


if __name__ == "__main__":
    main()
