# Display frames from the existing contact model

[日本語 (original)](CONTACT_FRAMES_ja.md) | **English** | [Document languages](../../README_en.md)

> Presentation-only translation of the unchanged Japanese source. Source SHA256: `bf472a485ea9bd2cb79a1290cfb8640df271071156c820c5a10b40e69df0c8f1`. Numbers, part IDs, equations, code and qualification limits are retained; this is not a new engineering revision.

**Stored existing converged quasi-static contact results**, not a new walking model or experimental video. [Floor-corrected](FLOOR_CORRECTION_en.md) CAD, mass, placement and stage speeds feed the same solver, recomputing corresponding loads/contact. Wind, friction, springs and convergence criteria were not changed to pass. A compact export of `ContactGait.evaluate()`.

[A](A/contact_frames.json) / [B](B/contact_frames.json) / [C](C/contact_frames.json) share a schema. From canonical 720 points at 0.5°, select 72 points at 5° and add an explicit endpoint: 73 frames. Contact at endpoint 360° uses the converged periodic 0° solution; accumulated advance/lateral/yaw use the original 720-point integral. No unconverged state is filled by zero or a previous value.

## Included

- Revision, source commit/hash, input/assembly hashes, coordinates, units and leg order.
- Crank phase, signed input angle, body height/2 slopes, advance/lateral/yaw integrated from the dense original velocities.
- Per-foot compression, guide direction, modeled contact point, normal force, loaded-state classification and slip velocity.
- Convergence residuals, original all-phase aggregates and display timestamps for **assumed 120 RPM input**.

Advance integrates existing solver velocities with the same rectangular rule; no arbitrary straight-line speed is added. Signed advance differs from the absolute travel distance used by old summaries. 120 RPM is not achieved/predicted speed.

The input shaft turns multiple times per 1 display interval. Wrapping `inputDegUnwrapped` at 360° before interpolation can alias into apparent stillness. Preserve signed unwrapped angles and timestamps.

Body pose is the original `body_z_slopex_slopey`. Its small-angle coordinate map is stored, not replaced with an exact rigid-world matrix or new SE(2) integration. `cadReferenceBodyOriginZMm` and the map distinguish native CAD Z from body-relative Z.

## Excluded

**Independent per-foot rocker angles are null.** Canonical analysis uses representative contact points/passive-rocker approximations, not independently solved rocker angles. Maximum required-angle sensitivities/envelopes differ from resolved time-series angles. Do not replace null with zero, a previous value or arbitrary pose for rendering.

No actual input speed, impact/dynamics, evolving spring-wire geometry or measured friction/floor/wind. A complete walking render needing missing states cannot be determined from this export alone. Separate it from comparison renderings/schema 2 assembly; displays must disclose missing states and small-angle/quasi-static approximations.

## Checks and reproduction

See [export consistency](contact_frames_validation.json) for aggregate comparisons. Reproducing only frames must not overwrite same-revision `work_budget.json`/`work_profile.csv`; use `--output-dir` with another analysis output and save frames through `--motion-output`/`--source-commit`. Floor correction changes actual geometry and updates aggregates with new inputs; Git preserves earlier revisions.

Initial slice1 differed from old aggregates/CSV by 0, apart from analysis-source hashes. Later floor geometry changes require consistency with the same new-input aggregates, normals, floor positions, compression and endpoint—not matching obsolete numbers. Not new independent physics review or physical walking verification.

Between-frame interpolation is a display operation, not additional contact-handoff validation. Retain `manufacturingRelease=false` and UNKNOWN physical starting/30 cm walking.
