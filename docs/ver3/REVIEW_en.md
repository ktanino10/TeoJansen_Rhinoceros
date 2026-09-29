# Ver.3 independent review and corrections

[日本語 (original)](REVIEW_ja.md) | **English** | [Document languages](../README_en.md)

> Presentation-only translation of the unchanged Japanese source. Source SHA256: `1a7ad82e2b4366130d5654dcb9819ee2e3a1d23e465ee8eb1dfa99c16a88f58a`. Numbers, part IDs, equations, code and qualification limits are retained; this is not a new engineering revision.

**Verdict: first cut for review. Not approval for manufacturing release, practical stable walking or all-direction wind self-starting.**

Completed CAD, BOM, assembly documents, generation conditions, Blender and actual MP4 files were reviewed mechanically and technically by **one AI reviewer in a context separate from design/visualization**. This was not qualified human engineering approval. Rather than re-searching the architecture, four interface/specification/sequence/display issues were narrowly corrected, and **the same reviewer checked every corrective diff**. No purchases, prints, physical assembly or operating tests occurred.

## Findings and responses

| ID | Priority | Independent evidence / impact | Correction | Status |
|---|---|---|---|---|
| **R1** | P1 | Against manufacturer 1309-0016-4008, draft hub/shaft flats were 15° wrong relative to the four holes; purchased hub/old shaft overlap was 22.81 mm³. Flipped hubs needed separate indexing | Changed hub bore/shaft section to 15° corner reference; flipped hubs index 90°, preserving square bolt holes, crank phases and ratios | Independent diff checks of all 38 hubs, 20 flipped hubs and 152 M4 hole positions |
| **R2** | P2 | A window geometry used 13 mm holes/M3×40/35 mm guard depth, but text said 10 mm/M3×35/31 mm. Old text risked insufficient nut engagement and adjustment rubbing | Store `window_aperture_mm`, `window_screw_length_mm`, `guard_depth` in canonical stage data; generate CAD holes, screws and BOM text from the same values. Check full-size templates/instructions too | Independent geometry/BOM/native-specification diff checks for all 7 stages |
| **R3** | P2; residual R3-A is P1 | Front carriers hid some A/B window screws. Follow-up found four A carriage screws intersecting retained windows by 12.566 mm³ each | Carrier-first disassembly with rotating-part support and A setting preservation. Add four 8.4 mm clearances to A's window; check unit removal over ±1.5 mm adjustment | Independent diff checked: A left, 26 parts × 3 adjustments × 10 extraction positions; native/STEP overlap 0 mm³, minimum screw clearance 0.70 mm |
| **R4** | P3 | Walking-panel `Wind-COP minimum` could not be identified from the image as the 5 m/s value, not the 8 m/s worst case | Separate `FIXED-POSE SENSITIVITY`, `COG +/-5 mm minimum`, `Wind-COP @5 m/s (+/-Y)` and their conditions without choosing more favorable values or physics | Independent checks of 3 PNGs, 1 frames from each MP4 and native files; 5 m/s labels match JSON |

R1 concerned a purchased-part reference angle **not discoverable by agreement between self-generated models alone**. It demonstrates the value of actual-part dimensional checks and independent review. Manufacturer CAD was temporarily acquired only for comparison, not redistributed.

R3-A concerned **cut sheet and metal mounting screws**, missed by checking printed parts or window tools alone. It was found by additionally checking the full carrier unit against the retained window, not created by the sequence correction. Four explicit clearance holes—not shorter screws sacrificing nut engagement—addressed it. New checks include ±1.5 mm adjustment extremes.

Corrected A left assembly separated 19 adjusting and 7 fixed parts and was independently rechecked at **adjustments −1.5/0/+1.5 mm × extraction 0/1/2/4/7.5/8/12/24/40/60 mm**. Both native and STEP window overlap were 0 mm³; minimum clearance of the four problematic screws was 0.70 mm. Holes, BOM, specifications and display meshes matched. Only the stated samples/combinations were checked, not physical tolerances, tool workability or performance.

