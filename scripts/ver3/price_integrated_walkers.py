"""Exact represented-BOM quantities and minimum purchase lots; no ordering."""

from collections import Counter
import argparse
import itertools
import json
import math
from pathlib import Path
import re

from walker_geometry import ROOT,OUT

BASE="https://www.nejinejikun.com/products/detail/"
DOMESTIC={
    "BOLT_M2_16":[(10,330,371466),(100,1430,371467)],
    "BOLT_M2_12":[(10,330,371457),(100,1001,371458)],
    "LOCK_NUT_M2":[(10,440,342110),(100,2530,342111)],
    "BOLT_M2_20":[(10,440,371472),(100,1870,371473)],
    "BOLT_M2_25":[(10,440,371478),(100,3080,371479)],
    "BOLT_M2_30":[(10,484,371481),(100,4510,371482)],
    "BOLT_M3_12":[(10,330,285460),(100,550,285461)],
    "BOLT_M3_16":[(10,330,285469),(100,550,285470)],
    "BOLT_M3_20":[(10,330,285475),(100,561,285476)],
    "BOLT_M4_12":[(10,330,285559),(100,550,285560)],
    "NUT_M2":[(100,440,361365)],"NUT_M3":[(100,440,361377)],
    "WASHER_M2":[(100,330,202153)],"WASHER_M3":[(100,330,202174)],
    "THRUST4":[(100,330,202180)],"THRUST6":[(100,330,94380)],
    "THRUST4_SMALL":[(100,330,94368)]
}


def best_lots(quantity,options):
    best=None
    for count in itertools.product(*(range(math.ceil(quantity/p)+1) for p,_,_ in options)):
        bought=sum(n*o[0] for n,o in zip(count,options))
        if bought<quantity:continue
        cost=sum(n*o[1] for n,o in zip(count,options))
        if best is None or (cost,bought)<(best["costJpy"],best["purchaseQuantity"]):
            best={"costJpy":cost,"purchaseQuantity":bought,"unused":bought-quantity,
                  "lots":[{"packs":n,"packSize":p,"packPriceTaxIncludedJpy":price,"url":BASE+str(code)}
                          for n,(p,price,code) in zip(count,options) if n]}
    if best is None:raise ValueError("No purchase lot covers the required quantity")
    return best


def shaft_order(pieces):
    choices=[(100,280),(200,400),(300,520),(500,760),(1000,1370)]
    best=None
    for counts in itertools.product(range(5),repeat=len(choices)):
        if not any(counts):continue
        price=sum(n*x[1] for n,x in zip(counts,choices))
        if best and price>=best["displayedPriceJpy"]:continue
        ordered=sorted([length for n,(length,_) in zip(counts,choices) for _ in range(n)],reverse=True)
        lengths=[length-2 for length in ordered]
        if sum(lengths)<sum(x+2 for x in pieces):continue
        layout=[[] for _ in lengths]
        def pack(i):
            if i==len(pieces):return True
            tried=set()
            for j,free in enumerate(lengths):
                if free in tried or free<pieces[i]+2:continue
                tried.add(free);lengths[j]-=pieces[i]+2;layout[j].append(pieces[i])
                if pack(i+1):return True
                layout[j].pop();lengths[j]+=pieces[i]+2
            return False
        if not pack(0):continue
        best={"displayedPriceJpy":price,"taxUnclearReserveJpy":math.ceil(price*.1),
              "orderedLengthsMm":ordered,
              "cutLayoutMm":layout,"remainingAfterKerfsMm":lengths,"kerfPerPieceMm":2,
              "stockNegativeLengthAllowanceMm":2,
              "source":"https://www.yokoyama-techno.net/detail/596.html"}
    if best is None:raise ValueError("No bounded stock-bar order fits all real shaft lengths")
    return best


def sheet_order(blanks,sheet=(300,450),edge=2,kerf=2):
    rectangles=sorted([(row["partId"],math.ceil(row["widthMm"])+kerf,
                        math.ceil(row["heightMm"])+kerf) for row in blanks],
                       key=lambda x:-x[1]*x[2])
    width,height=sheet[0]-2*edge,sheet[1]-2*edge
    for count in range(1,len(rectangles)+1):
        boards=[[] for _ in range(count)]
        def place(index):
            if index==len(rectangles):return True
            name,w,h=rectangles[index]
            for board in boards:
                for rw,rh in dict.fromkeys(((w,h),(h,w))):
                    xs=sorted({0,*[x["x"]+x["w"] for x in board]})
                    ys=sorted({0,*[x["y"]+x["h"] for x in board]})
                    for y in ys:
                        for x in xs:
                            if x+rw>width or y+rh>height:continue
                            if any(x<b["x"]+b["w"] and x+rw>b["x"] and y<b["y"]+b["h"] and y+rh>b["y"] for b in board):continue
                            board.append({"partId":name,"x":x,"y":y,"w":rw,"h":rh})
                            if place(index+1):return True
                            board.pop()
                if not board:break
            return False
        if place(0):
            return {"sheetCount":count,"stockMm":list(sheet),"edgeMarginMm":edge,"kerfAllowanceMm":kerf,
                    "layouts":boards,"method":"bounded rectangle blank nesting with rotation; hole scraps are not recovered as structural sheet"}
    raise ValueError("A guard blank does not fit the quoted sheet")


