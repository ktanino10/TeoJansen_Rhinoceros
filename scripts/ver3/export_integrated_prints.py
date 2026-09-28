"""Final rigid bed poses, fine STL meshes and 1:1 PET templates from native CAD."""

import argparse
import hashlib
import html
import json
import math
from pathlib import Path
import sys

import numpy as np

from walker_geometry import ROOT,OUT,CAD,PRINT,body_points


def export(design,library):
    sys.path.insert(0,library)
    import FreeCAD as App
    import MeshPart
    data=json.loads((OUT/design/"assembly.json").read_text())
    native=CAD/design/f"Walker_{design}.FCStd"
    doc=App.openDocument(str(native))
    try:
        c=data["parameters"]["common"];rows=[];templates=[]
        representatives={}
        for item in data["instances"]:representatives.setdefault(item["part_id"],item)
        for pid,item in representatives.items():
            part=data["parts"][pid]
            if part["category"] not in ("printed","sheet_cut"):continue
            shape=doc.getObject(item["name"]).Shape.copy()
            inverse=App.Placement(App.Matrix(*np.linalg.inv(np.array(item["transform"])).ravel().tolist()))
            shape.Placement=inverse.multiply(shape.Placement)
            if part["category"]=="sheet_cut":
                x=(shape.BoundBox.XMin+shape.BoundBox.XMax)/2
                wires=shape.slice(App.Vector(1,0,0),x)
                if not wires:raise ValueError("Empty PET section "+pid)
                box=shape.BoundBox;paths=[]
                for wire in wires:
                    points=wire.discretize(Deflection=.02)
                    commands=[f'{8+p.y-box.YMin:.5f},{28+box.ZMax-p.z:.5f}' for p in points]
                    paths.append("M"+"L".join(commands)+"Z")
                svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="297mm" height="420mm" viewBox="0 0 297 420">
