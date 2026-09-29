# Ver.3 — Assembly, installation paths and bench checks

[日本語 (original)](ASSEMBLY_ja.md) | **English** | [Document languages](../README_en.md)

> Presentation-only translation of the unchanged Japanese source. Source SHA256: `531fee38939b848a58a7b2d4d98a59ea927f72f80a0afeca2ceb94770a057616`. Numbers, part IDs, equations, code and qualification limits are retained; this is not a new engineering revision.

**Instructions for comparative prototypes to be read with drawings. Physical assembly, printing and wind tests have not been performed.** Do not infer unknown purchased-part dimensions, materials or tightening specifications from simplified CAD.

[BOM A](BOM_A.csv) / [B](BOM_B.csv) / [C](BOM_C.csv) govern IDs, quantities and cut lengths. Only `printed` parts are printable in each `STL/Ver.3/A|B|C`; `purchased`/`cut_to_length` are purchased/fabricated. The two Q-prefixed types are fit coupons with assembly quantity 0.

Coordinates: **X axial, Y leg travel plane, Z height**. Left is −X and right +X, not the apparent front/rear. Mirrored leg triangles carry `_R`.

## Tools and prerequisites

Use a caliper, roughly 0.05/0.1 mm shims/feeler gauges, a straight alignment rod, 2.5/3 mm hex keys and 5.5/7 mm small wrenches. M4 countersunk/M4 button heads nominally use 2.5 mm; ordinary M4 cap heads and the specified hub use 3 mm. Check actual purchased fasteners.

REX shafts require cutting/end finishing to BOM lengths and axial M4 taps at both ends. Without suitable fixtures/experience, investigate pre-machined parts or machining services. The specified cut lengths are not a claim of catalog stock.

Print at **100%, mm**, without applying historical 150% again. Flat faces of gears, frames, forks and legs face the bed; cups use an end face. STLs are oriented with minimum Z=0. Determine local infill, dimensional compensation and cup brims using coupons. Unverified slicer settings do not guarantee strength or mass.

A's largest frame is about **254.4 × 256 mm**, excluding brims and edge margins on a 256 mm-square bed. Check the actual usable/forbidden regions in the slicer first. Scaling down to fit would break purchased-part interfaces; a larger usable area or separately designed split is needed. Print success is not claimed.

## Numbered assembly sequence

1. **Check both coupons first.** Use `Q_BEARING_FIT`'s 21.9/22.1/22.3 mm pockets and `Q_JOINT_FIT`'s holes against actual bearings, shafts and bushes. The 22.2 mm seat is an FDM-compensated starting point, not guaranteed fit. Do not use excessive-play or splitting press-fit combinations.

2. **Sort shafts, sleeves and spacers.** Separate intermediate REX shafts, end shafts, rotor shaft, 6 mm fixed shaft and M4 tie rods by BOM ID. Similar tube lengths have different roles. Finish ends parallel, avoiding burr loads on inner rings/plastic. Check M4 shaft-end engagement without bottoming.

3. **Insert frame/retainer nuts first.** Insert nuts in `P_FRAME_LEFT/RIGHT/CORE/FRONT_LEFT/FRONT_RIGHT`'s M3 hex seats while backs are open. Apply bearing insertion force to outer rings. `P_BEARING_RETAINER` retains only the outer ring; shafts/inner-ring spacers pass freely through the central 20.2 mm opening. Do not clamp inner rings or shields.

4. **Prepare input-bearing carriages for A only.** Insert M3 retainer nuts behind the three `P_INPUT_CARRIAGE_*` parts, then bearings and retainers. Main-frame/left-front-carrier input holes are 28 mm clearances, not bearing seats. Loosely fasten four M4 countersunk screws in each carriage's slots, with flush heads and rear washers/locknuts. Do not finalize tension.

5. **Build the rotor independently.** A/C use `P_ROTOR_CORE`, integral `P_ROTOR_YOKE` and two cups, not stacked thin arms. Fasten two M4 at fork roots and M3 at cup ends through open nut seats. Opposite ends use `_R` hole placement. B fastens cups directly to small end plates. Four M4 bolts attach hubs; adhesive does not transmit torque.

