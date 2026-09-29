# Bounded redesign using a common commercial-dryer reference

[日本語 (original)](DESIGN_GATE_ja.md) | **English** | [Document languages](../../README_en.md)

> Presentation-only translation of the unchanged Japanese source. Source SHA256: `3d1ac38b0d92d8dc49ce1a525ea870f0dc450a73c117df2a6d03fc4cbd880368`. Numbers, part IDs, equations, code and qualification limits are retained; this is not a new engineering revision.

**`v3-commercial-r3-01` / Not new manufacturing CAD. Qualified complete prototypes: 0.**

Following acceptance of a common commercial-dryer reference, ReFa model number, photographs, anemometer and physical measurements were **removed as prerequisites for resuming design**. Old [`v3-r2-feasibility-02`](../feasibility_r2/GATE_ja.md) (Japanese archival original) remains unchanged; new common conditions informed dimensions, loads, synchronization and procurement. Work did not stop merely awaiting measurements. **Numerical shortfalls and manufacturing-error sensitivity remain under the fixed conditions below**, so complete-machine renderings/manufacturing release were not pursued.

Canonical sources: [inputs](../../../scripts/ver3/commercial_r3.json), [comparison JSON](comparison.json) / [CSV](comparison.csv), [source/figure revision contract](manifest.json). No physical airflow tests, purchases, printing, disassembly or appliance modification occurred.

## 1. Distinguish operating specifications, literature and assumptions

| Type | Evidence used | Inference not made |
|---|---|---|
| Representative commercial operating specification | Panasonic **EH-NE5L**. Manufacturer manual `SEHNE5L03 A1123-0`: **COLD = strong cold air**, built-in quick-dry nozzle described as producing strong/weak streams | No claim of manufacturer-measured cold-air velocity/width at 150 mm |
| Published cold-air experiment | Scott / Curran, ASEE 2025, paper 46692, §2.2/figure 8: “Hi, 150 mm, 6.4 m/s” in an experiment on a 19 mm disc | The table reports test-location velocity, not an established cross-sectional maximum, mean or Gaussian peak. Not a Panasonic/ReFa measurement |
| Reference design assumption | Cold air at 150 mm, following the model with the same nozzle/direction. **Assigning literature 6.4 m/s as the Gaussian peak is itself assumed**; velocity σ=20 mm | No airflow divided by an invented outlet area, electrical 1200 W equated to wind power, or hot-air values reused for cold air |
| Sensitivity inputs | Peak multipliers 0.8/1.0/1.2, σ 15/20/25 mm, aim offsets −10/0/+10 mm; 27 cells per design | ±20%, σ and aim errors are not measured confidence intervals or guarantees for all commercial dryers |

