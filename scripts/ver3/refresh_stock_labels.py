"""Metadata-only native/STEP labels: stable instance IDs are not part dimensions."""

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

from walker_geometry import OUT,CAD


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def shape_members(path):
    with zipfile.ZipFile(path) as archive:
        return {name:hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist()
                if name.lower().endswith((".brp",".brep"))}


def update(design,library):
    sys.path.insert(0,library)
    import FreeCAD as App
    folder=OUT/design;native=CAD/design/f"Walker_{design}.FCStd";step=CAD/design/f"Walker_{design}.step"
    data=json.loads((folder/"assembly.json").read_text())
    old_assembly=sha(folder/"assembly.json")
    old_native=sha(native);old_step=sha(step);before_shapes=shape_members(native)
    if not before_shapes:raise ValueError("No serialized native shapes available for label-only proof")
    doc=App.openDocument(str(native));changes={};by_name={}
    try:
        before_placements={i["name"]:list(doc.getObject(i["name"]).Placement.toMatrix().A) for i in data["instances"]}
        for item in data["instances"]:
            if item["motion"].get("piece")!="ROCKER_PIN":continue
            if item["part_id"] not in ("H_BOLT_M2_12","H_LOCK_NUT_M2","H_WASHER_4_SMALL"):continue
            obj=doc.getObject(item["name"]);label=item["part_id"]+"_"+item["name"].rsplit("_",1)[-1]
            if obj.Label!=label:
                changes[obj.Label]=label;obj.Label=label
                by_name[item["name"]]=label
                data.setdefault("nativeLabelOverrides",{})[item["name"]]=label
        if not changes:return
    finally:App.closeDocument(doc.Name)
    with tempfile.NamedTemporaryFile(prefix=native.stem+".labels-",suffix=".FCStd",dir=native.parent,delete=False) as stream:
        temporary=Path(stream.name)
    with zipfile.ZipFile(native) as old_archive:
        root=ET.fromstring(old_archive.read("Document.xml"))
        original=ET.tostring(root)
        old_labels={}
        for name,label in by_name.items():
            node=root.find(f"./ObjectData/Object[@name='{name}']/Properties/Property[@name='Label']/String")
            if node is None:raise ValueError("Missing native label property")
            old_labels[name]=node.get("value")
            node.set("value",label)
        restored_tree=deepcopy(root)
        for name in by_name:
            node=restored_tree.find(f"./ObjectData/Object[@name='{name}']/Properties/Property[@name='Label']/String")
            node.set("value",old_labels[name])
        if ET.tostring(restored_tree)!=original:raise ValueError("Native XML changed beyond the selected labels")
        with zipfile.ZipFile(temporary,"w") as updated:
            for info in old_archive.infolist():
                blob=ET.tostring(root,encoding="utf-8",xml_declaration=True) if info.filename=="Document.xml" else old_archive.read(info.filename)
                updated.writestr(info,blob)
    if before_shapes!=shape_members(temporary):
        raise ValueError("Native geometry serialization changed during a label-only update")
    reopened=App.openDocument(str(temporary))
    try:
        for item in data["instances"]:
            obj=reopened.getObject(item["name"])
            if obj.PartId!=item["part_id"] or not np.array_equal(list(obj.Placement.toMatrix().A),before_placements[item["name"]]):
                raise ValueError("Label-only update changed a part or placement")
    finally:App.closeDocument(reopened.Name)
    old_text=step.read_text();new_text=old_text
    for before,after in changes.items():new_text=new_text.replace("'"+before+"'","'"+after+"'")
    restored=new_text
    for before,after in changes.items():restored=restored.replace("'"+after+"'","'"+before+"'")
    if restored!=old_text:raise ValueError("STEP changes were not limited to product labels")
    if sha(native)!=old_native or sha(step)!=old_step or sha(folder/"assembly.json")!=old_assembly:
        raise ValueError("A source artifact changed concurrently during metadata preparation")
    temporary.replace(native)
    if new_text!=old_text:step.write_text(new_text)
    new_native=sha(native)
    proof={"designId":design,"oldNativeSha256":old_native,"newNativeSha256":new_native,
           "oldStepSha256":old_step,"newStepSha256":sha(step),
           "changedLabels":changes,"serializedNativeShapeMembersUnchanged":True,
           "partIdsAndPlacementsUnchanged":True,"nativeXmlOnlySelectedLabelsChanged":True,
           "stepProductLabelsChanged":new_text!=old_text,"stepGeometryTextUnchanged":True,
           "geometryOrPhysicalValuesChanged":False,
           "scope":"Only human-facing labels corrected after replacing16mm/cut bolts and large washers. Stable instance IDs remain unchanged; no new geometric verification or independent review is claimed."}
    data["stockLabelMetadataUpdate"]=proof
    (folder/"assembly.json").write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")
    def replace(value):
        changed=False
        if isinstance(value,dict):
            for key,item in value.items():
                if key=="nativeSha256" and item==old_native:value[key]=new_native;changed=True
                else:changed=replace(item) or changed
        elif isinstance(value,list):
            for item in value:changed=replace(item) or changed
        return changed
    for path in folder.glob("*.json"):
        if path.name=="assembly.json":continue
        value=json.loads(path.read_text())
        if replace(value):
            value["nativeLabelOnlyUpdateProof"]="stock_label_metadata_update.json"
            path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n")
    (folder/"stock_label_metadata_update.json").write_text(json.dumps(proof,indent=2)+"\n")
    print(design,"labels",len(changes),"serialized geometry and placements unchanged",flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freecad-lib",required=True)
    parser.add_argument("--designs",nargs="+",required=True)
    args=parser.parse_args()
    for design in args.designs:update(design,args.freecad_lib)
