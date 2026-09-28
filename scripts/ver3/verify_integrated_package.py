"""Verify the frozen engineering handoff, without equating it to physical qualification."""

from collections import Counter
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re

import numpy as np

from walker_geometry import ROOT,OUT,CAD,reducer
from build_integrated_contract import validate_path_inventory
from slice_integrated_representatives import PARTS
from walker_floor import identity as floor_identity
from walker_contact import error_cases


def load(path):
    return json.loads(path.read_text())


def verify_resources(value):
    if isinstance(value,dict):
        if {"path","bytes","sha256"}<=value.keys():
            path=(ROOT/value["path"]).resolve()
            if (not path.is_relative_to(ROOT) or not path.is_file() or path.stat().st_size!=value["bytes"]
                    or hashlib.sha256(path.read_bytes()).hexdigest()!=value["sha256"]):
                raise ValueError("Stale or invalid contract resource: "+value["path"])
        for item in value.values():verify_resources(item)
    elif isinstance(value,list):
        for item in value:verify_resources(item)


def validate_slicing(status,checks,provenance):
    if (status["status"]!="REPRESENTATIVE_TOOLPATHS_REVIEWED_WITH_LIMITATIONS"
            or not status["actualSlicingPerformed"] or not status["visualLayerReviewPerformed"]
            or status["fullAssemblySliced"] or status["printerContacted"]
            or status["physicalPrintingPerformed"] or status["manufacturingRelease"]
            or status["actualHardwareAndMaterialMatched"]):
        raise ValueError("Invalid representative-only slicing or physical qualification scope")
    rows=checks["parts"]
    if {r["partId"] for r in rows}!=set(PARTS) or len(rows)!=5 or status["representativePartCount"]!=5:
        raise ValueError("Representative slice set differs")
    profiles={r["partId"]:r for r in provenance["parts"]}
    has_intrusion=False
    for row in rows:
        if row["exitCode"] or row["firstLayerBoundingBoxAgreementWithOrcaMm"]>.05:
            raise ValueError("Unexecuted slice or inconsistent coordinate mapping")
        for key in ("stlSha256","effectiveSettingsSha256","gcodeSha256"):
            if row[key]!=profiles[row["partId"]][key] or not re.fullmatch(r"[0-9a-f]{64}",row[key]):
                raise ValueError("Slice provenance differs: "+key)
        if hashlib.sha256((ROOT/row["stl"]).read_bytes()).hexdigest()!=row["stlSha256"]:
            raise ValueError("Representative STL changed")
        for bore in row["bores"]:
            if not bore["modelNeverClosesBoreCenter"] or bore["minimumModelToolpathClearRadiusMm"]<=0:
                raise ValueError("A model bore is closed in the actual toolpath")
            has_intrusion|=bool(bore["supportIntrusionLayers"])
            if any(abs(layer["zMm"]-.2)>1e-9 or abs(layer["heightMm"]-.2)>1e-9
                   for layer in bore["supportIntrusionLayers"]):
                raise ValueError("Support enters a bore beyond the documented exposed first layer")
        for gear in row["gearLayers"]:
            if (gear["depositedEnvelopeTeeth"]!=gear["expectedTeeth"]
                    or not gear["allDetectedTipsOnOneRootConnectedComponent"]
                    or gear["maximumTipRadialSetbackMm"]>=.04):
                raise ValueError("A documented tooth-count/root/tip check failed")
        for image in row["layerImages"]:
            path=OUT/"slicing"/image["path"]
            if path.parent!=OUT/"slicing" or hashlib.sha256(path.read_bytes()).hexdigest()!=image["sha256"]:
                raise ValueError("Layer image identity differs")
    if has_intrusion and (status["allSupportFreeBores"] or not status["supportRemovalRequired"]):
        raise ValueError("Support removal was silently promoted to clear,finished bores")


