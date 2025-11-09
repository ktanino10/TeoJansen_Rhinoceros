# Theo Jansen “Rhinoceros” – Prototype Ver.2  

[English](#english) | [日本語](README_ja.md)

---
## Repository Contents

```text
TeoJansen_Rhinoceros/
├── Fusion360/          # Fusion 360 design files (.f3d)
├── STL/                # 3D printable parts (STL files)
├── docs/               # Additional documentation and images
│   └── images/         # Photos and diagrams
├── README.md           # This file (English)
└── README_JP.md        # Japanese documentation
```
![License](https://img.shields.io/badge/license-CC0%201.0-blue.svg)
![Educational](https://img.shields.io/badge/purpose-educational-green.svg)

---

## Background

I first discovered Theo Jansen’s *Strandbeest* on YouTube and was captivated by the beauty of its wind-powered, organic motion.  
At the same time, I became fascinated by its internal mechanisms and thought: *“I want to try recreating this with my own hands.”*

Rather than making a perfect replica, I wanted to incorporate **more mechanical aesthetics and my own design preferences**.  
In particular, I love the design of the **ν (Nu) Gundam**, so I drew inspiration from its **color scheme** and **structural nuances** for this project.

For those unfamiliar with the Nu Gundam, here’s the official promotional video used as a design reference for part of this build:

<a href="https://youtu.be/TQ98cSiHVVs?si=otUml2E1TVQzA8v8" target="_blank">
  <img src="https://img.youtube.com/vi/TQ98cSiHVVs/0.jpg" width="480" alt="Nu Gundam official promo video thumbnail">
</a>

---

## How to Use This Repository (Overview)

This “Rhinoceros” has evolved through multiple iterations from **Ver.1 to Ver.2**.  
While there is no fully detailed step-by-step manual, I believe you can build it by referencing the PDFs and animations below.

Each version includes the corresponding **STL files**.  
If you’re attempting this for the first time, I recommend starting by understanding the structure and motion of **Ver.1**.

I’ve also summarized my personal build log (as far as I can recall) in the following sections.

| Version | Summary | Drawings | Videos |
|--------|---------|---------|--------|
| Ver.1 | Initial design modeled in Fusion 360 | 1. [TeoJansen_2D_v1.pdf](./docs/テオヤンセン2Dv1.pdf)<br>2. [TeoJansen_2D_latest.pdf](./docs/テオヤンセン2D図面最新.pdf) | 1. [Assembly Video](https://youtu.be/Q7d0sq1SNJ0?si=nhAsBmjNhFsv74Ju)<br>2. [Motion Simulation](https://www.youtube.com/watch?v=RxUTcOTfPt0) |
| Ver.2 | Improved: 150% scale with more stable operation |  | 1. [First Motion Test](https://youtu.be/T3U7c1Mr3Y8?si=hUQZJXoczCW0qAUG)<br>2. [Overview / Re-verification](https://youtu.be/JzXOxTJvHzw?si=1MGZkGYogJQsFP-6) |

- **FYI**: This model is also published on Bambu Lab’s community platform [**MakerWorld**](https://makerworld.com/ja/models/1971139-n-gundam-style-strandbeest-ver-2).

---

# Ver.1 Build Process

## 1. Research
I observed YouTube videos and various images to infer and understand the structure and operating principles.  
Since many makers have shared their works worldwide, **web research and video viewing** are extremely helpful.

<a href="https://youtu.be/MYGJ9jrbpvg?si=qMYy9t26JGlFZo1x" target="_blank">
  <img src="https://img.youtube.com/vi/MYGJ9jrbpvg/0.jpg" width="480" alt="Theo Jansen Strandbeest YouTube thumbnail">
</a>

---

## 2. Design
All parts were 3D-modeled in Autodesk **Fusion 360**.  
In the early phase, I mainly traced shapes while closely observing real works;  
I performed little to no detailed mechanics calculations at that stage.

Because of that choice, I ended up iterating many rounds of prototyping and fine-tuning later—  
this became one of the most time-consuming and labor-intensive stages.  
Please treat the following drawing as **one reference among many**, not a strict blueprint.

### 📄 **Ver.1 2D Drawing**  
[TeoJansen_2D_latest.pdf](./docs/テオヤンセン2D図面最新.pdf)

> *Note:* GitHub may not preview PDFs inline. If so, please open them via the link above.

### 🎨 Ver.1 Concept Rendering (Fusion 360)

These are rendered images of Ver.1 in Fusion 360,  
created to verify geometry, structure, colors, and shading *before* actual printing—  
and to visualize the “moving art” concept during the design phase.

---

<div align="center">

| Oblique View | Front View | Side View |
|---|---|---|
| <img src="./docs/images/テオヤンセン1.png" width="280" alt="Oblique view"> | <img src="./docs/images/テオヤンセン2.png" width="280" alt="Front view"> | <img src="./docs/images/テオヤンセン3.png" width="280" alt="Side view"> |

| Rear View | Opposite Side | Reverse Oblique |
|---|---|---|
| <img src="./docs/images/テオヤンセン4.png" width="280" alt="Rear view"> | <img src="./docs/images/テオヤンセン5.png" width="280" alt="Opposite side"> | <img src="./docs/images/テオヤンセン6.png" width="280" alt="Reverse oblique"> |

</div>

### 🧩 Ver.1 Assembly Images  
[TeoJansen_2D_v1.pdf](./docs/テオヤンセン2Dv1.pdf)

> *Note:* If PDF preview doesn’t work on GitHub, please open via the link.

**Assembly Video**  
<a href="https://youtu.be/Q7d0sq1SNJ0?si=nhAsBmjNhFsv74Ju" target="_blank">
  <img src="https://img.youtube.com/vi/Q7d0sq1SNJ0/0.jpg" width="480" alt="Ver.1 Assembly video thumbnail">
</a>

### 🦿 Ver.1 Motion Image  
**Simulation Video**  
<a href="https://youtu.be/RxUTcOTfPt0?si=KSsferuiFyFRqOAX" target="_blank">
  <img src="https://img.youtube.com/vi/RxUTcOTfPt0/0.jpg" width="480" alt="Ver.1 Motion Simulation thumbnail">
</a>

---

## 3. 3D Printing
I optimized print directions and part splits to balance dimensional accuracy and strength.

<img src="./docs/images/88187.jpg" width="300" alt="3D printer in progress">

## Recommended Print Settings

- **Scale**: 150% (legs recommended at 160%)  
- **Material**: ABS (also common for Gunpla; heat resistance ~80 °C)  
- **Printer**: Bambu Lab FDM printer  
- **Note 1**: This model is also listed on [**MakerWorld**](https://makerworld.com/ja/models/1971139-n-gundam-style-strandbeest-ver-2).  
- **Note 2**: Depending on geometry, consider **splitting parts and bonding afterward**.  
  Although support is an option, considering **cost and time**, I mainly chose splitting (support kept minimal) except for the crankshaft.

---

🎥 **Test Print Video**  
[![Watch on YouTube](https://img.youtube.com/vi/IP1fvOTGgno/0.jpg)](https://www.youtube.com/shorts/IP1fvOTGgno)

---

## 4. Sanding
Surfaces that contact supports tend to be rough, so I sanded the crankshaft with a power sander.  
By stepping through **#400 → #600 → #800**, I smoothed layer lines for a clean finish.

<img src="./docs/images/88075_0.jpg" width="300" alt="Crankshaft after sanding">

🎥 **Sanding Process**  
[![Watch on YouTube](https://img.youtube.com/vi/w-jB8-OUFfA/0.jpg)](https://www.youtube.com/watch?v=w-jB8-OUFfA)

---

## 5. Ultrasonic Cleaning
After sanding, I cleaned parts with an **ultrasonic cleaner**.  
Adding a **small amount of detergent** reduces surface tension so bubbles penetrate details and remove fine dust and swarf.

<img src="./docs/images/88073_0.jpg" width="300" alt="Ultrasonic cleaning">

🎥 **Ultrasonic Cleaning Video**  
[![Watch on YouTube](https://img.youtube.com/vi/2DyWBz1phlA/0.jpg)](https://www.youtube.com/watch?v=2DyWBz1phlA)

### 🧴 Bonding After Cleaning
Some parts require **temporary sub-assembly by bonding** after cleaning.  
I used the following adhesive, which bonds ABS strongly and maintains strength after curing:

- **Adhesive**: [Tamiya ABS Cement](https://www.tamiya.com/japan/products/87137/index.html)  
  (Part no. 87137 / 40 ml)

> *Tip:* Waiting about 30 minutes for full cure improves joint stability.

---

## 6. Painting
I airbrushed the parts in a paint booth. Equipment used:

- Airbrush  
  <img src="./docs/images/2339528.jpg" width="300" alt="Airbrush used">

- Spray booth  
  <img src="./docs/images/88072.jpg" width="300" alt="Spray booth used">

- For safety, I wore a respirator.  
<img src="./docs/images/339.png" width="300" alt="Respirator mask">

- Prep image before painting  
  <img src="./docs/images/88208_0.jpg" width="300" alt="Painted parts">

### 🎨 Painted Parts
Below are comparisons of pre-/post- sanding, ultrasonic cleaning, and painting.

- Drying painted parts  
  <img src="./docs/images/88089_0.jpg" width="300" alt="Painted parts drying">

- Crankshaft finish comparison  
  Left = before processing; Right = after sanding/cleaning/paint.

| View | Left (before: no sanding/cleaning/paint) • Right (after: sanding/cleaning/paint) |
|---|---|
| **Oblique** | <img src="./docs/images/88209_0.jpg" width="400" alt="Crankshaft comparison oblique - before"> | <img src="./docs/images/88209_0.jpg" width="300" alt="Crankshaft comparison oblique - after"> |
| **Side** | <img src="./docs/images/88210_0.jpg" width="400" alt="Crankshaft comparison side - before"> | <img src="./docs/images/88210_0.jpg" width="300" alt="Crankshaft comparison side - after"> |
| **Gradient finish** | <img src="./docs/images/87814.jpg" width="400" alt="Crankshaft comparison gradient - before"> | <img src="./docs/images/87814.jpg" width="300" alt="Crankshaft comparison gradient - after"> |

---

## 7. Decals
I applied decals with a setting solution, adjusted positions with cotton swabs,  
and finished with a matte topcoat to enhance depth and definition in the details.

### 📸 Decal Application
Below are images taken during and immediately after application:

<img src="./docs/images/88060_0.jpg" width="300" alt="Decal work 1">  
<img src="./docs/images/88061_0.jpg" width="300" alt="Decal work 2">  
<img src="./docs/images/88062_0.jpg" width="300" alt="Decal work 3">  
<img src="./docs/images/88059_0.jpg" width="300" alt="Decal work 4">

---

## 8. Ver.1 Final Assembly & Functional Check

I verified gear transmission, crankshaft rotation, and wind-driven motion.  
While aiming for smooth operation overall, several issues were discovered.

For the wind turbine and gear shafts, I used **stainless steel round rods**  
and cut them to length with **metal shears**:

- [Stainless steel rods (Amazon)](https://www.amazon.co.jp/dp/B0FCYMZJF7?ref=ppx_yo2ov_dt_b_fed_asin_title&th=1)  
- [Metal shears (Amazon)](https://www.amazon.co.jp/dp/B0BQB8PLWK?ref=ppx_yo2ov_dt_b_fed_asin_title)


### Ver.1 Exterior (at completion)

<div align="center">

| Oblique | Front | Side |
|---|---|---|
| <img src="./docs/images/テオヤンセンver1完成1.jpg" width="280" alt="Ver1 oblique"> | <img src="./docs/images/テオヤンセンver1完成2.jpg" width="280" alt="Ver1 front"> | <img src="./docs/images/テオヤンセンver1完成3.jpg" width="280" alt="Ver1 side"> |

| Rear | Opposite Side | Reverse Oblique |
|---|---|---|
| <img src="./docs/images/テオヤンセンver1完成4.jpg" width="280" alt="Ver1 rear"> | <img src="./docs/images/テオヤンセンver1完成5.jpg" width="280" alt="Ver1 opposite"> | <img src="./docs/images/テオヤンセンver1完成6.jpg" width="280" alt="Ver1 reverse oblique"> |

</div>

### ⚙️ Observed Issues

- The wind turbine did not rotate well under wind power.  
- Some parts popped off during manual rotation.  
- The turbine was unstable and the shaft exhibited wobble.

These findings became key drivers for improvements in Ver.2.

🎥 **Initial Motion Test Video**  
[![Watch on YouTube](https://img.youtube.com/vi/Ic3GasmMlio/0.jpg)](https://youtu.be/Ic3GasmMlio?si=MSvn6-1x6faBUwIh)

---

## 9. Ver.1 Redesign & Structural Improvements

### ⚙️ Main Causes of Ver.1 Failures and Directions for Improvement

Several issues surfaced during Ver.1 prototyping.  
Below are the causes and how I addressed them toward Ver.2.

1) **Gear Ratio Insufficiency**  
The **gear ratio was too small** relative to the crankshaft, yielding insufficient torque from wind power and unstable rotation.

Taking a cue from bicycle gearing (trade-off between force and speed),  
I redesigned the gear train with large–small gear pairs that transmit torque more effectively,  
so the system can move even with low wind input.

<img src="./docs/images/88476.jpg" width="300" alt="Gear test 1">

> The photo above is an example of ratio tests toward Ver.2.  
Even a simple combination matters when you’re figuring out how to transmit and amplify small forces.

Because gears are **highly modular and combinable**, I explored many patterns for Ver.2:

<img src="./docs/images/87813.jpg" width="300" alt="Series of gear prototypes">

> Through repeated prototyping, I gradually appreciated how deep gear design can be—  
and my room ended up filled with gears.

2) **Inefficient Turbine Geometry**  
The initial **six-blade turbine** did not capture enough wind; torque was lacking.  
A chance observation of a very efficient garden turbine led me to realize it’s not only about *catching* wind but also **how to let it pass and harmonize** with the flow.  
I thus adopted the **Savonius** type, which stabilizes rotation using differential drag.

[![Watch on YouTube](https://img.youtube.com/vi/n7MyLVN-XGA/0.jpg)](https://youtube.com/shorts/n7MyLVN-XGA)

3) **Shaft Deflection (Stainless Rod)**  
The thin stainless rod **deflected**, causing unwanted friction and rotational wobble.  
I extended/reinforced supports so the rod stays **level**, reducing wobble and friction losses.

4) **Hook Disconnecting from Crankshaft**  
The hook that drives the legs often popped out because there was **no structure to resist the force vector** in the direction of disengagement.  
I added a supporting surface aligned with the force direction, significantly improving connection stability.

---

## 10. Ver.2 Completion & Review

### Ver.1 vs Ver.2 — Key Improvements

After revisiting each issue, structural rigidity and operational stability improved significantly.  
Below are the main differences:

| Item | Ver.1 (Initial) | Ver.2 (Improved) |
|---|---|---|
| **Front View** | <img src="./docs/images/テオヤンセンv2joint v32.png" width="400" alt="Ver1 front"> | <img src="./docs/images/テオヤンセンv4joint v15.1.png" width="400" alt="Ver2 front"> |
| **Side View** | <img src="./docs/images/テオヤンセンv2joint v322.png" width="400" alt="Ver1 side"> | <img src="./docs/images/テオヤンセンv4joint v15.png" width="400" alt="Ver2 side"> |
| **Gear Ratio** | Too small; insufficient torque under wind. | Redesigned ratios; runs stably with lighter wind. |
| **Gear Accuracy** | Thickness/pitch uneven; meshing losses. | Refined tooth profile; smoother rotation, lower friction. |
| **Structural Stability** | Weak shaft support; stainless rod deflected. | Extended/reinforced supports; **deflection issue mitigated**. |
| **Crank Layout** | Inefficient force paths; uneven leg motion. | Repositioned with force vectors in mind; smoother drive. |
| **Design** | Rough experimental look. | Balanced **mechanical aesthetics** and function. |

---

### Six-Blade vs. Savonius—Geometry Comparison

Below compares Ver.1 (six-blade) and Ver.2 (Savonius).  
In Ver.2, wind capture and torque transmission were reworked for stable rotation.

| View | Left (Ver.1) • Right (Ver.2) |
|---|---|
| **Front** | <img src="./docs/images/Wheel1.jpg" width="300" alt="Six-blade front"> | <img src="./docs/images/88209_0.jpg" width="300" alt="Savonius front"> |
| **Oblique** | <img src="./docs/images/Wheel2.jpg" width="300" alt="Six-blade oblique"> | <img src="./docs/images/88210_0.jpg" width="300" alt="Savonius oblique"> |
| **Top-down** | <img src="./docs/images/Wheel3.jpg" width="300" alt="Six-blade top"> | <img src="./docs/images/87814.jpg" width="300" alt="Finish gradient"> |

**Real prototypes (Left: six-blade / Right: Savonius)**  
<img src="./docs/images/87816.jpg" width="300" alt="Real turbine comparison">

Why Savonius performed better:

| Aspect | Six-Blade (Ver.1) | Savonius (Ver.2) |
|---|---|---|
| **Wind Interaction** | Strong head-on capture but large counter-drag on the rear. | Cup geometry channels flow while concentrating drag in the rotation direction. |
| **Torque** | Poor starting torque in low wind. | Differential drag enables easy start in weak wind. |
| **Stability** | Sensitive to wind direction; balance easily disturbed. | One cup receives wind while the other sheds it; stable rotation. |
| **Tuning** | Blade angle/shape optimization is tricky. | Simpler, more repeatable structure. |
| **Overall** | Visually light but low wind-use efficiency. | Balanced torque and stability; adopted as final form. |

---

### Hook–Crank Connection (Improvement)

In Ver.1, the **leg-drive hook** often popped out because the **force vector** aligned with the disengagement direction and nothing resisted it.  
In Ver.2, I added a **supporting surface** to accept that force direction and redesigned the hook geometry, greatly improving reliability.

| View | Left (Ver.1) • Right (Ver.2) |
|---|---|
| **Hook (1)** | <img src="./docs/images/hook.jpg" width="200" alt="Hook comparison 1"> |
| **Hook (2)** | <img src="./docs/images/hook2.jpg" width="200" alt="Hook comparison 2"> |

---

### Ver.2 Exterior

<div align="center">

| Oblique | Front | Side |
|---|---|---|
| <img src="./docs/images/テオヤンセンver2完成1.jpg" width="280" alt="Ver2 oblique"> | <img src="./docs/images/テオヤンセンver2完成2.jpg" width="280" alt="Ver2 front"> | <img src="./docs/images/テオヤンセンver2完成3.jpg" width="280" alt="Ver2 side"> |

| Rear | Opposite Side | Reverse Oblique |
|---|---|---|
| <img src="./docs/images/テオヤンセンver2完成4.jpg" width="280" alt="Ver2 rear"> | <img src="./docs/images/テオヤンセンver2完成5.jpg" width="280" alt="Ver2 opposite"> | <img src="./docs/images/テオヤンセンver2完成6.jpg" width="280" alt="Ver2 reverse oblique"> |

</div>

---

### Ver.2 Motion Videos

Here’s the moment it **first moved in real life**:

🎥 **Initial Motion Test**  
[![Watch on YouTube](https://img.youtube.com/vi/T3U7c1Mr3Y8/0.jpg)](https://youtu.be/T3U7c1Mr3Y8?si=hUQZJXoczCW0qAUG)

🎥 **Overview / Re-verification**  
[![Watch on YouTube](https://img.youtube.com/vi/JzXOxTJvHzw/0.jpg)](https://youtu.be/JzXOxTJvHzw?si=1MGZkGYogJQsFP-6)

**Summary**  
Ver.1 focused on *materializing the idea* and left room for improvement in gears and crank layout.  
Ver.2 rebuilt the mechanical balance, evolving into a **Rhinoceros that walks naturally on wind power alone**.

---

## 🌬️ What’s Next

For **Ver.3**, I aim for even more natural walking.  
I’ll take a short break to organize my learnings, then pursue the following improvements:

### 💡 Planned Improvements

- **Generative Design (GD)**  
  Using Autodesk **Fusion 360** generative design to optimize structural strength, weight, and stiffness balance.  
  This approach leaves material only where necessary, enabling **maximum stiffness at minimum mass**.

  Below are early experiments I tried:

  <div align="center">

  🧠 **GD in progress**  
  <img src="./docs/images/GD1.jpg" width="420" alt="GD design process">

  ⚙️ **Comparison (Top: GD candidate / Bottom: Ver.2)**  
  <img src="./docs/images/87811_0.jpg" width="420" alt="GD vs Ver2">

  </div>

  Also, practical applications of GD have progressed in industry—  
  for example, initiatives by Isuzu Central Research Laboratory (Autodesk official blog):  
  [Isuzu Central Research Laboratory × Generative Design](https://www.autodesk.com/products/fusion-360/blog/isuzu-central-research-laboratory-generative-design/)

---

- **Reducing Shaft Deflection**  
  In Ver.2, I used a thin stainless rod as a rotating shaft, which caused **deflection** (elastic bending), friction losses, and wobble.

  Based on **Young’s modulus (E)** and beam bending behavior, slender members have larger displacement under load.  
  I’m considering the following:

  - Switch to **larger-diameter lightweight hollow shafts** (e.g., carbon tube or aluminum alloy).  
  - Add **intermediate supports (support bearings)** to distribute deflection.  
  - Improve **coaxiality** between shaft and gears to increase torque transmission efficiency.

  These should increase **shaft rigidity (E×I)** and **reduce friction losses** for more stable operation.

---

- **CFD Visualization of Wind Energy**  
  I plan to use **CAE** tools to simulate the energy transfer from turbine blades to the crank mechanism via **CFD**.  
  I’ll analyze how **vortices and pressure distributions** vary with wind speed, blade angle, and Savonius geometry,  
  and quantitatively visualize torque generation—explaining physically **why “letting wind pass” yields stable rotation**.

---

## Reflections

Through this project, I deeply felt the fusion of **Theo Jansen’s philosophy and engineering**.  
Building everything by myself from “1” was challenging enough—and it made me appreciate even more that he started this from “0”.

Designing and fabricating the crankshaft and gears gave me hands-on insight into the depth and versatility of mechanical components—  
it felt like relearning the fundamentals of mechanical engineering through practice.  
Even in the journey toward Ver.3, I realized that *making a Strandbeest* itself becomes a gateway to learning across disciplines.

Harnessing wind—nature itself—to drive a kinetic sculpture truly sits at the **intersection of engineering and art**.  
The blend of function and beauty, design and sensibility, was an inspiring and invaluable experience for me.

I hope to continue sharing this project in education, exhibitions, and creative contexts.  
If you have ideas or suggestions, I’d love to hear them.

---

## 🧩 Extras

When I wanted to **batch-export multiple Fusion 360 components to STL**,  
I couldn’t find a GUI method—so I created a small **Fusion API add-on button**.

I implemented the coding smoothly with **GitHub Copilot**.  
If you haven’t tried Copilot yet, I highly recommend it—  
it speeds up development and broadens your creative options. 🚀

🔗 [Reference repo: Fusion360 Export All STL – Add-on Project](https://github.com/ktanino10/fusion360-export-all-stl/blob/main/README.md)

---

📘 **Japanese version:** [README_ja.md](./README_ja.md)


🦏 **Happy Building & Learning!**