Official references: [product](https://panasonic.jp/hair/products/EH-NE5L.html), [specifications](https://panasonic.jp/hair/products/EH-NE5L/spec.html), [retailer-hosted manufacturer manual](https://aeonretail.com/Contents/careproducts/pdf/P-4549980746394.pdf). Literature: [ASEE paper](https://peer.asee.org/laboratory-fixture-for-heat-transfer-using-a-hair-drier.pdf).

The paper's separate 73°C/16.8 m/s outlet experiment and electrical-power heat balance are not used. Other cold-air entries are Hi 100 mm/7.3 m/s and Low 100/200/300/400 mm at 5.8/4.5/3.6/2.9 m/s; these do not become a Panasonic distance-decay law. Gaussian width is not derived from the separate 44 mm-diameter heat-balance example.

The manufacturer specifies hair drying/styling. Using it as a **calculation operating reference** is not manufacturer approval for model drive. No operation, mounting or inlet/outlet obstruction contrary to instructions is directed.

## 2. Link dimensions, ratios and rotor dimensions changed

![Changed pin-to-pin dimensions](linkage_layout.svg)

With the same mechanical 0/180° alternating tripod, scale 0.7 and leg orientation, only **5 pin-to-pin lengths** were searched. Circle intersections solve closure to reduce vertical velocity during stance. No arbitrary forward motion or stretched links are added.

| Changed physical dimension | R2 | R3 |
|---|---:|---:|
| QP | 26.60mm | 26.9mm |
| OQ | 5.46mm | 7.4mm |
| DE | 27.58mm | 30.2mm |
| CF | 34.30mm | 37.1mm |
| EF | 45.99mm | 43.3mm |

Finite search: seed 27, maximum 60 generations, stopped at 2,440 evaluations—not convergence to a global optimum. Candidates rounded to 0.1 mm real pitches were reselected from 550 meeting conditions on a 0.25° grid. Merely rounding the continuous best would drop foot lift below 8 mm, so it was rejected. Records: [search JSON](linkage_search.json) / [closed-link evaluation CSV](linkage_search.csv). Invalid closures are counted in JSON `rejectedCounts.closure`, not CSV evaluation rows.

![Body-bounce comparison](gait_improvement.svg)

| Kinematic metric under the same definition | R2 | R3 nominal | R3 single-dimension ±0.1 mm error |
|---|---:|---:|---:|
| Body bounce | About 1.215 mm | About 0.354 mm | Maximum about 0.437 mm |
| Maximum vertical velocity coefficient during stance | About 3.224 mm/rad | About 0.477 mm/rad | Individual values in JSON below |
| Foot-path width over support interval | About 44.44 mm | About 45.15 mm | Individual values in JSON below |
| Maximum swing-phase ground clearance | About 15.67 mm | **About 8.25 mm** | **Minimum about 7.57 mm: below 8 mm criterion** |
| Horizontal velocity-coefficient jump at handoff | About 5.26 mm/rad | About 0.10 mm/rad | **Maximum about 6.64 mm/rad: above R2 nominal** |

Reduced bounce trades against foot lift and handoff sensitivity to fabrication errors. [Tolerance JSON](linkage_tolerance.json) varies one dimension at a time by ±0.1 mm, not every error simultaneously. **These results are not hidden behind claims that slip is solved or tolerances are robust.** Even flat floors have sole/assembly/surface errors; nominal optimization alone cannot authorize manufacturing release.

## 3. Revisions retain the three concept directions

| Design | Rotor diameter × width | Reduction | Rotor proxy mass added to R2 mass inputs |
|---|---|---|---:|
| A: large rotor, fewer stages | 150×48mm | 4×4=16:1, 2 stages | About 48 g |
| B: small rotor, high reduction | 70×48mm | 5×5×5=125:1, 3 stages | About 10 g |
| C: intermediate, generated lightweight design | 100×48mm | 5×5=25:1, 2 stages | About 12 g |

Whole-machine mass is not conveniently reduced. R2 mass-sensitivity inputs carry forward, adding only increased thin-wall/end-plate rotor volume. Not sliced, measured or final-CAD mass. B's high reduction adds no energy and costs speed, stage resistance and rotor inertia referred to the crank. Inertia is stored in each `candidate_*.json`'s `rotor_mass_proxy`.

Synchronization conditionally uses **two connecting rods in quadrature at 0/90°**, already compared in R2; shafts do not rotate independently. It includes 6 sliding interfaces, preload sensitivity 0/1/3 N and friction-induced reaction increases. Complete rod layers, tools and assembly tolerances remain unverified. This is not unbounded new-method exploration.

Fixed friction inputs are unchanged: journals 0.05/0.10/0.18, starting resistance of 1 bearing(s) 0.1/0.3/1.0 Nmm, gear efficiencies 0.95/0.90/0.80. These are not measured bounds. Values are not lowered merely by assuming low-friction purchases.

Pin reactions use frictionless-pin balance; static-friction losses are then added from load, relative speed and radius. Input torque and overall support reactions iterate, but friction-moment redistribution of every internal reaction, impact and acceleration/contact dynamics are not solved. Air loads cover the rotor, not the complete frame/guards. The upper sensitivity value is not a rigorous physical maximum.

## 4. Required torque at the same angle and in the same case

The table evaluates each design at its **nominal total-demand peak angle**, not a sum of component peaks at different angles. [Breakdown CSV](torque_decomposition.csv) and each design JSON's `torque_decomposition_at_same_peak` are canonical.

| Input-shaft equivalent, mN·m | A：191.5° | B：203.0° | C：190.5° |
|---|---:|---:|---:|
| Net leg demand through ideal reduction | 0.520 | 0.070 | 0.308 |
| Reduction-gear losses | 0.122 | 0.026 | 0.072 |
| Load-dependent rod losses | 0.049 | 0.007 | 0.029 |
| Rod preload/self-weight losses | 0.101 | 0.014 | 0.065 |
| Referred resistance of non-input bearings | 0.316 | 0.184 | 0.229 |
| **Resistance of 2 input bearings** | **0.600** | **0.600** | **0.600** |
| **Total demand** | **1.708** | **0.902** | **1.302** |
| Downstream demand after input bearings | 1.108 | 0.302 | 0.702 |
| Design-side 2× downstream target | 2.216 | 0.603 | 1.405 |
| **Gross torque target adding input-bearing resistance once** | **2.816** | **1.203** | **2.005** |

**“2×” is not simply 2 times total demand.** Multiply downstream demand after input bearings by 2, then add resistance of 2 input bearings once. Measured output after those bearings compares with the downstream target without deducting the same loss again. Factor 2 is a designer target, not a user-measured passing value.

Factors: [A](improvement_A.svg) / [B](improvement_B.svg) / [C](improvement_C.svg). “Ratio only” retains old mass, wind application point and linkage. Revised links, new wind application point, extra rotor mass and finally previously compared rods are added sequentially. A stronger reference wind is not mixed into an improvement percentage.

## 5. Uncalibrated supply proxy and quantified reference-condition shortfall

Angle-dependent supply: [A](torque_budget_A.svg) / [B](torque_budget_B.svg) / [C](torque_budget_C.svg). Full-crank demand: [A](startup_A.svg) / [B](startup_B.svg) / [C](startup_C.svg).

| Reference σ=20 mm, aim offset 0, nominal resistance | A | B | C |
|---|---:|---:|---:|
| All-angle minimum supply proxy × **design derating 0.5** | About 0.843 mN·m | About 0.289 mN·m | About 0.508 mN·m |
| Gross torque target in the same case | About 2.816 mN·m | About 1.203 mN·m | About 2.005 mN·m |
| This model budget | **FAIL** | **FAIL** | **FAIL** |
| Physical self-starting / continuous 30 cm walking | **UNKNOWN** | **UNKNOWN** | **UNKNOWN** |

0.5 is **design derating** of an uncalibrated panel-drag model, not a demonstrated lower supply bound or physical safety factor. The conservative budget uses minimum rotor-angle supply and maximum crank-angle demand; angular averages or ideal momentum bounds cannot qualify self-starting.

Across 27 cells, forces were integrated at 1° rotor spacing with 256 rays; support/friction were recalculated from lateral/vertical forces and signed torque. Demand samples include 2° spacing and both sides of contact handoff. All three designs met the derated-0.5 target in **0/27** cells for both nominal/high resistance. Nominal supply/target ratios are about A 0.105–0.591, B 0.074–0.403, C 0.085–0.452.

This is not a measurement proving the actual ReFa insufficient. The user's report of strong airflow remains qualitative evidence. It is not arbitrarily converted to m/s; comparison uses the accepted common design reference.

### Next dominant factors

At the same nominal peak, bearings account for about A 54%, B 87% and C 64%. More reduction in B does not reduce input-bearing resistance. Even algebraically setting bearing resistance to zero in A/C leaves the 2× target for current peak leg loads/other losses above supply proxy ×0.5; **replacing bearings alone is not a solution**. This is a fixed-peak algebraic diagnostic, not a new zero-friction simulation.

A bounded 18-condition check also varied vane count 12/16, curvature 20/40/60° and aim −0.5/−0.65/−0.8 radii. A small nominal benefit at −0.65 radius did not close the budget, so original 16 vanes/20°/−0.5 radius were retained. Favorable coefficients or airspeeds were not selected to force a pass.

## 6. Specific materials, structures and procurement issues

Member figures: [A](deflection_A.svg) / [B](deflection_B.svg) / [C](deflection_C.svg). New high-resistance inputs/reactions feed the tested R2 beam solver. AC pin spacing is unchanged, so its section model remains applicable. Figures/JSON retain per-member amplification, supports, loads and maximum locations. Shaft-only backlash-equivalent displacement is about 0.0025–0.0039 mm, not qualification of a complete frame, purchased interfaces and rod layers.

![Exclude incompatible contact surfaces](bearing_interface.svg)

NSK Micro tables distinguish **686A open / 686AZZ1 shielded** contact surfaces. Shield-side shaft-shoulder maximum OD is 7.4 mm. Domestic stainless spacer `c-sus-06-08-01` was listed at ID 6.2 × OD 8 × thickness 1 mm, SUS303, 2-pack JPY 1,400, shipping JPY 300. **Its 8 mm OD exceeds the limit by 0.6 mm, so this combination is not adopted.** Retail “ISC 686ZZ” identity with 686AZZ1 is unresolved.

Manufacturer: [NSK table, printed pages 42–43](https://www.nskmicro.co.jp/products/bearing/bearing_size_pdf/single_row_mm.pdf). Retailer: [spacer](https://store.shopping.yahoo.co.jp/neji-701/c-sus-06-08-01.html). Price/lead time were displayed on 2026-09-27, not reserved stock or tolerance guarantees.

A separate candidate was document-checked: **NSK 626ZZ (6×19×6 mm, JPY 198 tax-included, BENET lead time 1–2 days) + IWATA SC0607CB2**. IWATA lists 626ZZ fit, boss diameter 9.2 mm (0/−0.2), boss length 2.5 mm, overall 7.5 mm, bore 6 H8 and two M3×3 set screws. This is **not identical to the NSK Micro 626ZZ1 table**. Purchased NSK626ZZ contact faces, current collar dimensions, the 19 mm seat change, mass, friction and retail price remain open. Not substituted into R3 calculations.

Sources: [BENET 626ZZ](https://e-seki.net/products/detail1825.html), [IWATA catalog, printed pages 84–85](https://www.iwata-fa.jp/contents/assets/pdf/general.pdf). The IWATA PDF dates to 2022-09; old prices are not current quotes. A current distribution page's JPY 430 excluding tax is a catalog price, not a confirmed retail quotation.

The previous domestic partial estimate used JPY 160/USD: A/C JPY 11,816, B JPY 13,296. It is an **old partial table** including 14/16 bearings, 10/12 collars, minimum lots and tax—not a complete BOM including new rod, gear and support changes. Screws, shims, print material, import taxes and delivery remain unresolved. **The 1-machine budget of 2 × 10,000 JPY is retained and has not passed.**

## 7. Judgment and next boundary

Nominal link closure, same-phase mathematical paths and reduced bounce/required torque were confirmed. Specific remaining issues are **insufficient proxy-supply margin, worsened foot lift/handoff at ±0.1 mm errors and unresolved support interfaces**. That is the next gate—not “nothing can proceed without ReFa measurements.”

No new whole-machine rendering fills the gaps by presenting these as completed machines. Full FreeCAD/STEP/STL, complete BOM, tool/assembly routes and physical contact/self-starting are unfinished. Do not overlay these stresses or revised dimensions onto the site's first-cut GLBs. Comparison/figure `revisionId / designId / loadcaseId / method / units / displayAmplification / sourceHashes` travel together as one revision.

Optional physical observation is separated into [noninvasive V2 checks](V2_CHECK_en.md) and [blank record sheet](v2_observations.template.csv). Answers or photographs do not block continued common-reference design.

## Reproduction

```sh
python3 -m unittest discover -s scripts/ver3 -p 'test_*r3.py' -v
python3 scripts/ver3/commercial_r3.py
python3 scripts/ver3/commercial_r3.py --verify
python3 scripts/ver3/study_r2.py --verify
```

Uses existing NumPy/SciPy and tested R2 mechanics/beam helpers. No CFD, new large application, commercial generative-design service or physical appliance operation.

Runs 11 new and 17 existing automated checks. Refining nominal peaks from 0.5° to 0.25° gave matching A/B and about 0.000384% change for C. This is angular-sampling sensitivity, not drag/friction/print-error uncertainty. The 16 figures were checked for text overflow and representative appearance; linkage drawings were checked to stay clear of headings/dimension tables.
