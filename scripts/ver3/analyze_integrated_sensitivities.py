"""Finite common wind and rotor-imbalance sensitivities; no coefficient fitting."""

import argparse
import contextlib
import io
import hashlib
import json
from pathlib import Path
import tempfile

from analyze_integrated_walkers import analyze
from walker_geometry import OUT
from walker_floor import check as check_floor


def main(design,workdir):
    data=json.loads((OUT/design/"assembly.json").read_text())
    reference=json.loads((OUT/design/"work_budget.json").read_text())
    envelopes=json.loads((OUT/design/"floor_envelopes.json").read_text())
    if data["revisionId"]!=reference["revisionId"]:raise ValueError("Sensitivity input revisions differ")
    environments=[
        {"id":"speed80percent","peakMS":5.12,"sigmaMm":20,"aimShiftMm":0},
        {"id":"speed120percent","peakMS":7.68,"sigmaMm":20,"aimShiftMm":0},
        {"id":"narrowJet","peakMS":6.4,"sigmaMm":15,"aimShiftMm":0},
        {"id":"wideJet","peakMS":6.4,"sigmaMm":25,"aimShiftMm":0},
        {"id":"aim10mmInward","peakMS":6.4,"sigmaMm":20,"aimShiftMm":-10},
        {"id":"aim10mmOutward","peakMS":6.4,"sigmaMm":20,"aimShiftMm":10},
    ]
    rows=[]
    with tempfile.TemporaryDirectory(prefix=f"r7-{design}-air-",dir=workdir) as temporary:
        for case in environments:
            floor_results=[]
            def capture(assembly,gait,contact,result):
                floor=check_floor(assembly,envelopes,contact,{},case["id"])
                floor.pop("perInstance")
                floor_results.append(floor)
            with contextlib.redirect_stdout(io.StringIO()):
                result=analyze(design,.5,output_dir=temporary,air_case=case,contact_sink=capture)
            if len(floor_results)!=1:raise ValueError("Missing wind-case floor result")
            rows.append({"airCase":case,"wholeJetPowerW":result["proxy"]["whole_jet_kinetic_power_w"],
                         "supportWindEnvelope":result["supportWindEnvelope"],
                         "nominalSupport":result["contact"]["support_and_compliance_pass"],
                         "nonContactFloor":floor_results[0],
                         "cases":[{key:item[key] for key in (
                             "case","rawSupplyMinimumNm","requiredInputMaximumNm","rawPhaseMinimumMarginNm",
                             "rawEnvelopeMarginNm","halfProxyPhaseMinimumMarginNm","downstream2xPhaseMinimumMarginNm",
                             "maximumInputBearingPairForRawBalanceNm","rawReferenceBudgetStatus")}
                                  for item in result["cases"]]})
            print(design,case["id"],rows[-1]["cases"][1]["rawPhaseMinimumMarginNm"]*1000,"mNm",flush=True)
    rotor_mass=data["parts"]["P_ROTOR"]["mass_g"]/1000
    imbalance=[]
    for eccentricity in (0,.05,.1,.25):
        amplitude=rotor_mass*9.80665*eccentricity/1000
        imbalance.append({"rotorComOffsetMm":eccentricity,"worstStaticGravityAmplitudeNm":amplitude,
                          "cases":[{"case":row["case"],"minimumMarginWithAdverseOrientationNm":row["rawPhaseMinimumMarginNm"]-amplitude}
                                   for row in reference["cases"]]})
    result={"revisionId":data["revisionId"],"designId":design,"windCases":rows,"staticRotorImbalance":imbalance,
            "mechanicalInputSha256":reference["mechanicalInputSha256"],
            "nativeFloorEnvelopesSha256":hashlib.sha256((OUT/design/"floor_envelopes.json").read_bytes()).hexdigest(),
            "measuredAirOrResistance":False,
            "limits":["The same six sensitivity inputs are applied to every design,not optimized per candidate.",
                      "Wind support force,COM/contact solution,slip work and demand are recomputed with each jet,not only available torque scaled.",
                      "Gaussian width,20% speed and10mm aim bounds are design sensitivities,not measured product tolerances or confidence intervals.",
                      "Rotor eccentricity is a static adverse-orientation bound using actual nominal rotor mass; centrifugal loads and running dynamics remain uncalculated.",
                      "Nominal collar clocking is not a claim that a printed rotor has zero real eccentricity.",
                      "Arbitrary factor0.5 and2x-downstream design margins remain separate from raw proxy results."]}
    (OUT/design/"environment_sensitivity.json").write_text(json.dumps(result,indent=2)+"\n")
    if any(row["nonContactFloor"]["status"]!="PASS" for row in rows):
        raise ValueError("A declared wind case has unresolved non-contact floor clearance")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design",required=True,choices=("A","B","C"))
    parser.add_argument("--workdir",type=Path,required=True)
    args=parser.parse_args();main(args.design,args.workdir)
