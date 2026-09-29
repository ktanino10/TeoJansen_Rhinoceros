# Ver.3 — Design, calculation and generative-design notes

[日本語 (original)](DESIGN_ja.md) | **English** | [Document languages](../README_en.md)

> Presentation-only translation of the unchanged Japanese source. Source SHA256: `1751d32707447164ab5b30562961aa254eff08529389edfbdf06e7810b632228`. Numbers, part IDs, equations, code and qualification limits are retained; this is not a new engineering revision.

**Status: first-cut comparative prototypes with actual geometry. Not a manufacturing release or validation of wind self-starting, physical walking or fatigue life.**

This package contains FreeCAD B-rep, STEP, printable parts, BOMs, Blender visualization of the same geometry and reproducible calculations. Videos are **kinematic visualizations using prescribed input and a contact approximation**. Contact residuals and small support margins are not hidden through stretched members, arbitrary body sliding or claims of experimental validation.

## 1. Problems this design addresses

| Item | Evidence type | Ver.3 response | Remaining checks |
|---|---|---|---|
| Rotor/gears slip relative to rods instead of rotating together | Primary failure explicitly identified by the user | Geometric engagement between metal REX shaft flats and metal hubs. Plastic gears, cranks and rotor plates bolt to hubs through actual holes | Purchased-hub tightening specifications and physical slip torque |
| Gears escape axially | Reported concern | Hub fastening, shaft-end M4 bolts/washers, collars, inner-ring-only spacers, outer-ring retainers and removable guards | Shaft-end tapping, end-face contact and physical end play |
| Support friction and misalignment | Hypothesis; not established seizure | Rolling bearings, nearby supports, assembly alignment and distinct locating/floating sides for each shaft | Actual starting resistance, bore diameter/alignment and print shrinkage |
| Insufficient starting torque | Unmeasured; desktop sensitivity calculations exist | Compare rotor dimensions, stages and reduction in three designs. Treat joint static friction and each bearing's starting resistance separately | Static torque versus airspeed, direction and rotor angle |
| Leg loads vary with crank angle | Full-cycle canonical linkage calculations | Three opposing-leg modules at 0/180/0°. Report contact support and material-point residuals by phase | Ground, passive shoe joints, frame flexure and inertia |

Adhesive is not in the main torque path. Collars are **axial retention components**, not torque keys.

## 2. Formal comparison scope

| Design | Rotor outer diameter × axial width | Transmission | Aim and tradeoffs |
|---|---|---|---|
| **A: large rotor, fewer reduction stages** | 300 × 180 mm | Purchased HTD5M toothed belt 24:48 and spur gears 29:87; total **6:1** | More input area, with belt-tension adjustment, wind loading, tipping and split-rotor assembly costs |
| **B: small rotor, high reduction** | 90 × 180 mm | Three 21:84 spur stages; **64:1** | Retain a small rotor at lower speed. More stages, bearings, starting resistance and parts. Reduction does not increase input power |
| **C: intermediate rotor, generated lightweight structure** | 180 × 180 mm | Two 21:84 spur stages; **16:1** | Intermediate dimensions/stage count. Parametric generative design of rib width, thickness and layout while preserving required regions |

All spur gears use module 2, pressure angle 20° and face width 8 mm. A's primary stage is **a toothed belt, not gears**. Old single-stage or all-stages-on-one-side concepts are not mixed into adopted drawings.

See [comparison.csv](comparison.csv) and [CAD summary A](cad_validation_A.json) / [B](cad_validation_B.json) / [C](cad_validation_C.json) for solid-volume, assumed-density and purchased-mass comparisons. These are not slicer-verified print masses. Reduced infill cannot be interpreted as mass reduction without a stiffness change.

The off-center gearbox mass is addressed by **distributing stages between both ends**, not enormous shoes or arbitrary ballast. B also adjusts the axial layer of its foot triangle. Pin-to-pin linkage lengths are unchanged.

## 3. Relationship to existing records

Measurements use unscaled repository STLs and drawings. [legacy_measurements.csv](legacy_measurements.csv) stores file-coordinate bounding dimensions. STL has no inherent units; mm follows the existing documentation.

