# Common assembly — Whole-machine r7

[日本語 (original)](ASSEMBLY_ja.md) | **English** | [Document languages](../../README_en.md)

> Presentation-only translation of the unchanged Japanese source. Source SHA256: `b0b41df69184339e29f430740899f1e2cad6e5a9525b19df65f16457672dd69d`. Numbers, part IDs, equations, code and qualification limits are retained; this is not a new engineering revision.

**Assembly planning and finite CAD-path documentation.** Actual assembly, printing, tightening and starting tests are unperformed. Follow included/absent parts and check results in each design's `assembly_access.json`/`gait_motion.json`; do not relabel failed operations as passes.

[r7-16 floor correction](FLOOR_CORRECTION_en.md) changes C's stages and every design's PET lower edges/rocker-pin region. The old slice1 “geometry unchanged” statement applies only to that revision.

After R7-I1, fixed path inventories are automatically derived by replaying `orderedOperations`. Later fasteners are added after explicit boundaries. Workbench preparation contains only `prepareOnly` parts in an independent scene. Installed parts cannot be hidden to force PASS. [Review/corrections](REVIEW_en.md)

Only the input shaft is imported commercial 6D. Downstream uses domestic 5 mm-AF brass, NMB bearings, Hirosugi smooth metal sleeves, SAMINI springs and domestic screws. Addressing V2 relative shaft/rotor/gear slip, the input uses a metal D-hub and downstream actual hex sections. Threads are not sliding surfaces.

## Materials, tools and fabrication conditions

Each `BOM.csv` lists used quantities; `purchase_lots.json` lists purchase units, surplus and materials cost. Coupons/stand are separate in `common/accessories.json`, included in cost but excluded from walking mass. Shared purchase for 3 machines counts 1 common coupon/stand set.

Individual first-purchase estimates assume JPY 160/USD, filament JPY 3,000/kg and factor 1.2 on solids plus initial accessories. On 2026-09-28, **about JPY 24,000 in materials per 1 machine** was approved. Shipping, unresolved taxes and unowned tools such as DN-03 at about JPY 396 are separate. Not actual sliced consumption; extra supports/failures may exceed budget. Use same-revision sensitivities in each `purchase_lots.json`, not shared-purchase averages. Old JPY 23,000 versions remain historical.

Imports are limited to input parts/fastener lots. Surplus M4 screws/nuts also serve downstream caps; imported shafts/hubs are not duplicated on every axis. Used quantities and purchased lots such as 25-packs are separate.

Assumed tools: 1.5/2.5/3 mm hex keys, 4/5.5/7 mm small wrenches, hacksaw, file, measuring tools and PET cutter. Ownership/actual envelopes are unverified; no purchases/operations occurred. Do not substitute thin homemade tools or force insertion when specified tools do not fit.

B's final-stage right nut clearance was checked with a 5.5 mm tool-tip model of width ≤7.6 mm and thickness ≤1.8 mm. This does not verify an actual commercial tool/handle. Do not assume a larger tool fits; check `B/retainer_tool_access.json` conditions first.

- The 6D input shaft, 140 mm long, needs no cutting/end tapping.
- Domestic hex stock: main shafts 100 mm, intermediate shafts 58 mm. Check 58 mm stock within ±0.5 mm after finishing. Short ends are canonical PET-insertion geometry; do not independently lengthen shafts/STLs.
- First use coupons for bore diameter, 13 mm guide length, 8 mm round journal and actual tooth form. Manufacturer tolerances, printer compensation and layer strength are unqualified.
- A/B and C pair 2 use m1/25°. Only C pair 1 uses m0.9/20°, 12/156 teeth and shifts +0.35/−0.35. Do not mix with old C or A/B mating gears. About 0.53 mm tips require actual-layer/coupon checks; closed solids/contact ratio do not qualify printing.
- Do not enlarge the 6D metal hub to eliminate tiny nominal STEP overlaps during finishing. Open/clamped state, actual fit and tightening are separate unresolved matters.

