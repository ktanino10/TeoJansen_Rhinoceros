"""Read retained purchase evidence without inventing fresh quotes or stock."""

from collections import defaultdict
import json
import re


def retained_reference(row, fallback_date="UNKNOWN"):
    children = row.get("lots", [])
    if not isinstance(children, list) or any(not isinstance(item, dict) for item in children):
        raise ValueError("Expected a list of retained purchase lots")
    urls, units, prices = [], [], []
    for item in (row, *children):
        for key in ("source", "url"):
            value = item.get(key)
            if isinstance(value, str) and value.startswith("https://") and value not in urls:
                urls.append(value)
        if "packSize" in item:
            units.append(f"{item['packSize']} pieces/pack")
        if "minimumOrder" in item:
            units.append(f"minimum order {item['minimumOrder']}")
        for key, unit in (
            ("packPriceTaxIncludedJpy", "JPY/pack, tax included"),
            ("packPriceJpy", "JPY/pack, tax basis in source"),
            ("packPriceUsd", "USD/pack"),
            ("packPrice", "per pack, currency as recorded"),
            ("unitExTaxJpy", "JPY/piece, tax excluded"),
            ("unitPriceJpy", "JPY/piece, tax basis in source"),
            ("unitPriceTaxIncludedJpy", "JPY/piece, tax included"),
        ):
            if key in item:
                prices.append(f"{item[key]} {unit}")
    if not units and "purchasePacks" in row and row.get("purchasePacks"):
        units.append(f"{row['purchaseQuantity']} pieces in {row['purchasePacks']} reference packs")
    if not units and row.get("purchaseQuantityUnit"):
        units.append(row["purchaseQuantityUnit"])
    return {
        "urls": urls,
        "url_text": " ; ".join(urls) or "UNKNOWN",
        "sales_unit": " ; ".join(dict.fromkeys(units)) or "see reference group order quantity",
        "price_text": " ; ".join(dict.fromkeys(prices)) or str(row.get("costJpy", "UNKNOWN")),
        "price_basis": "historical seller unit/pack quote, NOT refreshed" if prices else "historical shared-group total JPY, NOT a unit price",
        "checked_date": row.get("checkedJst", fallback_date),
        "reference_lots": json.dumps(children or [row], ensure_ascii=False, separators=(",", ":")),
        "reference_order_quantity": row.get("purchaseQuantity", "UNKNOWN"),
    }


def purchase_groups(parts):
    groups = defaultdict(dict)
    for pid, part in parts.items():
        if part["category"] != "printed":
            groups[part.get("sku") or pid][pid] = part["quantity"]
    return dict(groups)


def retained_specification(pid, part, sources, common):
    """Nominal sizes come from frozen 3.1 CAD, not a new supplier certificate."""
    sku = part.get("sku") or pid
    nominal_steel = "steel density assumed in original CAD; actual grade/finish not recorded"
    match = re.fullmatch(r"BOLT_M([234])_(\d+)", sku)
    if match:
        diameter, length = int(match[1]), int(match[2])
        pitch = {2: 0.4, 3: 0.5, 4: 0.7}[diameter]
        key = {2: 1.5, 3: 2.5, 4: 3}[diameter]
        return f"M{diameter}x{length} socket-head screw; nominal pitch{pitch}mm; hex key{key}mm (3.1 CAD)", nominal_steel
    match = re.fullmatch(r"NUT_M([234])", sku)
    if match:
        size = int(match[1])
        af, height, pitch = {2: (4, 1.6, 0.4), 3: (5.5, 2.4, 0.5), 4: (7, 3.2, 0.7)}[size]
        return f"M{size}x{pitch} hex nut; AF{af}xheight{height}mm (3.1 CAD nominal)", nominal_steel
    washers = {"WASHER_M2": (2.2, 5, 0.3), "WASHER_M3": (3.2, 7, 0.5),
               "THRUST4": (4.3, 9, 0.8), "THRUST4_SMALL": (4.3, 8, 0.5), "THRUST6": (6.4, 11.5, 0.8)}
    if sku in washers:
        inner, outer, thickness = washers[sku]
        return f"Flat/thrust washer ID{inner} x OD{outer} x thickness{thickness}mm (3.1 CAD nominal)", nominal_steel
    for sleeve in sources["sleeves"]["items"]:
        if sku == sleeve["sku"]:
            return (f"{sku}: smooth sleeve OD{sleeve['odMm']} x ID{sleeve['idMm']} x length{sleeve['lengthMm']}mm",
                    sources["sleeves"]["material"])
    if sku == "HEX5":
        length = re.search(r"HEX(\d+)$", pid)[1]
        return f"5mm-AF C3604B brass hex bar; finished length{length}mm; shared stock cut plan, no end tapping", "C3604B brass"
    if sku == sources["bearing"]["sku"]:
        return part["spec"], sources["bearing"]["ringMaterial"] + " (retained source)"
    if sku == sources["coilSpring"]["sku"]:
        return part["spec"], sources["coilSpring"]["material"] + " (retained source)"
    if sku == "PAC34-05":
        guard = common["guards"]
        width, length = guard["petSheetDimensionsMm"]
        return f"{part['spec']} Shared stock {width}x{length}x{guard['petThicknessMm']}mm; this row counts cut pieces, not sheets.", "PET"
    return part["spec"], "not stated in retained dimensional record; see source listing"