<rect width="297" height="420" fill="white"/>
<text x="8" y="10" font-size="4">{html.escape(design+" "+pid)}</text>
<text x="8" y="17" font-size="3">PET 0.5 mm / A3 / 100% / no fit-to-page / outline-center cut</text>
<text x="8" y="23" font-size="3">native B-rep section; arc chord deflection 0.02 mm; not a release to manufacture</text>
<path d="{' '.join(paths)}" fill="none" fill-rule="evenodd" stroke="#124f8f" stroke-width="0.18"/>
<path d="M8,{38+box.ZLength:.3f}h50m-50,-1v2m50,-2v2" stroke="black" stroke-width="0.2"/>
<text x="8" y="{44+box.ZLength:.3f}" font-size="3">50 mm calibration bar</text>
</svg>'''
                path=OUT/design/(pid+"_cut.svg");path.write_text(svg+"\n")
                templates.append({"partId":pid,"svg":str(path.relative_to(ROOT)),
                                  "thicknessMm":box.XLength,"outlineWidthMm":box.YLength,
                                  "outlineHeightMm":box.ZLength,"scale":1,"chordDeflectionMm":.02})
                continue
            pose=[]
            if pid.startswith("P_CHASSIS_"):
                degrees=90 if pid.endswith("_L") else -90
                shape.rotate(App.Vector(),App.Vector(0,1,0),degrees);pose.append(["rotateY",degrees])
            elif pid=="P_ROTOR_CAGE_CAP":
                shape.rotate(App.Vector(),App.Vector(1,0,0),180);pose.append(["rotateX",180])
            elif pid.startswith(("P_LEG_","P_CRANK_JOURNAL","P_COMPOUND","P_SYNC_","P_OUTPUT_WHEEL",
                                 "P_INPUT_PINION","P_INTER_STOP","P_MAIN_INNER_STOP")):
                degrees=90 if pid.endswith("_L") or pid.startswith("P_CRANK_JOURNAL_-1") else -90
                shape.rotate(App.Vector(),App.Vector(0,1,0),degrees);pose.append(["rotateY",degrees])
            elif pid.startswith("P_FOOT_"):
                p=body_points(0,common=c)
                gamma=math.atan2(*(p["E"]-p["C"])[::-1])-math.radians(c["foot"]["pitchReferenceBodyAngleDeg"])
                co,si=math.cos(gamma),math.sin(gamma);shift=c["foot"]["toeOffsetFromFNeutralMm"][0]
                side=-1 if pid.endswith("_L") else 1
                foot=np.eye(4);foot[:3,:3]=[[1,0,0],[0,co,-si],[0,si,co]]
                foot[:3,3]=[side*c["foot"]["centerAbsXmm"],p["F"][0]+co*shift,p["F"][1]+si*shift]
                change=App.Placement(App.Matrix(*np.linalg.inv(foot).ravel().tolist()))
                shape.Placement=change.multiply(shape.Placement)
                pose.append(["inverseReferenceFootPose",foot.tolist()])
            shift=-shape.BoundBox.ZMin
            shape.translate(App.Vector(0,0,shift));pose.append(["translateZ",shift])
            path=PRINT/design/(pid+".stl")
            MeshPart.meshFromShape(Shape=shape,LinearDeflection=.04,AngularDeflection=.08,Relative=False).write(str(path))
            box=shape.BoundBox
            rows.append({"partId":pid,"stl":str(path.relative_to(ROOT)),"rigidBedTransforms":pose,
                         "boundsMm":[box.XLength,box.YLength,box.ZLength],
                         "nativeVolumeMm3":part["solid_volume_mm3"],
                         "linearDeflectionMm":.04,"angularDeflectionRad":.08,
                         "supportsMayBeRequired":pid.startswith(("P_CHASSIS","P_COMPOUND","P_LEG_CEF","P_FOOT","P_CRANK")),
                         "sliced":False})
        result={"revisionId":data["revisionId"],"designId":design,
                "nativeSha256":hashlib.sha256(native.read_bytes()).hexdigest(),
                "printedParts":rows,"sheetTemplates":templates,
                "noScalingOrMeshRepairApplied":True,"actualSlicingPerformed":False}
        (OUT/design/"print_geometry.json").write_text(json.dumps(result,indent=2)+"\n")
        print(design,"fine STL",len(rows),"PET templates",len(templates),flush=True)
    finally:
        App.closeDocument(doc.Name)


def verify(design):
    import trimesh
    import fitz
    path=OUT/design/"print_geometry.json";data=json.loads(path.read_text())
    native=CAD/design/f"Walker_{design}.FCStd"
    if hashlib.sha256(native.read_bytes()).hexdigest()!=data["nativeSha256"]:
        raise ValueError("Native changed after print export")
    errors=[]
    for row in data["printedParts"]:
        file=ROOT/row["stl"];mesh=trimesh.load_mesh(file)
        relative=abs(mesh.volume-row["nativeVolumeMm3"])/row["nativeVolumeMm3"]
        row.update({"watertight":bool(mesh.is_watertight),"volumeRelativeDifference":relative,
                    "meshExtentMm":mesh.extents.tolist(),"sha256":hashlib.sha256(file.read_bytes()).hexdigest()})
        if not mesh.is_watertight or relative>.002:errors.append(row["partId"])
    for row in data["sheetTemplates"]:
        file=ROOT/row["svg"];pdf=file.with_suffix(".pdf")
        with fitz.open(stream=file.read_bytes(),filetype="svg") as document:
            pdf.write_bytes(document.convert_to_pdf())
        with fitz.open(pdf) as document:
            size=[document[0].rect.width*25.4/72,document[0].rect.height*25.4/72]
        if not np.allclose(size,[297,420],atol=.05):raise ValueError("PET template is not1:1 A3")
        row.update({"pdf":str(pdf.relative_to(ROOT)),"pdfPageMm":size,"pdfSha256":hashlib.sha256(pdf.read_bytes()).hexdigest()})
    data["geometryStatus"]="FAIL" if errors else "PASS";data["meshFailures"]=errors
    path.write_text(json.dumps(data,indent=2)+"\n")
    print(design,data["geometryStatus"],"unqualified slicing kept separate")
    if errors:raise ValueError("Fine print geometry failed: "+", ".join(errors))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--designs",nargs="+",required=True)
    parser.add_argument("--mode",choices=("export","verify"),required=True)
    parser.add_argument("--freecad-lib")
    options=parser.parse_args()
    if options.mode=="export" and not options.freecad_lib:parser.error("--freecad-lib is required for export")
    for design in options.designs:
        export(design,options.freecad_lib) if options.mode=="export" else verify(design)
