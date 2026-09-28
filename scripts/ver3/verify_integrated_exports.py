"""Native/STEP B-rep correspondence, distinct from assembly or physics approval."""

import argparse
import json
from pathlib import Path
import sys

import numpy as np


def verify(design,root):
    import FreeCAD as App
    import Part
    out=root/"docs/ver3/integrated_r7"/design
    cad=root/"FreeCAD/Ver.3/integrated_r7"/design
    manifest=json.loads((out/"assembly.json").read_text())
    print("STAGE_BEGIN verify-native-open",design,flush=True)
    doc=App.openDocument(str(cad/f"Walker_{design}.FCStd"))
    try:
        objects=[o for o in doc.Objects if o.TypeId=="Part::Feature"]
        if len(objects)!=len(manifest["instances"]):
            raise RuntimeError("Native object count differs from canonical instances")
        for index,(item,obj) in enumerate(zip(manifest["instances"],objects)):
            if index%100==0:print("STAGE_BEGIN verify-native-solids",design,index,flush=True)
            if obj.PartId!=item["part_id"] or not obj.Shape.isValid():
                raise RuntimeError("Native part correspondence/validity failed: "+obj.Name)
            if item["name"]!=obj.Name:
                item["requestedName"]=item["name"]
                item["name"]=obj.Name
        source=[(o.Name,s) for o in objects for s in o.Shape.Solids]
        print("STAGE_BEGIN verify-step-open",design,flush=True)
        exchange=Part.read(str(cad/f"Walker_{design}.step"))
        target=exchange.Solids
        if len(source)!=len(target) or not exchange.isValid() or any(not s.isValid() for s in target):
            raise RuntimeError("STEP solid count or validity failed")
        rows=[];surface=[]
        keys=("XMin","XMax","YMin","YMax","ZMin","ZMax")
        for index,((name,s),t) in enumerate(zip(source,target)):
            if index%100==0:print("STAGE_BEGIN verify-correspondence",design,index,flush=True)
            bounds=max(abs(getattr(s.BoundBox,k)-getattr(t.BoundBox,k)) for k in keys)
            relative=abs(t.Volume-s.Volume)/s.Volume
            if bounds>1e-4 or relative>5e-5:
                raise RuntimeError(f"STEP changes solid dimensions or volume: {name},{bounds},{relative}")
            rows.append({"nativeName":name,"boundsDeltaMaxMm":bounds,"nativeVolumeMm3":s.Volume,
                         "stepVolumeMm3":t.Volume,"relativeVolumeDifference":relative})
            if relative>1e-6:
                maxima=[]
                for first,second in ((s,t),(t,s)):
                    points=[v.Point for v in first.Vertexes]
                    points += [e.valueAt((e.FirstParameter+e.LastParameter)/2) for e in first.Edges]
                    samples=np.linspace(0,len(points)-1,min(120,len(points)),dtype=int)
                    maximum=max(second.distToShape(Part.Vertex(points[i]))[0] for i in samples)
                    maxima.append(maximum)
                    if maximum>1e-4:raise RuntimeError("STEP B-rep surface mismatch: "+name)
                surface.append({"nativeName":name,"bidirectionalSampleMaximumMm":maxima,
                                "samplesPerDirection":120,"method":"actual vertices/edge parameters to B-rep surfaces,not a mesh replacement"})
        native_volume=sum(s.Volume for _,s in source)
        step_volume=sum(s.Volume for s in target)
        relative=abs(step_volume-native_volume)/native_volume
        if relative>1e-5:raise RuntimeError("Whole STEP volume error exceeds the integration tolerance")
        native_mass=sum(o.NominalMassGram for o in objects)
        if abs(native_mass-manifest["nominalTotalMassG"])>1e-7:
            raise RuntimeError("Mass property sum differs from canonical BOM")
        summary={"designId":design,"nativeObjects":len(objects),"nativeSolids":len(source),
                 "stepSolids":len(target),"nativeVolumeBySolidsMm3":native_volume,
                 "stepVolumeBySolidsMm3":step_volume,"totalRelativeVolumeDifference":relative,
                 "maximumBoundsDifferenceMm":max(r["boundsDeltaMaxMm"] for r in rows),
                 "surfaceChecks":surface,"massG":native_mass,"printedMassG":manifest["nominalPrintedMassG"],
                 "nominalCogMm":manifest["nominalCenterOfMassMm"],
                 "tolerances":{"totalVolumeRelative":1e-5,"perSolidVolumeRelative":5e-5,"boundsAndSurfaceMm":1e-4},
                 "reasonForIntegrationTolerance":"Captured valid native and STEP chassis have coincident B-rep surfaces but differ by about1.76mm3 in default volume integration; all bodies,dimensions and representative surfaces are checked separately.",
                 "nativeStepStatus":"PASS","assemblyInterferenceStatus":"NOT_YET_QUALIFIED",
                 "manufacturingOrPhysicalApproval":False}
        (out/"step_correspondence.json").write_text(json.dumps(rows,indent=2)+"\n")
        (out/"cad_validation.json").write_text(json.dumps(summary,indent=2)+"\n")
        manifest["nativeStepStatus"]="PASS"
        (out/"assembly.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
        print(json.dumps({k:summary[k] for k in ("designId","nativeObjects","nativeSolids",
              "stepSolids","totalRelativeVolumeDifference","massG","nominalCogMm","nativeStepStatus")}),flush=True)
        return summary
    finally:
        App.closeDocument(doc.Name)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freecad-lib",required=True)
    parser.add_argument("--design",required=True,choices=("A","B","C"))
    args=parser.parse_args()
    sys.path.insert(0,args.freecad_lib)
    verify(args.design,Path(__file__).resolve().parents[2])
