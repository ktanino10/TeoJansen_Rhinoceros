"""Verify the frozen engineering handoff, without equating it to physical qualification."""

from collections import Counter
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re

import numpy as np

from walker_geometry import ROOT,OUT,CAD


def load(path):
    return json.loads(path.read_text())


def main():
    manifest=load(OUT/"manifest.json")
    contract=load(OUT/"integration_contract.json")
    comparison=load(OUT/"comparison.json")
    for doc in (manifest,contract,comparison):
        if doc["manufacturingRelease"] or doc["qualifiedWalkingPrototypeCount"]!=0:
            raise ValueError("Physical qualification was incorrectly promoted")
    if contract["requirements"]["materialBudgetJpy"]!=23000:
        raise ValueError("The current user-approved budget is missing")
    if contract["sourceHash"]!=manifest["sourceHash"] or not re.fullmatch(r"[0-9a-f]{40}",contract["sourceCommit"] or ""):
        raise ValueError("Missing or inconsistent source identity")
    for row in manifest["files"]:
        path=(ROOT/row["path"]).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():raise ValueError("Missing/out-of-scope artifact "+row["path"])
        if path.stat().st_size!=row["bytes"] or hashlib.sha256(path.read_bytes()).hexdigest()!=row["sha256"]:
            raise ValueError("Artifact hash changed: "+row["path"])
    for design in contract["designs"]:
        name=design["id"];folder=OUT/name;a=load(folder/"assembly.json")
        if a["revisionId"]!=contract["revisionId"] or a["parameters"]["requirements"]["materialBudgetJpy"]!=23000:
            raise ValueError("Mixed current design or requirement revision")
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
        motion=load(folder/"gait_motion.json")
        if motion["poses"]!=216:raise ValueError("Operating pose set differs")
        printing=load(folder/"print_geometry.json")
        if printing["nativeSha256"]!=native_hash or printing["geometryStatus"]!="PASS":raise ValueError("Stale print output")
        stages=load(folder/"assembly_stages.json");visible=set();seen=set()
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
        work=load(folder/"work_budget.json");price=load(folder/"purchase_lots.json")
        if abs(work["cadMassKg"]*1000-total)>1e-7 or any(c["physicalSelfStart"]!="UNKNOWN" for c in work["cases"]):
            raise ValueError("Work model mass or qualification differs")
        if work["cases"][1]["rawPhaseMinimumMarginNm"]<0:
            raise ValueError("The nominal raw-proxy torque budget does not close")
        environment=load(folder/"environment_sensitivity.json")
        if len(environment["windCases"])!=6 or len(environment["staticRotorImbalance"])!=4:
            raise ValueError("Wind or imbalance sensitivity set is incomplete")
        if not price["guardsAndFitCouponsFullyIncluded"] or price["targetMaterialCostApproxJpy"]!=23000:
            raise ValueError("Full approved cost scope is incomplete")
        if price["sourceDisplayedPlusMaterialWithoutUncertainTaxReservesJpy"]>23000:
            raise ValueError("Standalone reference cost exceeds approval")
        if any(row["clockingAlreadyIncludedInCadTransforms"] is not True
               for row in stages["stages"] if "clockingAlreadyIncludedInCadTransforms" in row):
            raise ValueError("Ambiguous collar transforms")
    for file in OUT.rglob("*.md"):
        for href in re.findall(r"\]\(([^)]+)\)",file.read_text()):
            if re.match(r"^[a-z]+:",href) or href.startswith("#"):continue
            target=(file.parent/href.split("#",1)[0]).resolve()
            if not target.exists():raise ValueError(f"Broken document link: {file.relative_to(ROOT)} -> {href}")
    if load(OUT/"slicing_status.json")["actualSlicingPerformed"]:
        raise ValueError("An unexecuted slicer check was incorrectly marked complete")
    print("PASS: frozen hashes,three native sets,actual instances/BOM/mass,all declared finite checks,stage operations,links and approved standalone budgets.")
    print("Physical qualification remains0; actual airflow,friction,materials,tools,slicing and30cm travel remain separately unverified.")


if __name__=="__main__":main()
