"""Same-revision lists, comparison and native sections for the integrated A."""

import argparse
from collections import Counter
import csv
from html import escape
import json
from pathlib import Path
import re
import sys

import numpy as np

from build_m3_trial import ROOT, BASE, sha, write_json
from build_m3_a34 import DOC, CAD, REVISION
from purchase_reference import purchase_groups, retained_reference, retained_specification

SOURCES = {
    "H_M34_BOLT_M3_15": ("EEHD-6D5D", "Sengoku", "stainless; grade/finish UNKNOWN", "minimum10; then per piece", 33, "JPY per piece, tax included", "https://www.sengoku.co.jp/mod/sgk_cart/detail.php?code=EEHD-6D5D"),
    "H_M34_BOLT_M3_20": ("EEHD-6D5E", "Sengoku", "stainless; grade/finish UNKNOWN", "minimum10; then per piece", 33, "JPY per piece, tax included", "https://www.sengoku.co.jp/mod/sgk_cart/detail.php?code=EEHD-6D5E"),
    "H_M34_BOLT_M3_30": ("EEHD-6D5G", "Sengoku", "stainless; grade/finish UNKNOWN", "minimum10; then per piece", 44, "JPY per piece, tax included", "https://www.sengoku.co.jp/mod/sgk_cart/detail.php?code=EEHD-6D5G"),
    "H_M34_NUT_M3": ("114372", "Akizuki", "brass", "10 per pack", 120, "JPY per pack, tax included", "https://akizukidenshi.com/catalog/g/g114372/"),
    "H_M34_WASHER3": ("EEHD-6EC4 / BSW3mm", "Sengoku", "brass/nickel", "minimum10; then per piece", 25, "JPY per piece, tax included", "https://www.sengoku.co.jp/mod/sgk_cart/detail.php?code=EEHD-6EC4"),
    "H_M34_THRUST6": ("EEHD-6EC8 / BSW6mm", "Sengoku", "brass/nickel", "minimum10; then per piece", 25, "JPY per piece, tax included", "https://www.sengoku.co.jp/mod/sgk_cart/detail.php?code=EEHD-6EC8"),
    "H_M34_SLEEVE_8": ("EEHD-6CJF", "Sengoku", "brass", "4 per pack", 200, "JPY per pack, tax included", "https://www.sengoku.co.jp/mod/sgk_cart/detail.php?code=EEHD-6CJF"),
    "H_M34_SLEEVE_20": ("CE-320N", "Hirosugi; documented domestic-stock exception", "lead-free brass/nickel", "minimum50", 26, "JPY per piece, tax EXCLUDED", "https://hirosugi.co.jp/shop/g/gCE-301N/"),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freecad-lib", required=True)
    args = parser.parse_args()
    data = json.loads((DOC / "assembly.json").read_text())
    static = json.loads((DOC / "checks.json").read_text())
    motion = json.loads((DOC / "motion_check.json").read_text())
    floor = json.loads((DOC / "floor_check.json").read_text())
    drive = json.loads((DOC / "drive_comparison.json").read_text())
    access = json.loads((DOC / "access_check.json").read_text())
    if not (static["staticStatus"] == motion["status"] == floor["status"] == access["status"] == "PASS"
            and motion["complete"] and drive["control31Reproduced"]):
        raise ValueError("Integrated checks are not complete; do not generate a success-shaped release")
    counts = Counter(i["part_id"] for i in data["instances"])
    old = json.loads((ROOT / "docs/ver3/integrated_r7/A/assembly.json").read_text())
    old_lots = json.loads((ROOT / "docs/ver3/integrated_r7/A/purchase_lots.json").read_text())
    lots = {r["sku"]: r for r in old_lots["rows"]}
    sources = old["parameters"]["sources"] if "sources" in old["parameters"] else json.loads((ROOT/"scripts/ver3/walker_r7.json").read_text())["sources"]
    groups = purchase_groups(data["parts"])
    sys.path.insert(0, args.freecad_lib)
    import FreeCAD as App
    import Mesh
    sliced = {p["partId"]: p for p in json.loads((DOC / "slicing.json").read_text())["parts"]}
    with (DOC / "print-list.csv").open() as stream:
        reader = csv.DictReader(stream)
        fields, print_rows = list(reader.fieldnames), list(reader)
    extra = ("purpose", "support_plan", "nozzle_diameter_mm", "material_and_machine",
             "slicing_scope", "size_x_mm", "size_y_mm", "size_z_mm", "bed_fit")
    fields += [key for key in extra if key not in fields]
    for row in print_rows:
        pid = row["part_id"]
        box = Mesh.Mesh(str(ROOT / row["file"])).BoundBox
        row.update(purpose=data["parts"][pid]["spec"],
                   support_plan=("enabled in representative slice; remove and inspect" if sliced[pid]["supportEnabled"]
                                 else "disabled in representative slice; physical confirmation required") if pid in sliced
                                else "UNREVIEWED for0.2mm; inspect overhangs and the retained3.1 plan",
                   nozzle_diameter_mm="0.2",
                   material_and_machine="P1S / Generic PETG inspection assumptions; actual printer/material UNKNOWN",
                   slicing_scope="new3.4 representative inspection" if pid in sliced else "not newly sliced at0.2mm",
                   size_x_mm=f"{box.XLength:.3f}", size_y_mm=f"{box.YLength:.3f}", size_z_mm=f"{box.ZLength:.3f}",
                   bed_fit="UNKNOWN for user machine; dimensions exclude brim/support placement")
    with (DOC / "print-list.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(print_rows)
    with (DOC / "purchase-list.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("revision", "part_id", "category", "needed", "verified_on_hand", "additional_purchase_quantity",
                         "specification", "material", "sku", "shop", "sales_unit", "displayed_price",
                         "price_basis", "official_url", "checked_date", "stock_status", "qualification",
                         "purchase_group", "group_required_cad_parts", "shared_group_note",
                         "reference_group_order", "reference_lots", "reference_source"))
        for pid, part in data["parts"].items():
            if part["category"] == "printed":
                continue
            if pid in SOURCES:
                sku, shop, material, unit, price, basis, url = SOURCES[pid]
                date, stock = "2026-11-15", "listing checked; exact local/online quantity not reserved"
                specification = part["spec"]
                reference_order, reference_lots = "see sales unit; subtract verified on-hand", ""
                reference_source = url
            else:
                sku = part["sku"] or pid
                lot = lots.get(sku, {})
                if sku == "HEX5":
                    plan = old_lots["shaftStockOrder"]
                    lot = {**plan, "costJpy": plan["displayedPriceJpy"],
                           "purchaseQuantity": len(plan["orderedLengthsMm"]),
                           "purchaseQuantityUnit": "stock bars; ordered lengths and shared cut layout in reference_lots"}
                reference = retained_reference(lot, sources["checkedJst"] + " (catalog-level retained date)")
                shop = "unchanged3.1 source; current listing not refreshed"
                specification, material = retained_specification(pid, part, sources, old["parameters"]["common"])
                unit, price, basis = reference["sales_unit"], reference["price_text"], reference["price_basis"]
                url, date, stock = reference["url_text"], reference["checked_date"], "current stock UNKNOWN; retained reference only"
                reference_order, reference_lots = reference["reference_order_quantity"], reference["reference_lots"]
                reference_source = "docs/ver3/integrated_r7/A/purchase_lots.json @ " + BASE
            group_key = part["sku"] or pid
            shared_note = "Apply the group purchase/cut plan ONCE across its rows; do not multiply the quoted lot by the number of rows."
            if group_key == "HEX5":
                shared_note += " Retained plan: one500mm bar ->100/100/100/58mm pieces; not one stock bar per row."
            elif group_key == "PAC34-05":
                shared_note += " Retained plan: one300x450x0.5mm sheet ->three cut panels."
            writer.writerow((REVISION, pid, part["category"], counts[pid], "UNKNOWN", "UNKNOWN; subtract verified on-hand",
                             specification, material, sku, shop, unit, price, basis, url, date, stock,
                             "specification/quantity list, NOT a purchase authorization; actual fit and stock unqualified",
                             group_key, json.dumps(groups[group_key], separators=(",", ":")), shared_note,
                             reference_order, reference_lots, reference_source))

    def bolt_counts(assembly):
        result = Counter()
        for item in assembly["instances"]:
            match = re.search(r"BOLT_M(\d+)_(\d+)", item["part_id"])
            if match:
                result[f"M{match[1]}x{match[2]}"] += 1
        return dict(sorted(result.items()))

    old_bolts, new_bolts = bolt_counts(old), bolt_counts(data)
    summary = {
        "revisionId": REVISION, "publicVersion": "3.4", "source31Commit": BASE,
        "manufacturingRelease": False, "status": "INTEGRATED_DEVELOPMENT_NOT_PHYSICAL_RELEASE",
        "native": "FreeCAD/Ver.3/m3_a34/Walker_A_3_4.FCStd",
        "step": "FreeCAD/Ver.3/m3_a34/Walker_A_3_4.step",
        "instances": len(data["instances"]),
        "printedTypes": sum(p["category"] == "printed" for p in data["parts"].values()),
        "printedQuantity": sum(counts[pid] for pid, p in data["parts"].items() if p["category"] == "printed"),
        "changedPrintedQuantity": sum(counts[pid] for pid in data["m3Integration"]["changedParts"] if data["parts"][pid]["category"] == "printed"),
        "oldBoltCounts": old_bolts, "newBoltCounts": new_bolts,
        "oldM3BoltCount": sum(n for k, n in old_bolts.items() if k.startswith("M3")),
        "newM3BoltCount": sum(n for k, n in new_bolts.items() if k.startswith("M3")),
        "oldNominalMassG": old["nominalTotalMassG"], "newNominalMassG": data["nominalTotalMassG"],
        "wholeToolSetReduced": False,
        "toolNote": "14 modified locations use2.5mm hex/5.5mm spanner. Complete machine still needs legacy M2/M4 and rocker tools; do not claim whole-tool elimination.",
        "fullPurchaseCostJpy": None,
        "budgetNote": "Historical3.1 estimate and the900JPY bench fastener packs are NOT the whole3.4 budget. On-hand counts, retained-part prices, tax/shipping remain unconfirmed.",
        "retainedM2Reason": data["m3Integration"]["retainedM2"],
        "sourcingException": "Continuous20mm6-OD metal sleeve CE-320N, domestic maker MOQ50; avoid unsupported splices/cutting. Explained before adoption in DESIGN_ja.md.",
        "checks": {"static": "checks.json", "motion": "motion_check.json", "floor": "floor_check.json",
                   "drive": "work_budget.json", "comparison": "drive_comparison.json", "access": "access_check.json"},
        "sourceHashes": {str(p.relative_to(ROOT)): sha(p) for p in (Path(__file__), Path(__file__).with_name("purchase_reference.py"), DOC/"assembly.json",
                          DOC/"checks.json", DOC/"motion_check.json", DOC/"floor_check.json", DOC/"drive_comparison.json", DOC/"access_check.json")},
    }
    write_json(DOC / "summary.json", summary)

    sys.path.insert(0, args.freecad_lib)
    import FreeCAD as App
    import Part
    document = App.openDocument(str(CAD / "Walker_A_3_4.FCStd"))
    items = data["instances"]

    def draw(name, title, selected, clip, axes):
        groups, points = [], []
        for label, members in selected:
            shape = Part.makeCompound([document.getObject(i["name"]).Shape.copy() for i in members])
            shape = shape.common(clip)
            lines = []
            for edge in shape.Edges:
                row = [(tuple(v)[axes[0]], -tuple(v)[axes[1]]) for v in edge.discretize(Deflection=0.2)]
                points.extend(row)
                lines.append(row)
            if lines:
                groups.append((label, lines))
        if not points:
            raise ValueError("Empty native section")
        x0, y0 = (min(p[k] for p in points) for k in range(2))
        x1, y1 = (max(p[k] for p in points) for k in range(2))
        scale = min(820/max(1, x1-x0), 360/max(1, y1-y0))
        text = ['<svg xmlns="http://www.w3.org/2000/svg" width="960" height="600" viewBox="0 0 960 600">',
                '<rect width="960" height="600" fill="#fbfaf6"/>',
                f'<text x="24" y="30" font-size="18" font-family="sans-serif">{escape(title)}</text>',
                f'<text x="24" y="56" font-size="12" font-family="sans-serif">{REVISION} / actual native B-rep section / mm / physical fit UNKNOWN</text>']
        for index, (label, lines) in enumerate(groups):
            color = ("#17685d", "#94600e", "#315b94", "#983e45")[index % 4]
            for row in lines:
                xy = " ".join(f"{60+(x-x0)*scale:.2f},{85+(y-y0)*scale:.2f}" for x, y in row)
                text.append(f'<polyline points="{xy}" fill="none" stroke="{color}" stroke-width="1"/>')
            text.append(f'<text x="{24+460*(index%2)}" y="{480+22*(index//2)}" fill="{color}" font-size="12" font-family="sans-serif">{escape(label)}</text>')
        text.append("</svg>")
        (DOC / name).write_text("\n".join(text) + "\n")

    station = -84
    gear = next(i for i in items if i["part_id"] == "P_M34_SYNC_DRIVE" and i["transform"][1][3] == station)
    gear_hardware = [i for i in items if i["part_id"].startswith("H_M34")
                     and i["group"] == "synchronization" and i["motion"]["axisYz"][0] == station]
    draw("gear-section-3.4.svg", "Ver.3.4 / installed front gear clamp (section at Y=-78)", [
        ("P_M34_SYNC_DRIVE", [gear]),
        ("M3x20 head / two washers / captive and outer nuts", gear_hardware)],
         Part.makeBox(50, 20, 40, App.Vector(-15, -78, 50)), (0, 2))
    draw("gear-end-3.4.svg", "Ver.3.4 / actual keyed gear face and nut-slot opening", [
        ("P_M34_SYNC_DRIVE / bore clocked to existing5mm-AF shaft", [gear])],
         Part.makeBox(50, 60, 60, App.Vector(-15, -114, 40)), (1, 2))
    pin = [i for i in items if i["motion"].get("station") == -84 and i["motion"].get("side") == 1
           and i["motion"].get("node") == "A"]
    local = [i for i in items if i["name"] in ("P_CRANK_JOURNAL_1_180_001", "P_LEG_AB_R_001", "P_LEG_AC_R_001")]
    draw("pin-section-3.4.svg", "Ver.3.4 / actual A-root stack (section at Y=-93.75)", [
        ("M3 crank root / AB / AC", local),
        ("continuous20mm sleeve / M3x30 / washers / both nuts", pin)],
         Part.makeBox(45, 15, 20, App.Vector(40, -93.75, 60)), (0, 2))
    App.closeDocument(document.Name)
    write_json(DOC / "files.json", {str(p.relative_to(ROOT)): sha(p)
                                   for folder in (DOC, CAD, ROOT/"STL/Ver.3/m3_a34")
                                   for p in sorted(folder.rglob("*"))
                                   if p.is_file() and p.name != "files.json" and p.suffix not in {".FCBak", ".FCStd1"}})
    print("Reported integrated Ver.3.4 A", summary["instances"], "instances,", summary["printedQuantity"], "prints")


if __name__ == "__main__":
    main()
