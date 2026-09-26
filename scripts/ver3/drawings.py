"""Actual B-rep sections and one-to-one purchased-sheet drilling templates."""

import argparse
from html import escape
import json
import math
from pathlib import Path
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--freecad-lib", type=Path)
args = parser.parse_args()
if args.freecad_lib:
    sys.path.insert(0, str(args.freecad_lib))
import FreeCAD as App
import Part

from core import CONFIG, ROOT, OUT, LINKS, gait

DRAW = OUT/"drawings"
DRAW.mkdir(parents=True, exist_ok=True)
for ident in "ABC":
    for name in (f"gear_section_{ident}.svg", f"window_pattern_{ident}.svg"):
        obsolete = DRAW/name
        if obsolete.exists():
            obsolete.unlink()


def ink(obj):
    if any(word in obj.Name for word in ("PINION", "WHEEL", "PULLEY")):
        return "#b47a00"
    if obj.Category == "printed":
        return "#146b75"
    return "#964fa3" if "608" in obj.Name else "#475569"


def svg(name, body, box, width=1100, height=720):
    (DRAW/name).write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="{box}">'
        '<style>text{font-family:Arial,sans-serif} path,circle,line,rect{vector-effect:non-scaling-stroke}</style>'
        +body+"</svg>\n")


def section_paths(objects, face, project):
    paths = []
    for obj in objects:
        cut = obj.Shape.section(face)
        for edge in cut.Edges:
            points = [project(v) for v in edge.discretize(Deflection=0.15)]
            if len(points) < 2:
                continue
            path = "M"+" L".join(f"{x:.5f},{y:.5f}" for x, y in points)
            paths.append(f'<path d="{path}" fill="none" stroke="{ink(obj)}" stroke-width="0.6"><title>{escape(obj.Name)}</title></path>')
    return "".join(paths)


def make_section(name, title, objects, corners, project, bounds):
    face = Part.Face(Part.makePolygon(corners+[corners[0]]))
    x0, x1, y0, y1 = bounds
    body = f'<rect x="{x0-10}" y="{y0-16}" width="{x1-x0+20}" height="{y1-y0+30}" fill="white"/>'
    body += f'<text x="{x0}" y="{y0-7}" font-size="4">{escape(title)}</text>'
    body += section_paths(objects, face, project)
    body += f'<text x="{x0}" y="{y1+8}" font-size="3">mm / actual native-solid section. Purchased tooth profiles may be envelopes. Not manufacturing tolerances.</text>'
    svg(name, body, f"{x0-10} {y0-16} {x1-x0+20} {y1-y0+30}")


for ident in "ABC":
    manifest = json.loads((OUT/f"assembly_{ident}.json").read_text())
    design = manifest["design"]
    span = CONFIG["linkage"]["bay_count"]*CONFIG["linkage"]["bay_pitch"]
    height = CONFIG["linkage"]["crank_height"]
    doc = App.openDocument(str(ROOT/"FreeCAD"/"Ver.3"/ident/f"Ver3_{ident}.FCStd"))
    objects = [obj for obj in doc.Objects if obj.TypeId == "Part::Feature"]
    crank_objects = [obj for obj in objects if obj.Shape.BoundBox.XMin < 100 and obj.Shape.BoundBox.XMax > -18
                     and obj.Shape.BoundBox.ZMin <= height <= obj.Shape.BoundBox.ZMax]
    make_section(f"crank_section_{ident}.svg", f"{ident} / first paired crank module / Z=150 mm",
                 crank_objects, [App.Vector(x, y, height) for x, y in ((-18, -82), (100, -82), (100, 82), (-18, 82))],
                 lambda v: (v.x, -v.y), (-18, 100, -82, 82))
    for index, stage in enumerate(design["stages"]):
        left = stage["side"] == "left"
        near = -stage["body_offset"] if left else span+stage["body_offset"]
        x = near-6 if stage["type"] == "belt" else near+(-4 if left else 4)
        bounds = design["case"][stage["side"]]["stages"][str(index)]["bounds"]
        y0, y1, z0, z1 = bounds
        selected = [obj for obj in objects if obj.Shape.BoundBox.XMin <= x <= obj.Shape.BoundBox.XMax]
        title = f"{ident} {stage['id']} / {stage['type']} {stage['pinion_teeth']}:{stage['wheel_teeth']} / X={x:g}"
        make_section(f"stage_{ident}_{stage['id']}.svg", title, selected,
                     [App.Vector(x, y, z+height) for y, z in ((y0, z0), (y1, z0), (y1, z1), (y0, z1))],
                     lambda v: (v.y, height-v.z), (y0, y1, -z1, -z0))

        window = next(obj for obj in objects if obj.PartId == f"S_WINDOW_{index+1}")
        local = window.Shape.copy()
        local.transformShape(window.Placement.inverse().toMatrix())
        box = local.BoundBox
        if abs(box.ZMin) > 1e-5 or abs(box.ZMax-1) > 1e-5:
            raise RuntimeError("Window template was not transformed back to its true one-mm local solid")
        face = Part.Face(Part.makePolygon([
            App.Vector(box.XMin-1, box.YMin-1, 0.5), App.Vector(box.XMax+1, box.YMin-1, 0.5),
            App.Vector(box.XMax+1, box.YMax+1, 0.5), App.Vector(box.XMin-1, box.YMax+1, 0.5),
            App.Vector(box.XMin-1, box.YMin-1, 0.5)]))
        lines = []
        for edge in local.section(face).Edges:
            points = [(p.x-box.XMin+10, box.YMax-p.y+10) for p in edge.discretize(Deflection=0.05)]
            path = "M"+" L".join(f"{x:.5f},{y:.5f}" for x, y in points)
            lines.append(f'<path d="{path}" fill="none" stroke="black" stroke-width="0.35"/>')
        width, length = box.XLength, box.YLength
        body = "".join(lines)
        body += f'<text x="10" y="{length+18}" font-size="3">{ident} {stage["id"]} / PETG sheet1mm / {width:.3f} x {length:.3f} / print100%</text>'
        body += f'<line x1="10" y1="{length+25}" x2="60" y2="{length+25}" stroke="black" stroke-width="0.4"/>'
        body += f'<text x="65" y="{length+26}" font-size="3">50mm calibration line; verify with ruler.</text>'
        legend = f"Shaft holes:{stage['window_aperture_mm']} / cover holes:3.3 / case rods:10.4 mm"
        if stage["type"] == "belt":
            legend += f" / 4 carriage holes:{stage['carriage_screw_window_bore_mm']} mm"
        body += f'<text x="10" y="{length+33}" font-size="2.7">{escape(legend)}</text>'
        svg(f"window_pattern_{ident}_{stage['id']}.svg", body, f"0 0 {width+20} {length+39}",
            f"{width+20}mm", f"{length+39}mm")
    App.closeDocument(doc.Name)

