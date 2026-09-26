"""Independent geometric checks against exported native solids, not render meshes."""

import argparse
import json
from pathlib import Path
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument("--freecad-lib", type=Path)
parser.add_argument("--only", default="A", choices=["A", "B", "C"])
args = parser.parse_args()
if args.freecad_lib:
    sys.path.insert(0, str(args.freecad_lib))
import FreeCAD as App
from core import ROOT, OUT, dump

manifest = json.loads((OUT / f"assembly_{args.only}.json").read_text())
document = App.openDocument(str(ROOT / "FreeCAD" / "Ver.3" / args.only / f"Ver3_{args.only}.FCStd"))
objects = [o for o in document.Objects if o.TypeId == "Part::Feature"]
collisions = []
tested = 0
started = time.monotonic()
for i, first in enumerate(objects):
    first_printed = first.Category == "printed"
    box = first.Shape.BoundBox
    for second in objects[i + 1:]:
        if not first_printed and second.Category != "printed":
            continue
        other_box = second.Shape.BoundBox
        if (box.XMax <= other_box.XMin + 1e-5 or other_box.XMax <= box.XMin + 1e-5
                or box.YMax <= other_box.YMin + 1e-5 or other_box.YMax <= box.YMin + 1e-5
                or box.ZMax <= other_box.ZMin + 1e-5 or other_box.ZMax <= box.ZMin + 1e-5):
            continue
        tested += 1
        common = first.Shape.common(second.Shape)
        if common.Volume > 0.05:
            item = {"first": first.Name, "second": second.Name, "volume_mm3": common.Volume}
            collisions.append(item)
            print(json.dumps(item), flush=True)
result = dict(prototype=args.only, native_printed_vs_all_pairs_tested=tested,
              intersections_over_0_05_mm3=collisions,
              seconds=time.monotonic() - started,
              scope="Assembled theta=0; every printed part versus every CAD solid with intersecting AABB. Excludes purchased/purchased thread-envelope interference. Full motion checked separately.")
dump(OUT / f"intersections_{args.only}.json", result)
print("RESULT", tested, len(collisions), "seconds", result["seconds"], flush=True)
if collisions:
    sys.exit(1)
