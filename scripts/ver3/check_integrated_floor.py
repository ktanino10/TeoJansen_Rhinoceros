"""All non-contact native geometry against the existing dense/finite contact cases."""

import argparse
import hashlib
import json
from pathlib import Path

from analyze_integrated_walkers import analyze
from check_integrated_contact import check as contact_cases
from walker_floor import check as floor_check
from walker_geometry import OUT


def check(design,envelopes_path,scratch,output,nominal_only=False):
    envelopes=json.loads(envelopes_path.read_text())
    cases=[];worst_by_instance={}
    source_hashes={name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                   for name in ("walker_floor.py","check_integrated_floor.py","check_integrated_contact.py",
                                "analyze_integrated_walkers.py","walker_contact.py","walker_kinematics.py")}
    def receive(assembly,contact,errors,case_id):
        report=floor_check(assembly,envelopes,contact,errors,case_id)
        for row in report.pop("perInstance"):
            before=worst_by_instance.get(row["instance"])
            if before is None or before["minimumReservedClearanceMm"]>row["minimumReservedClearanceMm"]:
                worst_by_instance[row["instance"]]={**row,"caseId":case_id}
        cases.append(report)
        print("STAGE_END floor-case",design,case_id,report["status"],report["worst"],flush=True)
        save()
    def save():
        data={"designId":design,"revisionId":envelopes["revisionId"],"nativeSha256":envelopes["nativeSha256"],
              "mechanicalIdentity":envelopes["mechanicalIdentity"],
              "checkerSourcesSha256":source_hashes,
              "envelopesSha256":hashlib.sha256(envelopes_path.read_bytes()).hexdigest(),
              "status":"PASS" if cases and all(c["status"]=="PASS" for c in cases) else "FAIL",
              "caseCount":len(cases),"poseCount":sum(c["phaseCount"] for c in cases),
              "complete":len(cases)==(1 if nominal_only else 163),
              "allNonContactInstancesChecked":True,"cases":cases,
              "worstPerInstance":list(worst_by_instance.values()),
              "scope":"Canonical dense720 nominal phases plus existing162 support scenarios across180 phases each. Native-containing envelopes cover every non-contact part and each rocker core across its continuous +/-5-degree stop range. Only the defined rolling-pad volumes are contact geometry. Not continuous crank-angle or physical-floor certification.",
              "physicalTestsPerformed":False}
        output.write_text(json.dumps(data,indent=2)+"\n")
    analyze(design,output_dir=scratch,contact_sink=lambda a,gait,contact,result:receive(a,contact,{},"nominal_dense"))
    if not nominal_only:
        reference=OUT/design/"work_budget.json"
        if json.loads(reference.read_text())["revisionId"]!=envelopes["revisionId"]:
            raise ValueError("Refresh the canonical work budget before support/floor scenarios")
        result=contact_cases(design,output=scratch/"contact_sensitivity.json",case_sink=receive)
        if result["passed"]!=result["total"]:
            raise ValueError("Existing support scenario failed; floor results cannot be qualified independently")
    save()
    if len(cases)!=(1 if nominal_only else 163):raise ValueError("Incomplete floor-case inventory")
    if any(case["status"]!="PASS" for case in cases):
        raise ValueError("Unresolved non-contact floor clearance; explicit case/part failures saved")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design",choices=("A","B","C"),required=True)
    parser.add_argument("--envelopes",type=Path,required=True)
    parser.add_argument("--scratch",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--nominal-only",action="store_true")
    args=parser.parse_args()
    check(args.design,args.envelopes,args.scratch,args.output,args.nominal_only)