body = '<rect x="-145" y="-160" width="290" height="325" fill="white"/>'
body += '<text x="-136" y="-146" font-size="6">Ver.3 / opposed closed Jansen linkage</text>'
body += '<text x="-136" y="-135" font-size="3.5">Own construction from reference length facts, scale1.4. X shaft normal to view.</text>'
for mirror, color in ((False, "#b88700"), (True, "#187b89")):
    trace = [gait(math.radians(i), mirror)["F"] for i in range(361)]
    path = "M"+" L".join(f"{p[0]:.4f},{-p[1]:.4f}" for p in trace)
    body += f'<path d="{path}" stroke="{color}" stroke-width="1" fill="none" stroke-dasharray="3 2"/>'
    points = gait(0, mirror)
    for names in LINKS.values():
        pairs = list(zip(names, names[1:]+names[:1])) if len(names) == 3 else [(names[0], names[1])]
        for a, b in pairs:
            p, q = points[a], points[b]
            body += f'<line x1="{p[0]}" y1="{-p[1]}" x2="{q[0]}" y2="{-q[1]}" stroke="{color}" stroke-width="2"/>'
    for name, point in points.items():
        body += f'<circle cx="{point[0]}" cy="{-point[1]}" r="1.6" fill="white" stroke="{color}"/>'
        body += f'<text x="{point[0]+2}" y="{-point[1]-2}" font-size="4">{name}{"R" if mirror else ""}</text>'
body += '<circle cx="0" cy="0" r="21" stroke="#64748b" fill="none"/>'
body += '<text x="-136" y="149" font-size="3.5">Three paired modules at0/180/0deg. F=foot; P=fixed pivot; O=crank axis.</text>'
body += '<text x="-136" y="157" font-size="3.5">Prescribed kinematics; no wind or contact-dynamics validation.</text>'
svg("linkage.svg", body, "-145 -160 290 325", 850, 950)
clock = math.radians(CONFIG["hardware"]["rex_clocking_degrees"])
body = '<rect width="240" height="115" fill="white"/>'
body += '<text x="8" y="12" font-size="6">REX interface datum / same square bolt pattern</text>'
for origin, flipped in ((58, False), (178, True)):
    body += f'<circle cx="{origin}" cy="55" r="32" fill="#f8fafc" stroke="#475569" stroke-width="1"/>'
    for x in (-8, 8):
        for y in (-8, 8):
            body += f'<circle cx="{origin+2*x}" cy="{55-2*y}" r="3.3" fill="white" stroke="#475569" stroke-width="1"/>'
    bore_points = [(7.08/math.sqrt(3)*math.cos(clock+i*math.pi/3),
                    7.08/math.sqrt(3)*math.sin(clock+i*math.pi/3)) for i in range(6)]
    body += f'<polygon points="{" ".join(f"{origin+2*x:.4f},{55-2*y:.4f}" for x,y in bore_points)}" fill="white" stroke="#b45309" stroke-width="1"/>'
    shaft_points = []
    normals = [clock+math.pi/6+i*math.pi/3 for i in range(6)]
    for degrees in range(361):
        angle = math.radians(degrees)
        radius = min(4, 3.5/max(math.cos(angle-normal) for normal in normals))
        shaft_points.append((origin+2*radius*math.cos(angle), 55-2*radius*math.sin(angle)))
    body += f'<polygon points="{" ".join(f"{x:.4f},{y:.4f}" for x,y in shaft_points)}" fill="#0f766e"/>'
    body += f'<text x="{origin}" y="97" text-anchor="middle" font-size="4">{"Reversed face: index +90deg" if flipped else "Normal face: corner datum15deg"}</text>'
body += '<text x="8" y="110" font-size="3.3">8mm corner diameter / 7mm across flats / 4xM4 on16mm square. Diagram enlarged; not a supplier drawing.</text>'
svg("hub_clocking.svg", body, "0 0 240 115", 1200, 575)
print("Wrote native sections and exact window templates to docs/ver3/drawings")
