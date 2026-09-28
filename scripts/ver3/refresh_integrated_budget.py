"""Rebind the approved budget without rerunning or relabeling physical analysis."""

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import subprocess

from price_integrated_walkers import price
from walker_floor import identity
from walker_geometry import ROOT,OUT

BASELINE="e82a9d981388631b26b04ba90294c32992674f23"
PROOF="docs/ver3/integrated_r7/budget_metadata_update.json"
BUDGET_KEYS={"materialBudgetJpy","budgetApproval"}
PRICE_KEYS={"targetMaterialCostApproxJpy","approvedReferenceBudgetCeilingJpy",
            "representedCostDifferenceFromTargetJpy","completeMachineBudgetStatus"}
METADATA_SOURCES={"scripts/ver3/walker_r7.json","scripts/ver3/build_integrated_contract.py",
                  "scripts/ver3/report_integrated_walkers.py","scripts/ver3/verify_integrated_package.py"}


def encoded(value):
    return (json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode()


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def prior(relative):
    return subprocess.check_output(["git","show",BASELINE+":"+relative],cwd=ROOT)


def assert_only_changed(before,after,allowed):
    changed={key for key in before.keys()|after.keys() if before.get(key)!=after.get(key)}
    if not changed<=allowed:
        raise ValueError("Unexpected non-budget change: "+", ".join(sorted(changed-allowed)))


def rebind_assembly(before,requirements):
    old=before["parameters"]["requirements"]
    assert_only_changed(old,requirements,BUDGET_KEYS)
    if old["materialBudgetJpy"]!=23000 or requirements["materialBudgetJpy"]!=24000:
        raise ValueError("Expected the explicitly approved23000-to24000 budget transition")
    after=deepcopy(before)
    after["parameters"]["requirements"]=deepcopy(requirements)
    after["budgetMetadataUpdate"]=PROOF
    return after


def expected_update(source_commit):
    from build_integrated_contract import source_identity

    if not re.fullmatch(r"[0-9a-f]{40}",source_commit or ""):
        raise ValueError("Budget refresh requires a committed immutable source")
    sources,dependencies,source_hash=source_identity()
    for row in sources+dependencies:
        blob=subprocess.check_output(["git","show",source_commit+":"+row["path"]],cwd=ROOT)
        if digest(blob)!=row["sha256"]:
            raise ValueError("Uncommitted budget-refresh source: "+row["path"])
    old_contract=json.loads(prior("docs/ver3/integrated_r7/integration_contract.json"))
    for row in old_contract["sourceFiles"]+old_contract["readOnlyExistingDependencies"]:
        if row["path"] not in METADATA_SOURCES and digest((ROOT/row["path"]).read_bytes())!=row["sha256"]:
            raise ValueError("A frozen engineering source changed: "+row["path"])
    cfg=json.loads((ROOT/"scripts/ver3/walker_r7.json").read_text())
    old_cfg=json.loads(prior("scripts/ver3/walker_r7.json"))
    assert_only_changed(old_cfg,cfg,{"requirements"})
    assert_only_changed(old_cfg["requirements"],cfg["requirements"],BUDGET_KEYS)
    approval=json.loads((OUT/"requirements_approval.json").read_text())
    if (approval["approvedApproximateBudgetJpyPerMachine"]!=24000 or approval["recordedDateJst"]!="2026-09-28"
            or approval["purchasingAuthorized"] or approval["printingAuthorized"]
            or approval["applianceOperationAuthorized"] or not approval["publicationAuthorized"]):
        raise ValueError("The recorded approval does not match this budget-only publication scope")
    pending={};designs=[]
    def original(name):
        return json.loads(prior(str((OUT/name).relative_to(ROOT))))
    def stage(name,value):
        pending[str((OUT/name).relative_to(ROOT))]=encoded(value)
    for name in "ABC":
        before=original(name+"/assembly.json")
        assembly=rebind_assembly(before,cfg["requirements"])
        stage(name+"/assembly.json",assembly)
        old_identity=identity(before);new_identity=identity(assembly)
        envelope=original(name+"/floor_envelopes.json")
        if envelope["mechanicalIdentity"]!=old_identity:
            raise ValueError("The prior native envelope is stale")
        envelope.update(mechanicalIdentity=new_identity,budgetMetadataUpdate=PROOF)
        stage(name+"/floor_envelopes.json",envelope)
        envelope_sha=digest(encoded(envelope))
        floor=original(name+"/floor_clearance.json")
        if floor["mechanicalIdentity"]!=old_identity:
            raise ValueError("The prior floor check is stale")
        floor.update(mechanicalIdentity=new_identity,envelopesSha256=envelope_sha,budgetMetadataUpdate=PROOF)
        stage(name+"/floor_clearance.json",floor)
        environment=original(name+"/environment_sensitivity.json")
        environment.update(nativeFloorEnvelopesSha256=envelope_sha,budgetMetadataUpdate=PROOF)
        stage(name+"/environment_sensitivity.json",environment)
        frames=original(name+"/contact_frames.json")
        frames["generationSourceCommit"]=frames["sourceCommit"]
        frames["generationSourceHash"]=frames["sourceHash"]
        frames.update(sourceCommit=source_commit,sourceHash=source_hash,
                      assemblySha256=digest(encoded(assembly)),budgetMetadataUpdate=PROOF)
        stage(name+"/contact_frames.json",frames)
        designs.append({"designId":name,"instanceCount":len(assembly["instances"]),
                        "beforeRequirementInclusiveIdentity":old_identity,
                        "afterRequirementInclusiveIdentity":new_identity,
                        "unchangedPhysicalInputSha256":frames["mechanicalInputSha256"],
                        "unchangedFrameCount":len(frames["frames"]),
                        "unchangedFrameDataSha256":digest(encoded(frames["frames"]))})
    for selected in (["A"],["B"],["C"],["A","B","C"]):
        name=(selected[0]+"/" if len(selected)==1 else "")+"purchase_lots.json"
        before=original(name);after=price(selected)
        assert_only_changed(before,after,PRICE_KEYS)
        stage(name,after)
    validation=original("contact_frames_validation.json")
    validation["executionSourceCommit"]=validation["sourceCommit"]
    validation["executionSourceHash"]=validation["sourceHash"]
    validation.update(sourceCommit=source_commit,sourceHash=source_hash,budgetMetadataUpdate=PROOF)
    for row in validation["designs"]:
        path=str((OUT/row["designId"]/"contact_frames.json").relative_to(ROOT))
        row["contactFramesSha256"]=digest(pending[path])
    stage("contact_frames_validation.json",validation)
    previous_manifest=json.loads(prior("docs/ver3/integrated_r7/manifest.json"))
    regenerated={"manifest.json","integration_contract.json","requirements_approval.json","publication_readiness.json",
                 "comparison.json","comparison.csv"}
    preserved=[]
    for row in previous_manifest["files"]:
        path=Path(row["path"])
        in_scope=row["path"].startswith(("FreeCAD/Ver.3/integrated_r7/","STL/Ver.3/integrated_r7/",
                                         "docs/ver3/integrated_r7/"))
        if not in_scope or row["path"] in pending or path.suffix==".md" or path.name in regenerated:
            continue
        if digest((ROOT/path).read_bytes())!=row["sha256"]:
            raise ValueError("An unchanged physical artifact was modified: "+row["path"])
        preserved.append(row)
    proof={"baselineArtifactCommit":BASELINE,"sourceCommit":source_commit,"sourceHash":source_hash,
           "status":"VERIFIED_BUDGET_METADATA_ONLY","approvalDateJst":"2026-09-28",
           "oldApproximatePartsBudgetJpy":23000,"approvedApproximatePartsBudgetJpy":24000,
           "unownedDn03ToolApproximateCostJpySeparate":396,
           "cadOrPhysicalValuesChanged":False,"solverOrCadRerunPerformed":False,
           "originalSliceResultsChanged":False,"manufacturingRelease":False,
           "qualificationPromoted":False,"designs":designs,
           "identityScope":"The existing floor identity includes requirements; only its budget fields are rebound. All cases,envelopes,geometry,physical inputs and frame arrays are unchanged. Original execution source hashes remain recorded.",
           "preservedResourceCount":len(preserved),"preservedResourceBytes":sum(row["bytes"] for row in preserved),
           "preservedInventorySha256":digest(encoded(preserved)),
           "updatedResources":[{"path":path,"beforeSha256":digest(prior(path)),"afterSha256":digest(blob)}
                               for path,blob in pending.items()]}
    return pending,proof


def refresh(source_commit):
    pending,proof=expected_update(source_commit)
    for path in pending:
        if (ROOT/path).read_bytes()!=prior(path):
            raise ValueError("Refusing to overwrite unexpected artifact edits: "+path)
    if (ROOT/PROOF).exists():
        raise ValueError("Budget update already exists; verify instead of repeating it")
    for path,blob in pending.items():(ROOT/path).write_bytes(blob)
    (ROOT/PROOF).write_bytes(encoded(proof))
    print("Budget-only identities refreshed; no CAD/solver execution; preserved resources",proof["preservedResourceCount"])


def verify_budget_update():
    proof=json.loads((ROOT/PROOF).read_text())
    pending,expected=expected_update(proof["sourceCommit"])
    if proof!=expected:raise ValueError("Budget-only proof differs from its frozen baseline")
    for path,blob in pending.items():
        if (ROOT/path).read_bytes()!=blob:
            raise ValueError("Unexpected artifact difference after budget-only update: "+path)
    comparison=json.loads((OUT/"comparison.json").read_text())
    before=json.loads(prior("docs/ver3/integrated_r7/comparison.json"))
    if len(comparison["rows"])!=3:raise ValueError("Comparison lost a design")
    for old,new in zip(before["rows"],comparison["rows"]):
        assert_only_changed(old,new,{"approvedApproximateBudgetJpy","budgetStatus"})
        if new["approvedApproximateBudgetJpy"]!=24000 or new["budgetStatus"]!="CONDITIONAL_WITHIN_APPROVED_BUDGET":
            raise ValueError("Comparison uses an unapproved budget")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit",required=True)
    args=parser.parse_args();refresh(args.source_commit)