After approval, official OrcaSlicer 2.4.2 was installed separately and [5 representative actual slices](SLICING_en.md) inspected. P1S/0.4 mm/PETG are inspection assumptions, not verified hardware matches. A/C input-pinion teeth begin 10 mm above the bed in exported orientation and need supports. The 2 checked gears retain 0.2 mm bottom support spanning bores; removal, bore/tooth-bottom finishing and fit remain necessary. No printer connection, transmission or printing occurred. Not whole-machine print qualification; see `slicing_status.json`.

## Sequence

1. **Prepare separate left/right frames.** Large compound gears are not forced through already joined frames. Identify bearings, caps, round journals, hex keys and joint faces; prepare parts inserted from outside first.
2. **Prepare left retention and downstream drive.** Insert left-crank journals into left bearings; place metal hex shafts, compound gears and left intermediate stops. Do not project clamp screws/nuts before passing parts. Right ends of 58 mm intermediate shafts and printed journals lie inside the upper PET plane.
3. **Close the right frame** following `frame_right_close`. Include bearings/caps/idlers positioned with the right frame among moving parts, and every already-installed left-side part among fixed parts. Right cranks, legs, input rotor/shaft and guards come later. Align front hex location and rear relieved key; add 4 M3 joints after seating. Keys locate the frame; bolt friction alone does not carry lateral load.
4. **Upper PET.** Temporarily withdraw the main shaft −53 mm in X; input shaft and idler outer-cap screws remain absent. Raise the panel from below offset **−4 mm in Y**, then seat at unchanged height along **Y=-4→0 mm**. Distinct from stage 07's X offset. Short intermediate journals, upper input notch and end-opening crossbar relief are prerequisites. Add waiting screws after seating. Do not ignore fixed parts/gears as invisible; check the stage inventory in JSON.
5. **Lower/side PET on both sides.** Install before right cranks and both leg sets. Existing cap fasteners are used, but steel-washer stacks—not PET compression spacers—carry clamping load. Large PET holes and outer retaining faces capture the sheet without adding bearing preload.
6. **Rotor into front basket.** Align metal D-hub, rotor, 4 M4 bolts and coaxial input pinion, entering through the open rear. The shaftless pinion requires hand-supported alignment. Diameter differs from capture width: axial root 4 mm, capture width 32 mm, end 2 mm, total 38 mm.
7. **Place rotor/front basket along two segments.** Before input shaft/rear guard, lower the complete rotor/hub/pinion/basket subassembly offset **+4 mm in X**. At final height, seat axially **X=+4→0 mm**. The 2 continuous segments retain identical moving/fixed inventories, including PET/fasteners from stages 04/05. Temporary collars/spacers are placed only afterward. This assembly-only offset does not change final positions, leg paths, wind or mass. Hand-support until shaft insertion; airborne self-support is not claimed.
8. **Insert input shaft.** Pass the 140 mm shaft through collars, spacers, pinion and metal hub. Distinguish manufacturer-specified 6D compatibility from nominal reference contact and actual open/clamped state.
9. **Rear guard and retention.** Pass forward-open rear-cap relief over fixed supports. After seating, add rear fasteners and 3 front-basket joints. Do not install later bolts early for checks or erase existing parts. Distinguish inner/outer-ring contact: locate on the left, leave right float. Guard removal does not require passing a closed integral cage over supports.
10. **Input collar orientation.** Follow each `inputCollarClocking`. Rotate the same 2 round-bore collars to reduce nominal gravitational imbalance without changing axial locations, quantity or mass. Print eccentricity, purchased centers of mass and dynamic balance remain unmeasured.
11. **Main shafts and crank phases.** 3 shafts retain 84 mm pitch and 42-tooth synchronization gears. C's 156-tooth gear moves from the floor-near final stage to the higher intermediate stage. C uses 13×12, final 144 teeth, total 156:1. Match shaft engagement/clamp direction. Left/right phases front-to-rear are 0/180, 180/0, 0/180°. Hex indexing differing by 60° is not the same phase.
12. **Legs, metal pins and feet.** Distinguish A/P/B/C/D/E sleeves and illustrated link layers. At P, hold the inner M2 head with a hex key; 2 nuts stay outside. No buried nut is tightened through a narrow window. M2 screws axially clamp sleeves, not lock printed links.

