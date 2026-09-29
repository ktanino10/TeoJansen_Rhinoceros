# Common input cartridge assembly and removal

[日本語 (original)](ASSEMBLY_ja.md) | **English** | [Document languages](../../README_en.md)

> Presentation-only translation of the unchanged Japanese source. Source SHA256: `75095ecd6051ff8c18796e634a3bb7f79c1be22b6fe8187d0f0531d7dced68d0`. Numbers, part IDs, equations, code and qualification limits are retained; this is not a new engineering revision.

**`v3-common-input-r4-01`. Partial-assembly sequence checked in actual CAD; printing, physical assembly and equipment operation are unperformed.** A new common input unit, not a drop-in V2 replacement. No rotor, legs, gear train or string/coin load fixture is included.

X is axial, Y lateral, Z up; X increases left to right. [BOM](BOM.csv) and [canonical instances/operation set](assembly.json) govern. Native labels match the names below.

## Preparation

Print in mm at 100%. Carrier rails face the bed; retainers/flange/coupon use flat faces. Horizontal carrier bearing bores need supports/bridging/cleaning not yet sliced. Do not press bearings into the body without cleaning and fit checks. Do not apply old 150% scaling.

Starting tool choices: 3 mm hex for external M4, 7 mm nut wrench, 2.5 mm hex for hub clamps and 3 mm hex for collar clamps. Check actual fasteners. Measuring tools are needed for fabrication, but user ownership is not assumed and no purchasing/measuring is performed for them. Unpublished tightening torque is not invented.

## Assembly sequence

1. **Check coupon and carrier.** `Q_BEARING_FIT` is a coupon with quantity 0, not installed. Starting from the corner with the 2×3 mm notch, compare seats 14.0/14.15/14.3/14.45 mm with real bearings and assess the body's nominal 14.2 mm bore. Do not bolt-force tight fits or push outer rings through inner-ring loading. 4 mounting holes exist, but mating material, mounting screws and fixing require separate confirmation.

2. **Insert `BEARING_LOC` from the left, then fit `CAP_LOC`.** Flange faces left; bearing X=14–19 mm, flange 14–15 mm, cap 10.7–13.7 mm. Use 2 M4×20 screws, 1 washers on each head/nut side and 1 locknut each. Seated caps retain nominal 0.30 mm outer-ring space. Before shafts/collars are inserted, nut tools have straight access.

3. **Insert `BEARING_FLOAT` from the right, then fit `CAP_FLOAT`.** Bearing nominal X=94–99 mm, flange facing right within the long X=97–100 mm groove; cap 100–103 mm. Use 2 M4×20 screws with head/nut washers and locknuts as on the left. Preserve ±1 mm outer-ring movement; do not add a right collar and axially clamp it.

4. **Preassemble `D_HUB`+`TEST_FLANGE` outside the carrier.** Match 4 holes on a 16 mm square; orient the 14 mm pilot into the 14.3 mm pocket, 2.15 mm deep. Use M4×12 and 1 mm washers, 4 each. Nominal engagement is 7 mm with 1 mm to the hub rear. Distinguish these 4 external screws from the hub's 2 clamp screws. Place the supported unit between bearings from above; its displayed final position does not imply shaft attachment.

5. **Place left locating spacers/collars.** `SPACER_OUT` at X=10–14 mm, `SPACER_IN` at 19–23 mm. Bosses face spacers. Nominal outer/inner collar boss faces are 9.9/23.1 mm, leaving 0.1 mm per side, 0.2 mm total play. The 2 collars are not distributed one per bearing. Support shaftless parts against falling.

6. **Release clamps and insert `SHAFT` from the left.** Pass outer collar, outer spacer, left bearing, inner spacer/collar, hub and right bearing. This is the manufacturer's 6 mm D-shaft/metal-hub pairing. Align flats; do not force insertion, file the shaft or enlarge CAD hubs. Distinguish tiny reference overlap from real fit as [explained](README_en.md).

7. **Check positions/free clearance, then fasten.** Hub body X=35–43 mm, test flange 43–47 mm. Leave space between inner collar/hub. Collar screws clamp the shaft, not preload bearings. Check outer-ring play, total inner-ring-stack clearance 0.10–0.30 mm, right outer-ring float and rotation after tightening. Stop for rubbing, sinking caps, increased resistance or strong misalignment. Specific torque/low starting resistance remain unverified.

8. **Finish as an unpowered checking stage.** This document does not direct dryer, motor or string-load operation. Separately verify bench fixing, purchased-part tightening, physical fits and protection. Apparently free unloaded motion does not qualify supply torque, all-angle self-starting or 30 cm walking.

## Removal sequence

![Actual-CAD explanatory removal layout](removal_sequence.svg)

With power absent, all movement stopped and parts supported, release hub/collar clamps. **Extract the shaft left first**, then lift out the hub/test-flange unit; remove inner collar/spacers after the shaft too. Do not pass a 32 mm hub through a 6 mm bearing bore or lift it with the shaft retained.

For explanation, the figure offsets the shaft 124 mm left, flange 50 mm up and collars sideways. Not a simultaneous-motion instruction. Leftward shaft and upward flange paths are separate entries in `assembly_access.json`. Verify D-interface release and real fit using manufacturer instructions and physical parts.

Remove rotating parts before accessing cap screws/nuts to remove bearings/caps. Left bearing exits left, right exits right. Do not assume a long nut-driver path while the hub remains inside the carrier.

## Tool paths and tolerances

`assembly_access.json` checks a 7 mm nut driver with OD 12 mm/length 28 mm and key-shaft envelopes diameter 4 mm, lengths 26/28 mm. Clamp access is recorded from the upper half-space with the entire rotating assembly at the same selected stop angle—not automatic rotation during work. Actual tool/finger shape and all-angle usability are not guaranteed.

Cap-seat indentation/tightening deformation is unmeasured. Acceptance calculations allow cap compression/sinking up to 0.05 mm; exceeding it invalidates the assumptions. **Crushing plastic to fit or eliminating play by tightening is not assumed.** Check metal inner/outer contact faces, side-specific tolerances and thermal/deflection allowances separately.

Even with cartridge geometry, quantities and paths defined, the three new whole machines, actual rotor capture efficiency and physical part friction remain future work.
