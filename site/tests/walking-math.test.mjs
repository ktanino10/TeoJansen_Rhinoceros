import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createMotion, linkage, multiply, planarPose, coilMesh, TAU } from "../r7-walk-math.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const read = name => JSON.parse(fs.readFileSync(path.join(root, name)));
const packets = Object.fromEntries(["A", "B", "C"].map(d => [d, read(`docs/ver3/r7_walking_v1/motion_${d}.json`)]));
const near = (a, b, tolerance, label) => assert.ok(Math.abs(a - b) <= tolerance, `${label}: ${a} != ${b} (tolerance ${tolerance})`);
const compare = (a, b, tolerance, label) => { assert.equal(a.length, b.length); a.forEach((v, i) => near(v, b[i], tolerance, `${label}[${i}]`)); };
const distance = (a, b) => Math.hypot(...a.map((x, i) => x - b[i]));
function gram(matrix) {
  for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) {
    near([0, 1, 2].reduce((s, k) => s + matrix[k * 4 + i] * matrix[k * 4 + j], 0), Number(i === j), 1e-9, "rotation Gram");
  }
}
function supportMargin(points, cop) {
  const p = points.toSorted((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (a, b, c) => (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
  const half = list => {
    const hull = [];
    for (const q of list) { while (hull.length > 1 && cross(hull.at(-2), hull.at(-1), q) <= 0) hull.pop(); hull.push(q); }
    return hull.slice(0, -1);
  };
  const hull = [...half(p), ...half([...p].reverse())];
  return Math.min(...hull.map((a, i) => cross(a, hull[(i + 1) % hull.length], cop) / distance(a, hull[(i + 1) % hull.length])));
}

for (const design of ["A", "B", "C"]) {
  const packet = packets[design], motion = createMotion(packet);
  test(`${design}: Python and JS agree at unsampled phases and after multiple cycles`, () => {
    const fixtures = read(`docs/ver3/r7_walking_v1/reference_${design}.json`);
    for (const reference of fixtures) {
      const pose = motion.at(reference.crankDegUnwrapped * Math.PI / 180);
      compare(pose.body, reference.body.flat(), 1e-7, `${design} body`);
      pose.groups.forEach((m, i) => compare(m, reference.groups[i].flat(), 1e-7, `${design} group ${i}`));
      for (const key of ["compression", "rocker", "normal", "padMinimum"]) compare(pose.feet.map(f => f[key]), reference[key], 1e-8, key);
    }
  });
  test(`${design}: 5760 phases retain pin distances, contact, support, travel and continuity`, () => {
    let previous;
    const metrics = { pad: Infinity, compression: 0, balance: 0, support: Infinity, adjacentFootMm: 0 };
    for (let index = 0; index <= 5760; index++) {
      const theta = index / 5760 * TAU, pose = motion.at(theta);
      const [weight, copX, copY] = pose.target;
      const normal = pose.feet.reduce((sum, foot) => sum + foot.normal, 0);
      const moments = [0, 1].map(axis => pose.feet.reduce((sum, foot) => sum + foot.normal * foot.center[axis], 0));
      const error = Math.max(Math.abs(normal - weight), Math.abs(moments[0] - weight * copX) / 100, Math.abs(moments[1] - weight * copY) / 100);
      metrics.balance = Math.max(metrics.balance, error);
      assert.ok(error < .01, `${design} phase ${theta}: normal/100mm moment balance ${error}`);
      const active = pose.feet.filter(f => f.normal > .02 * weight);
      assert.ok(active.length >= 3);
      metrics.support = Math.min(metrics.support, supportMargin(active.map(f => f.center.slice(0, 2)), [copX, copY]));
      for (const [i, foot] of pose.feet.entries()) {
        assert.ok(foot.padMinimum >= -1e-8, `${design} foot ${i} penetrates the floor`);
        assert.ok(foot.compression >= 0 && foot.compression < 6);
        assert.ok(Math.abs(foot.rocker) <= 5 * Math.PI / 180);
        assert.ok(packet.foot.springFreeLengthMm - foot.compression > packet.foot.springTotalTurns * packet.foot.springWireMm);
        if (foot.normal > 1e-8) near(foot.padMinimum, 0, 1e-8, "loaded pad touches Z0");
        if (previous) {
          metrics.adjacentFootMm = Math.max(metrics.adjacentFootMm, distance(foot.worldCenter, previous.feet[i].worldCenter));
          assert.ok(Math.abs(foot.compression - previous.feet[i].compression) < .1);
          assert.ok(Math.abs(foot.rocker - previous.feet[i].rocker) < .002);
        }
        metrics.pad = Math.min(metrics.pad, foot.padMinimum);
        metrics.compression = Math.max(metrics.compression, foot.compression);
      }
      if (index % 16 === 0) {
        for (const m of [pose.body, ...pose.groups]) gram(m);
        for (const phase of [0, Math.PI]) {
          const p = linkage(theta + phase, packet.lengthsMm);
          for (const [a, b, key] of [["O", "A", "OA"], ["A", "B", "AB"], ["P", "B", "BP"], ["A", "C", "AC"],
            ["P", "C", "PC"], ["B", "D", "BD"], ["P", "D", "PD"], ["C", "E", "CE"], ["D", "E", "DE"], ["C", "F", "CF"], ["E", "F", "EF"]]) {
            near(distance(p[a], p[b]), packet.lengthsMm[key], 1e-9, key);
          }
        }
      }
      previous = pose;
    }
    assert.ok(metrics.support > 3, JSON.stringify(metrics));
    assert.ok(metrics.adjacentFootMm < .25, JSON.stringify(metrics));
    const first = motion.at(0), last = motion.at(TAU);
    first.groups.forEach((m, i) => compare(m, last.groups[i], 1e-8, "periodic group"));
    for (const boundary of [0, TAU, 2 * TAU, 5 * TAU]) {
      const before = motion.at(boundary - 1e-8), after = motion.at(boundary + 1e-8);
      compare(before.body, after.body, 1e-5, "periodic body continuity");
      before.feet.forEach((f, i) => compare(f.worldCenter, after.feet[i].worldCenter, 1e-5, "periodic foot continuity"));
    }
    console.log(design, JSON.stringify(metrics));
  });
  test(`${design}: each gear plane has the correct sign and tooth-count ratio`, () => {
    for (const stage of packet.reducer.stages) {
      near(stage.pinion * stage.pinionSpeedPerCrank + stage.wheel * stage.wheelSpeedPerCrank, 0, 1e-10, "no tooth-speed mismatch");
      assert.ok(stage.pinionSpeedPerCrank * stage.wheelSpeedPerCrank < 0);
    }
    for (const seconds of [.013, .019, 11.123, 91.234]) {
      const pose = motion.at(seconds / motion.cycleSeconds * TAU);
      near(pose.inputDegUnwrapped, Math.sign(packet.inputTurnsPerCrank) * 720 * seconds, 1e-7, "unwrapped input time");
    }
  });
}

test("120rpm and identical time factors leave B genuinely slower; source advance is not v*t", () => {
  const motions = Object.fromEntries(Object.entries(packets).map(([d, p]) => [d, createMotion(p)]));
  assert.equal(motions.A.cycleSeconds, 72);
  assert.equal(motions.B.cycleSeconds, 256);
  assert.equal(motions.C.cycleSeconds, 78);
  assert.equal(packets.B.inputTurnsPerCrank, -512);
  const angles = Object.fromEntries(Object.entries(motions).map(([d, m]) => [d, 20 / m.cycleSeconds * TAU]));
  assert.ok(angles.B < angles.A && angles.B < angles.C);
  for (const [d, motion] of Object.entries(motions)) {
    near(motion.at(4 * TAU).forwardMm, 4 * packets[d].forwardPerCycleMm, 1e-8, "four-cycle advance");
    assert.ok(motion.at(4 * TAU).forwardMm > 300);
    const q = motion.at(TAU / 4).forwardMm, half = motion.at(TAU / 2).forwardMm;
    assert.ok(Math.abs(q * 2 - half) > .1, "source forward trajectory was replaced by constant speed");
  }
  compare(packets.C.reducer.stages.map(s => s.moduleMm), [.9, 1], 1e-12, "C modules");
  compare(packets.C.reducer.stages.map(s => s.pressureAngleDeg), [20, 25], 1e-12, "C pressure angles");
  near(packets.C.reducer.stages[0].pinionProfileShift, .35, 1e-12, "C pinion shift");
  near(packets.C.reducer.stages[0].wheelProfileShift, -.35, 1e-12, "C wheel shift");
});

test("cycle translations are transported by yaw, including reverse cycle queries", () => {
  const rows = [[0, 0, 0], [5, -100, .2]];
  const compose = (a, b) => [a[0] + Math.cos(a[2]) * b[0] - Math.sin(a[2]) * b[1],
    a[1] + Math.sin(a[2]) * b[0] + Math.cos(a[2]) * b[1], a[2] + b[2]];
  let target = [0, 0, 0];
  for (let cycle = 0; cycle <= 8; cycle++) {
    compare(planarPose(rows, cycle * TAU), target, 1e-9, "SE2 cycle composition");
    target = compose(target, rows[1]);
  }
  const inverse = planarPose(rows, -TAU);
  compare(compose(inverse, rows[1]), [0, 0, 0], 1e-9, "inverse cycle");
});

test("procedural springs retain wire radius, mean radius, turns and bounded seat distance", () => {
  const f = packets.C.foot, segments = 164, sides = 8;
  for (const compression of [0, 1.234, 3.18, 6]) {
    const { positions } = coilMesh(f, compression, segments, sides);
    for (let i = 0; i <= segments; i++) {
      const section = Array.from({ length: sides }, (_, j) => [...positions.slice((i * (sides + 1) + j) * 3, (i * (sides + 1) + j) * 3 + 3)]);
      const center = [0, 1, 2].map(axis => section.reduce((s, p) => s + p[axis], 0) / sides);
      near(Math.hypot(center[0], center[1]), 3.2, 1e-6, "mean radius");
      section.forEach(p => near(distance(p, center), .3, 1e-6, "wire radius"));
      near(center[2], .3 + (14.4 - compression) * i / segments, 1e-6, "pitch/seat distance");
    }
  }
  assert.throws(() => coilMesh(f, 6.1), /ばね/);
  assert.throws(() => createMotion({ ...packets.C, canonicalIndependentRockerAngleRad: 0 }), /契約|一致/);
});
