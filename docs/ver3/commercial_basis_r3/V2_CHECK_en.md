# Optional noninvasive V2 checks — No instrument purchase

[日本語 (original)](V2_CHECK_ja.md) | **English** | [Document languages](../../README_en.md)

> Presentation-only translation of the unchanged Japanese source. Source SHA256: `93ae46cdda304243b5b5683a59862208c1d47d6ddad47ac7a0156fedc5a294a1`. Numbers, part IDs, equations, code and qualification limits are retained; this is not a new engineering revision.

**Optional material for common design revision `v3-commercial-r3-01`, not a prerequisite to restart design.** The user confirmed possession of Ver.2 with a rotor installed, but current photos, joint strength and removability are unverified. Published V3 first-cut/R3 skeleton geometry is not treated as identical to the physical V2.

## Begin without applied loads

No new instruments, coins, string, bearings, drums, disassembly, drilling or rebonding are required. First observe only **how far motion propagates: rotor → shaft → gears → legs**.

1. **Up to 2 photographs with power OFF and all motion stopped.** Show the whole machine and rotor/shaft joint or gear-side shaft end. Put a ruler beside it only while stopped. Do not force disassembly or hand rotation.
2. **Only if safely reachable, identify corresponding positions across a joint.** Use small removable marks or existing features. Do not contaminate bearing surfaces or hang tape, paper or string from rotating parts. If marking is impractical, use existing photographed features.
3. **Optional short observation video: record unassisted starting and transmission.** Only under conditions consistent with the appliance manual and permitted uses: cold air, same setting/nozzle, recorded distance/direction and visible machine/joint. Do not push or hold rotating parts. Stop for pronounced wobble, detachment, unusual noise or looseness. Change orientation only after airflow is off and motion fully stopped; never force a resistant mechanism.

“Strong airflow” remains qualitative. Paper movement, unloaded RPM and catalog volume flow are not converted into m/s or torque.

| Observation | Record | Not yet established |
|---|---|---|
| Rotor moves but corresponding shaft mark does not follow | Relative joint displacement, orientation and video | Bearing seizure as the cause, or numerical mN·m supply |
| Shaft moves but gear does not follow | Relative shaft/gear displacement | A guarantee that stronger adhesive handles every load |
| Gears move but legs stop | Stopping location/angle, return and play | Numerical leg torque or ground friction |
| Nothing moves / intermittent movement | Starting orientation and repeatability under unchanged conditions | A definitive single cause: weak wind, static friction or dead point |
| Whole machine moves | Distance, contact, marks and lateral deviation | All-angle self-starting or identical performance with another R3 rotor |

Records: [CSV](v2_observations.template.csv) / [status JSON](optional_v2_check.json). Unobserved means blank/unknown; a stop is not relabeled as precise 0 rpm measurement or torque 0.

## Quantitative coin/string tests remain on hold until attachment is verified

Do not wrap string around known weak bonded joints or vanes. Load tests remain on hold until photos/dimensions establish **a mechanically secured drum/arm, retention, load path, anti-entanglement enclosure, stable support and allowable load**. Without a safe attachment, use qualitative observation only. Modifying the machine is not assumed.

Even if those conditions are later satisfied, coins have nominal masses. The Japan Mint's [1-yen specification](https://www.mint.go.jp/operations/production/operations_coin_presently-minted.html) states 1 g, 20 mm diameter and pure aluminum, not a guaranteed lower mass for each used coin. Bulk-inspection tolerances do not become a tolerance for 1 coin.

```text
名目負荷トルク [mN·m] = 0.00980665 × 名目質量 [g] × 有効半径 [mm]
```

For example, nominal 1 g for a 1-yen coin at 30 mm radius gives a **nominal conversion** of 0.294 mN·m. This is neither an allowable applied load nor a demonstrated lower bound. Separate container/fixture/hanging-string weight, effective string-center radius, changing radius, tool precision and mass errors. Unknown total mass/radius means lower bound `null`, retaining only nominal or qualitative results.

The previous measurement proposal's 22/50/102 g values are **unit-conversion examples for an unbuilt new module**, not loads to apply to physical V2. Allowable test mass for current V2 is unset.

### What “it lifted” establishes

If an acceptable fixture/load/short catch-tray gap is established, record initial angle, observed shaft end, clockwise/counterclockwise direction, winding direction, effective radius and lift height consistently. A 5 mm lift at 30 mm radius is only about 9.5°, not a full revolution. Do not infer RPM from phone slow motion without playback factors/frame timestamps.

Distinguish no-wind return, initial friction/play and any initial spin or falling-weight inertia. Lifting a real load from rest evidences **output at that shaft, starting angle, short interval and support condition**, not unmeasured angles or other rotors. Coasting while decelerating does not establish an instantaneous torque lower bound.

Do not subtract the same input-bearing loss again from output already downstream of those bearings. With legs connected, it is residual output including leg load, not rotor-alone output. Common-commercial-reference comparison can continue without a viable quantitative fixture.