def price(designs,fx=160,filament=3000):
    quantities=Counter();pieces=[];printed=0.;masses={};blanks=[];guard_status=[]
    requirements=json.loads((ROOT/"scripts/ver3/walker_r7.json").read_text())["requirements"]
    budget=requirements["materialBudgetJpy"]*len(designs)
    for design in designs:
        data=json.loads((OUT/design/"assembly.json").read_text())
        count=Counter(i["part_id"] for i in data["instances"])
        printed+=data["nominalPrintedMassG"]
        masses[design]=data["nominalTotalMassG"]
        blanks.extend({**row,"partId":design+"_"+row["partId"]} for row in data.get("guardSheetBlanks",[]))
        guard_status.append(bool(data.get("guardSheetBlanks")) and "P_ROTOR_CAGE_CAP" in data["parts"])
        for pid,part in data["parts"].items():
            sku=part.get("sku")
            if sku:quantities[sku]+=count[pid]
            if sku=="HEX5":
                length=int(re.search(r"HEX(\d+)$",pid).group(1))
                pieces += [length]*count[pid]
    imports={p["sku"]:p for p in json.loads((ROOT/"scripts/ver3/input_cartridge.json").read_text())["parts"]}
    imports["2101-0006-0140"]={**imports["2101-0006-0120"],"packPriceUsd":5.09,
         "url":"https://www.gobilda.com/2101-series-stainless-steel-d-shaft-6mm-diameter-140mm-length/"}
    imports["BOLT_M4_20"]=imports["2800-0004-0020"]
    rows=[];total=0.;import_base=0.;unclear_tax=0.
    for sku,quantity in sorted(quantities.items()):
        row={"sku":sku,"neededQuantity":quantity,"checkedJst":"2026-09-27"}
        if sku in ("HEX5","PAC34-05"):continue
        if sku in DOMESTIC:
            row.update(best_lots(quantity,DOMESTIC[sku]));row["tax"]="included"
            if sku in ("BOLT_M2_12","LOCK_NUT_M2"):row["checkedJst"]="2026-09-28"
            if sku=="THRUST4_SMALL":
                row["checkedJst"]="2026-09-28"
                row["nominalDimensionsMm"]={"inner":4.5,"outer":8,"thickness":.5}
                row["dimensionSource"]="https://www.nejinejikun.com/html/upload/save_image/kikaku_data/a4010100000000_d.gif"
        elif sku in imports:
            p=imports[sku];packs=math.ceil(quantity/p["pack"]);cost=packs*p["packPriceUsd"]*fx
            row.update({"costJpy":cost,"purchaseQuantity":packs*p["pack"],"unused":packs*p["pack"]-quantity,
                        "packPriceUsd":p["packPriceUsd"],"purchasePacks":packs,"fxAssumed":fx,"source":p["url"],
                        "tax":"Japanese import tax and shipping not quoted"})
            import_base+=cost
        elif sku=="DDL-1680HH":
            row.update({"costJpy":220*quantity,"purchaseQuantity":quantity,"unused":0,"tax":"included",
                        "source":"https://e-seki.net/products/detail1750.html","availability":"page1-2days,not reserved"})
        elif sku.startswith("CE-"):
            prices={"CE-308N":19,"CE-2008N":22,"CE-2012N":24,"CE-2015N":26,"CE-2018N":30,"CE-2020N":31}
            if sku not in prices:raise ValueError("Unverified sleeve price: "+sku)
            bought=50*math.ceil(quantity/50)
            row.update({"costJpy":bought*prices[sku]*1.1,"purchaseQuantity":bought,"unused":bought-quantity,
                        "unitExTaxJpy":prices[sku],"tax":"10% added to posted unit price",
                        "source":"https://hirosugi.co.jp/shop/g/gCE-301N/",
                        "minimumOrder":50,"purchaseMultiple":"conservative whole50-piece multiples; no fractional purchase"})
        elif sku=="12-0721":
            bands=[(1,180),(5,140),(10,85),(20,56),(50,36),(100,33)]
            candidates=[]
            for q in {quantity,*[n for n,_ in bands if n>=quantity]}:
                unit=max((x for x in bands if x[0]<=q),key=lambda x:x[0])[1]
                candidates.append((q*unit,q,unit))
            cost,bought,unit=min(candidates)
            reserve=math.ceil(cost*.1)
            row.update({"costJpy":cost+reserve,"displayedCostJpy":cost,"taxUnclearReserveJpy":reserve,
                        "purchaseQuantity":bought,"unused":bought-quantity,"unitPriceJpy":unit,
                        "tax":"displayed row does not state treatment;10%reserve,not claimed tax charge",
                        "source":"https://www.spring-net.com/search/?q=12-0721"})
            unclear_tax+=reserve
        else:raise ValueError("No verified price for actual BOM item: "+sku)
        total+=row["costJpy"];rows.append(row)
    shaft=shaft_order(sorted(pieces,reverse=True))
    total+=shaft["displayedPriceJpy"]+shaft["taxUnclearReserveJpy"]
    unclear_tax+=shaft["taxUnclearReserveJpy"]
    sheet=None
    if blanks:
        sheet=sheet_order(blanks)
        cost=sheet["sheetCount"]*680
        rows.append({"sku":"PAC34-05","neededQuantity":len(blanks),"neededQuantityUnit":"cut blanks; some produce multiple mounted pieces",
                     "installedPanelQuantity":quantities["PAC34-05"],
                     "purchaseQuantity":sheet["sheetCount"],"purchaseQuantityUnit":"300x450x0.5mm sheets",
                     "costJpy":cost,"tax":"included","source":"https://www.dcm-ekurashi.com/goods/217260",
                     "sheetNesting":sheet})
        total+=cost
    accessory_path=OUT/"common"/"accessories.json"
    accessories=json.loads(accessory_path.read_text()) if accessory_path.exists() else None
    accessory_mass=accessories["totalFirstBuildPrintedMassG"] if accessories else 0
    printing=(printed+accessory_mass)/1000*filament*1.2
    import_reserve=import_base*.1
    result={"designs":designs,"cadNominalMassG":masses,"rows":rows,"shaftStockOrder":shaft,
            "purchasedSubtotalJpy":round(total,2),"printedSolidMassG":printed,
            "firstBuildAccessoryMassG":accessory_mass,
            "commonAccessoriesSetsPurchased":1 if accessories else 0,
            "firstBuildAccessoriesIncluded":accessories is not None,
            "filamentJpyKgAssumed":filament,"printWasteFactorAssumed":1.2,
            "printedMaterialEstimateJpy":round(printing,2),
            "representedBomSubtotalJpy":round(total+printing,2),
            "optionalImportTaxReserve10PercentJpy":round(import_reserve,2),
            "representedBomWithImportReserveJpy":round(total+printing+import_reserve,2),
            "includedUnclearDomesticTaxReserveJpy":unclear_tax,
            "shippingJpy":None,"paymentFeesJpy":None,
            "guardsAndFitCouponsFullyIncluded":all(guard_status) and accessories is not None,
            "sourceDisplayedPlusMaterialWithoutUncertainTaxReservesJpy":round(total+printing-unclear_tax,2),
            "completeMachineBudgetStatus":"UNKNOWN",
            "targetMaterialCostApproxJpy":budget,
            "approvedBudgetDateJst":requirements.get("budgetApprovalDateJst"),
            "representedCostDifferenceFromTargetJpy":round(total+printing-unclear_tax-budget,2),
            "approvedReferenceBudgetCeilingJpy":budget,
            "note":"Quoted minimum purchase lots,real cut-sheet blanks,cage and first-build coupons/cradles are counted when present. A complete bill is not safety,material,airflow or budget approval. Single-build and joint-order lots remain distinct."}
    if result["guardsAndFitCouponsFullyIncluded"]:
        result["completeMachineBudgetStatus"]=("CONDITIONAL_WITHIN_APPROVED_BUDGET"
            if result["sourceDisplayedPlusMaterialWithoutUncertainTaxReservesJpy"]<=budget
            else "ABOVE_APPROVED_REFERENCE_BUDGET")
    result["budgetCondition"]=f"Reference FX{fx:g}JPY/USD and1.2x solid+accessory print material; no measured slice cost. Shipping and unquoted tax/fees excluded from the approved comparison."
    for waste_factor in (1.,1.2,1.5):
        result.setdefault("printMaterialSensitivity",[]).append(
            {"solidPlusAccessoriesMassG":printed+accessory_mass,"materialFactor":waste_factor,
             "partsAndMaterialWithoutUncertainTaxReservesJpy":round(total-unclear_tax+(printed+accessory_mass)/1000*filament*waste_factor,2),
             "notSlicerMeasured":True})
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--designs",nargs="+",required=True)
    args=parser.parse_args()
    result=price(args.designs)
    folder=OUT/args.designs[0] if len(args.designs)==1 else OUT
    file=folder/"purchase_lots.json"
    file.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:result[k] for k in ("designs","purchasedSubtotalJpy","printedMaterialEstimateJpy",
                                          "representedBomSubtotalJpy","representedBomWithImportReserveJpy","completeMachineBudgetStatus")}))