Representative file bounds: Ver.2 rotor about 90 mm diameter and 180.692 mm wide; `gear.stl` about 67.44 × 67.48 × 23 mm; `Crankshaft_Part1.stl` about 40.70 × 97.31 × 37.39 mm. These are **file bounds**, not physical measurements, tooth counts or guaranteed bore sizes. PDF shapes, dimensions and parts tables were consulted, but no complete parametric Ver.2 model exists.

The old README's 150% / legs 160% are historical settings. **Ver.3 STLs use real-size mm at 100%**; do not scale to 150% again. New linkage/bearing/hub standards mean they are not drop-in Ver.2 replacements.

## 4. Positive torque transmission and axial retention

### Purchased interfaces

- goBILDA **1309-0016-4008 Sonic Hub**: for 8 mm REX, 7 mm across flats, 32 mm outer diameter, 8 mm body, pilot diameter 14 mm × 2 mm, four M4 holes on a 16 mm square, catalog mass 14 g.
- 8 mm REX is not “8 mm hex.” It is **a 7 mm-AF hexagon with corners finished to a 8 mm circle**. CAD uses that intersection section, not a renamed round rod.
- **Relative angles** of flats and mounting holes match the purchased part. With local hole-center angles 45/135/225/315°, flat normals start at 45° in 60° increments; shaft corner reference is 15°. Opposing flipped hubs index by 90° onto the same shaft. Square mounting holes and crank phases 0/180/0° are unchanged. This corrects the draft's 15° error found by independent comparison with manufacturer CAD.
- CAD includes hub/shaft engagement flats, pilots, gear/crank mounting holes, fasteners and shaft-end stops.
- Nominal 608 bearings are 8 × 22 × 7 mm. Balls, cages, threads and special commercial-hub flexures are simplified. Purchased parts are excluded from printable STLs.

These are **dimension models of purchased parts** based on standard dimensions and public manufacturer drawings—not redistributed manufacturer CAD or drawing images. Check stock, shipping, actual tolerances, material grades and tightening torque before ordering.

![REX reference angle and flipped-hub indexing](drawings/hub_clocking.svg)

### Load path

Rotor cups → bolted forks/end plates → four M4 bolts → metal hub → REX flats → transmission stages → metal hub → crank plate → double-supported M4 pin → legs.

The crank is not one continuous main shaft: AB/AC cross the main-axis center O, so a through-shaft would collide during a cycle. Actual geometry uses **three open crank bays, paired cheeks, a 20 mm pin gap and bay-specific REX shafts**.

M4 shaft-end stops sit recessed with washers, without heads projecting into rod clearance. Countersunk cheek/hub screws sit flush.

Locating-bearing inner rings use collars/hubs and **8.1 mm ID × 10 mm OD** spacers, not simultaneous clamping of shields/outer rings. Outer rings are retained by shoulders and retainers with 20.2 mm openings. Locating outer-ring pockets are 7.2 mm; floating ones 7.7 mm. Nominal inner-ring play is 0.2 mm, to be reset by physical measurement/shims. Do not axially clamp multiple bearings end-to-end into preload.

## 5. A's toothed belt is not a lossless line

The specified purchased combination is:

| Part | Checked specification |
|---|---|
| 3411-0014-0024 | 24T, HTD5M, 14 mm bore, 12 mm width, 9.25 mm belt groove, aluminum, 23 g |
| 3415-0014-0048 | 48T, HTD5M, 14 mm bore, 12 mm width, 9.3 mm belt groove, plastic, 42 g |
| 3412-0009-0520 | HTD5M, 104 teeth, 520 mm pitch length, 9 mm width, neoprene/glass fiber |

The 24T pulley has threaded and through-holes. **Use aligned through-holes and counterbores of 7.2 mm diameter × 4 mm depth, not two threaded interfaces.** Use the specified through-holes on the 48T side.

The open-belt equation is solved with small/large pitch radii $r$/$R$ and center distance $C$.

$$
L=2\sqrt{C^2-(R-r)^2}+\pi(R+r)+2(R-r)\arcsin\frac{R-r}{C}
$$

