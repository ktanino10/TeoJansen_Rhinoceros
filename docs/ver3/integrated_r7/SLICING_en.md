# r7: actual toolpath inspection of 5 representative parts

[日本語 (original)](SLICING_ja.md) | **English** | [Document languages](../../README_en.md)

> Presentation-only translation of the unchanged Japanese source. Source SHA256: `fb6df3ee3a57392dd7894fef37f7b2c97ece06357014e80230f7de2eac55f82e`. Numbers, part IDs, equations, code and qualification limits are retained; this is not a new engineering revision.

**5 parts were actually sliced and layers inspected, not fabrication-qualified.** Tooth counts/root continuity and model-side holes were checked, but 2 gears require removal of the initial 0.2 mm support spanning the bore. Physical support removal, tooth finishing, fit and strength remain unverified.

This records 5 representative r7-15/slice1 parts. STLs match reviewed `f50978e55384d1b03417ed7115395e6e2c010e85` byte-for-byte; those 5 remain unchanged through later [floor correction](FLOOR_CORRECTION_en.md). This does not mean all later CAD/mass/BOM is unchanged. It is not slicing of the full machine/all 140 STLs; revised C/feet are not in these 5 samples. No purchasing, printer connection/transmission/printing or dryer operation.

C's new m0.9 shifted pair has [a separate 2-part layer record](C/SLICING_en.md). Old 5-sample judgments or sub-0.04 mm values are not reused for new C's first supported face.

[Frozen 229-file unchanged check](frozen_artifact_invariance.json) is old slice1 history, not evidence for r7-16 geometry changes. Contracts/change scopes remain revision-specific.

## Assumptions and provenance

