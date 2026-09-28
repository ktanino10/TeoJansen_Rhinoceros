"""Small controls for offline profile and actual-extrusion inspection."""

import json
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from export_integrated_prints import support_may_be_required
from inspect_integrated_toolpaths import parse_gcode, parse_gcode_lines, point_clearance, Segment
from slice_integrated_representatives import flatten_profile, verify_effective
from walker_geometry import OUT
from verify_integrated_package import validate_slicing


class SlicingInspectionTests(unittest.TestCase):
    def test_leaf_profile_inheritance_is_resolved_without_mutating_bundled_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/"process").mkdir()
            base=root/"process/base.json"; leaf=root/"process/leaf.json"
            base.write_text(json.dumps({"name":"base","layer_height":"0.16","wall_loops":"2"}))
            leaf.write_text(json.dumps({"name":"leaf","inherits":"base","wall_loops":"4"}))
            result, sources=flatten_profile(root,"process","leaf")
            self.assertEqual(result,{"name":"leaf","layer_height":"0.16","wall_loops":"4"})
            self.assertEqual(len(sources),2)
            self.assertEqual(json.loads(leaf.read_text())["inherits"],"base")

    def test_profile_names_alone_do_not_prove_the_effective_material(self):
        with self.assertRaisesRegex(ValueError,"Effective setting mismatch"):
            verify_effective({"printer_model":"Bambu Lab P1S","filament_settings_id":["Generic PETG"],
                              "filament_type":["PLA"]},False)

    def test_only_actual_positive_xy_extrusion_is_counted(self):
        text="""; total layer number: 1
; extruder_offset = 0x2
G90
M83
G1 X0 Y0 Z0.2
; CHANGE_LAYER
; Z_HEIGHT: 0.2
; LAYER_HEIGHT: 0.2
; FEATURE: Outer wall
; LINE_WIDTH: 0.4
G1 X10 Y0 E1
G1 X11 E-0.5
G1 E0.5
M82
G92 E0
G1 X11 Y1 E0.2
; FEATURE: Custom
G1 X100 Y100 E100
"""
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"control.gcode"; path.write_text(text)
            layers,_=parse_gcode(path)
        self.assertEqual(len(layers),1)
        self.assertEqual(len(layers[0].segments),2)
        self.assertAlmostEqual(sum(s.extrusion for s in layers[0].segments),1.2)
        self.assertEqual(layers[0].segments[0].start,(0,2))
        self.assertEqual(layers[0].segments[0].end,(10,2))

    def test_full_circle_extrusion_cannot_silently_disappear(self):
        text="""; total layer number: 1
; extruder_offset = 0x0
M83
; CHANGE_LAYER
; Z_HEIGHT: 0.2
; LAYER_HEIGHT: 0.2
; FEATURE: Outer wall
; LINE_WIDTH: 0.4
G2 I1 J0 E1
"""
        with self.assertRaisesRegex(ValueError,"Extruding arcs"):
            parse_gcode_lines(text.splitlines())

    def test_bore_check_uses_bead_width_not_just_its_centerline(self):
        segment=Segment((1,-1),(1,1),.4,1,"Outer wall")
        self.assertAlmostEqual(point_clearance([segment],(0,0)),.8)

    def test_support_flag_follows_the_existing_bed_pose(self):
        for name,expected in (("A",True),("B",False),("C",True)):
            assembly=json.loads((OUT/name/"assembly.json").read_text())
            printing=json.loads((OUT/name/"print_geometry.json").read_text())
            row=next(r for r in printing["printedParts"] if r["partId"]=="P_INPUT_PINION")
            shift=next(p[1] for p in row["rigidBedTransforms"] if p[0]=="translateZ")
            self.assertEqual(support_may_be_required("P_INPUT_PINION",assembly,shift),expected)
            self.assertEqual(row["supportsMayBeRequired"],expected)

    def test_known_support_film_cannot_be_labeled_support_free(self):
        status=json.loads((OUT/"slicing_status.json").read_text())
        checks=json.loads((OUT/"slicing/toolpath_checks.json").read_text())
        provenance=json.loads((OUT/"slicing/profile_provenance.json").read_text())
        validate_slicing(status,checks,provenance)
        wrong=deepcopy(status);wrong["allSupportFreeBores"]=True
        with self.assertRaisesRegex(ValueError,"Support removal"):
            validate_slicing(wrong,checks,provenance)


if __name__=="__main__":
    unittest.main()