Center distance and small-pulley wrap matching 520 mm pitch length are in [selected_designs.json](selected_designs.json). At least 8 engaged teeth is **this design's screening criterion**. Real belt tolerance/stretch requires alignment of all three input-bearing carriages with one rod and tension adjustment through **actual ±1.5 mm slots**. Intermediate shafts and spur-gear centers stay fixed.

Initial tension of 10 N per span is assumed. About 20 N radial load is included in the common 30 N frame shaft-load assumption, not ignored. Starting resistance is varied per bearing; assumed belt efficiency is 0.95. Overtightening does not create low friction.

Purchased pulley/belt teeth are **clearance/display envelopes**. Do not use them as HTD manufacturing drawings or printable tooth data; use the specified compatible purchased parts.

## 6. Spur gears and rotation directions

Involute flanks are generated mathematically, with radial root closure. This does not reproduce a hob-generated root trochoid or tooth-root fatigue analysis. Checks cover tip/root clearances, material between holes and roots, contact ratio, unshifted interference and the complete meshing cycle.

- Pressure angle 20°, no profile shift. Input tooth count is at least 21, following KHK's explanation of standard undercut limits.
- Nominal total circumferential backlash is **0.30 mm**, removing 0.15 mm from each gear. A fit-test starting point, not a printer-specific guarantee.
- Contact ratio ≥1.4, tip thickness ≥0.8 mm and hole-to-root material ≥4.5 mm are this design's screening criteria.
- A's open belt preserves direction; one spur stage reverses it. B's three spur stages reverse overall; C's two preserve direction. Canonical signs match rotor-cup orientation.
- With positive crank rotation, signed input ratios are **A −6, B −64, C +16**. Intermediate-shaft ratios appear in [validation_A.json](validation_A.json) / [B](validation_B.json) / [C](validation_C.json).

## 7. Canonical linkage and advancing scenes

