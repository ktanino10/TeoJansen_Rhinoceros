"""Numerical contract for the single common input cartridge, not the walkers."""

from decimal import Decimal
import hashlib
import itertools
import json
import math
from pathlib import Path

from beam import d_section, solve_beam, twist_bound

ROOT = Path(__file__).resolve().parents[2]
INPUT = Path(__file__).with_suffix(".json")
OUT = ROOT / "docs/ver3/common_input_r4"
CAD = ROOT / "FreeCAD/Ver.3/common_input_r4"
PRINT = ROOT / "STL/Ver.3/common_input_r4"


def load():
    return json.loads(INPUT.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n")


def stack_contract(cfg):
    l, a = cfg["layout"], cfg["acceptanceScenarios"]
    fixed_free = l["fixedFlangeShoulderMm"]-l["fixedHolderStartMm"]-l["bearingFlangeThicknessMm"]
    float_free = l["floatHolderEndMm"]-l["floatFlangePocketStartMm"]-l["bearingFlangeThicknessMm"]
    collar_gap = l["innerCollarBossFaceMm"]-l["outerCollarBossFaceMm"]-(
        l["bearingWidthMm"]+2*l["spacerLengthMm"])
    scenarios = []
    for dp, dt, df in itertools.product(a["fixedPocketDepthErrorMm"],
                                        a["flangeThicknessErrorMm"], a["floatingPocketLengthErrorMm"]):
        fixed_clearance = fixed_free+dp-dt-a["capCompressionAllowanceMm"]
        floating_travel = float_free+df-dt-a["capCompressionAllowanceMm"]
        shift_budget = (fixed_free+max(a["fixedPocketDepthErrorMm"])-min(a["flangeThicknessErrorMm"])
                        + max(a["collarGapTotalMm"])/2
                        + max(abs(x) for x in a["supportSpacingErrorMm"])
                        + a["additionalAxialThermalOrHousingDeflectionBudgetMm"])
        scenarios.append({"pocket_error_mm": dp, "flange_error_mm": dt, "floating_pocket_error_mm": df,
                          "fixed_outer_clearance_min_mm": fixed_clearance,
                          "floating_total_travel_min_mm": floating_travel,
                          "required_one_sided_float_budget_mm": shift_budget,
                          "one_sided_float_remaining_mm": floating_travel/2-shift_budget})
    if min(s["fixed_outer_clearance_min_mm"] for s in scenarios) <= 0:
        raise ValueError("Selected printed/purchased acceptance limits can clamp the fixed outer ring")
    if min(s["one_sided_float_remaining_mm"] for s in scenarios) < 0:
        raise ValueError("Floating travel cannot cover the declared acceptance stack")
    flange_engagement = l["flangeScrewLengthMm"]-l["flangeThicknessMm"]-l["washerThicknessMm"]
    fixed_projection = l["capsScrewLengthMm"]-(l["fixedHolderEndMm"]-l["fixedHolderStartMm"]
        + l["coverThicknessMm"]+2*l["washerThicknessMm"]+l["locknutEnvelopeHeightMm"])
    float_projection = l["capsScrewLengthMm"]-(l["floatHolderEndMm"]-l["floatHolderStartMm"]
        + l["coverThicknessMm"]+2*l["washerThicknessMm"]+l["locknutEnvelopeHeightMm"])
    if min(fixed_projection, float_projection) < a["minimumThreadProjectionMm"]:
        raise ValueError("A cap screw does not pass through the locking nut by one pitch")
    return {
        "fixed_outer_ring_axial_play_nominal_mm": fixed_free,
        "floating_outer_ring_total_travel_nominal_mm": float_free,
        "collar_inner_ring_stack_play_nominal_mm": collar_gap,
        "fixed_screw_projection_mm": fixed_projection,
        "floating_screw_projection_mm": float_projection,
        "hub_flange_thread_engagement_mm": flange_engagement,
        "hub_flange_remaining_to_back_face_mm": l["hubBodyWidthMm"]-flange_engagement,
        "scenarios": scenarios,
        "scope": "acceptance dimensions only; actual prints, bearing tolerance and tightening deflection not measured",
        "physicalPreloadStatus": "UNKNOWN",
    }


def cost(cfg, printed_mass_g, coupon_mass_g=0.0):
    total = Decimal(0)
    catalogue_mass = 0.0
    rows = []
    for p in cfg["parts"]:
        packs = math.ceil(p["quantity"]/p["pack"])
        subtotal = Decimal(str(p["packPriceUsd"]))*packs
        total += subtotal
        catalogue_mass += p["massG"]*p["quantity"]
        rows.append({**p, "purchasePacks": packs, "purchaseQuantity": packs*p["pack"],
                     "unusedPieces": packs*p["pack"]-p["quantity"], "subtotalUsd": float(subtotal)})
    return {
        "purchasedRows": rows, "purchasedMinimumLotUsd": float(total),
        "purchasedCatalogueMassG": catalogue_mass,
        "historicalFourSkuSubtotalUsd": cfg["procurement"]["historicalFourSkuSubtotalUsd"],
        "historicalFourSkuMassG": cfg["procurement"]["historicalFourSkuCatalogueMassG"],
        "printedSolidMassG": printed_mass_g,
        "couponSolidMassG": coupon_mass_g,
        "couponCostBasis": "one quantity0 fit coupon included in first-print material estimate, not in assembled mass",
        "wholeCartridgeNominalMassG": catalogue_mass+printed_mass_g,
        "jpyScenarios": [{"fxJpyPerUsd": fx, "purchasedSubsetJpy": float(total*fx),
                         "filamentPriceJpyPerKgAssumed": price,
                         "solidFilamentPlusWasteCostJpy": round(printed_mass_g/1000*price*cfg["materials"]["supportWasteFactorAssumption"], 2),
                         "firstPrintIncludingCouponAndWasteCostJpy": round((printed_mass_g+coupon_mass_g)/1000*price*cfg["materials"]["supportWasteFactorAssumption"], 2),
                         "materialSubtotalExShippingTaxFeesJpy": round(float(total*fx)+(printed_mass_g+coupon_mass_g)/1000*price*cfg["materials"]["supportWasteFactorAssumption"], 2)}
                        for fx in cfg["procurement"]["jpyPerUsdAssumptions"]
                        for price in cfg["materials"]["filamentPriceJpyPerKgAssumptions"]],
        "shippingJpy": None, "importTaxJpy": None, "paymentFeesJpy": None,
        "measuredMassG": None, "slicedMassG": None,
        "externalMountingFastenersIncluded": False,
    }


def mechanics(cfg):
    l, m, loadcase = cfg["layout"], cfg["materials"], cfg["loadScreen"]
    supports = [(l[k]+l["bearingWidthMm"]/2, "translation")
                for k in ("fixedBearingStartMm", "floatingBearingStartMm")]
    section = d_section(6, 0.5)
    result = solve_beam(l["shaftLengthMm"], m["steelElasticModulusMpa"], section,
                        [(loadcase["radialLoadXmm"], -loadcase["radialLoadN"])], supports)
    result.update({
        "source": loadcase["source"], "supportModel": "two radial simple supports; bearing rotations free",
        "supports": supports, "loadN": loadcase["radialLoadN"], "loadXmm": loadcase["radialLoadXmm"],
        "torsion": twist_bound(loadcase["appliedInputTorqueNmm"], supports[1][0]-supports[0][0],
                               m["steelShearModulusMpa"], section),
        "two_input_bearing_drag_nmm_sensitivity": [2*d for d in loadcase["bearingStartTorqueNmmEachSensitivity"]],
        "real_starting_resistance_nmm": None, "real_running_resistance_nmm": None,
        "complete_support_stiffness_status": "UNKNOWN; printed supports, fits and clamp forces require separate evidence",
    })
    return result
