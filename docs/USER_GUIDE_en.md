# Using the website and documents

[日本語](USER_GUIDE_ja.md) | [English](USER_GUIDE_en.md) | [Document language pairs](README_en.md)

## Choose the right page

The [Japanese site](https://ktanino10.github.io/TeoJansen_Rhinoceros/) retains the existing URLs. [English](https://ktanino10.github.io/TeoJansen_Rhinoceros/en/) provides equivalent content. Each page's language switch preserves the page, design query and heading anchor. Language selection uses no account, remote preference storage or analytics.

| Page | Content and revision |
|---|---|
| [Overview](https://ktanino10.github.io/TeoJansen_Rhinoceros/en/index.html) | Physical Ver.1/2 records and entry points to first-cut Ver.3 and current r7 |
| [Build records](https://ktanino10.github.io/TeoJansen_Rhinoceros/en/production.html) | Ver.1 fabrication and the recorded Ver.2 improvements, completed photographs and historical tests |
| [First-cut comparison](https://ktanino10.github.io/TeoJansen_Rhinoceros/en/comparison.html) | Changes and limitations of historical A300/B90/C180 mm |
| [First-cut 360° and assembly](https://ktanino10.github.io/TeoJansen_Rhinoceros/en/viewer.html) | Exact meshes, part IDs and source-bound stages from that same historical revision |
| [Calculations](https://ktanino10.github.io/TeoJansen_Rhinoceros/en/calculations.html) | Separate r3 materials/structures/fluid models and r4 input cartridge |
| [r7 comparison, 360° and 12 stages](https://ktanino10.github.io/TeoJansen_Rhinoceros/en/r7.html) | Floor-corrected A750/B785/C750 = 2,285 parts; separate from the first cut |
| [Continuous walking](https://ktanino10.github.io/TeoJansen_Rhinoceros/en/walking.html) | Separately versioned kinematic/quasi-static display model and videos using r7 geometry |

## Operate 3D and videos

The 3D engine, GLB and motion data load only after choosing a design and pressing Load. Walking starts paused. Drag/one finger rotates; wheel/two fingers zoom and pan. Focus the 3D area: arrows rotate, +/− zoom and Home fits all. Assembly also supports Shift+arrows to pan; walking supports Space to play/pause. Instructions appear beside each viewer.

“Complete” assembly is an on-screen reference, not completed physical work. In r7, “Operation boundary / path sample” traces inventories, temporary removal and same-ID reinsertion. Separate-workbench preparation does not add to installed machine quantities. Static instructions, parts tables, images and documents remain available without JavaScript or WebGL.

Videos do not autoplay. Japanese walking pages use Japanese on-screen notes; English pages use English notes. Walking CC is optional rather than duplicated by default. A user's enabled CC is not repeatedly forced off. On small screens, use fullscreen, optional captions and the normal-sized explanatory text beside the video. No blanket shrinking CSS reduces caption readability.

All walking videos use **prescribed 120 rpm input, 16× time compression and 4 cycles**. A about 18 s/B about 64 s/C about 20 s and about 37 cm advance are calculated displays, not measured distance or actual walking performance. Airborne-rocker neutral return and procedural springs are declared display assumptions; canonical independent rocker angles remain null.

[Bilingual media provenance](ver3/r7_walking_locales_v1/manifest.json) records language-specific notes, posters and captions from the same motion and timing. The original model document and its first-release media/delivery-budget statements remain frozen historical records, separate from the current bilingual presentation.

## Document and fabrication-file legend

The 18 major English documents translate unchanged Japanese originals. Each English header links to the original and records its SHA256. The [coverage manifest](translation-manifest.json) records scope and hashes. The existing bilingual repository READMEs preserve Ver.1/2 build records.

- **CAD, STEP, STL and GLB:** shared across languages. No language-driven redesign, remodeling or omitted parts.
- **Seven BOMs and numerical JSON/CSV:** BOM fields are already English/neutral, so original bytes are shared. Quantities, part IDs, SKUs, prices and URLs are unchanged. JSON source annotations may be Japanese; paired major documents provide English explanations.
- **Ver.1 PDF drawings:** [assembly reference](テオヤンセン2Dv1.pdf) / [detail reference](テオヤンセン2D図面最新.pdf) remain **Original drawing (Japanese)**. They are neither translated English drawings nor Ver.2-specific drawings. Missing dimensions, tolerances and operations are not reconstructed from photos.
- **r7 PET templates and sections:** original part IDs and dimensions are shared. Match design, revision and part ID; use the stated mm dimensions. Translation does not change outlines, holes or dimensions. Design-specific and common assembly documents explain cutting and tool conditions.
- **Photos and historical videos:** physical photographs remain distinct from renderings. External YouTube videos retain their original language and are not reuploaded. Existing r7 assembly movies have English burned-in labels, with corresponding Japanese or English stage captions on each page.

Do not apply historical Ver.1/2 scaling of 150% / legs 160% to Ver.3, which uses mm at 100%. Representative slicing is limited software inspection, not qualification of whole-machine printing, support removal or fit. No printer transmission or print start is performed.

## Distinguish status and cost

Current r7 materials guideline: **about JPY 24,000 per machine**. Individual initial estimates A JPY 23,305.13/B JPY 23,735.37/C JPY 23,154.43 exclude unowned tools such as DN-03 at about JPY 396, shipping and unresolved taxes. Shared-purchase averages do not replace individual costs. Old JPY 20,000/23,000 conditions remain historical to their respective revisions.

`manufacturingRelease=false`, physically qualified count 0, and real wind, physical self-starting and physical 30 cm walking remain UNKNOWN. Finite digital PASS does not qualify every continuous path, tolerance, CFD/FEM, endurance or physical operation. Follow actual product/material, bonding/curing and tool instructions; historical records alone do not guarantee safety.
