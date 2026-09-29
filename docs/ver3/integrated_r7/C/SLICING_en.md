# C shifted gear pair: 2 additional slices

[日本語 (original)](SLICING_ja.md) | **English** | [Document languages](../../../README_en.md)

> Presentation-only translation of the unchanged Japanese source. Source SHA256: `620cdcfb9cb10f65e62d307b0ce2be9ef41f49a2f7e38064d5401177bdae3877`. Numbers, part IDs, equations, code and qualification limits are retained; this is not a new engineering revision.

**2 new mating C parts were actually sliced and checked for tooth count, root continuity, holes and support—not physical print/mesh qualification.** Inputs are pinned to C STLs from `f72b2cf64813978f0d31d1a1eaeb4d968948caf5`. [Previous A/common 5 samples](../SLICING_en.md) are separate unchanged records.

New first pair: m0.9, 20°, 12/156 teeth, shifts +0.35/−0.35. The compound's next 12-tooth stage uses m1/25°. Do not mix with old C or A input gears.

OrcaSlicer2.4.2; assumed P1S 0.4 mm / Generic PETG / model layer 0.16 mm / Arachne 4 walls / 100% / normal support. Actual machine/material match unverified. Official inheritance/effective values, nozzle offset and 3MF/G-code coordinate mapping were checked.

|Subject|Model / total layers with support|Material estimate|Total time estimate|Actual-layer checks|
|---|---:|---:|---:|---|
|C input pinion|219／254|1.69g|24 min 52 s|12 teeth retained, connected roots and D-bore open through all model layers|
|C compound 1|275／342|46.35g|2 h 43 min 15 s|156 and next-stage 12 teeth retained, connected spokes/roots and hex bore open through all model layers|

Software estimates under these individual conditions including support/startup, not direct whole-machine cost or physical print-time conversions.

**At the 156-tooth wheel's first supported face, Z=20.2 mm, tips recede up to about 0.052 mm from original STL outlines.** Internal Z=21 mm layers remain below 0.001 mm. This is not relabeled as the old A sample's “below 0.04 mm.” All teeth remain, but support removal, lower-edge finishing and physical meshing need checking.

Both bores retain a thin film only at the bottom 0.2 mm support layer, not deep support columns. Physical removal, bore size and fit remain unverified. Raw G-code/configured 3MF stay private, unpublished.

[Machine-readable checks](slicing/toolpath_checks.json) / [settings/STL hashes](slicing/profile_provenance.json) / [warnings and scope](slicing_status.json)

[Input layers](slicing/P_INPUT_PINION_layers.png) / [input tips](slicing/P_INPUT_PINION_tooth_detail.png) / [input bottom support](slicing/P_INPUT_PINION_support_bore.png)

[Compound layers](slicing/P_COMPOUND_1_layers.png) / [156-tooth tips](slicing/P_COMPOUND_1_tooth_detail.png) / [compound bottom support](slicing/P_COMPOUND_1_support_bore.png)

Layer images derive from actual extrusion lines/stated widths—not print photos or Orca screenshots. No printer connection, transmission or printing occurred.
