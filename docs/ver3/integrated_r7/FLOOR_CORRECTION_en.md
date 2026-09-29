# r7-16-floor2: bounded floor, gear and commercial-fastener corrections

[日本語 (original)](FLOOR_CORRECTION_ja.md) | **English** | [Document languages](../../README_en.md)

> Presentation-only translation of the unchanged Japanese source. Source SHA256: `f8c2f0b6322a1d868d31d570d0dfa3f20c20d20ee5d4266dc07910f30944280d`. Numbers, part IDs, equations, code and qualification limits are retained; this is not a new engineering revision.

[Publication-preparation record](publication_readiness.json) is separate from technical checks below. Explicit approval on 2026-09-28 updated the materials guideline to about JPY 24,000/machine. Tools, shipping and unresolved taxes remain separate; no purchases. [Budget-only evidence](budget_metadata_update.json) tracks unchanged preapproval CAD, physics and each set of 73 frames.

**Old r7-15/slice1 had floor interference. Passing support-foot calculations did not establish clearance of every object from the floor.** PR10/old revisions remain unmodified, with [original failing controls](review/floor_conflict_baseline.json) preserved. These are author geometry/calculation/finite-check corrections, not new independent review or physical walking tests.

Canonical floor is Z=0; native body datum Z=70 mm. Original double-precision meshes and stored first-order small-angle mapping already gave C PET Z=−5.201387/−5.519445/−4.388603 mm at 0/120/240°, C output gear Z=−1.249765 mm at saved 110°, and B left PET Z=−0.011338 mm at 120°. Rendering orthogonalization/unresolved rocker angles were not the cause.

## C's actual gear pairs

Simply moving the large 156-tooth wheel upward in an m1, 13×12 trial still overlapped the main shaft by 29.0124 mm³ and output connection by 47.5167 mm³. [Rejected trial preserved](review/ratio_swap_collision_control.json).

Final C: **pair 1: m0.9, 20°, 12/156 teeth, shifts +0.35/−0.35; pair 2: m1, 25°, 12/144 teeth, shift 0**. Total 156:1 and 2 stages are preserved. Simple reduction to m0.9/25° was rejected because contact ratio 1.210 missed the existing 1.3 criterion. Adopted pair: contact ratio 1.386, minimum tip width 0.538 mm and standard-rack undercut avoidance. Criteria were not lowered.

Wheel 1's outer radius 70.785 mm leaves about 3.215 mm radial margin to the output-connection sleeve radius 4 mm at center distance 78 mm. Tips, shifts, centers and phases are canonical inputs checked against actual B-rep flanks. Do not mix C pair 1 with old C or A/B m1 parts.

Shaft positions, frame/guards, speeds, mass/center of mass, reactions, required torque and contact frames were regenerated from actual geometry. Gear reactions use real pitch radii and enter input-shaft bending. Differences from earlier gravity/wind-only evaluation are not directly mechanical-improvement effects.

## PET and unmodified commercial fasteners

Full-width rectangular PET lower edges following maximum side diameter were replaced by rotational-envelope contours retaining supports/upper connections. Upper extra cover is 3 mm; the floor-near final gear's lower cover adds 0.65 mm, leaving 0.35 mm after cutting-profile allowance 0.3 mm. This is not an exclusion exposing gear tips, nor safety-standard/physical-deflection certification.

Rocker-pin region now uses the commercial arrangement below. **No precision cutting, machining to 12.5 mm or 0.8 mm-thick wrench is required.**

- Unmodified commercial M2×12 and M2 nylon locknut (4.5 mm AF, 2.5 mm high). Not demonstrated equivalent in holding torque/reuse life to old 2 jam nuts.
- A 1 mm step lets smooth 8 mm sleeve ends and steel washers carry clamp force. Threads are not sliding surfaces. Foot placement, pad radius/area, spring rate and 6 mm stroke are unchanged.
- DN-03 clearance diameter 8.2 mm gives local fork width 12.8 mm, retaining 2.3 mm side material and 1 mm stepped ear thickness. Overall foot width is not enlarged.
- Noncontact boss radius 4.3 mm, rocker width 4.4 mm and paired small M4 washers (OD 8 mm, thickness 0.5 mm) total 5.4 mm, preserving 0.6 mm inside the 6 mm fork.

Acceptance checks screw length 11.7–12.3 mm below the head and nut height 2.5 mm against design conditions—not a retailer guarantee of those tolerances. Even shortest accepted screws calculate 0.6 mm beyond full nut height, but **check real chamfers, complete threads and nylon engagement during assembly**. Do not machine/force incompatible parts into agreement.

Nylon holding torque/reuse count is unverified. The plan assumes new nuts after disassembly, not an invented manufacturer reuse limit. A 10-pack supplies 6 nuts for 1 machine. See [commercial parts/tools](stock_fasteners_and_tools.json).

A/B tracking IDs retain old dimensional names; current parts follow `part_id`, BOM and native labels. Labels now identify commercial M2×12, nylon nuts and small washers. [A](A/stock_label_metadata_update.json) / [B](B/stock_label_metadata_update.json) confirm a metadata-only update retaining serialized B-rep, transforms and part IDs.

## Actual tool and work sequence