6. **Prepare six mirrored/nonmirrored legs.** Correctly combine AB/AC/PC/DE rods with PBD/CEF triangles. At B/C/D/E joints, 3.2 mm metal sleeves slightly exceed 3 mm plastic. Check by hand that tightening stops on metal without locking plastic joints. Threads are not sliding surfaces. Distinguish P's sleeve for the 6 mm fixed shaft.

7. **Assemble three shared cranks.** Fasten hubs to paired `P_CRANK_CHEEK` cheeks with countersunk M4, heads clear of rod travel. Align **purchased REX hub flats**, not only the square holes. Canonical shaft corner reference is 15°; opposing flipped hubs index another 90°. Rotating 90° preserves the four mounting holes. Do not force shafts or change crank phase. Recess M4 button heads and thin 12 mm-OD end washers. Between cheeks place the table's 20 mm stack, double-supported by M4×45 pins, washers and locknuts. Operate end stops in the reference pose where legs do not block the main axis.

8. **Close the mechanism progressively from −X.** Main left frame → crank/opposing legs → next bearing frame → next crank. Fit sleeves, spacers and aluminum tubes in order on the 6 mm fixed shaft and two M4 tie rods. **Do not pass a 32 mm hub through a 8 mm bearing bore.** Install each bay's hub/shaft before closing its neighboring frame. Cranks are outer 0°, center 180°, outer 0°. Check intermediate REX shafts and every cheek phase.

9. **Insert rotor/transfer shafts and close the last frame.** Place the rotor between supports and slide the last frame over free shaft ends. Transfer shaft M1 and B's M2 avoid leg/rotor motion. Align with a rod and progressively tighten tie rods. Do not jam fixed-shaft spacers or preload multiple outer rings axially.

10. **Install shoes and replaceable soles.** Attach each shoe with M3 through F's metal sleeve without locking pitch rotation. Two ties sit in shallow sole grooves without excessive underside projection. B's CEF axial position differs from A/C; do not reuse their spacers. Match stage sides/layers rather than hiding center-of-mass issues with shoe width.

11. **Install side stages from the main frame outward.** Fit four M4 case rods, tubes and guard back plates in sequence; nonmounting guard regions have actual passage holes. Prefasten all four hub/gear screws outside the case, following step 7's flat reference and flipped indexing. Do not rely on reaching rear screws after inserting a gear. On B's right, **finish S1 and its window before S3**. Left S2 mounts to the transfer shaft. Fasten outermost windows before front carriers. Temporary carrier fitting for hand rotation/A alignment must not block window-screw access during fastening.

12. **Install and adjust A's belt.** Mount 24T using aligned manufacturer through-holes/counterbores, not a bolt forced through two threaded interfaces. Align grooves with 48T and fit the 520×9 mm belt. An open front carrier avoids stretching over flanges. Temporarily refit the carrier, align three carriages with one rod and adjust tension. Record slots; **remove the carrier with carriages/bearings as a unit to fasten the window**, then refit. Separate from the shaft opening are **four 8.4 mm screw-clearance holes on a 36 mm square**. They clear four projecting M4×30 screws over ±1.5 mm travel and cannot be omitted. Preserve settings and recheck alignment/hand rotation. 10 N/span is assumed, not measured. M1 and secondary-gear centers stay fixed. A S1 uses **13 mm shaft hole and M3×40**; spur windows use **10 mm and M3×35**. BOMs/templates follow these stage-specific values.

13. **Adjust positioning/retention and close cases.** Spacers/collars act only on designated locating inner rings of intermediate/rotor shafts. Main cranks use hub/collar/end-stop combinations. Measure nominal 0.2 mm play; do not tighten floating bearings. Follow hub manufacturer's tightening instructions. Check directions/ratio during temporary assembly, then **fasten windows, refit front carriers, and complete end stops/case fastening last**. Retain main-frame bearings/hubs; hand-support rotating parts or use suitable stands while carriers are off, without driving them. Guards are containment concepts, not certified finger/impact protection.