Final media distinguish COG ±5 mm from wind 5 m/s in ±Y. Wind labels A −1.42 / B −1.98 / C −5.68 mm match canonical JSON. Hashes of 31 deliverables including native files agree; saved Blender vertices for 5 instances including A windows/hubs match corrected CAD meshes within rounding, with exact face indices. [Visualization validation](../../Blender/Ver.3/ver3_validation.json) SHA-256 is `c5650b763c98649c4abdd23278f204da3de1b69a8cfe54218befdf77fff8299b`. This confirms display/data consistency, not a new physical-performance judgment.

## Initial independent-review scope

- Independently opened all FCStd features, canonical IDs/transforms/volumes/specifications and STEP validity/solid counts. Initial native/STEP counts matched at A827/B844/C791.
- Checked closed single-solid printable STLs, volume and bounds. Some parts reach **exactly 256 mm**; brims and physical bed-edge margins are not guaranteed.
- Checked printed versus other actual B-rep parts at **24 poses spaced 15°**. A3443/B3676/C3500 actual Boolean checks found no overlap above 0.05 mm³.
- Checked differently moving nonprinted pairs at **36 poses spaced 10°** too. Co-rotating nominal threaded interfaces and intended purchased-belt/pulley envelopes were distinguished.
- For six spur pairs, extracted native tooth boundaries and checked 0 area overlap at 121 samples per meshing period. Verified signed ratios and purchased HTD5M length, wrap, width and mounting holes.
- Actual solids at AC/fixed-pivot-spacer closest angle 191.5996° showed 0.522766 mm clearance. Checked open crank bays, sleeve stacks, recesses, axial retention and inner/outer-ring contacts.
- Reran the declared search separately; selected JSON, candidate CSV and three structural-search files were byte-identical to the initial revision. Starting/contact metrics reproduced as conditional models.
- Opened Blender independently with automatic script execution disabled; verified canonical placements, absence of scaling/deformation and B's unwrapped rotation direction.
- Decoded distributed MP4 files and visually inspected key walking, drivetrain and exploded frames: forward motion relative to fixed ground grid, time factors, failed residual targets and physically-unverified notices.

These are **sample-angle checks**, not rigorous proof of clearance at every continuous angle/tool/finger/tolerance condition. Initial results do not mean all checks were rerun after correction; post-correction checks targeted affected areas.

## Remaining fabrication and performance checks

1. **All designs miss the contact target.** 3 mm is a design-side target, not a silently relaxed user criterion. Initial partial episodes, complete episodes and all-near-foot audits without load thresholds are recorded separately. Material-point motion includes shoe rocking, not measured ground slip.
2. **Near feet are not loaded feet.** A geometric count of at least 3 near feet does not establish practical tripod support. Physical checks must cover assumed center of mass, passive shoe hinges, mass error and wind tipping moments.
3. **B lacks input even in comparison conditions.** At 8 m/s and assumed coefficient 0.20, nominal starting demand is not covered. Favorable A/C cells do not establish self-starting/sustained rotation at adverse angles or low coefficients.
4. **Mass and strength are assumed.** Solid-volume/purchased-mass assumptions are not measured print mass, center of mass or layer strength. AC's Euler proxy ratio about 1.56–1.94 is not a printed-part safety factor or fatigue-life guarantee.
5. **Check purchased/fabricated interfaces physically.** Bearing faces, clearance, alignment, metal-shaft cuts/taps, tightening, belt tension/starting resistance and pin/bush/shoe friction remain to be checked.

Canonical results: [comparison](comparison.json), [design](DESIGN_en.md), [assembly](ASSEMBLY_en.md), [installation A](assembly_access_A.json) / [B](assembly_access_B.json) / [C](assembly_access_C.json), [walking A](walk_A.json) / [B](walk_B.json) / [C](walk_C.json).

Provided as a **comparative first cut**. Documents, renderings and animations are not a physically validated complete machine or safety certification.