def main():
    manifest=load(OUT/"manifest.json")
    contract=load(OUT/"integration_contract.json")
    comparison=load(OUT/"comparison.json")
    budget_exceptions=[]
    approved_budget=load(OUT/"requirements_approval.json")["approvedApproximateBudgetJpyPerMachine"]
    verify_resources(contract)
    for doc in (manifest,contract,comparison):
        if doc["manufacturingRelease"] or doc["qualifiedWalkingPrototypeCount"]!=0:
            raise ValueError("Physical qualification was incorrectly promoted")
    if contract["requirements"]["materialBudgetJpy"]!=approved_budget:
        raise ValueError("The current user-approved budget is missing")
    if contract["schemaVersion"]!=2:
        raise ValueError("Assembly paths must use the inventory-bound workflow schema")
    review=load(OUT/"review/correction_status.json")
    if review["independentFollowUpStatus"]!="CONFIRMED":
        raise ValueError("R7-I1 requires the same independent review context's corrective-diff confirmation")
    if contract["sourceHash"]!=manifest["sourceHash"] or not re.fullmatch(r"[0-9a-f]{40}",contract["sourceCommit"] or ""):
        raise ValueError("Missing or inconsistent source identity")
    for row in manifest["files"]:
        path=(ROOT/row["path"]).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():raise ValueError("Missing/out-of-scope artifact "+row["path"])
        if path.stat().st_size!=row["bytes"] or hashlib.sha256(path.read_bytes()).hexdigest()!=row["sha256"]:
            raise ValueError("Artifact hash changed: "+row["path"])
    for design in contract["designs"]:
        name=design["id"];folder=OUT/name;a=load(folder/"assembly.json")
        if a["revisionId"]!=contract["revisionId"] or a["parameters"]["requirements"]["materialBudgetJpy"]!=approved_budget:
            raise ValueError("Mixed current design or requirement revision")
        train=reducer(a["candidate"],a["parameters"]["common"])
        if (not np.allclose(train["axesYzMm"],a["reduction"]["axesYzMm"],atol=1e-9)
                or not np.allclose(train["speedRatios"],a["reduction"]["speedRatios"],atol=1e-9)):
            raise ValueError("Reducer coordinates or signed shaft ratios are stale")
        if len(train["stages"])!=len(a["reduction"]["stages"]):
            raise ValueError("A physical reducer stage was omitted")
        for expected,saved in zip(train["stages"],a["reduction"]["stages"]):
            for key in ("pinion","wheel","centreMm","xMm","pinionProfileShift","wheelProfileShift"):
                if abs(expected[key]-saved[key])>1e-9:raise ValueError("Reducer stage differs: "+key)
            if (saved.get("moduleMm",1)!=expected["moduleMm"]
                    or saved.get("pressureAngleDeg",25)!=expected["pressureAngleDeg"]):
                raise ValueError("A mesh lost its own module or pressure angle")
        native=CAD/name/f"Walker_{name}.FCStd";native_hash=hashlib.sha256(native.read_bytes()).hexdigest()
        if design["native"]["sha256"]!=native_hash or a["nativeStepStatus"]!="PASS":
            raise ValueError("Native/STEP identity or correspondence failed")
        ids=[i["name"] for i in a["instances"]]
        if len(ids)!=len(set(ids)):raise ValueError("Duplicate assembly instance")
        count=Counter(i["part_id"] for i in a["instances"])
        total=0.;moment=np.zeros(3)
        for item in a["instances"]:
            part=a["parts"][item["part_id"]];mass=part["mass_g"]
            total+=mass;moment+=mass*(np.array(item["transform"])@np.r_[part["local_com_mm"],1])[:3]
        if abs(total-a["nominalTotalMassG"])>1e-7 or not np.allclose(moment/total,a["nominalCenterOfMassMm"],atol=1e-8):
            raise ValueError("CAD mass/COM does not match actual instances")
        with (folder/"BOM.csv").open() as stream:bill=list(csv.DictReader(stream))
        if {r["part_id"]:int(r["quantity"]) for r in bill}!=dict(count):raise ValueError("BOM does not match actual instances")
        with gzip.open(ROOT/a["cadMeshes"],"rt") as stream:meshes=json.load(stream)
        if set(meshes)!=set(a["parts"]):raise ValueError("Mesh/part definition set differs")
        for filename in ("static_collisions.json","gait_motion.json","assembly_access.json","rotating_clearance.json"):
            result=load(folder/filename)
            if result["revisionId"]!=a["revisionId"] or result["status"]!="PASS":
                raise ValueError(name+" has an incomplete geometric check: "+filename)
            if "nativeSha256" in result and result["nativeSha256"]!=native_hash:raise ValueError("Stale native check")
        contact=load(folder/"contact_sensitivity.json")
        if contact["passed"]!=contact["total"] or contact["total"]!=162:raise ValueError("Support cases are incomplete")
        floor=load(folder/"floor_clearance.json");envelopes=load(folder/"floor_envelopes.json")
        if (floor["status"]!="PASS" or not floor["complete"] or floor["caseCount"]!=163
                or floor["poseCount"]!=29880 or floor["nativeSha256"]!=native_hash
                or envelopes["nativeSha256"]!=native_hash
                or floor["mechanicalIdentity"]!=floor_identity(a)
                or envelopes["mechanicalIdentity"]!=floor_identity(a)):
            raise ValueError("Incomplete or stale whole-body floor verification")
        expected_cases={"nominal_dense"}|{f'{entry["id"]}/guide={mode}/couple={sign}'
            for entry in error_cases(a["parameters"]["common"]) for mode in (-1,0,1) for sign in (-1,1)}
        if ({case["caseId"] for case in floor["cases"]}!=expected_cases or len(floor["cases"])!=163
                or sum(case["phaseCount"] for case in floor["cases"])!=29880):
            raise ValueError("A declared floor scenario was omitted or duplicated")
        if {r["instance"] for r in floor["worstPerInstance"]}!=set(ids) or len(floor["worstPerInstance"])!=len(ids):
            raise ValueError("The floor result omitted an assembly instance")
        if set(envelopes["parts"])!=set(a["parts"]):
            raise ValueError("A native floor-envelope definition is missing")
        for filename,digest in envelopes["generatorSourcesSha256"].items():
            if hashlib.sha256((ROOT/"scripts/ver3"/filename).read_bytes()).hexdigest()!=digest:
                raise ValueError("Native-envelope generator source changed")
        for case in floor["cases"]:
            expected=720 if case["caseId"]=="nominal_dense" else 180
            if (case["status"]!="PASS" or case["phaseCount"]!=expected
                    or case["checkedInstances"]!=len(ids) or case["failures"]
                    or case["worst"]["minimumReservedClearanceMm"]<0
                    or not case["maximumModeledFootNormalN"]>0):
                raise ValueError("A whole-body floor case is incomplete or failed")
        for filename,expected_hash in floor["checkerSourcesSha256"].items():
            if hashlib.sha256((ROOT/"scripts/ver3"/filename).read_bytes()).hexdigest()!=expected_hash:
                raise ValueError("Floor checker source differs from the executed result")
        tool=load(folder/"rocker_pin_access.json")
        if (tool["nativeSha256"]!=native_hash or tool["status"]!="PASS_STOCK_TOOL_ENVELOPE"
                or not tool["toolModelAndPublishedDimensionsConfirmed"]
                or len(tool["records"])!=6 or any(r["status"]!="PASS" for r in tool["records"])):
            raise ValueError("Rocker-pin required-tool access is incomplete")
        lock_nuts={i["name"] for i in a["instances"] if i["part_id"]=="H_LOCK_NUT_M2"}
        if {row["targetNut"] for row in tool["records"]}!=lock_nuts:
            raise ValueError("A stock locking nut was omitted from tool verification")
        lookup={i["name"]:i for i in a["instances"]}
        for row in tool["records"]:
            m=lookup[row["targetNut"]]["motion"]
            expected_scene={i["name"] for i in a["instances"]
                            if i["motion"].get("station")==m["station"] and i["motion"].get("side")==m["side"]
                            and (i["motion"]["kind"]=="foot" or i["motion"].get("link")=="CEF")}
            if set(row["sceneInstances"])!=expected_scene or len(row["sceneInstances"])!=len(expected_scene):
                raise ValueError("Foot-tool preassembly inventory was filtered")
            if (len(row["insertionSamples"])!=6 or any(s["intersections"] for s in row["insertionSamples"])
                    or row["fullRotationEnvelopeIntersections"] or row["gripEnvelopeIntersections"]):
                raise ValueError("Stock driver insertion,rotation or grip clearance failed")
        motion=load(folder/"gait_motion.json")
        if motion["poses"]!=216:raise ValueError("Operating pose set differs")
        printing=load(folder/"print_geometry.json")
        if printing["nativeSha256"]!=native_hash or printing["geometryStatus"]!="PASS":raise ValueError("Stale print output")
        stages=load(folder/"assembly_stages.json");visible=set();seen=set()
        if stages["schemaVersion"]!=2:raise ValueError("Legacy unbound assembly stage schema")
        for stage in stages["stages"]:
            for op in stage["orderedOperations"]:
                names=set(op["instances"])
                if not names<=set(ids):raise ValueError("Stage references unknown instances")
                if op["operation"]=="add":
                    if names&seen:raise ValueError("Reinsert mislabeled as add")
                    visible|=names;seen|=names
                elif op["operation"]=="remove":
                    if not names<=visible:raise ValueError("Removing absent part")
                    visible-=names
                elif op["operation"]=="reinsert":
                    if not names<=seen or names&visible:raise ValueError("Invalid reinsertion")
                    visible|=names
                else:raise ValueError("Unknown stage operation")
            if visible!=set(stage["visibleAfter"]):raise ValueError("Stage inventory mismatch")
        if visible!=set(ids):raise ValueError("Final assembly stage is incomplete")
        validate_path_inventory(a,load(folder/"assembly_access.json"),stages["stages"])
        work=load(folder/"work_budget.json");price=load(folder/"purchase_lots.json")
        frames=load(folder/"contact_frames.json")
        if (frames["sourceCommit"]!=contract["sourceCommit"] or frames["sourceHash"]!=contract["sourceHash"]
                or frames["assemblySha256"]!=design["assembly"]["sha256"]
                or frames["mechanicalInputSha256"]!=work["mechanicalInputSha256"]
                or frames["frameCount"]!=73 or frames["rawPhaseCount"]!=720
                or len(frames["frames"])!=73 or len(frames["footOrder"])!=6):
            raise ValueError("Stale or incomplete contact-frame identity")
        for index,frame in enumerate(frames["frames"]):
            if frame["crankDeg"]!=index*5 or frame["independentRockerAngleRad"] is not None:
                raise ValueError("Changed contact phase or invented rocker state")
            for key,shape in (("bodyHeightAndSlopes",(3,)),("integratedPlanarComponents",(3,)),
                              ("normalN",(6,)),("springCompressionMm",(6,)),("toesBodyMm",(6,3))):
                values=np.asarray(frame[key])
                if values.shape!=shape or not np.all(np.isfinite(values)):
                    raise ValueError("Missing/nonfinite contact frame "+key)
        expected=[work["contact"][key] for key in ("lateral_per_cycle_mm","advance_per_cycle_mm","yaw_per_cycle_rad")]
        if not np.allclose(frames["frames"][-1]["integratedPlanarComponents"],expected,rtol=1e-9,atol=1e-8):
            raise ValueError("Frame advance disagrees with the unchanged dense solver summary")
        if abs(work["cadMassKg"]*1000-total)>1e-7 or any(c["physicalSelfStart"]!="UNKNOWN" for c in work["cases"]):
            raise ValueError("Work model mass or qualification differs")
        if work["cases"][1]["rawPhaseMinimumMarginNm"]<0:
            raise ValueError("The nominal raw-proxy torque budget does not close")
        environment=load(folder/"environment_sensitivity.json")
        if len(environment["windCases"])!=6 or len(environment["staticRotorImbalance"])!=4:
            raise ValueError("Wind or imbalance sensitivity set is incomplete")
        if (environment["mechanicalInputSha256"]!=work["mechanicalInputSha256"]
                or environment["nativeFloorEnvelopesSha256"]!=hashlib.sha256((folder/"floor_envelopes.json").read_bytes()).hexdigest()):
            raise ValueError("Wind-case floor verification is stale")
        for wind in environment["windCases"]:
            case=wind["nonContactFloor"]
            if case["status"]!="PASS" or case["phaseCount"]!=720 or case["checkedInstances"]!=len(ids):
                raise ValueError("Incomplete non-contact floor check for a declared wind case")
        if not price["guardsAndFitCouponsFullyIncluded"] or price["targetMaterialCostApproxJpy"]!=approved_budget:
            raise ValueError("Full approved cost scope is incomplete")
        if price["sourceDisplayedPlusMaterialWithoutUncertainTaxReservesJpy"]>approved_budget:
            budget_exceptions.append({"design":name,"referenceJpy":price["sourceDisplayedPlusMaterialWithoutUncertainTaxReservesJpy"],"recordedBudgetJpy":approved_budget})
        if any(row["clockingAlreadyIncludedInCadTransforms"] is not True
               for row in stages["stages"] if "clockingAlreadyIncludedInCadTransforms" in row):
            raise ValueError("Ambiguous collar transforms")
    for file in OUT.rglob("*.md"):
        for href in re.findall(r"\]\(([^)]+)\)",file.read_text()):
            if re.match(r"^[a-z]+:",href) or href.startswith("#"):continue
            target=(file.parent/href.split("#",1)[0]).resolve()
            if not target.exists():raise ValueError(f"Broken document link: {file.relative_to(ROOT)} -> {href}")
    validate_slicing(load(OUT/"slicing_status.json"),load(OUT/"slicing/toolpath_checks.json"),
                     load(OUT/"slicing/profile_provenance.json"))
    extra_status=load(OUT/"C/slicing_status.json")
    extra=load(OUT/"C/slicing/toolpath_checks.json")
    if (extra_status["status"]!="TWO_C_GEAR_TOOLPATHS_REVIEWED_WITH_WARNINGS"
            or not extra_status["visualReviewPerformed"] or extra_status["dimensionalManufacturingApproval"]
            or extra_status["printerContacted"] or extra_status["physicalPrintingPerformed"]
            or {p["partId"] for p in extra["parts"]}!={"P_INPUT_PINION","P_COMPOUND_1"}):
        raise ValueError("Invalid scope for additional C toolpath inspection")
    for part in extra["parts"]:
        if part["exitCode"] or hashlib.sha256((ROOT/part["stl"]).read_bytes()).hexdigest()!=part["stlSha256"]:
            raise ValueError("Additional C toolpath input changed")
        if any(not b["modelNeverClosesBoreCenter"] for b in part["bores"]):
            raise ValueError("An additional C model bore closed")
        for gear in part["gearLayers"]:
            if gear["depositedEnvelopeTeeth"]!=gear["expectedTeeth"] or not gear["allDetectedTipsOnOneRootConnectedComponent"]:
                raise ValueError("Additional C tooth-count/root check failed")
        for image in part["layerImages"]:
            if hashlib.sha256((OUT/"C/slicing"/image["path"]).read_bytes()).hexdigest()!=image["sha256"]:
                raise ValueError("Additional C layer image changed")
    compound=next(p for p in extra["parts"] if p["partId"]=="P_COMPOUND_1")
    if abs(compound["gearLayers"][0]["maximumTipRadialSetbackMm"]-extra_status["firstWheelFaceMeasuredSetbackMm"])>1e-9:
        raise ValueError("The reported first-face C slicing warning changed")
    if budget_exceptions:
        raise ValueError("All other package checks completed; standalone reference costs require budget confirmation: "+json.dumps(budget_exceptions))
    print("PASS: current hashes,three native sets,instances/BOM/mass,declared finite checks,all-instance floor cases,required-tool access,stage operations,links and approved standalone budgets.")
    print("Physical qualification remains0. Five representative toolpaths are inspected,with exposed first-layer support removal unresolved; actual airflow,friction,fit,strength,tools and30cm travel remain unverified.")


if __name__=="__main__":main()
