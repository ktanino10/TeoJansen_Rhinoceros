# Ver.3 development — assembly, printing, purchasing and 360-degree views

[日本語](README_ja.md) · [Retained trial HTML](https://ktanino10.github.io/TeoJansen_Rhinoceros/en/ver3-2.html)

**Ver.2 is the completed public build. Its content, presentation and existing URLs are preserved.
Ver.3 and later are separate work in progress.** Main was checked on 2026-11-15:
`18dd3f40fb811b3d50cfa527b6fafbfa55a6e781`.
Ver.3.1 is a whole-machine reference design, not a qualified physical walker.
**Ver.3.2 / `v3.2-m3-r1-bench` is a small M3 connection trial**, not a new complete kit
or a drop-in replacement for the 3.1 frame, guards or leg stack.

## Select the appropriate revision

|Purpose|Ver.3.1 A: full reference assembly|Ver.3.2: M3 bench trial|
|---|---|---|
|Understand the mechanism|[750 instances, 360-degree selection and 12 stages](https://ktanino10.github.io/TeoJansen_Rhinoceros/en/r7.html?design=A#viewer)|[22 bench instances and separate coupons](https://ktanino10.github.io/TeoJansen_Rhinoceros/en/ver3-2.html#viewer)|
|Assembly|[Canonical 12-step guide](../integrated_r7/ASSEMBLY_en.md)|[Numbered trial instructions below](#trial-assembly-sequence)|
|Printing|[44 definitions / 115 installed prints](print-list-3.1-A.csv), [original STLs](../../../STL/Ver.3/integrated_r7/A)|[5 definitions / 6 trial prints](print-list.csv), [new STLs](../../../STL/Ver.3/m3_r1)|
|Purchasing|[Historical required quantities and lots](purchase-list-3.1-A.csv), [original](../integrated_r7/A/purchase_lots.json)|[Specifications, quantities, packs, official sources and dates](purchase-list.csv)|
|Editable CAD|[3.1 FreeCAD / STEP](../../../FreeCAD/Ver.3/integrated_r7/A)|[New FreeCAD](../../../FreeCAD/Ver.3/m3_r1/M3AssemblyTrial.FCStd), [new STEP](../../../FreeCAD/Ver.3/m3_r1/M3AssemblyTrial.step)|

The 3.1 lists preserve their original check dates, prices and limited 0.4mm slicing conditions.
They are **not M3 conversions, current stock confirmations or full-machine print qualifications**.
The 115 prints exclude [common coupons/stand](../integrated_r7/common/accessories.json) and the three
[PET sheet templates](../integrated_r7/A/).

## Torque transmission, axial retention and free rotation

The [joint CSV](joints.csv) separately records the old/new methods, screws, anti-rotation,
axial retention, free-running surfaces, tool direction and checks.

|Joint|Torque path|Axial retention|Free-running surface / actual CAD evidence|
|---|---|---|---|
|J1 Rotor / hub / input shaft: 3.1 reference|Four M4x12 fasteners and commercial metal 6D hub|Hub and input collars; actual tightening unverified|Commercial bearing rings. [CAD diagram](input-3.1.svg), [360 connections](https://ktanino10.github.io/TeoJansen_Rhinoceros/en/r7.html?design=A&focus=connection#viewer)|
|J2 Synchronizing gear / shaft: 3.2 trial|5mm-AF metal hex shaft and 5.12mm-AF bore, not adhesive|Split clamp with two jammed nuts; a complete machine additionally needs shoulders/bearing retention|Gear must not rotate relative to shaft. [Bolt-axis section](gear-3.2.svg), [hex bore and side slots](gear-top-3.2.svg)|
|J3 Left/right supports: 3.1 reference|Front locating key and rear relieved key|Locating/floating supports, outer-ring caps, shoulders and washers|Bearing rings. PET is not a compression spacer. [CAD diagram](supports-3.1.svg), [360 retention](https://ktanino10.github.io/TeoJansen_Rhinoceros/en/r7.html?design=A&focus=retention#viewer)|
|J4 Leg pin: 3.2 trial|Captive nut in the stationary bracket; the link is intentionally free|M3x20, metal washers at both ends and two nuts; force closes on the 12mm metal sleeve|6.2mm link bore on approximately 6mm smooth brass, never on screw threads. [Section including both nuts/washers](pivot-3.2.svg)|

The reported V2 issue was **relative slip** between shaft and rotor/gear, not proven seizure.
Positive flats prevent relative rotation; they do not by themselves prevent axial escape.
Nuts and washers have not been removed just to reduce assembly operations.

## Trial print and hardware list

All STLs use mm at 100%. Do not scale them or apply the old V2 150% / ABS instructions.

|STL|Quantity|Orientation and purpose|Support / inspection|
|---|---:|---|---|
|[Q_SLEEVE_FIT](../../../STL/Ver.3/m3_r1/Q_SLEEVE_FIT.stl)|1|Flat base down; left-to-right bores 6.1 / 6.2 / 6.3mm|No support planned; first measure actual sleeve OD, groove and burrs|
|[Q_NUT_HEX_FIT](../../../STL/Ver.3/m3_r1/Q_NUT_HEX_FIT.stl)|1|Pockets up; near row nut AF5.6/5.7/5.8, far row shaft AF5.08/5.12/5.20mm|No support planned; check actual nut height and across-flats|
|[P_M3_GEAR42](../../../STL/Ver.3/m3_r1/P_M3_GEAR42.stl)|2|Flat gear face down; hub up|Inspect/remove local nut-slot and transverse-hole support; do not thin the teeth|
|[P_M3_PIVOT](../../../STL/Ver.3/m3_r1/P_M3_PIVOT.stl)|1|Exported base down|Support under upper lug; remove from 6mm gap and nut slot|
|[P_M3_LINK](../../../STL/Ver.3/m3_r1/P_M3_LINK.stl)|1|Broad face down|No support planned; check bores and layer splitting|

**0.2mm is the nozzle diameter**, not layer height or guaranteed fit.
P1S / Generic PETG / 0.10mm layers are inspection assumptions; the user's actual printer/material remain unknown.
[Actual layer report](slicing.json) records effective settings and hashes.
Machine-specific 3MF/G-code is not distributed. No purchase, printer connection, upload or printing was performed.

|Hardware|Required|Minimum purchase if none owned, displayed tax-inclusive price on 2026-11-15|
|---|---:|---|
|M3x20 stainless socket screw; strength grade unknown|3|Sengoku EEHD-6D5E, 10 for JPY330|
|M3x0.5 brass hex nut|6|Akizuki 114372, 10 for JPY120|
|M3 x OD8 x 0.5 washer, nickel-plated brass|6|Sengoku EEHD-6EC4, 10 for JPY250|
|M3 through sleeve, approximately OD6 x 12, brass|1|Sengoku EEHD-6CJH, 4 for JPY200|
|5mm-AF brass hex stock, two 30mm pieces|2 pieces|Existing domestic 3.1 stock family; cut from one 100mm bar; current price/shipping unconfirmed|

The four fastener packs total **JPY900 if none are owned**, excluding shaft stock, tools, filament and shipping.
Additional quantities require subtracting verified on-hand stock, which is currently UNKNOWN.
Use a 2.5mm hex key, 5.5mm spanner and caliper; a saw/file is needed only for spare metal-stock cutting.
[Sengoku's matching 2.5mm key](https://www.sengoku.co.jp/mod/sgk_cart/detail.php?code=EEHD-6TMA) is listed at JPY110.
Online listing, online inventory and store handling information are separate CSV fields; store availability is not guaranteed.
The brass hex shaft is an existing non-fastener material choice, not a new proprietary imported fastener.

## Trial assembly sequence

1. **Check revision and dimensions using only the two coupons first.** Measure the actual sleeve OD/ID/end groove,
   nut AF/height (nominal acceptance assumptions 5.5/2.4mm), washer bore and metal shaft.
   Do not force fits. Feed any dimensional correction back into the CAD, rather than treating nozzle size as a tolerance.
2. **Side-load the inner washer, then inner nut into each gear.** Use the +X opening in the
   [section](gear-3.2.svg); align the nut flats with the captive slot. Do not tighten the outer nut yet.
3. **Insert and axially position the metal hex shaft.** Assemble M3x20 → washer → split hub →
   inner washer → captive inner nut → outer nut. Hold the head with the 2.5mm key and bring the outer nut
   against the inner nut with the 5.5mm spanner. No unsupported tightening torque is specified.
   Stop on whitening, cracking or a fully closed slit.
4. **Mesh the two gears on 42mm centres.** This is a 42:42, 1:1 unloaded trial, not the complete A 144:1 reducer.
   No powered drive or shaft-support jig is supplied. Match shaft phase to the gear, mark shaft/gear,
   and check relative slip separately from axial movement. Do not power the trial.
5. **Assemble the pivot separately.** Side-load the upper washer and inner nut into the bracket.
   Place the 5.4mm link between the 6mm-spaced lugs and pass the smooth sleeve through all three holes.
   Inspect the sleeve end groove and burrs; keep the groove away from the moving bore.
6. **From below: M3x20 → lower washer → 12mm sleeve → upper washer → inner nut → outer nut.**
   Clamp the metal sleeve ends, not the link; compare the [actual section](pivot-3.2.svg).
   Nominal axial freedom is 0.6mm, diametral clearance 0.2mm and bolt projection 2.2mm.
   Confirm complete thread engagement with the real fasteners.
7. **Check free rotation and retention separately after tightening.** The link must remain free, the sleeve must
   stay captured and the screw/nuts must not co-rotate. The ±80-degree CAD samples do not cover all real tolerances.
8. **Record results before integrating a whole machine.** Record measured dimensions, assembly direction,
   binding, whitening, loosening and wear. Do not retrofit these parts by enlarging the old holes.
   Input 6D hardware, all leg layer spacings, supports, guards, floor clearance and whole-machine mass remain integration work.

## What was computed, and what remains physical

[Checks](checks.json) record native reopening, STEP correspondence, positive solids, the 22-instance scene,
52 side-insertion samples, four tool envelopes, 17 pivot positions and 19 samples across one tooth period.
Diagrams derive from the same B-rep edges/sections; neither display clipping nor an exploded diagram proves physical assembly.

The reused gear profile is module 1, 42 teeth, 25-degree pressure angle, 3.2mm face and 0.3mm backlash.
Contact ratio is approximately 1.362, minimum tip thickness 0.539mm and root chord 2.251mm.
The 0.2mm nozzle does not establish tooth strength. Per 1N·m of transmitted torque, tangential force is
47.62N and radial force 22.21N; these are conversion coefficients, not an operating-load instruction.
PETG allowable tooth load, fatigue and wear remain UNKNOWN.

The [comparison](comparison.json) covers **two drive clamps and one free pivot only**, not two complete machines:
two screw variants (M3x16/M2x16) become one (M3x20); four fastening-tool sizes become two.
Three screws and six nuts remain, and washers increase from two to six.
Captive seats, thicker links and larger smooth sleeves cost mass and space.
Whole-machine 3.2 part count, mass, drag and budget are not established.
The old A approximately 1065g / JPY24,000 material background is not a new-machine promise.

Treat gear/shaft slip, axial escape, plastic creep, sleeve/bore wear, loosening and tooth breakage as separate failure modes.
More adhesive or tightening is not a universal remedy.
Hair-dryer cold-air self-start and physical 30cm walking have not been performed; old 120rpm animation is not measured performance.

## Reproduction and scope rules

Sources: [CAD](../../../scripts/ver3/build_m3_trial.py), [0.2mm inspection](../../../scripts/ver3/slice_m3_trial.py),
[list generator](../../../scripts/ver3/report_m3_trial.py).
Existing FreeCAD 1.1.3 / OrcaSlicer 2.4.2 use `scripts/ver3/requirements_m3.txt`, inheriting the existing requirements and adding networkx for section paths.
Pass installed FreeCAD lib / Orca bundle locations explicitly. Generators do not publish, purchase or control printers.
The implementation reuses repository generators and the [official FreeCAD API](https://freecad.github.io/SourceDoc/d8/ded/classPart_1_1TopoShape.html).
The [Part wiki](https://wiki.freecad.org/Part_API) warns that some documentation is old; actual native reopening and shape checks are retained.

[Ver.3-only instructions](../../../.github/instructions/ver3-assembly.instructions.md) preserve the M3,
Akizuki/Sengoku, 0.2mm and completed-Ver.2 requirements. No personal global settings or user memory were changed.