The separate assembly stand matches frame rail centers X=-39.5/32 mm and is removed for walking. This document does not authorize actual dryer/printer operation.

B's upper PET comprises 2 independent panels for 2 intermediate supports. Each has 2 retention points and its own used-part BOM entry; a mounting-bearing piece is not discarded as scrap. Procurement nests them as 1 cutting rectangle, neither inflating nor undercounting sheet area.

## Feet, springs and contact

Each foot uses 2 commercial 12-0721 springs, 20 mm metal guides and a passive rocker with 2 rolling-contact regions. Listed spring rate is 0.882 N/mm per spring, not obtained by adjusting assumed FDM modulus.

Rocker pins use 1 mm stepped seats placing washers against 8 mm metal-sleeve ends. **Commercial M2×12 and M2 nylon locknuts (4.5 mm AF, 2.5 mm high)** require neither precision cutting nor thin wrenches. Accepted screw lengths 11.7–12.3 mm give calculated protrusion ≥0.6 mm; actual chamfers, full threads and nylon engagement still require checking.

Preassemble only the CEF-integrated foot on a separate bench. Hold the M2 head with a normal 1.5 mm hex tool, use actual ENGINEER DN-03 on the nut, then add other links. DN-03: tip OD 8 mm/length 18 mm, socket depth 9 mm, shaft 75 mm, overall 145 mm, handle OD 13 mm. It matches 8.2 mm relief and local fork width 12.8 mm. Published dimensions/full envelope were checked, not ownership, physical operation or retention torque. [Sources/acceptance conditions](stock_fasteners_and_tools.json)

The nylon locknut is not demonstrated equivalent to the old 2 jam nuts in retention torque/reuse endurance. Retained performance after disassembly is not assumed; reassembly assumes new nuts.

Rocker axial width 4.4 mm plus small M4 steel washers on both sides (OD 8 mm, thickness 0.5 mm) totals 5.4 mm, preserving 0.6 mm end play inside the 6 mm fork. Do not mix old OD 9 mm/thickness 0.8 mm washers. Pad positions/radii/width, foot placement and spring travel are unchanged.

The foot module is physically mounted 4 mm forward of original F. Pad area/width and ballast are unchanged. A 8 mm option improved support but increased handoff potential-energy demand, so was rejected.

Mechanical stroke 6 mm compares with catalog allowable deflection 10.3 mm, estimated solid height 4.08 mm and free length 15 mm. Stops, guide overlap, screw ends and spring seats require actual-geometry checks. Stroke limits are not hidden by changing spring rate or floor height.

[A intermediate-stroke checks](A/foot_motion.json) store 0–6 mm in 0.5 mm steps plus rocker poses for the common foot. These are specified-part/sample checks separate from each whole-machine 216-pose check.

Loads and relative movement at contacts yield nonnegative slip work. Obtaining 3-leg support does not meet the old 3 mm slip target. Tolerance analysis covers finite link errors, both-end pin play, phase, floor height, spring rate, guide friction and input-couple cases—not a rigorous full-domain proof.

Airborne clearance is distance from the floor including body sinking caused by other feet's spring compression. Compression is not added twice to required clearance. A separate 0.9 mm margin covers untraversed floor/geometry.

## Remaining fastening and maintenance checks

No tightening torque is invented without manufacturer evidence. Fastener grades, plastic creep, printed bearing pressure/fits and actual tools remain to be checked. Guards are real BOM parts, not certified finger/fragment protection or impact-tested products.

Track cap checks, removal paths and sheet notches in actual files. A physically filed-to-fit part is not automatically the canonical CAD. Record required changes back into dimensions, mass and BOM.

`cad_validation.json`/`step_correspondence.json` check only native/STEP correspondence. They alone do not qualify assembly clearance; consult separate `static_collisions.json`, `gait_motion.json`, `assembly_access.json`, `rotating_clearance.json`. None certifies physical performance.
