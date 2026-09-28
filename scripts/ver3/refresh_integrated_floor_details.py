"""Increment only side PET and rocker-pin details, preserving the rest of the native assembly."""

import argparse
from collections import Counter
from copy import deepcopy
import csv
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import numpy as np


def refresh(name,b,backup,hardware_only=False):
    folder=b.OUT/name;cad=b.CAD/name
    data=json.loads((folder/"assembly.json").read_text())
    candidate=next(c for c in b.CFG["candidates"] if c["id"]==name)
    if candidate!=data["candidate"]:raise ValueError("Guard-only refresh cannot change the mechanism")
    old_common=deepcopy(data["parameters"]["common"]);new_common=deepcopy(b.C)
    allowed={"sideSheetOutline","sideSheetGearCoverageMarginMm","sideSheetLowerCoverageMarginMm","sideSheetUpperBridgeBottomMm"}
    foot_allowed={"rockerWidthAtPivotMm","rockerBossRadiusMm","rockerPinSeatInsetMm",
                  "rockerPinSeatDiameterMm","rockerPinBoltLengthMm","rockerPinStockBoltLengthMm",
                  "rockerPinCutAcceptanceMm","rockerThrustWasherInnerMm","rockerThrustWasherOuterMm",
                  "rockerThrustWasherThicknessMm","rockerForkWidthMm","rockerPinBoltLengthToleranceMm",
                  "rockerLockNutAcrossFlatsMm","rockerLockNutHeightMm","rockerPinLocking"}
    for values in (old_common,new_common):
        for key in allowed:values["guards"].pop(key,None)
        for key in foot_allowed:values["foot"].pop(key,None)
    if old_common!=new_common:raise ValueError("Guard-only refresh refuses other common geometry changes")
    target=backup/name;target.mkdir(parents=True,exist_ok=True)
    for p in [folder/"assembly.json",folder/"BOM.csv",cad/f"Walker_{name}.FCStd",cad/f"Walker_{name}.step",cad/"render_geometry.json.gz"]:
        shutil.copy2(p,target/p.name)
    native=cad/f"Walker_{name}.FCStd";previous_hash=hashlib.sha256(native.read_bytes()).hexdigest()
    doc=b.App.openDocument(str(native))
    try:
        selected={"P_FOOT_SLIDER_L","P_FOOT_SLIDER_R"}
        if not hardware_only:selected.update({"S_GUARD_LEFT","S_GUARD_LOWER_RIGHT","P_FOOT_ROCKER_L","P_FOOT_ROCKER_R"})
        moving={i["name"] for i in data["instances"] if i["motion"].get("piece")=="ROCKER_PIN"}
        def signature(shape):
            box=shape.BoundBox
            volume=sum(s.Volume for s in shape.Solids)
            center=sum((s.CenterOfMass*s.Volume for s in shape.Solids),b.V())/volume
            return [volume,*list(center),box.XMin,box.XMax,box.YMin,box.YMax,box.ZMin,box.ZMax,
                    len(shape.Faces),len(shape.Edges),len(shape.Solids)]
        unchanged={i["name"]:signature(doc.getObject(i["name"]).Shape) for i in data["instances"]
                   if i["part_id"] not in selected and i["name"] not in moving}
        definitions=SimpleNamespace(id=name,candidate=candidate,red=data["reduction"],input=data["inputLayout"],
                                    cap_mounts=data["bearingMounts"],frame_members=data["frameMembersBeforeUnion"],defs={})
        definitions.define=lambda *args,**kwargs:b.Whole.define(definitions,*args,**kwargs)
        definitions.add=lambda *args,**kwargs:None
        if not hardware_only:
            b.add_gear_shields(definitions,only=("LEFT","LOWER_RIGHT"))
            if set(definitions.defs)!={"S_GUARD_LEFT","S_GUARD_LOWER_RIGHT"}:
                raise ValueError("Unexpected PET part split or inventory change")
        for side in (-1,1):
            for kind,shape in (("SLIDER",b.foot_slider()),("ROCKER",b.foot_rocker())):
                if hardware_only and kind=="ROCKER":continue
                part=b.transformed(shape,b.foot_axes(b.P["F"]))
                if side<0:part=b.mirror_x(part)
                definitions.define(f"P_FOOT_{kind}_{'L' if side<0 else 'R'}",part,"printed",
                                   "Floor correction: same foot position/spring/rolling pads; recessed metal clamp seats, reduced non-contact boss and preserved axial stack.")
        replacements={}
        groups={}
        for item in data["instances"]:
            m=item["motion"]
            if m.get("piece")=="ROCKER_PIN":groups.setdefault((m["station"],m["side"],m["phase"]),[]).append(item)
        if len(groups)!=6 or any(len(v) not in (7,8) for v in groups.values()):
            raise ValueError("Unexpected rocker-pin physical inventory")
        removed=[]
        for (station,side,phase),items in groups.items():
            queued=[]
            definitions.add=lambda pid,matrix,*args,**kwargs:queued.append((pid,matrix))
            p=b.body_points(phase,common=b.C)
            mount=np.asarray(b.link_pose(p,b.P,b.rigids()["CEF"],station,b.Z0))
            foot=b.foot_axes(b.P["F"])
            if side<0:foot=np.diag([-1,1,1,1])@foot
            location=mount@foot
            for kind,size,position,length in b.rocker_hardware(b.C["foot"]):
                origin=(location@np.array([0,position,b.C["foot"]["toeOffsetFromFNeutralMm"][1],1]))[:3]
                b.Whole.hardware(definitions,kind,size,origin,location[:3,1],length)
            if len(items)==8:
                if items[4]["part_id"]!="H_NUT_M2" or items[5]["part_id"]!="H_NUT_M2":
                    raise ValueError("Only the identified jam-nut pair can be replaced")
                removed.append(items[5]["name"]);items=items[:5]+items[6:]
            if len(queued)!=len(items):raise ValueError("Rocker-pin replacement count differs")
            for item,(pid,matrix) in zip(items,queued):
                replacements[item["name"]]=(pid,matrix)
        selected.update({"H_BOLT_M2_12","H_LOCK_NUT_M2","H_WASHER_4_SMALL"})
        meshes=json.loads(gzip.decompress((cad/"render_geometry.json.gz").read_bytes()))
        changes=[]
        for pid,entry in definitions.defs.items():
            if pid not in selected:continue
            before=data["parts"].get(pid);shape=entry["shape"]
            data["parts"][pid]={k:v for k,v in entry.items() if k!="shape"}
            vertices,triangles=shape.tessellate(.16)
            meshes[pid]={"vertices":[list(v) for v in vertices],"triangles":triangles,"category":entry["category"]}
            changes.append({"partId":pid,"beforeMassG":before["mass_g"] if before else None,"afterMassG":entry["mass_g"]})
        for ident in removed:doc.removeObject(ident)
        data["instances"]=[i for i in data["instances"] if i["name"] not in removed]
        for item in data["instances"]:
            replacement=replacements.get(item["name"])
            if replacement:
                item["part_id"],item["transform"]=replacement
            pid=item["part_id"]
            if pid not in selected and replacement is None:continue
            shape=definitions.defs[pid]["shape"];part=data["parts"][pid]
            feature=doc.getObject(item["name"]);feature.Shape=shape
            feature.Placement=b.App.Placement(b.App.Matrix(*np.asarray(item["transform"]).ravel().tolist())).multiply(shape.Placement)
            feature.NominalMassGram=part["mass_g"];feature.PartId=pid
            feature.Category=part["category"];feature.Specification=part["spec"]
        for item in data["instances"]:doc.getObject(item["name"]).RevisionId=b.CFG["revisionId"]
        active={i["part_id"] for i in data["instances"]}
        data["parts"]={pid:p for pid,p in data["parts"].items() if pid in active}
        meshes={pid:p for pid,p in meshes.items() if pid in active}
        doc.recompute()
        if any(not np.allclose(signature(doc.getObject(key).Shape),value,rtol=1e-12,atol=1e-8) for key,value in unchanged.items()):
            raise ValueError("An unrelated native shape changed")
        data["incrementalFloorDetailsUpdate"]={"previousNativeSha256":previous_hash,"previousRevisionId":data["revisionId"],
                                       "changedParts":changes,"unchangedNativeShapeCount":len(unchanged),
                                       "printedStlFilesTouched":0,"inputHashes":b.BUILD_HASHES,
                                       "removedSurplusJamNutInstances":removed,
                                       "lockingChange":"Two jam nuts replaced by one stock nylon insert nut; no holding-torque or durability equivalence claimed"}
        data["revisionId"]=b.CFG["revisionId"];data["parameters"]=deepcopy(b.CFG)
        data["nativeStepStatus"]="PENDING"
        data["fullAssemblyVerification"]="IN_PROGRESS"
        if not hardware_only:
            new_blanks={r["partId"]:r for r in definitions.guard_sheet_blanks}
            data["guardSheetBlanks"]=[new_blanks.get(r["partId"],r) for r in data["guardSheetBlanks"]]
            data["guardCutScrap"]=[r for r in data["guardCutScrap"] if r["panel"] not in ("LEFT","LOWER_RIGHT")]+definitions.guard_cut_scrap
        total=printed=0.;moment=np.zeros(3)
        for item in data["instances"]:
            part=data["parts"][item["part_id"]];mass=part["mass_g"];total+=mass
            moment+=mass*(np.asarray(item["transform"])@np.r_[part["local_com_mm"],1])[:3]
            if part["category"]=="printed":printed+=mass
        data.update(nominalTotalMassG=total,nominalPrintedMassG=printed,nominalCenterOfMassMm=(moment/total).tolist())
        temporary=cad/f"Walker_{name}.guard-update.FCStd";doc.saveAs(str(temporary));temporary.replace(native)
        b.Part.export([o for o in doc.Objects if o.TypeId=="Part::Feature"],str(cad/f"Walker_{name}.step"))
        step=cad/f"Walker_{name}.step";step.write_text("\n".join(line.rstrip() for line in step.read_text().splitlines())+"\n")
        (cad/"render_geometry.json.gz").write_bytes(gzip.compress(json.dumps(meshes,separators=(",",":")).encode(),mtime=0))
        (folder/"assembly.json").write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")
        count=Counter(i["part_id"] for i in data["instances"])
        with (folder/"BOM.csv").open("w",newline="") as stream:
            writer=csv.writer(stream,lineterminator="\n")
            writer.writerow(["part_id","category","quantity","sku","unit_nominal_mass_g","total_nominal_mass_g","basis","spec"])
            for pid,part in data["parts"].items():
                writer.writerow([pid,part["category"],count[pid],part["sku"],part["mass_g"],count[pid]*part["mass_g"],part["mass_basis"],part["spec"]])
        print("STAGE_END guard-refresh",name,changes,flush=True)
    finally:b.App.closeDocument(doc.Name)
    from verify_integrated_exports import verify
    verify(name,b.ROOT)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freecad-lib",required=True)
    parser.add_argument("--design",choices=("A","B","C"),required=True)
    parser.add_argument("--backup",type=Path,required=True)
    parser.add_argument("--hardware-only",action="store_true")
    args=parser.parse_args()
    sys.argv=[sys.argv[0],"--freecad-lib",args.freecad_lib]
    import build_integrated_walkers as builder
    refresh(args.design,builder,args.backup,args.hardware_only)
