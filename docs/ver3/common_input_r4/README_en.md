# Common input cartridge — Actual CAD of holder and test flange

[日本語 (original)](README_ja.md) | **English** | [Document languages](../../README_en.md)

> Presentation-only translation of the unchanged Japanese source. Source SHA256: `85509d69ae32ea690813f2ff591a5b669c379f4e1ef80a25ecb1a6807ac23db8`. Numbers, part IDs, equations, code and qualification limits are retained; this is not a new engineering revision.

**`v3-common-input-r4-01`. Actual CAD of 1 input assembly, not demonstrated low resistance, manufacturing release or completion of three walkers.**

The preceding [common-cold-air study](../commercial_basis_r3/DESIGN_GATE_en.md) is not overwritten. Without expanding rotor/gear/leg searches, this revision is limited to 1 set of a commercial 120 mm D-shaft, 2 bearings, metal D-hub and axial retention. **No shaft cutting, drilling or end tapping is needed.**

![Input cartridge from actual CAD](cad_preview.svg)

## Files

| Contents | Canonical source |
|---|---|
| Native FreeCAD | [CommonInputR4.FCStd](../../../FreeCAD/Ver.3/common_input_r4/CommonInputR4.FCStd) |
| STEP | [CommonInputR4.step](../../../FreeCAD/Ver.3/common_input_r4/CommonInputR4.step) |
| Printable STL | [Carrier](../../../STL/Ver.3/common_input_r4/P_CARRIER.stl), [retainers ×2](../../../STL/Ver.3/common_input_r4/P_CAP.stl), [test flange](../../../STL/Ver.3/common_input_r4/P_FLANGE.stl), [fit coupon](../../../STL/Ver.3/common_input_r4/Q_BEARING_FIT.stl) |
| Assembly and BOM | [Instructions](ASSEMBLY_en.md), [BOM.csv](BOM.csv), [canonical placements and operation set](assembly.json) |
| Dimensions and generation | [input_cartridge.json](../../../scripts/ver3/input_cartridge.json), [CAD generator](../../../scripts/ver3/build_input_cartridge.py) |
| Contacts and paths | [assembly_access.json](assembly_access.json), [tolerance stack](tolerance_stack.json) |
| Mass, cost and numerical results | [CAD checks](cad_validation.json), [procurement](procurement.json), [shaft beam model](shaft_mechanics.json), [STL checks](stl_validation.json) |
| Revision, sources and hashes | [manifest.json](manifest.json) |

FreeCAD contains 36 named Part features with IDs, specifications and mass bases. JSON/scripts govern parameters; this is not a Sketcher history driven by arbitrary display-property edits. Native/STEP agree at 44 solids. Purchased internals are **new dimension models**, not copied/distributed manufacturer proprietary shapes, B-rep, drawings or meshes.

## What became concrete

| Item | Result in this revision | Still unverified |
|---|---|---|
| Carrier | Integral supports, cap seats, bearing-flange grooves and 4 mounting holes | Actual shrinkage, alignment and layer-direction strength |
| Location | **2 collars and 2 spacers straddle the left 1 bearing**. Total inner-ring-stack play 0.20 mm | Actual bearing internal clearance and end play after tightening |
| Floating support | Right outer-ring flange axial travel 2.00 mm total, nominal ±1.00 mm | Actual free movement including fit and support deformation |
| Torque transmission | 6 mm D-shaft → manufacturer-specified metal D-hub → 4 M4 bolts on a 16 mm square → test flange | Tightening, physical torque capacity and fatigue |
| Removal / installation | Checked sequence: both caps first, preassembled hub/flange, shaft insertion from left | Finger access and all tool/tolerance conditions |
| Starting resistance | Geometry excludes unwanted nominal contacts; resistance remains an independent sensitivity input | **Actual starting/running resistance is unpublished and unmeasured** |

## Locating/floating sides and overtightening preload

![Actual-CAD section](bearing_sections.svg)

X is axial, Y lateral, Z vertical. Shaft center Z=30 mm; support centers X=16.5/96.5 mm, 80 mm apart.

Left locating side provides 1.30 mm pocket depth for a 1.00 mm outer-ring flange. **The 3 mm cap seats on carrier side lands, not against the bearing face.** Commercial steel spacers, about 8 mm OD and 4 mm long, sit before/after the inner ring to clear the collar's 9 mm boss from thin caps. Canonical CAD uses manufacturer-reference 6.05 mm ID/7.95 mm OD spacers.

Instead of the previous candidate's 1 collar at each shaft end, **both 2 collars straddle the locating side**. No added right-bearing collar clamps the whole span through multiple inner rings.