Reference lengths are factual dimensions from [Frido Verweij's Jansen mechanism explanation](https://library.fridoverweij.com/codelab/strandbeest/index.html). Code and illustrations were not copied; circle-intersection equations and diagrams were implemented independently.

| Segment | Reference length | Segment | Reference length |
|---|---:|---|---:|
| QP / OQ | 38 / 7.8 | OA | 15 |
| AB / BP | 50 / 41.5 | AC / PC | 61.9 / 39.3 |
| BD / PD | 55.8 / 40.1 | CE / DE | 36.7 / 39.4 |
| CF / EF | 49 / 65.7 | Scale factor | 1.4 |

O and P are fixed, A is the crank pin and F the foot. PBD/CEF are rigid triangles. OA becomes 21 mm, allowing space for the 32 mm-diameter metal hub, pin head and tools. Left/right legs are correctly mirrored closed linkages, not simply reciprocating rods.

![Canonical linkage and foot path](drawings/linkage.svg)

Full-cycle checks cover link closure, foot path, overlapping axial layers and clearance to fixed rods, auxiliary shafts and rails. Near-minimum AC/fixed-shaft-spacer clearance is also numerically minimized. Small CAD gaps are not guaranteed to survive printing.

### Walking-visualization definition

Advance derives from contact-shoe CAD vertices, support polygons and persistent material-point anchors. The whole body receives rigid transforms: **no arbitrary-speed sliding or stretched links**. All input rotors use prescribed 120 rpm.

| Design | Prescribed time for 3 crank cycles | Video duration |
|---|---:|---:|
| A | 9 s | 9 s, 1× |
| B | 96 s | 12 s, 8× |
| C | 24 s | 12 s, 2× |

This does not claim every rotor reaches 120 rpm at the same airspeed. It is **the same prescribed input** for speed comparison. Airspeed/assumed tip-speed-ratio comparisons are separately labeled calculations.

[walk_A.json](walk_A.json) / [B](walk_B.json) / [C](walk_C.json) store advance, ground gap, CAD-vertex penetration checks, support margin and material-point residuals per loaded contact episode.

The main table's slip metric is maximum horizontal displacement of a material point from its touchdown/video-start anchor within one continuous episode carrying **at least 2%** of calculated total load. **Partial episodes already active at video start are included and flagged.** Horizontal path length accumulates travel within the same episode and is a different quantity. Neither is the three-cycle total. Any ratio reports **body advance in that same episode**, not an entire cycle's distance as denominator.

| Final metrics using consistent definitions | A | B | C |
|---|---:|---:|---:|
| Maximum loaded-episode anchor residual (including initial partial episodes) | 9.55 mm | 10.30 mm | 8.88 mm |
| Maximum residual for fully contained loaded episodes only | 7.18 mm | 6.99 mm | 5.89 mm |
| All-near-foot material-point audit without load threshold (video-frame samples) | 8.90 mm | 8.54 mm | 7.56 mm |
| Maximum fully contained-episode residual in that audit | 7.16 mm | 7.03 mm | 7.35 mm |

[All-near-foot audit A](contact_review_A.json) / [B](contact_review_B.json) / [C](contact_review_C.json) tracks material points at actual video frames without excluding feet by load. Horizontal movement includes shoe rocking; it is not measured Coulomb-friction slip. The two audits use different references/sample intervals and are not mixed to claim improvement.

At least 3 geometrically near feet exist at every video sample, but during handoff only 2 feet in A/B and 1 in C may exceed the load model's 2% threshold. **This does not establish practical tripod load support at all times.** Near-contact tolerance 0.25 mm differs from display offset 0.02 mm; maximum absolute near-foot gap is about 0.269 mm.

3 mm is a demanding design-side target. Its failure is reported, not renamed a pass. The approximation uses 0.25 mm near-contact tolerance, rigid members, prescribed shoe-hinge poses and assumed masses—not ground contact dynamics, inertia, impact or actual friction.

**A positive support margin around 0.1 mm is not practical stability.** It does not adequately cover print, assembly and center-of-mass uncertainties. Sensitivity to ±5 mm center-of-mass shifts and wind tipping moments is a fixed-nominal-pose diagnostic, not guaranteed physical tipping resistance.

## 8. Torque, wind and starting resistance

All designs use common airspeeds 3/5/8 m/s, assumed torque-coefficient range 0.05–0.20 and friction conditions.

$$
T_\mathrm{wind}=\tfrac12\rho (2RL)\,R\,C_Q\,v^2
$$

Density is 1.225 kg/m³; $R$ is rotor radius and $L$ axial width. **Static torque coefficient is unmeasured** and can be zero or negative at adverse direction/rotor angles. Tables assuming positive coefficients cannot guarantee all-angle self-starting.

Compare static-friction coefficients 0.05/0.10/0.18, starting torque per bearing 0.1/0.3/1 Nmm and assumed ground-resistance coefficients 0.005/0.015/0.03. Joint reactions come from force/moment balance on each link, using journal radii and relative angular-speed ratios. **Starting friction is not collapsed into one transmission-efficiency constant.**

Nominal efficiency assumptions are 0.95 for the belt and 0.90 per spur stage. Each shaft's bearing resistance is referred to input through its actual ratio and assumed efficiencies. Friction assumptions are not selectively favorable to bearing-heavy B.

See [startup_A.json](startup_A.json) / [B](startup_B.json) / [C](startup_C.json) and [comparison summary](comparison.csv) for phase-dependent values and conditions. Available and required input are both shown. Failed starting phases are not assumed traversable by inertia once rotating. Inertia, wind pulsation and sustained rotation are unverified.

![Phase-dependent input torque under common assumptions](drawings/startup_torque.svg)

Ground loads use the second prescribed-walking cycle at common 1° intervals. Nonnegative whole-machine load distribution does not prove static/dynamic realizability of every internal mechanism including free shoe hinges. Local leg balance is conditional on those loads. AC's simple pin-supported Euler-buckling screening ratio is only about 1.56–1.94, not a strength margin covering print tolerance, layers and fatigue.

## 9. Scope of the executed generative design

The term is **parametric generative design**. No Autodesk Generative Design, CFD, solid FEA or topology optimization is claimed.

1. Search tooth counts, shaft/support positions and left/right stage distribution within the approved rotor-size/stage scope.
2. Constrain bearing/fixed-shaft/bolt-seat preserved regions, full rotor/leg motion, through-shafts, tool/installation regions and a 256 mm print envelope.
3. Generate ribs from Delaunay connectivity; subdivide long spans with physically connected nodes/ribs, not only calculation subdivisions.
4. Use common assumed shaft load 30 N, fixed-pivot load 10 N, Young's modulus 1700 MPa and allowable stress 10 MPa.
5. Calculate an in-plane linear axial-force network and an out-of-plane 1 N cantilever approximation on the longest free rib. Screen against 0.3 mm in-plane and 0.8 mm out-of-plane displacement.
6. For C, minimize volume proxy over the declared width/thickness grid. Distinguish summed overlapping rib/boss proxies from generated CAD solid volume.

Bounds/selected values: [design.json](../../scripts/ver3/design.json), [selected_designs.json](selected_designs.json). Candidates: [gear_search.csv](gear_search.csv), [structure search A](structure_search_A.json) / [B](structure_search_B.json) / [C](structure_search_C.json).

The following compares candidates within the same C shaft positions, preserved regions and loads.

| C structural candidate | Thickness × rib width | Summed-member-volume proxy | In-plane displacement proxy | Out-of-plane displacement proxy |
|---|---:|---:|---:|---:|
| Thick-rib baseline candidate | 8 × 14 mm | 1,101,318 mm³ | 0.02198 mm | 0.38717 mm |
| Selected generated candidate | 8 × 8 mm | 713,124 mm³ | 0.03846 mm | 0.67754 mm |

Volume proxy falls about 35.25%, while displacement proxies rise. Meeting the declared displacement screens does not validate physical stiffness. This is a **summed proxy** including overlapping ribs/bosses—not a claim of 35.25% less CAD solid volume or whole-machine mass.

This is not solid analysis adequately representing local screw seats, thin walls, bearing rings, print layers, joint bending or fatigue. Frame-volume reduction is not whole-machine efficiency improvement.

## 10. Files and regeneration

| Contents | Location |
|---|---|
| Dimensions, materials and assumptions | [scripts/ver3/design.json](../../scripts/ver3/design.json) |
| Closed links, velocities and canonical transforms | [core.py](../../scripts/ver3/core.py) |
| Constrained search | [system_search.py](../../scripts/ver3/system_search.py) |
| FreeCAD generation | [build_cad.py](../../scripts/ver3/build_cad.py)、[cad_parts.py](../../scripts/ver3/cad_parts.py) |
| Native, STEP and identical visualization mesh | [FreeCAD/Ver.3](../../FreeCAD/Ver.3) |
| Printable parts only | [STL/Ver.3](../../STL/Ver.3) |
| BOM including purchased/cut parts | [A](BOM_A.csv)、[B](BOM_B.csv)、[C](BOM_C.csv) |
| Actual sections and cover templates | [drawings](drawings) |
| Results and comparisons | [comparison.csv](comparison.csv)、`validation_*.json`、`intersections_*.json` |
| Assembly and bench checks | [ASSEMBLY_ja.md](ASSEMBLY_en.md) |
| Independent review | [REVIEW_ja.md](REVIEW_en.md) |

FCStd contains native Part features with names/specifications. Canonical geometry changes require editing settings/generation scripts and regenerating; this is not a Sketcher history that follows arbitrary text-property edits.

Use existing FreeCAD/Blender installations. This work installed no new large application, made no purchases and operated no printer.

```bash
# リポジトリのルートから。通常の Python 環境には requirements.txt の依存が必要。
python3 scripts/ver3/system_search.py

# macOS の既存 FreeCAD アプリの例。環境に応じて二つのパスを変更。
FC_PY=/Applications/FreeCAD.app/Contents/Resources/bin/python
FC_LIB=/Applications/FreeCAD.app/Contents/Resources/lib
"$FC_PY" scripts/ver3/build_cad.py --freecad-lib "$FC_LIB"
"$FC_PY" scripts/ver3/check_cad.py --freecad-lib "$FC_LIB" --only A
"$FC_PY" scripts/ver3/check_cad.py --freecad-lib "$FC_LIB" --only B
"$FC_PY" scripts/ver3/check_cad.py --freecad-lib "$FC_LIB" --only C
python3 scripts/ver3/validate.py
python3 scripts/ver3/walking.py
python3 scripts/ver3/contact_report.py
python3 scripts/ver3/startup.py --only A
python3 scripts/ver3/startup.py --only B
python3 scripts/ver3/startup.py --only C
"$FC_PY" scripts/ver3/drawings.py --freecad-lib "$FC_LIB"
python3 scripts/ver3/reports.py
"$FC_PY" scripts/ver3/access_checks.py --freecad-lib "$FC_LIB"

# Blender は別のヘッドレスプロセスで実行。既存のユーザーシーンを操作しない。
# ffmpeg / ffprobe も PATH に必要。生フレームはリポジトリ外の一時領域へ。
blender --background --threads 4 --python scripts/ver3/render_blender.py -- \
  --profile system --phase all

# 再レンダリングせず、保存済みネイティブとソース・動画を照合する場合
blender --background --threads 4 --python scripts/ver3/render_blender.py -- \
  --profile system --phase validate
```

Walking JSON pins CAD/mesh/core hashes. Regenerate walking/videos after CAD changes; do not use old images as evidence for new designs.

The old `first-cut` profile in `render_blender.py` is historical experimentation, not used for the current package. Current outputs are `Blender/Ver.3/ver3_ABC.blend` and `docs/ver3/media/` in `--profile system`. `.blend` has baked prescribed walking and gear-shaft rotation, requiring no automatic Python execution to view. In B's 8× video, the input turns −240° per video frame, so even correctly unwrapped rotation may show strobing at 24 fps.

Guard/window specifications derive from each stage's `guard_depth`, `window_aperture_mm` and `window_screw_length_mm`. A's belt stage is 35 mm deep with 13 mm shaft hole and M3×40; spur stages use 31 mm, 10 mm and M3×35. Front carriers block some straight window-screw tool paths, requiring carrier-first removal/carrier-last assembly. [Installation-path checks](assembly_access_A.json) record the required partial-assembly states.

A's four additional window holes use `carriage_screw_window_points`/`carriage_screw_window_bore_mm`: **8.4 mm diameter on a 36 mm square**. They include M4 carriage screws of diameter 4 mm, adjustment ±1.5 mm and remaining radial margin 0.7 mm. They differ from 3.3 mm window-screw holes and the 13 mm rotating-shaft opening. Carrier-unit removal with the window retained is checked at adjustment extremes too.

## 11. Public evidence and pending checks

- [KHK — Involute gear profile](https://khkgears.net/new/gear_knowledge/gear_technical_reference/involute_gear_profile.html)
- [KHK — Gear dimensions](https://khkgears.net/new/gear_knowledge/gear_technical_reference/calculation_gear_dimensions.html)
- [goBILDA Sonic Hub](https://www.gobilda.com/1309-series-sonic-hub-8mm-rex-bore/)
- [goBILDA REX shafting](https://www.gobilda.com/stainless-steel-rex-shafting/)
- [24T HTD5M pulley](https://www.gobilda.com/3411-series-5mm-htd-pitch-aluminum-hub-mount-timing-belt-pulley-14mm-bore-24-tooth/)
- [48T HTD5M pulley](https://www.gobilda.com/3415-series-5mm-htd-pitch-hub-mount-timing-belt-pulley-14mm-bore-48-tooth/)
- [HTD5M belt specifications](https://www.gobilda.com/5mm-htd-timing-belts/)
- [Jansen dimensional reference](https://library.fridoverweij.com/codelab/strandbeest/index.html)
- [Autodesk — preserve geometry](https://help.autodesk.com/cloudhelp/ENU/Fusion-GenerativeDesign/files/GD-PRESERVE-GEOM.htm)
- [Autodesk — obstacle geometry, including tools and motion](https://help.autodesk.com/cloudhelp/ENU/Fusion-GenerativeDesign/files/GD-OBSTACLE-GEOM.htm)

Required physical measurements remain: crank-angle-dependent machine loads, journal/bearing starting resistance, static torque versus airspeed/direction/rotor angle, printed mass and center of mass, shaft-end retention, walking slip and tipping. Missing experiments are not filled with estimates.
