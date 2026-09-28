"""Initial fit pieces and two assembly cradles, separate from walking mass."""

import csv
import json

import build_integrated_walkers as b


def main():
    root=b.ROOT
    out=b.OUT/"common";cad=b.CAD/"common";stl=b.PRINT/"common"
    for folder in (out,cad,stl):folder.mkdir(parents=True,exist_ok=True)
    parts={}
    coupon=b.Part.makeBox(104,40,5)
    holes=[(8+12*i,8,d) for i,d in enumerate((4,4.1,4.2,4.3))]
    holes += [(60+12*i,8,d) for i,d in enumerate((8,8.1,8.2))]
    holes += [(10+20*i,27,d) for i,d in enumerate((14,14.2,14.4,16,16.2))]
    for x,y,diameter in holes:coupon=b.cut(coupon,b.cylinder(diameter/2,7,x,y,-1))
    parts["T_DIAMETER_COUPON"]=(coupon,1,"Left-to-right nominal diameters are printed in accessories.json; fit gauge,not installed")
    guide=b.Part.makeBox(36,8,2)
    for i,diameter in enumerate((4.15,4.25,4.35)):
        guide=b.union([guide,b.translate(b.disk(4,13,diameter),(4+12*i,4,0))])
        guide=b.cut(guide,b.cylinder(diameter/2,15,4+12*i,4,-1))
    parts["T_GUIDE_COUPON"]=(guide,1,"Actual13mm engagement length; preserve the selected fit rather than sanding a threaded screw")
    journal=b.Part.makeBox(36,10,2)
    for i,diameter in enumerate((7.9,7.95,8)):
        x=6+12*i
        journal=b.union([journal,b.cylinder(diameter/2,7,x,5,0)])
        journal=b.cut(journal,b.translate(b.hexagon(5.12,9),(x,5,-1)))
    parts["T_JOURNAL_COUPON"]=(journal,1,"Three round-journal gauges7.90/7.95/8.00mm with the actual5.12mm-AF bore; verify steel bearing/print fit without claiming measured drag")
    cradle_parts=[b.Part.makeBox(86,48,3,b.V(-43,-24,0)),b.Part.makeBox(82,12,6,b.V(-41,-6,94))]
    for x in (-39.5,32):
        cradle_parts += [b.rod([x,0,3],[x,0,100],6),b.rod([x,-20,3],[x,0,94],6),
                         b.rod([x,20,3],[x,0,94],6),b.Part.makeBox(12,14,6,b.V(x-6,-7,98))]
    cradle=b.union(cradle_parts)
    for x in (-39.5,32):cradle=b.cut(cradle,b.Part.makeBox(6.4,16,5,b.V(x-3.2,-8,100)))
    parts["T_ASSEMBLY_CRADLE"]=(cradle,2,"Chassis-rail cradle for stationary assembly only; remove both before any floor travel")
    for teeth in (12,120):
        gear=b.cut(b.gear_disk(teeth,0),b.hex_x(5.12,-1,6))
        parts[f"T_GEAR_{teeth}"]=(gear,1,"Actual25-degree zero-shift tooth profile with shortened tips; first print/slice mesh coupon")
    doc=b.App.newDocument("R7_Assembly_Accessories")
    rows=[]
    for index,(pid,(shape,quantity,description)) in enumerate(parts.items()):
        if not shape.isValid() or len(shape.Solids)!=1:raise RuntimeError("Invalid accessory "+pid)
        feature=doc.addObject("Part::Feature",pid);feature.Shape=shape
        feature.addProperty("App::PropertyInteger","PrintQuantity","Accessory");feature.PrintQuantity=quantity
        feature.addProperty("App::PropertyString","Purpose","Accessory");feature.Purpose=description
        feature.Placement.Base+=b.V(index*150,0,0)
        printable=shape.copy()
        if pid.startswith("T_GEAR"):
            printable.rotate(b.V(),b.V(0,1,0),-90)
        printable.translate(b.V(0,0,-printable.BoundBox.ZMin))
        b.MeshPart.meshFromShape(Shape=printable,LinearDeflection=.1,AngularDeflection=.15,Relative=False).write(str(stl/(pid+".stl")))
        rows.append({"partId":pid,"quantity":quantity,"unitCadMassG":shape.Volume*1.27/1000,
                     "unitSolidVolumeMm3":shape.Volume,"purpose":description,
                     "stl":str((stl/(pid+".stl")).relative_to(root))})
    doc.recompute();doc.saveAs(str(cad/"AssemblyAccessories.FCStd"))
    b.Part.export([obj for obj in doc.Objects if obj.TypeId=="Part::Feature"],str(cad/"AssemblyAccessories.step"))
    b.App.closeDocument(doc.Name)
    reopened=b.App.openDocument(str(cad/"AssemblyAccessories.FCStd"))
    if len([o for o in reopened.Objects if o.TypeId=="Part::Feature" and o.Shape.isValid()])!=len(rows):
        raise RuntimeError("Accessory native reopen failed")
    b.App.closeDocument(reopened.Name)
    total=sum(p["quantity"]*p["unitCadMassG"] for p in rows)
    result={"revisionId":b.CFG["revisionId"],"parts":rows,"totalFirstBuildPrintedMassG":total,
            "installedWalkingMassG":0,"nativeStep":"native reopen and valid solids checked; not installed in walker export",
            "cradleRailCentersXmm":[-39.5,32],"cradleSeatHeightMm":100,
            "diameterCouponHoles":holes,
            "purchaseReuse":"Fit checks use one of the already purchased sleeves/bearings,then return it to the assembly; no new import lot",
            "physicalTestsPerformed":False}
    (out/"accessories.json").write_text(json.dumps(result,indent=2)+"\n")
    print("STAGE_END accessories",total,"g first-build material,not walking mass",flush=True)


if __name__=="__main__":main()
