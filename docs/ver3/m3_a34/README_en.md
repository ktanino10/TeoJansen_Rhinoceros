# Ver.3.4 A — development assembly, printing and purchasing

[日本語](README_ja.md) · [Dedicated HTML / whole-machine360 view](https://ktanino10.github.io/TeoJansen_Rhinoceros/en/ver3-4.html) · [Development index](https://ktanino10.github.io/TeoJansen_Rhinoceros/en/development.html)

**Ver.2 remains the completed public build, with its content, presentation and existing URLs preserved.
Ver.3.4 is separate work in progress.** Engineering ID: `v3.4-a-m3-r1`.
Actual3.1 A geometry was revised using the retained [3.2 bench trial](../m3_r1/README_en.md).
No completed3.3 is claimed. `manufacturingRelease=false`; physical printing, assembly and wind walking remain unverified.

## Files for this revision

|Purpose|Ver.3.4 source|
|---|---|
|Rotate and inspect the whole mechanism / changes|[360-degree model and changed parts](https://ktanino10.github.io/TeoJansen_Rhinoceros/en/ver3-4.html?design=A&focus=modified#viewer)|
|Editable whole-machine CAD|[Native FreeCAD](../../../FreeCAD/Ver.3/m3_a34/Walker_A_3_4.FCStd), [STEP](../../../FreeCAD/Ver.3/m3_a34/Walker_A_3_4.step)|
|Print files and quantities|[Whole-machine print CSV](print-list.csv), [changed STLs](../../../STL/Ver.3/m3_a34/)|
|Required purchased parts|[Specifications, material, quantities, packs, price basis, sources and dates](purchase-list.csv), [BOM](BOM.csv)|
|Actual connections|[Gear section](gear-section-3.4.svg), [hex bore / nut-slot view](gear-end-3.4.svg), [A-root section](pin-section-3.4.svg)|
|Calculations and unknowns|[All-phase drive budget](work_budget.json), [same-condition comparison](drive_comparison.json), [quantity/scope summary](summary.json)|

The whole assembly has **754 instances** and **45 printed types /115 prints, of which38 prints changed**.
The CSV distinguishes new3.4 STLs from retained3.1 STLs and gives each file's hash.
It includes purpose, orientation, support plan, nozzle/material assumptions and actual STL bounds.
Fit on the user's printer, including brim/support placement, is unverified.
Instance IDs retain3.1 tracking identity. Even if an instance name still contains `H_BOLT_M2_...`,
use the updated `PartId` / `Specification` and3.4 BOM, not the instance name, to identify screw dimensions.
Coupons, the stand and PET cutting are separate from the115 prints:
see [retained accessories](../integrated_r7/common/accessories.json) and [three PET templates](../integrated_r7/A/).

## What fixes each connection

|Connection|Fastener / torque path|Retention, free rotation and tools|
|---|---|---|
|Input rotor / hub|Retain four M4x12 fasteners and commercial metal6D hub|Retain collars and bearing support. The [3.1 input diagram](../m3_r1/input-3.1.svg) documents unchanged geometry|
|Front/centre synchronizing gears|Each uses one M3x20, two M3 washers and two nuts; inner nut is side-loaded into a captive slot|Hex flats transmit torque; split clamp retains axially. 2.5mm key and5.5mm spanner. Rear gear remains unchanged|
|Frames / bearings|Retain front hex key, relieved rear key and M3/M4 fasteners|Keep locating/floating support and outer/inner-ring load paths separate; PET is not a compression spacer|
|A roots on six legs|Each uses M3x30, two M3 washers, two nuts and one continuous20mm/6mm-OD sleeve|An actual6.2mm passage admits the head/key; side-load the8mm head washer. The printed root seat carries clamp load, so creep requires checking|
|D joints on six legs|Each uses M3x15, two M3 washers, two nuts and an8mm/approximately6mm-OD sleeve|Run on smooth metal, not screw threads. Do not clamp the link. 2.5mm key and5.5mm spanner|
|P/B/C/E, feet and idlers|Retain M2 /4mm smooth journals|M3 P nuts collided with AC. M6 B washers collided with the frame during motion. Do not substitute thin specialist washers, weakened frames or wider leg layers just to force conversion|

**Anti-rotation, axial retention and free motion are different functions. Torque does not depend on adhesive alone.**
The reported V2 failure was relative slip, not proven seizure.
Distinguish slip, axial escape, creep, bore wear, loosening and tooth damage.
No unsupported tightening torque is specified. Stop on whitening, cracking or a fully closed clamp slit.

## Numbered assembly plan

This is a **CAD-backed plan, not an account of completed physical assembly**.
The HTML whole/changed/coupon states are discovery views, not insertion animation or assembly order.

1. **Sort by revision.** Use the3.4 CSV/BOM and separate changed and retained parts.
   First test real sleeves, nuts and shaft with the [two fit coupons](../m3_r1/print-list.csv).
   A0.2mm nozzle does not guarantee the6.2mm bore or the nominal5.5mm-AF/2.4mm-high nut.
2. **Prepare front/centre gears on the bench.** Side-load inner washer, then inner nut.
   Head-side order: M3x20 → washer → split hub → inner washer → captive nut → outer nut.
   The bore is clocked30degrees to match the existing shaft; the old3.2 gear is not an interchangeable replacement.
3. **Load the left-side shafts and drive train.** Follow retained3.1 steps01–03 for bearings, shafts,
   compound gear and synchronizing gears. Keep12x12=144:1 reduction,42 teeth and42mm adjacent gear pitch.
4. **Close the keyed right frame and install PET.** Follow the original
   [steps04–05](../integrated_r7/ASSEMBLY_en.md), including the upper PET Y=-4mm offset.
   Carry clamping load through metal washers, not through PET into the bearings.
5. **Fit input rotor and guards.** Keep the metal6D hub, four M4 connections, front basket and rear cap.
   Refer to original steps06–10 for the temporary X=+4mm offset and shaft order.
   Old paths/videos are not proof of assembling modified parts.
6. **Prepare leg/crank subassemblies outside the machine.** Side-load the A-root8mm-OD head washer,
   then feed M3x30 through the6.2mm passage. Add sleeve, links, outer washer and both nuts.
   Do not plan to force a tool into the inner side after installation.
7. **Prepare D and the retained joints.** D uses M3x15, an8mm sleeve, end washers and double nuts.
   Place A/D M6 thrust washers in0.3mm face reliefs. The13mm bosses retain2.5mm bearing width;
   original4.1mm layer pitch and foot positions remain.
   Add fixed-P hardware when mounting the module; P/B/C/E and feet retain M2.
8. **Install and set phase.** Align the shaft, positive crank coupling and fixed P pivot.
   Left/right phases from front to rear are0/180,180/0,0/180degrees.
   Complete head-side subassembly work first. Check washer/nut direction and restore retention/guards
   before any hand-turn inspection; do not clamp the moving links.
9. **Record real checks.** Separately check slip, axial escape, binding, full thread engagement,
   support removal, whitening/cracks, loosening and wear. Do not force motion or overcome a fault with
   extra airflow/heating. Publishing these files does not operate a printer or blower.

[Tool/insertion checks](access_check.json) cover declared separate gear or leg/crank subassemblies.
The key approach uses a4mm envelope; the spanner gauge has a10mm-wide/2mm-thick head and31mm handle.
Actual tools, hand clearance, washer side-loading and the complete continuous installation path remain unqualified.

## Printing and procurement

Use **mm at100%**. **0.2mm is nozzle diameter**, not layer height or a fit guarantee.
[Actual layers](slicing.json) cover the new3.4 gear, AB link and crank.
P1S /Generic PETG /0.10mm layers are inspection assumptions, not confirmed user hardware/material.
Inspect support removal and finished holes/seats. This does not qualify all115 prints.
Machine-assumption G-code/3MF is not distributed; native/STEP/STL and effective-setting provenance/hashes are retained.

New fastener candidates are Akizuki114372 M3 nuts and Sengoku M3x15/20/30 socket screws,
BSW3mm/BSW6mm washers and BS3x8 sleeves. The purchase CSV separates required quantities, pack/minimum order,
unit versus pack price, tax inclusion/exclusion, official URL and check date.
On-hand quantities are UNKNOWN and no purchases were made.

**Continuous20mm CE-320N sleeves are the documented domestic-maker exception.**
This length of metal M3 through sleeve was not verified at the two preferred shops.
Splicing short sleeves would interrupt bending support and add parts.
[Hirosugi's official table](https://hirosugi.co.jp/shop/g/gCE-301N/) lists20mm, JPY26 excluding tax,
minimum50, checked2026-11-15. Stock/shipping remain unknown.
See the prior [exception and rejected options](DESIGN_en.md).
Retained3.1 purchases keep their historical dates/estimates, not refreshed-price claims.
URLs, sales units and pack prices are retained from both top-level `source` and nested `lots`.
Apply each `purchase_group` quote/cut plan once, rather than buying a lot for every BOM row.
The retained hex-stock plan cuts100/100/100/58mm from one500mm bar; three PET panels share one sheet.
**JPY900 covers only four3.2 bench fastener items, not the complete3.4 machine.**

## Improvement and cost

M3 screws increase **34→46**, M2 decreases50→38 and M4 remains14.
The14 modified locations use2.5mm keys /5.5mm spanners, but the complete tool set is not reduced.
Diameter/length combinations increase8→10. This improves use of ordinary M3 stock;
it is not a claim of lower total part count or elimination of all tools.

Nominal whole-machine mass rises from approximately1.065kg to1.12kg, based on CAD volume and nominal density,
not weighing. Exact numbers and the reproduced3.1 control appear in the [comparison](drive_comparison.json).
At equal load/friction,4→6mm A/D journals would raise friction torque1.5-fold.
The analysis instead re-solves actual new mass, COM and reactions, keeping P/B/C/E at4mm.
It retains low/nominal/high resistance,720 crank states plus input-phase interpolation, per-stage losses and forces.

Cold air at6.4m/s and20mm spread is uncalibrated. Nominal margin is small;
high resistance or half supply is insufficient. Loaded speed, self-starting and physical30cm travel remain UNKNOWN.
The old120rpm display is not an achieved-speed prediction. Root dimensions and42 deposited teeth do not
qualify allowable tooth load, layer fatigue or wear.

## Reproduction and preservation

[CAD generator](../../../scripts/ver3/build_m3_a34.py), [whole-machine checks](../../../scripts/ver3/verify_m3_a34.py),
[versioned analysis](../../../scripts/ver3/m3_a34_analysis.py), [0.2mm inspection](../../../scripts/ver3/slice_m3_trial.py),
[lists and native sections](../../../scripts/ver3/report_m3_a34.py).
To preserve frozen3.1 source contracts, only two analysis entry functions are versioned for3.4;
existing kinematics, airflow, contact and gear-power helpers are reused, with a frozen-result reproduction control.
[Ver.3-only instructions](../../../.github/instructions/ver3-assembly.instructions.md) preserve
Ver.1/2 originals, non-Ver.3 README content and the completed public area.