| Nominal dimensions and acceptance scenarios | Value |
|---|---:|
| Locating outer-ring axial play | 0.30mm |
| Total collar play around locating inner ring + 2 spacers | 0.20mm |
| Total floating outer-flange travel | 2.00mm |
| Remaining locating outer-ring gap at acceptance extremes | Minimum 0.10 mm |
| Remaining one-sided float allowance at acceptance extremes | Minimum 0.05 mm |

Pocket error ±0.10 mm, flange-thickness error ±0.05 mm and cap-compression allowance 0.05 mm are **design acceptance conditions to check before adoption**, not guaranteed delivery tolerances. Recalculate if actual parts/material/tightening do not meet them. Tightening until caps sink, forcing collars to eliminate play or pulling tight bearings in with bolts is not assumed.

Nominal minimum cylindrical support length at the floating end is about 2 mm. The flange also guides radially, but radial play, tilt and retaining stiffness are not guaranteed. Check coupons and free physical movement; reject tilt-induced binding. Rotor load, gear mesh and machine mounting belong to the next integration stage.

## D-hub: neither “tiny overlap means incompatible” nor “enlarge it to pass”

Manufacturer [1309-0016-1006](https://www.gobilda.com/1309-series-sonic-hub-6mm-d-bore/) explicitly specifies a 6 mm D-shaft, 2 clamp screws and release during disassembly. This **manufacturer-specified combination** supports design compatibility.

However, manufacturer STEP puts the hub D-flat about 2.48 mm from center and shaft flat about 2.50 mm, producing about 0.669 mm³ nominal overlap. Open/clamped reference state, numerical tolerance and clamping displacement are undocumented. **No hub enlargement or fictitious shaft shaving removes it.** The exception remains “manufacturer-specified clamp interface, state unverified,” separate from physical insertion, tightening and torque checks.

The hub's 4 mounting holes form a square at center ±8 mm; pilot is 14×2 mm. A 4 mm test flange, 1 mm washers and M4×12 give nominal engagement 7 mm and 1 mm to the hub rear. Threadless CAD contact volumes are not interference-free clearance fits.

The product page lists hub mass 14 g, while an older linked sheet says 9.6 g. Whether this reflects bolts/body-only or revision differences is unresolved. **The earlier 4-item 59 g subtotal remains a purchased-assembly reference using 14 g, not conveniently reduced to 9.6 g.**

## Small BOM, mass and cost

All parts serve this one input cartridge, not an instruction to duplicate imports across every leg/shaft. Purchased hub/collar assemblies include clamp screws; they are not counted twice.

| Part number | Required quantity | Purchase unit | Displayed USD unit price | Evidence |
|---|---:|---:|---:|---|
| 2101-0006-0120, 6 mm D-shaft, 120 mm long | 1 | 1 shaft(s) | 4.69 | [Manufacturer](https://www.gobilda.com/2101-series-stainless-steel-d-shaft-6mm-diameter-120mm-length/) |
| 1611-0514-0006, flanged bearing | 2 | 2 piece(s) | 3.99 | [Manufacturer](https://www.gobilda.com/1611-series-flanged-ball-bearing-6mm-id-x-14mm-od-5mm-thickness-2-pack/) |
| 2910-0919-0006, clamp collar | 2 | 1-pack ×2 | 4.49/piece | [Manufacturer](https://www.gobilda.com/2910-series-aluminum-clamping-collar-6mm-id-x-19mm-od-9mm-length/) |
| 1309-0016-1006, metal D-hub | 1 | 1 piece(s) | 7.99 | [Manufacturer](https://www.gobilda.com/1309-series-sonic-hub-6mm-d-bore/) |
| 1521-0008-0040, 4 mm steel spacer | 2 | 4 piece(s) | 2.49 | [Manufacturer](https://www.gobilda.com/1521-series-6mm-id-spacer-8mm-od-4mm-length-4-pack/) |
| 2800-0004-0012、M4×12 | 4 | 25 shaft(s) | 3.59 | [Manufacturer](https://www.gobilda.com/m4-x-0-7mm-zinc-plated-socket-head-screw-12mm-length/) |
| 2800-0004-0020、M4×20 | 4 | 25 shaft(s) | 3.99 | [Manufacturer](https://www.gobilda.com/m4-x-0-7mm-zinc-plated-socket-head-screw-20mm-length-25-pack/) |
| 2801-0004-0008, 4×8×1 mm washer | 12 | 25 washer(s) | 1.99 | [Manufacturer](https://www.gobilda.com/2801-series-zinc-plated-steel-washer-4mm-id-x-8mm-od/) |
| 2812-0004-0007, M4 locknut | 4 | 25 piece(s) | 2.99 | [Manufacturer](https://www.gobilda.com/m4-x-0-7mm-nylock-nut/) |
| Printed: carrier / retainers / flange | 1／2／1 | As listed in STL quantities | Material price assumed | [BOM](BOM.csv) |

**Minimum purchase lots including surplus, not just installed quantities: $40.70.** At assumed JPY 140/160/180 per USD: JPY 5,698/6,512/7,326. Japan shipping, import taxes and exchange/payment fees remain separate and unresolved. Prices/options displayed on month 9, day 27 do not reserve stock or guarantee arrival.

| Mass | Evidence | Value |
|---|---|---:|
| Earlier subtotal of 4 items only | Nominal purchase-page values | **59.00g** |
| All purchased parts | Above plus spacers and all fasteners | **85.28g** |
| 4 printed solids | Actual CAD solid volume × assumed PETG density 1.27 g/cm³ | **39.70g** |
| Cartridge total | Sum of the above 2 entries | **124.98g** |
| Measured / sliced mass | Not performed | **UNKNOWN** |

Fit coupons have assembly quantity 0 and are excluded from machine mass. At assumed filament JPY 2,000–4,000/kg and 1.2× support allowance, body material costs about JPY 95–191; this is not actual sliced consumption or purchase of 1 spool. Initial cost separately includes 1 coupon(s), about 13 g, distinguished from body-only in `procurement.json`'s `firstPrintIncludingCouponAndWasteCostJpy`. Failed prints/reprints are unresolved. **This small BOM does not establish a complete-walker budget of 2 × 10,000 JPY.** The 4 stand/machine mounting screws are excluded because mating thickness is unset; this does not permit unmounted operation.

## Checks performed

Actual manufacturer STEP was read privately and compared separately with new public dimension models. Vendor geometry is not distributed.

- Checked 630 static pairs and 7,560 moving/fixed combinations at 24 poses spaced 15°. No overlap outside threaded and designated D-clamp interfaces.
- Sampled rotating/printed minimum clearance about 1.080 mm. Also checked all rotating parts at X=−0.60/0/+0.15 mm and 30° increments.
- Left outer-ring travel −0.30–0 mm and right travel ±1 mm gave carrier/retainer overlap 0.
- Front/rear 4 mm spacers each contact actual manufacturer inner-ring faces over about 13.91 mm².
- Recorded bearing-then-cap order, leftward shaft extraction, upward hub/flange extraction after shaft removal and upper clamp-key access at selected stop angles.
- Native reload: 36 objects, 44 solids; matching STEP volumes/placements. 4 STL types are closed single solids within 230 mm bounds.

These check stated samples/tool envelopes, **not every continuous path, finger, tool or physical tolerance condition**. Free passage through the 6 mm bearing bore and D-clamp requires manufacturer specifications and physical checks.

## Do not confuse demand, resistance and margin

A simply supported shaft-only screen with 80 mm support spacing and 2 N at X=67 mm gives maximum deflection about 0.00183 mm and bending stress 2.11 MPa. At 12 Nmm torsion, twist is bounded around 0.000102–0.000144 rad. **D-section torsion constant is not replaced by polar second moment.** Loads/E/G are rounded comparative assumptions near R3 inputs, not actual/allowable test loads or material certificates.

Holder, printed-seat and fastening deformation are excluded. Manufacturer starting/running torque values were not found; 0.2/0.6/2.0 Nmm for 2 bearings remain **sensitivity inputs**. Selecting parts or avoiding CAD rubbing does not establish that physical resistance stays below them.

Net fluid-torque proxy, actual-part resistance and optional downstream 2× margin/supply derating 0.5 are separate. Defining cartridge geometry does not turn uncalibrated fluid values into guarantees.

## Regeneration

Uses existing FreeCAD 1.1.3 bundled Python and NumPy/SciPy/trimesh. Manufacturer parts are individually downloaded into private folders outside the repository as `bearing.step / collar.step / shaft.step / hub.step / spacer.step`. Public downloads are not redistributed.

```sh
/Applications/FreeCAD.app/Contents/Resources/bin/python \
  scripts/ver3/build_input_cartridge.py \
  --freecad-lib /Applications/FreeCAD.app/Contents/Resources/lib \
  --vendor-dir /path/to/private-reference
python3 -m unittest discover -s scripts/ver3 -p 'test_input_cartridge.py' -v
python3 scripts/ver3/cartridge_report.py
python3 scripts/ver3/cartridge_report.py --verify
```

These commands generate/check data; they do not operate printers, dryers or the user's live CAD scene. Native files contain timestamps, so byte differences are not automatically geometry differences; compare shape, placement, volume and input hashes.
