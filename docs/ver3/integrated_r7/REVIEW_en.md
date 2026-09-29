# r7-15 independent integration review and bounded correction

[日本語 (original)](REVIEW_ja.md) | **English** | [Document languages](../../README_en.md)

> Presentation-only translation of the unchanged Japanese source. Source SHA256: `8093daac68b4b20cfb9f8e5a11bfb4daa3ec0aedcfa1a446aef32058a8ffe108`. Numbers, part IDs, equations, code and qualification limits are retained; this is not a new engineering revision.

**This independent review covers only old r7-15 and R7-I1.** Later [floor-interference/r7-16 correction](FLOOR_CORRECTION_en.md) is the author's geometry/calculation/finite-check update; CONFIRMED below is not extended to that new geometry.

**Initial verdict: REQUEST CHANGES (1 Critical/High finding, R7-I1). Bounded follow-up in the same independent-review context: CONFIRMED, no remaining R7-I1 finding. Not manufacturing or physical 30 cm walking qualification.**

## Frozen scope and ownership

Initial subject: `922a47c5ab815fc186dd1486726123ab08552ede`; source: `2bec2d1784c0850946cc6a426aab7fd206bcf02c`,
SourceHash: `f537ee3120f5ea8dbbe8fbe501142375e65d67a3b53ffb2f540b7cb5df3a9574`.
The snapshot is preserved; correspondence between stages and checks was corrected without changing CAD, STEP, STL, numbers or BOM.

Independent reviewer: `8e708228-0ade-45b3-bc89-9c88abb9c78a`, a new 1 context with no model override.
The R6 reviewer had a synchronous-continuation limitation, and no continuation was found for R6-1; the coordinator therefore directed this 1 review.
This is not endorsement by the old R6/R6-1 reviewers. No new review swarm or redesign search occurred.

[Initial independent review (only working paths redacted)](review/INITIAL_REVIEW_ja.md) (Japanese archival original) / [original hashes, findings and execution results](review/initial_review_record.json) / [same-reviewer bounded follow-up](review/FOLLOWUP_R7-I1_ja.md) (Japanese archival original) / [follow-up hashes/results](review/followup_review_record.json)

## R7-I1

|Contents|Independent check|
|---|---|
|Issue|B stage 04 installed upper PET/retention bolts, but the old stage 07 path check restricted fixed parts to `frames+drive`|
|Existing +10 mm lowering point|`H_INPUT_HUB_001` × `S_GUARD_UPPER_RIGHT_2_001`: **9.6624645869 mm³** overlap; `P_ROTOR_CAGE_FRONT_001` × `H_BOLT_M3_20_011`: **2.5404894418 mm³**|
|Tolerance|Overlap volume `<=0.00001mm³`; threshold unchanged|
|Final position|At 0 mm, overlap 0; a valid final static position does not validate intermediate paths|
|Impact|Old PASS checked a different configuration with fewer parts than the real sequence, so did not support the public candidate's stage consistency|

Known limits—unmeasured wind, uncalibrated aerodynamics, negative adverse margins and slicing not yet performed—were not counted as new defects.
The independent reviewer used 6 bounded probes covering contact, continuous branches, work/air, native sections, contract inventories and individual purchase lots.
It was not merely a rerun of the author's 65 tests, 216 poses and 162 support cases.

## Author's bounded correction

- Replay stages from a single `orderedOperations`; include **every installed nonmoving part** at the chosen boundary as fixed. No handwritten exclusions.
- Explicitly add stage 03 joint bolts, stage 07 collars/spacers and stage 09 joint bolts only after corresponding insertion/seating.
- Stage 07: **lower at X=+4 mm, then seat at the same height from X=+4 to 0 mm**, in 2 continuous segments. PET/retention bolts are neither removed nor hidden from checks.
- Workbench preparation uses an independent scene containing only declared uninstalled parts. Temporarily floating display parts are not self-support or operating validation.
- Stage/path contracts use schema 2, checking hashes of operation boundary, fixed inventory, temporary poses and path definition. Regression tests reject a dropped-part PASS and discontinuous 2-segment paths.

## Author's reproduced results

After reproducing the old path's 2 overlaps at +10 mm, the 2 segments using frozen B native and 276 fixed parts after stage 06 had overlap 0.
All 10 paths reconstructed from actual inventories passed with A 608, B 642, C 607 B-rep part-pair checks.
Stage 07 fixed inventories contain 241 parts each for A/C, 276 for B, including the reported PET and 2 retention bolts.

These are **author correction results**. The independent reviewer separately reproduced the scope below and confirmed bounded R7-I1 correction.

## Same independent reviewer's confirmation

Follow-up subject: `a756a229ed133d15b70149ea949a5347ad24d684`; corrected source: `124cf4a4555c7b68dd6a01deb41146ca39ed29e6`,
SourceHash: `197e5533bd60783c3ba5ff7222798223ffaa2712d92eb38e3d3c0b7a8aec5ee1`.
The initial reviewer followed only R7-I1; no new reviewer or whole-machine rereview.

- Independently rebuilt inventory from each instance's history; both B segments retained the same 276 fixed parts, including PET and 2 retention bolts.
- Reproduced old 9.6624645869/2.5404894418 mm³ overlaps from the same native. New path, including extra intermediate points: 10 samples, 124 B-rep pair checks, maximum overlap 0.
- Both connecting endpoints of 2 segments are `[4,0,0]mm`; after seating, `[0,0,0]mm`. Final geometry was not left displaced.
- Main shaft remains in fixed inventory with its specified −53 mm pose. Control overlap 1.3021210204 mm³ becomes 0.
- Rejected 11 negative controls including dropped installed parts with recomputed hashes, altered operation boundaries/fixed poses and discontinuous paths.

Also verified unchanged candidate 284 files, 263 original files outside correction scope and initial/author evidence.
CONFIRMED concerns this bounded diff and finite samples. It does not mean all A/C native paths were independently recomputed or continuous paths, all tolerances, hand support, real tools or operation are guaranteed.
The initial finding remains a valid historical record against its original snapshot.

## Unchanged boundaries

Original snapshot geometry, mass, center of mass, airflow, friction assumptions, supply/demand, purchase lots and JPY 23,000 baseline are unchanged.
At independent follow-up, physical slicing/publication had not occurred. Later approved [5 representative layer checks](SLICING_en.md) and [stage 04 Y-direction wording correction](review/stage04_documentation_correction.json) are finishing-author records, not independently rereviewed wording/slices. Publication to the existing repository/Pages is authorized; this does not authorize/qualify physical printing or equipment operation.
`manufacturingRelease=false`, `qualifiedWalkingPrototypeCount=0` and UNKNOWN physical starting/30 cm walking are retained.