14. **Remove front carriers first for disassembly.** Stop wind/drive input and support machine/rotating parts. Release accessible end stops and outer case-rod fastening; **pull front carriers outward as bearing/retainer units, then outer window → hub fasteners → outer stage → inner window/stage**. Retain main-frame bearings/locators and prevent shafts/rotors falling. Remove A's carriages with the carrier, preserving slot settings and rechecking alignment on return. In B, remove S3's window, gear, hub, back plate and spacers before S1's window. Do not pass hubs/pulleys through bearing bores. Rotor removal also reverses main-frame assembly. Simultaneous video motion does not waive order or support.

## Shared-crank 20 mm stack

| Order | Axial length | Function |
|---|---:|---|
| Washer | 0.5 mm | Cheek side |
| Sleeve | 3.2 mm | Nonmirrored AB |
| Washer | 0.5 mm | Separate sliding surfaces |
| Sleeve | 3.2 mm | Nonmirrored AC |
| Washer | 0.5 mm | Separation |
| Sleeve | 3.2 mm | Mirrored AB |
| Washer | 0.5 mm | Separation |
| Sleeve | 3.2 mm | Mirrored AC |
| Washer | 0.5 mm | Separation |
| Spacer | 4.7 mm | To opposite cheek |
| **Total** | **20.0 mm** | All four rods must rotate |

Long spacers/pins at ordinary B/C/D/E joints and the F shoe pin differ from this stack. Check BOM IDs and [canonical assembly A](assembly_A.json) / [B](assembly_B.json) / [C](assembly_C.json).

## Reading installation paths and tool space

Actual sections are in [drawings](drawings). Inspect bearing, hub and end-stop sections, not only completed renderings.

[CAD installation checks A](assembly_access_A.json) / [B](assembly_access_B.json) / [C](assembly_access_C.json) record nut extraction and axial gear/hub or belted-pulley paths in the listed disassembly states. They do not establish passage through installed front bearings.

| Location | Required sequence / space |
|---|---|
| Gear M4 flange screws | Join gear/hub outside the case first, avoiding later rear-face access |
| Hub tightening | Remove front carrier then outer window, support rotation, orient the shaft and insert a 3 mm key |
| Shaft-end M4 button head | Access from the shaft end; recess must not enter the rod sweep |
| Carriage M4 countersunk heads | Use canonical slots, align all three; alignment rod must withdraw after tightening |
| Guard-window nuts | Insert into hex seats while backs are open, not forced into closed cavities |
| Guard-window screws | Some are hidden by front carriers. Remove carriers first; in B, remove S3 window/stage before S1's window. Do not silently assume unusually short or high-angle tools |
| Cup/fork nuts | Insert from the cup's concave side; curved walls must clear axial nut/tool paths |
| Transfer shaft / hub | Insert transfer shaft, install hubs progressively, then close front carrier |

## Bench checklist — All unperformed

For physical measurements. Calculations/videos are not evidence that these tests occurred.

| Unperformed item | Record / stop condition |
|---|---|
| Fit test | Outer-ring seats, shafts/bushes and bores. Do not proceed with cracks, excessive play or forceful press fits |
| Marked torque transmission | Continuous marks across shaft/hub/gear; start at low load. Do not conceal slip with adhesive |
| Axial play | Physically measure cold, starting around 0.1–0.3 mm; reset for manufacturer/actual conditions. Stop if tightening sharply increases resistance |
| Retention | End stops, collars, four gear bolts and case: check escape/loosening under low hand load, not to destruction |
| Unloaded stage rotation | Record starting resistance separately before/after leg connection and belt-tension changes |
| Full-turn hand rotation | At least two cycles with all legs. Stop for interference, catching or excessive play in rods, shafts, tubes, cases or shoes |
| Crank torque versus angle | Measure several angles with a small force gauge and known lever arm; convert `力 × 腕長` units if needed |
| Mass and center of mass | Physical measurements, not just slicer estimates; include part-mass differences, cables and additions |
| Bench walking | Material-point slip, individual foot loads, passive shoe rotation, tipping and frame bending; record differences from video |
| Rotor alone | Static torque with recorded airspeed, direction and rotor angle; record zero/reverse torque at adverse angles too |

Free wind-driven walking follows these checks and assessment of retention/tipping risk. 3D prints can break and eject parts; do not run an unverified large rotor unattended near people. No purchasing, printing, equipment operation or wind test was performed here.