Official [OrcaSlicer 2.4.2](https://github.com/OrcaSlicer/OrcaSlicer/releases/tag/v2.4.2), Mac Universal on Apple Silicon. Published SHA256, signature and macOS Notarized Developer ID acceptance were verified; execution used an area separate from user settings. No unsafe-warning bypass or credential entry.

Official P1S 0.4 mm, 0.16 mm Optimal and Generic PETG are **inspection assumptions**, not confirmed physical P1S/0.4 mm/material. 255°C, Textured PEI 70°C, initial layer 0.2 mm, subsequent model layers 0.16 mm, Arachne, 4 walls, 100% rectilinear, 5 top/bottom layers, outer brim 5 mm. 2 gears use normal(auto) supports, top gap 0.2 mm/XY gap 0.35 mm. Independent support layers make total/model layer counts differ.

CLI does not automatically expand leaf-preset `inherits`; official parents were expanded and **actual CLI-exported settings** checked for machine, 256 mm bed, PETG, density, layer height and support. Inputs named PETG but effectively using PLA defaults were rejected.

Official nozzle offset is `[0,2]mm`. [Orca transforms](https://github.com/OrcaSlicer/OrcaSlicer/blob/v2.4.2/src/libslic3r/GCode.cpp#L8123-L8134) map G-code back to model/bed coordinates; first-layer bounds also match the 3MF within 0.022 mm. Automatic Z rotation is recorded from actual 3MF, not called zero rotation.

CLI warned that it could not create OpenGL 3.4, skipping 3MF thumbnails; missing optional `filament_retract_lift_above/below/enforce` source fields were also recorded. Actual G-code/settings were generated and principal effective values checked. Public layer images are separately drawn from G-code, not substitute completed renderings for unavailable thumbnails.

[Actual settings/STL hashes and preset inheritance](slicing/profile_provenance.json) / [machine-readable layer checks](slicing/toolpath_checks.json) / [judgment and unverified scope](slicing_status.json)

## Results

|Representative part|Model / total layers including support|Slicer material estimate|Slicer total time estimate|Checks / remaining work|
|---|---:|---:|---:|---|
|A input pinion|219／254|1.72g|24 min 26 s|12 teeth, continuous roots; remove 0.2 mm bore-bottom support|
|A compound gear 1|275／342|49.23g|2 h 46 min 22 s|Actual mating 144-tooth and coaxial 12-tooth wheels, connected spokes/roots; remove 0.2 mm bore-bottom support|
|13 mm guide coupon|81／81|2.16g|25 min 26 s|3 holes open through all model layers; actual guide friction/diameter unmeasured|
|Round-journal coupon|43／43|1.28g|17 min 15 s|3 hex holes and round outlines checked; real 7.90/7.95/8.00 mm distinction and bearing fit unqualified|
|Diameter coupon|31／31|19.03g|1 h 30 min 10 s|12 holes from 4–16.2 mm open through all model layers; compensation/fit unqualified|

Software estimates for 1 of each part, including each job's support/brim and about 6 min 41 s startup time. Material estimates may exclude standard startup purge and real waste/failures. These 5 samples do not replace solid mass, whole-BOM material factor 1.2 or the about-JPY-23,000 budget assumption.

Continuous extrusion-width-aware contours retain tooth counts at input 12-tooth layers 10.12/11.08 mm, mating 144-tooth layers 20.20/21.00 mm and compound 12-tooth layer 30.92 mm. Near-tip extrusion width is about 0.42 mm; maximum radial recession at specified sections is below 0.040 mm. A 4-wall setting cannot fit 4 lines in an approximately 0.53 mm tip. Images/toolpaths do not qualify fatigue, layer strength or physical meshing.

Specified hole centers remain open in model material through every layer, including extrusion width. This is not roundness or required-diameter inspection. Minimum bed-edge margin with supports/brims was 50.78 mm. Startup nozzle cleaning/purge motion is separate from this part-placement envelope.

## Support and removal still required

Exported input-pinion teeth begin 10 mm above the bed, creating initial Overhang wall without supports. Supports are added for this orientation; `supportsMayBeRequired` and generators for similar A/C inputs were corrected. B starts teeth at the bed, so the change was not mechanically propagated. At this slicing-record revision, all actual STLs remained unchanged.

Gear supports touch lower tooth faces, spokes and shoulders. XY clearance separates tooth sides, but removal chips/burrs can affect meshing. Images show access from the perimeter, spokes and open underside; **actual removal force or finished tooth shape is unverified**.

For both gears, support spans the shaft bore only in the first 0.2 mm bed layer. Reducing initial support expansion 2→0 mm did not remove this film; the final setting remains 2 mm. No deep bore support column remains, but remove underside support and check bore/journal physically. manufacturingRelease stays false.

## Actual layer images

Images draw actual positive-extrusion G-code moves and stated line widths—not completed renderings, printer screenshots or print photographs. Orange: support; blue: walls; purple: overhangs; red: bridges.

[Input-pinion layers](slicing/P_INPUT_PINION_layers.png) / [thin-tip detail](slicing/P_INPUT_PINION_tooth_detail.png) / [bottom support to remove](slicing/P_INPUT_PINION_support_bore.png)

[Mating compound-gear layers](slicing/P_COMPOUND_1_layers.png) / [144-tooth tip detail](slicing/P_COMPOUND_1_tooth_detail.png) / [bottom support to remove](slicing/P_COMPOUND_1_support_bore.png)

[Guide coupon](slicing/T_GUIDE_COUPON_layers.png) / [round-journal coupon](slicing/T_JOURNAL_COUPON_layers.png) / [diameter coupon](slicing/T_DIAMETER_COUPON_layers.png)

## Reproduction and publication scope

Give `scripts/ver3/slice_integrated_representatives.py` the approved Orca application and a new dedicated output: it copies 5 frozen STLs, checks settings and slices offline. `scripts/ver3/inspect_integrated_toolpaths.py` produces checks/small layer images from G-code. No device-control/transmission code.

Public artifacts are sources, setting names/diffs/hashes, check JSON and 9 layer images. Raw G-code, configured 3MF, application, downloaded DMG and private-path logs are not published. Not a manufacturing profile matched to actual printer, material and calibration.
