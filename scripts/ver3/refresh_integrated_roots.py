"""Incremental native/STEP update for only the strengthened A-pin socket boss."""

import argparse
from collections import Counter
from copy import deepcopy
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

import numpy as np


def leaves(value,prefix=""):
    if isinstance(value,dict):
        result={}
        for key,item in value.items():result.update(leaves(item,prefix+"."+key if prefix else key))
        return result
    return {prefix:value}


def refresh(design,b,backup):
    folder=b.OUT/design;cad=b.CAD/design
    data=json.loads((folder/"assembly.json").read_text())
    old_parameters=deepcopy(data["parameters"]);new_parameters=deepcopy(b.CFG)
    old_parameters["candidates"]=[c for c in old_parameters["candidates"] if c["id"]==design]
    new_parameters["candidates"]=[c for c in new_parameters["candidates"] if c["id"]==design]
    before=leaves(old_parameters);after=leaves(new_parameters)
    changed={key for key in before.keys()|after.keys() if before.get(key)!=after.get(key)}
    allowed={"revisionId","common.legJournals.rootPocketEmbedMm","common.legJournals.loadPath"}
    if not changed<=allowed:raise ValueError("Incremental updater refuses unrelated parameter changes: "+str(changed-allowed))
    backup=backup/design;backup.mkdir(parents=True,exist_ok=True)
    for file in (folder/"assembly.json",folder/"BOM.csv",cad/f"Walker_{design}.FCStd",cad/f"Walker_{design}.step",cad/"render_geometry.json.gz"):
        shutil.copy2(file,backup/file.name)
    native=cad/f"Walker_{design}.FCStd"
    old_hash=hashlib.sha256(native.read_bytes()).hexdigest()
    print("STAGE_BEGIN root-native-open",design,flush=True)
    doc=b.App.openDocument(str(native))
    print("STAGE_END root-native-open",design,flush=True)
    try:
        def signature(shape):
            bounds=shape.BoundBox
            volume=sum(s.Volume for s in shape.Solids)
            center=sum((s.CenterOfMass*s.Volume for s in shape.Solids),b.V())/volume
            return np.array([volume,*list(center),*[getattr(bounds,k) for k in
                ("XMin","XMax","YMin","YMax","ZMin","ZMax")],len(shape.Solids),len(shape.Faces),len(shape.Edges)])
        untouched={i["name"]:signature(doc.getObject(i["name"]).Shape) for i in data["instances"]
                   if not i["part_id"].startswith("P_CRANK_JOURNAL_")}
        meshes=json.loads(gzip.decompress((cad/"render_geometry.json.gz").read_bytes()))
        changed_parts=[];definitions=type("Definitions",(),{"id":design,"defs":{}})()
        for pid,part in list(data["parts"].items()):
            if not pid.startswith("P_CRANK_JOURNAL_"):continue
            side,phase=pid.rsplit("_",2)[-2:]
            shape=b.left_crank(math.radians(float(phase))) if side=="-1" else b.main_crank(1,math.radians(float(phase)))
            b.Whole.define(definitions,pid,shape,"printed",part["spec"],density=b.C["materials"]["printedDensityGcm3"])
            updated=definitions.defs[pid]
            data["parts"][pid]={k:v for k,v in updated.items() if k!="shape"}
            for item in data["instances"]:
                if item["part_id"]!=pid:continue
                feature=doc.getObject(item["name"])
                feature.Shape=shape
                feature.Placement=b.App.Placement(b.App.Matrix(*np.array(item["transform"]).ravel().tolist())).multiply(feature.Placement)
                feature.NominalMassGram=updated["mass_g"]
            vertices,triangles=shape.tessellate(.16)
            meshes[pid]={"vertices":[list(v) for v in vertices],"triangles":triangles,"category":"printed"}
            printable=shape.copy();printable.translate(b.V(0,0,-printable.BoundBox.ZMin))
            b.MeshPart.meshFromShape(Shape=printable,LinearDeflection=.12,AngularDeflection=.18,Relative=False).write(str(b.PRINT/design/(pid+".stl")))
            changed_parts.append({"partId":pid,"beforeMassG":part["mass_g"],"afterMassG":updated["mass_g"]})
        for item in data["instances"]:
            feature=doc.getObject(item["name"]);feature.RevisionId=b.CFG["revisionId"]
        doc.recompute()
        if any(not np.allclose(signature(doc.getObject(name).Shape),values,rtol=1e-12,atol=1e-8)
               for name,values in untouched.items()):
            raise RuntimeError("An unrelated native shape changed during the incremental update")
        data["incrementalGeometryUpdate"]={"kind":"A-pin socket-mouth boss only; no shifted linkage centers",
            "previousRevisionId":data["revisionId"],"previousNativeSha256":old_hash,
            "previousBuildInputSha256":data["buildInputSha256"],"changedParts":changed_parts,
            "unchangedNativeShapesChecked":len(untouched),"check":"volume,centroid,bounds,solid/face/edge counts unchanged; OCC object-identity hashes are not geometric hashes",
            "backupDirectory":str(backup),"fullExportReverified":False}
        data["revisionId"]=b.CFG["revisionId"];data["parameters"]=deepcopy(b.CFG)
        data["buildInputSha256"]=b.BUILD_HASHES;data.pop("nativeStepStatus",None)
        data["fullAssemblyVerification"]="IN_PROGRESS"
        total=0.;printed=0.;moment=np.zeros(3)
        for item in data["instances"]:
            part=data["parts"][item["part_id"]];mass=part["mass_g"]
            total+=mass;moment+=mass*(np.array(item["transform"])@np.r_[part["local_com_mm"],1])[:3]
            if part["category"]=="printed":printed+=mass
        data.update(nominalTotalMassG=total,nominalPrintedMassG=printed,nominalCenterOfMassMm=(moment/total).tolist())
        temporary=cad/f"Walker_{design}.root-update.FCStd";doc.saveAs(str(temporary));temporary.replace(native)
        print("STAGE_END root-native",design,flush=True)
        b.Part.export([o for o in doc.Objects if o.TypeId=="Part::Feature"],str(cad/f"Walker_{design}.step"))
        print("STAGE_END root-step",design,flush=True)
        (cad/"render_geometry.json.gz").write_bytes(gzip.compress(json.dumps(meshes,separators=(",",":")).encode(),mtime=0))
        (folder/"assembly.json").write_text(json.dumps(data,indent=2)+"\n")
        count=Counter(i["part_id"] for i in data["instances"])
        with (folder/"BOM.csv").open("w",newline="") as stream:
            writer=csv.writer(stream,lineterminator="\n")
            writer.writerow(["part_id","category","quantity","sku","unit_nominal_mass_g","total_nominal_mass_g","basis","spec"])
            for pid,part in data["parts"].items():
                writer.writerow([pid,part["category"],count[pid],part["sku"],part["mass_g"],count[pid]*part["mass_g"],part["mass_basis"],part["spec"]])
    finally:
        b.App.closeDocument(doc.Name)
    from verify_integrated_exports import verify
    print("STAGE_BEGIN root-native-step-check",design,flush=True)
    verify(design,b.ROOT)
    data=json.loads((folder/"assembly.json").read_text())
    data["incrementalGeometryUpdate"]["fullExportReverified"]=True
    data["incrementalGeometryUpdate"].pop("backupDirectory")
    (folder/"assembly.json").write_text(json.dumps(data,indent=2)+"\n")
    print("STAGE_END root-refresh",design,data["nominalTotalMassG"],flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freecad-lib",required=True)
    parser.add_argument("--designs",nargs="+",required=True)
    parser.add_argument("--backup",type=Path,required=True)
    options=parser.parse_args()
    sys.argv=[sys.argv[0],"--freecad-lib",options.freecad_lib]
    import build_integrated_walkers as builder
    for design in options.designs:refresh(design,builder,options.backup)
