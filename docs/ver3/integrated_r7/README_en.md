# Ver.3, 3 integrated designs: whole-machine geometry and conditional judgments

[日本語 (original)](README_ja.md) | **English** | [Document languages](../../README_en.md)

> Presentation-only translation of the unchanged Japanese source. Source SHA256: `cd8bf579f31b2316acab4d63d9c7b04016f498f3dcd0c633e6b3f991be0511b8`. Numbers, part IDs, equations, code and qualification limits are retained; this is not a new engineering revision.

**The primary requirement of 3 demonstrably working machines is unfinished.**
Old r3/r4/r6 and the public first cut are unchanged. This folder integrates new whole-machine CAD, complete BOMs, contact/drive calculations and assembly paths in one revision.
manufacturingRelease=false; qualified walkers=0. No purchasing, printing or dryer operation occurred. Publishing design documents in the existing repository/Pages is distinct from physical qualification.

[Independent-review history](REVIEW_en.md) covers only old r7-15 and R7-I1. Current [floor correction](FLOOR_CORRECTION_en.md) changes C's stage distribution, all PET lower edges and rocker-pin regions, updating mass, loads and all-body floor checks coherently. This is not new independent endorsement.

Current indicative design budget: **about JPY 24,000 in materials for 1 machine** (user approval 2026-09-28 JST). Shipping, unresolved taxes and unowned tools such as DN-03 at about JPY 396 are separate. Individual first purchases and shared lots are distinct; no purchases were made.

|Design|Diameter / reduction|Nominal g|Individual first purchase, JPY|Raw proxy / nominal demand, mN·m|Slip work, Nmm/cycle|30 cm time at assumed 120 RPM, min|
|---|---:|---:|---:|---:|---:|---:|
|[A](A/README_en.md)|220/144|1065.39|23,305|1.6166/1.4344|47.13|3.90|
|[B](B/README_en.md)|160/512|1101.37|23,735|1.1566/0.9422|50.05|13.83|
|[C](C/README_en.md)|200/156|1031.43|23,154|1.4629/1.3463|44.34|4.22|

## Same-definition comparison with old A

|Item|Stored old A|Final A|Change|
|---|---:|---:|---:|
|Nominal mass, g|977.709|1065.388|+8.97%|
|Input demand with final equations at 0.5° steps, mN·m|2.5798|1.4344|-44.40%|
|Nonnegative floor-slip work, Nmm/cycle|24.1646|47.1326|+95.05%|

Old 2.84621 mN·m is a historical result from the old model, distinct from the same-equation recalculated baseline. Equation corrections are not mechanical improvements. Old A lacked the full guards/initial accessories, so price and completeness are not equivalent.
Finite static checks, 216 poses and 162 support cases verify their specified subjects/assumptions. Input 120 RPM is not a predicted achieved speed.

## Actual changes in this revision
Uses smooth commercial 4 mm metal sleeves and M2 axial fastening, not threads as sliding surfaces.
PC pitch changes 25.545→26.5 mm, retaining circle-intersection closure margin with pitch error and both-end pin clearances. Coordinate-order branch switching was replaced by equations preserving the same assembly branch.
42-tooth synchronization gears and 84 mm shaft pitch provide actual clearance to downstream gears/guards, not wider feet or added ballast.
Includes real 16-sided prism sections, keyed split frames, rotor guard split into front basket/rear cap, and PET side guards whose clamp load bypasses the sheet through steel washers.
2 commercial collars are clocked without changing position to reduce nominal gravitational imbalance. Physical balance is unmeasured.

Floor correction redistributes C to 13×12; pair 1 uses m0.9, 20°, profile shifts +0.35/−0.35; final gear m1, 144 teeth. PET lower edges, stepped seats, small M4 washers and noncontact bosses are revised. Commercial M2×12, nylon locknuts and actual DN-03 avoid precision cutting/thin tools. Foot positions, contact area, spring rate and 6 mm stroke are retained.

## Responses to V2 issues

|Observed issue|Concrete r7 response|Not yet qualified|
|---|---|---|
|Rotor/gears slipped relative to shafts and failed to transmit torque|Commercial metal 6D input hub; downstream 5 mm-AF positive engagement and smooth metal journals|Actual tightening, fit and endurance torque. Bearing seizure is not asserted as V2's cause|
|Weak self-starting|144/512/156:1 using actual-CAD mass and slip work, 4 mm journals and collar orientation reducing nominal imbalance|Uncalibrated aerodynamics, unmeasured friction and loaded rpm|
|Axial gear escape|Distinct locating/floating caps, shoulders, collars, sleeves and keyed frames|Physical tolerances, joint flexure and overtightening preload|
|Contact handoff and manufacturing error|PC26.5 mm, continuous branch, 84 mm synchronization pitch, actual springs/guides/rockers and 162 tolerance cases|Impact, wear and physical 30 cm walking. Slip is not eliminated|
|Insufficient integrated design covering procurement and assembly|Domestic downstream parts, all fasteners/guards/stand/coupons, split frames and machine-readable stages|No V2 native CAD exists; drop-in replacement is not established|

## Separate calculation corrections from mechanical improvements
First combine work from coaxial opposing legs/rotating fasteners, then count each actual gear pair's losses once. The old implementation assigning fictitious gear losses to 4 balanced bolts is not used.
Horizontal airflow force and yaw couple enter Coulomb ground reactions; actual-CAD centers of mass and contact poses are iteratively reconciled over all phases.
Numerical changes from equation/implementation corrections are distinct from lighter parts or better performance. The stored old 977.709 g baseline is recalculated with the same equations.
Gear-pair reaction upper bounds derived from real pitch radii/transmitted work are stored and added to input-shaft bending. This is not a same-load comparison with old gravity/wind-only beams, nor calibration of real bearing resistance or dynamic tooth friction.
Slip work remains nonnegative. 8 mm foot lift and 3 mm slip are older designer targets, not relabeled user requirements or erased failures.

## Essential remaining conditions
1. Actual aerodynamics/resistance: input-bearing resistance limits, print eccentricity and loaded rpm. Raw stationary proxy, design derating 0.5 and UNKNOWN measured lower bound are separate.
2. Fabrication/joints: 5 representative parts were actually sliced, but bottom support-film removal, tooth-bottom finishing, coupon fit, thin tips/layer strength and frame joints/retention/tools are unverified. Whole-machine printing or local beam fixity does not prove global stiffness.
3. Ground operation: finite-tolerance support cases and a physical 30 cm walk including slip, collisions and starting. Unperformed, so not counted as 3 qualified machines.

[Common assembly](ASSEMBLY_en.md) / [initial coupons and stand](common/accessories.json) / [shared lots for 3 machines](purchase_lots.json) / [integration contract](integration_contract.json) / [5 representative slices and remaining work](SLICING_en.md) / [canonical contact-frame scope](CONTACT_FRAMES_en.md)

## Reproduction environment
CAD used existing FreeCAD1.1.3 independent Python, numpy/scipy/Shapely/trimesh/Pillow/PyMuPDF. After approval, official OrcaSlicer2.4.2 was added in a dedicated area for representative slicing.
Python dependencies: `scripts/ver3/requirements_integrated_r7.txt`; canonical inputs: `scripts/ver3/walker_r7.json`. FreeCAD executable/library locations are explicit CLI arguments.
Final source/file hashes are in `integration_contract.json` and `manifest.json`. Generation does not publish to the network. Track deployment through main and normal Pages Actions, explicitly separate from the old first cut.
