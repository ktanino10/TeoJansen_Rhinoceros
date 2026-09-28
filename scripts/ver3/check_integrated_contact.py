"""Finite dimensional-clearance, support and spring-guide sensitivity cases."""

import argparse
import json
import math
from pathlib import Path

import numpy as np

from walker_contact import ContactGait,dimensions,error_cases,functional_swing_budget
from walker_geometry import OUT


def check(design,step_deg=2,output=None,case_sink=None):
    a=json.loads((OUT/design/"assembly.json").read_text())
    c=a["parameters"]["common"];mass=a["nominalTotalMassG"]/1000
    work=json.loads((OUT/design/"work_budget.json").read_text())
    if work["revisionId"]!=a["revisionId"]:raise ValueError("Regenerate work/COM data for the current CAD before contact checks")
    momentum=1.225*6.4**2*math.pi*.02**2
    normal=mass*9.80665+momentum
    gait=ContactGait(c,dimensions("reference"),step_deg)
    reference=np.array(work["effectiveSupportCopTrajectoryMm"])
    source_angles=np.arange(len(reference))*2*math.pi/len(reference)
    effective=np.column_stack([np.interp(gait.angles,np.r_[source_angles,2*math.pi],
                                       np.r_[reference[:,i],reference[0,i]]) for i in (0,1)])
    couple=math.ceil(max(row["requiredInputMaximumNm"] for row in work["cases"])*1000)
    cases=[]
    for entry in error_cases(c):
        for mode,sign in ((mode,sign) for mode in (-1,0,1) for sign in (-1,1)):
            with_couple=effective.copy();with_couple[:,1]+=sign*couple/normal
            try:
                result=gait.evaluate(mass+momentum/9.80665,cog_xy=with_couple,errors=entry["errors"],
                                     guide_mode=mode,external_planar_load=(0,2*momentum,56*momentum))
            except ValueError as error:
                cases.append({"id":entry["id"],"guideMode":mode,"inputCoupleSign":sign,"status":"FAIL","reason":str(error)})
                continue
            if case_sink is not None:
                case_sink(a,result,entry["errors"],f'{entry["id"]}/guide={mode}/couple={sign}')
            selected={k:result[k] for k in (
                "minimum_loaded_feet","minimum_support_margin_mm","maximum_body_tilt_deg",
                "maximum_guide_compression_mm","maximum_spring_force_n",
                "maximum_required_rocker_angle_deg","minimum_of_each_foot_maximum_swing_gap_mm",
                "maximum_predicted_loaded_episode_slip_mm","advance_per_cycle_mm",
                "support_and_compliance_pass","tangential_force_moment_residual_normalized_max")}
            swing_budget=functional_swing_budget(c)
            functional=(result["support_and_compliance_pass"]
                        and result["maximum_required_rocker_angle_deg"]<=c["foot"]["rockerTravelDeg"]
                        and result["minimum_of_each_foot_maximum_swing_gap_mm"]>swing_budget
                        and abs(result["advance_per_cycle_mm"])>2*c["errors"]["floorHeightErrorMm"])
            cases.append({"id":entry["id"],"guideMode":mode,"inputCoupleSign":sign,"status":"PASS" if functional else "FAIL",
                          "functionalSwingClearanceBudgetMm":swing_budget,**selected})
    failures=[x for x in cases if x["status"]!="PASS"]
    result={"designId":design,"revisionId":a["revisionId"],"cadMassKg":mass,
            "crankStepDeg":step_deg,"cases":cases,"passed":len(cases)-len(failures),"total":len(cases),
            "inputTorqueCoupleEnvelopeNmm":couple,
            "supportFunctionalStatus":"FAIL" if failures else "PASS",
            "legacy3mmSlideTargetStatus":"FAIL" if any(x.get("maximum_predicted_loaded_episode_slip_mm",0)>3 for x in cases) else "PASS",
            "limits":["Finite seeded assemblies plus two declared adverse patterns,not an interval proof.",
                      "Each effective link pitch includes print pitch +/-0.1mm plus two pin radial clearances of0.1mm. Constant realizations bound dimensions,not a solved load-dependent backlash trajectory.",
                      "Support polygon and loaded-foot count use the same2% normal-load criterion.",
                      "Angle-indexed nominal CAD COM/pose is used,with both signs of a rounded envelope of the calculated input torque in addition to the stated3mm COM error budget.",
                      "Pure guide compression/recovery friction envelopes at the high assumed friction are separate from the reference-work losses; spring energy is not charged twice.",
                      "Swing gap is already in world coordinates after spring-induced body settling. Only0.6mm future floor and0.3mm additional geometry clearance are reserved; loaded compression is not deducted again.",
                      "Three millimetres of slide and8mm swing are legacy designer targets,not user constraints. Slide work is retained even if functional support passes.",
                      "No measured floor,friction,print tolerance or30cm travel qualification."]}
    file=Path(output) if output else OUT/design/"contact_sensitivity.json"
    file.write_text(json.dumps(result,indent=2)+"\n")
    print(design,result["supportFunctionalStatus"],result["passed"],"/",len(cases),
          "failures",[(x["id"],x["guideMode"],x.get("minimum_loaded_feet"),x.get("maximum_guide_compression_mm"),x.get("reason")) for x in failures[:5]],flush=True)
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design",required=True);parser.add_argument("--step-deg",type=float,default=2)
    parser.add_argument("--output")
    options=parser.parse_args();check(options.design,options.step_deg,options.output)