**ENGINEER DN-03** was checked in official 2026 catalog printed page 69/PDF page 72: AF 4.5 mm, tip OD 8 mm/length 18 mm, socket depth 9 mm, shaft 75 mm, overall 145 mm, handle OD 13 mm. Reference price JPY 360 excluding tax (JPY 396 at 10%). Model/published-dimension checks do not establish ownership or physical operation.

Prepare the CEF-integrated foot on a separate bench, hold M2 heads with normal 1.5 mm hex tools and fit nylon nuts using DN-03 before adding remaining links. Schema 2's `footFirstBenchSubassemblies` states this order/inventory.

DN-03 checks include the full 75 mm shaft in an OD 8 mm cylinder, plus OD 13 mm/length 70 mm handle—not only its tip. [A](A/rocker_pin_access.json) / [B](B/rocker_pin_access.json) / [C](C/rocker_pin_access.json) store insertion, rotational envelope and diameter 70 mm/length 75 mm grasp space. Grasp space is a design condition, not a demonstrated hand/glove/posture fit.

## All-body floor checks and deducted allowances

Per design: nominal 720 poses at 0.5° and 180 poses at 2° for 27 error sets × 3 guide-friction modes × 2 input-couple signs = 162 cases, **29,880 poses total**. Existing 6 wind conditions add 720 poses each, 4,320 total. This is not the Cartesian product of 6 wind conditions and all 162 error cases.

Track every instance, classifying only intended volumes of 2 rolling pads as contact objects. Rocker cores, all hardware and guards remain checked. Cores cover the full ±5° stop range rather than inventing an independent 0° angle. Nut-related quantity changes enter BOMs; checks dropping parts/cases are rejected.

Enclosing envelopes derive from native faces/edges. Partial arcs use their actual parameter ranges and tangent bounds, limiting over-envelope error to 0.001 mm. Overly coarse bounds treating nonexistent lower circular halves as material were corrected. Neither floor nor threshold was relaxed.

Worst-case examples follow. **Z lower bounds conservatively enclose actual geometry with the listed errors, springs and poses already included; they are not print measurements.** B's screws include the maximum accepted 12.3 mm length envelope.

|Design / object|Worst-pose lower Z bound, mm|Deducted upper-floor allowance, mm|Additional material-geometry allowance, mm|Remaining after allowances, mm|
|---|---:|---:|---:|---:|
|A · Locknut|0.415|0.300|0|0.115|
|B · Maximum-length commercial M2 screw envelope|0.389|0.300|0|0.089|
|C · Locknut|0.419|0.300|0|0.119|
|A · Lowest PET|1.150|0.300|0.300|0.550|
|B · Lowest PET|0.999|0.300|0.300|0.399|
|C · Lowest PET|1.319|0.300|0.300|0.719|

For B's controlling screw at the same worst pose: nominal bound 0.38854 mm, length-acceptance bound difference 0 mm, floor allowance 0.300 mm, remainder 0.08854 mm. The head controls this pose; maximum length was not excluded. Pose, springs and specified errors already affect coordinates and are not deducted twice.

Previously reported 0.03–0.05 mm referred to rejected precision-cut/thin-tool fastening trials, not the current commercial arrangement. Current remaining clearance is still not a large physical-stability margin.

**Excluded:** whole-machine/joint deflection, actual tightening/creep, purchased tolerances outside acceptance, wear, impact, arbitrary floor unevenness, real aerodynamics/resistance. Local input-tower beam deflection is not reused as whole-machine floor movement. Neither between-sample continuity nor the full tolerance domain is proven.

[A](A/floor_clearance.json) / [B](B/floor_clearance.json) / [C](C/floor_clearance.json) store raw Z, parts/phases/cases, material/floor allowances and screw-length effects. Actual tooth, static, 216-pose, inventory/path, floor, support and tool judgments remain separate.

## Slicing and cost scope

[Previous A/common 5 samples](SLICING_en.md) are byte-identical. C's new pair received [2 additional actual layer checks](C/SLICING_en.md). First supported face of the 156-tooth wheel recedes up to about 0.052 mm at tips; 0.2 mm support-film removal, tooth-bottom finishing and physical fit remain unverified. Not all machines or changed STLs were physically printed.

Commercial-arrangement first-purchase estimates remain A JPY 23,305.13 / B JPY 23,735.37 / C JPY 23,154.43. Comparison now uses the approved 2026-09-28 guideline of about JPY 24,000/machine. Exchange rate and material factor 1.2 are unchanged; shipping/unresolved taxes remain separate. Unowned hand tools such as DN-03, about JPY 396, cost extra. Approval is in `requirements_approval.json`; each `purchase_lots.json` governs purchase lots/sensitivities. Estimates do not guarantee actual payment or sliced cost.

New renderings/assembly documents use new geometry/contracts, not relabeled old media. Retain `manufacturingRelease=false`, qualified walkers 0, and UNKNOWN real wind/starting/30 cm walking. Independent rocker angles and complete rigid walking poses were still unresolved in this record; no new dynamics or arbitrary advance was added.

[Change-scope trace](floor_correction_scope.json): of 140 old STLs, 121 remain byte-identical and 19 are design changes. Final instances: A750/B785/C750. Nylon-nut substitution removes 6 per design in BOMs, not by hiding checked parts.
