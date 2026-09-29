# Floor-corrected r7: continuous-walking display model v1

[日本語 (original)](MODEL_ja.md) | **English** | [Document languages](../../README_en.md)

> Presentation-only translation of the unchanged Japanese source. Source SHA256: `6bf9c2c8fdf7890d9792d0bbab41c10c56d88ecbcd2977cc02bb76d606f4a1a5`. Numbers, part IDs, equations, code and qualification limits are retained; this is not a new engineering revision.

**Calculated visualization, not a physical walking demonstration.** Retains `manufacturingRelease=false`, physically qualified count 0,
and UNKNOWN physical self-starting/30 cm walking. Not CFD or impact dynamics predicting rpm from wind speed.

[Continuous 3D and videos](https://ktanino10.github.io/TeoJansen_Rhinoceros/en/walking.html) /
[Comparison, canonical CAD and assembly](https://ktanino10.github.io/TeoJansen_Rhinoceros/en/r7.html)

## Separate canonical sources from added states

- Mechanical revision: `v3-integrated-walkers-r7-16-floor2`; artifact `09d49e396ec0a4b527ff6545c955df91995fd197`,
  input `369434e046acc5cb8f9da0f9f338308d29938d1e`. Verify `site/r7-source.json`'s contract, manifests and original hashes.
- Added display revision: `r7-floor2-walking-kinematic-v1`. `motion_A/B/C.json` retains units, coordinates, all instance IDs,
  actual reduction stages, analytical link lengths, body-pose samples, original integrated displacement and additional assumptions.
- Original 73 contact frames, null independent rocker angles, earlier 3-phase diagnostics/omissions, CAD, BOM and mechanical approval are unchanged.
  First-cut A300/B90/C180 videos are not reused. This model is A220/B160/C200 mm.
- Retains gears including C's upper m0.9/20°/shifts +0.35/−0.35 and lower m1/25°, guards and commercial foot fasteners.

## Added model

**Rigid links.** Analytically close any crank angle with the same oriented circle intersections/fixed assembly branch as `points_many`.
No vertex interpolation or nonorthogonal small-angle maps on legs, pins, gears or frame. Parts retain identical rigid meshes, placements and tracking IDs.
Browser and video-frame export use the same `site/r7-walk-math.js` and versioned JSON.

**Contact realignment.** Interpolate the original small-angle solution's vertical resultant and XY application point, fixing them as load targets for the new display model.
Resolve body height/two slopes using polar-decomposition-equivalent orthogonal rotation, actual guide axes and two cylindrical pads of radius 6 mm.
Compression uses unilateral contact with floor gap projected onto the guide axis. Normal force projects the nominal combined rate 1.764 N/mm of 2 springs onto that axis.
Not arbitrary body lifting to evade the floor. Nor a full reconvergence of mechanism masses, wind loads and friction in the new pose.
Save height/pose solutions every 0.125°. At arbitrary display angles, interpolate only pose parameters and recalculate contact compression/linkage.
Interpolated resultant and moment errors are checked too.

**Loaded rockers.** Use the actual rocker-axis angle equalizing pad-axis heights; reject generation outside ±5°.
Compute minimum height from cylinder radius, axial length and pad spacing. A center above ground does not permit ends below ground.

**Airborne rocker: `VISUAL_REST_V1`.** Once compression ends, over a ground gap up to 3 mm,
smoothstep returns the equal-height angle to relative neutral. This **display-return assumption** preserves angular continuity with contact.
Not claimed as passive motion predicting gravity equilibrium, damping/hysteresis or landing impact.

**Springs: `PROCEDURAL_COIL_V1`.** The same 12 `H_FOOT_SPRING` IDs retain real upper/lower seats, wire diameter 0.6 mm,
mean radius 3.2 mm and 6.8 turns; only helix pitch changes with compression.
Check free length 15 mm, operating limit 6 mm and geometric solid length 4.08 mm. End pitch is simplified.
Undeformed CAD wire is not globally scaled. No stress, fatigue or real-spring certification.

**Advance and time.** Within 1 cycle, interpolate stored integrated forward/lateral/yaw motion. Repeat cycles by SE(2) composition, carrying heading forward.
No arbitrary constant speed is added. Original floor slip remains unresolved. Input is assumed absolute 120 rpm,
with signed input/crank ratios A+144, B−512, C+156. Input angle derives from unwrapped time.
At equal time factors, B's crank actually turns more slowly. All videos use 16×; the browser offers 1/4/8/16×.

## Numerical scope

| Design | Advance, mm/cycle | Maximum compression, mm | Maximum rocker angle, degrees | Minimum noncontact floor clearance, mm | Minimum support margin, mm |
|---|---:|---:|---:|---:|---:|
| A | 92.382036 | 3.170179 | 0.790634 | 1.074156 | 6.342434 |
| B | 92.583845 | 3.127876 | 0.718049 | 1.068438 | 5.634264 |
| C | 92.388135 | 3.040939 | 0.746420 | 1.076509 | 6.630170 |

Maximum height changes from interpolated stored values are A0.04045/B0.03279/C0.04058 mm; slope changes as approximate angles are
A0.04676/B0.02569/C0.03331°, with maximum guide-compression change 0.10179 mm.

Check pad contact, compression, angles, support and interpolated loads at 5760 phases (0.0625°) per design.
Pad minima stay within rounding (about −1.3e−14 mm); at least 3 loaded feet. Support polygons use 6 foot centers, not widened footprints.
Vertical-resultant error <0.01 N; moments about both horizontal axes each <1 Nmm.
Maximum link-length and spring upper-seat error must be <1e−8 mm; rotation orthogonality error <1e−9.
Also check conservative source-CAD noncontact envelopes for all 2285 instances at 720 phases (0.5°) each.
Only the two cylindrical pads use separate contact checks. Rocker core, fasteners, springs and guards remain included.

Finite samples, not continuous collision detection of every moving pair or guarantees for fabrication tolerances, real floor, wind or friction.
Original maximum loaded-episode slip around 22 mm remains. Normal-force overlays show this display realignment, not tangential friction or FEM stress.
See `validation_A/B/C.json` and the per-build `site/tests/walking-math.test.mjs` checks for details.

## Video, native scenes and reproduction

Every design: 4 cycles, about 37 cm calculated advance. At 120 rpm input, prescribed times are A288/B1024/C312 s,
compressed at 16× to about 18/64/19.5 s. Every 24 fps frame uses the browser's analytical equations.
Fast axes use unwrapped Euler angles with exposure motion blur. Frame-rate apparent rotation is not a measurement of actual speed.
Blender includes all designs, 2285 IDs, 12 Geometry Nodes springs per design and editable rigid keyframes.
Between-keyframe native interpolation/blur interpolates displayed rigid poses, not newly solved contacts between frames.
Native float32 quantization versus browser float64 reference is separately recorded in validation JSON.
Original mesh vertices/triangles match. Representative native frames use separate display-precision limits: rotation orthogonality 2e−6,
whole-machine corner difference 0.15 mm and rocker-vertex below-floor tolerance 0.001 mm.
Do not confuse these with analytical link/contact tolerance 1e−8 mm or manufacturing tolerances.

```bash
# 通常公開ビルド。既存の固定された配布物から生成（Blender/SciPy不要）
python3 site/build.py
npm --prefix site run test:static
npm --prefix site test -- walking.spec.mjs

# 任意：新しい表示解の再計算。正規CAD・接地原本には書き込まない
python3 site/r7_walk_model.py --design C
python3 site/r7_walk_model.py --design A
python3 site/r7_walk_model.py --design B

# 保存JSONから映像を再現。既存Node/Blender/ffmpegを使用し、必ず直列
node site/r7-walk-export.mjs --design C
node site/r7-walk-export.mjs --design A
node site/r7-walk-export.mjs --design B
blender --background --factory-startup --python site/r7_walk_render.py -- --build-native
blender --background --factory-startup --python site/r7_walk_render.py -- --design C
blender --background --factory-startup --python site/r7_walk_render.py -- --design A
blender --background --factory-startup --python site/r7_walk_render.py -- --design B
blender --background --factory-startup --python site/r7_walk_verify_native.py
python3 site/r7_walk_finalize.py
```

No connection to a live Blender scene. Each frame PNG is passed to ffmpeg and immediately removed; large image sequences are not retained.
Original Japanese on-screen notes use outlined existing macOS fonts; font files are not distributed.
The normal site loads only the chosen GLB/motion JSON and videos on request. This original walking package has a separate 16 MB budget;
previous static 12 MB / historical 3D 18 MB / r7 comparison/assembly 30 MB limits remain. Large Blender originals are not copied to Pages.
Interactive 3D retains every mesh under diffuse lighting; videos use EEVEE. Input processing receives time between redraws;
Even on a slow GPU, angles use actual elapsed time rather than treating frame count as prescribed time.
