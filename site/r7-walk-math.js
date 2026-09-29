// Rigid evaluator of the versioned motion packet, shared by the browser and Node tests.
export const TAU = 2 * Math.PI;
const identity = () => [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
const add = (a, b) => a.map((x, i) => x + b[i]);
const sub = (a, b) => a.map((x, i) => x - b[i]);
const scale = (a, s) => a.map(x => x * s);
const dot = (a, b) => a.reduce((s, x, i) => s + x * b[i], 0);
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
export const transformPoint = (m, p) => [0, 1, 2].map(r => m[r * 4] * p[0] + m[r * 4 + 1] * p[1] + m[r * 4 + 2] * p[2] + m[r * 4 + 3]);
const rotate = (m, p) => [0, 1, 2].map(r => dot(m.slice(r * 3, r * 3 + 3), p));
export function multiply(a, b) {
  return Array.from({ length: 16 }, (_, i) => {
    const row = Math.floor(i / 4), col = i % 4;
    return a[row * 4] * b[col] + a[row * 4 + 1] * b[col + 4] + a[row * 4 + 2] * b[col + 8] + a[row * 4 + 3] * b[col + 12];
  });
}
const displacement = (v) => { const m = identity(); [m[3], m[7], m[11]] = v; return m; };
function rotation(axis, angle, point = [0, 0, 0]) {
  const [x, y, z] = axis, c = Math.cos(angle), s = Math.sin(angle), q = 1 - c;
  const m = [c + x * x * q, x * y * q - z * s, x * z * q + y * s, 0,
    y * x * q + z * s, c + y * y * q, y * z * q - x * s, 0,
    z * x * q - y * s, z * y * q + x * s, c + z * z * q, 0, 0, 0, 0, 1];
  const t = sub(point, transformPoint(m, point));
  [m[3], m[7], m[11]] = t;
  return m;
}
function polar(sx, sy) {
  const skew = [0, 0, -sx, 0, 0, -sy, sx, sy, 0], n = Math.sqrt(1 + sx * sx + sy * sy);
  return skew.map((v, i) => {
    const r = Math.floor(i / 3), c = i % 3;
    const square = [0, 1, 2].reduce((s, k) => s + skew[r * 3 + k] * skew[k * 3 + c], 0);
    return (r === c ? 1 : 0) + v / n + square / (n * (n + 1));
  });
}
export function sample(rows, phase) {
  const position = phase / TAU * (rows.length - 1), index = Math.min(Math.floor(position), rows.length - 2);
  return rows[index].map((x, i) => x + (rows[index + 1][i] - x) * (position - index));
}
function circle(p, radius, q, other, orientation) {
  const d = sub(q, p), length = Math.hypot(...d);
  if (length <= Math.abs(radius - other) || length >= radius + other) throw new Error("リンクの円交差が閉じません");
  const along = (radius ** 2 - other ** 2 + length ** 2) / (2 * length);
  const height = Math.sqrt(Math.max(0, radius ** 2 - along ** 2));
  return [p[0] + (along * d[0] - orientation * height * d[1]) / length,
    p[1] + (along * d[1] + orientation * height * d[0]) / length];
}
export function linkage(theta, c) {
  const P = [-c.QP, -c.OQ], A = [c.OA * Math.cos(theta), c.OA * Math.sin(theta)];
  const B = circle(A, c.AB, P, c.BP, -1), C = circle(A, c.AC, P, c.PC, 1);
  const D = circle(B, c.BD, P, c.PD, -1), E = circle(C, c.CE, D, c.DE, 1);
  const F = circle(C, c.CF, E, c.EF, 1);
  return { O: [0, 0], P, A, B, C, D, E, F };
}
export function planarPose(rows, theta) {
  const cycle = Math.floor(theta / TAU), phase = theta - cycle * TAU, end = rows.at(-1);
  const local = sample(rows, phase), yaw = cycle * end[2];
  let offset;
  if (Math.abs(end[2]) < 1e-12) offset = scale(end.slice(0, 2), cycle);
  else {
    const magnitude = Math.sin(yaw / 2) / Math.sin(end[2] / 2), angle = (cycle - 1) * end[2] / 2;
    const re = magnitude * Math.cos(angle), im = magnitude * Math.sin(angle);
    offset = [end[0] * re - end[1] * im, end[0] * im + end[1] * re];
  }
  return [offset[0] + Math.cos(yaw) * local[0] - Math.sin(yaw) * local[1],
    offset[1] + Math.sin(yaw) * local[0] + Math.cos(yaw) * local[1], yaw + local[2]];
}

export function createMotion(packet) {
  if (packet.schemaVersion !== 1 || packet.revisionId !== "r7-floor2-walking-kinematic-v1"
    || packet.canonicalIndependentRockerAngleRad !== null || packet.manufacturingRelease !== false
    || packet.physicalQualifiedCount !== 0 || packet.instances && Object.keys(packet.instances).length !== packet.instanceCount) {
    throw new Error("歩行表示モデルの版・部品・未検証条件が一致しません");
  }
  const f = packet.foot, z0 = packet.bodyReferenceZMm;
  const reference = new Map();
  for (const m of packet.motionGroups) if (m.phase !== undefined && !reference.has(m.phase)) reference.set(m.phase, linkage(m.phase, packet.lengthsMm));
  const footIndex = (m) => packet.footOrder.findIndex(x => x.stationYmm === m.station && x.side === m.side);
  const groupFeet = packet.motionGroups.map(footIndex);
  const cycleSeconds = 60 * Math.abs(packet.inputTurnsPerCrank) / packet.prescribedInputRpm;

  function at(theta) {
    if (!Number.isFinite(theta)) throw new Error("非有限のクランク位相です");
    const phase = ((theta % TAU) + TAU) % TAU, cycle = Math.floor(theta / TAU);
    const [h, sx, sy] = sample(packet.bodySamples, phase), r = polar(sx, sy);
    const current = new Map([...reference.keys()].map(p => [p, linkage(phase + p, packet.lengthsMm)]));
    const feet = packet.footOrder.map(foot => {
      const p = current.get(foot.phaseDeg * Math.PI / 180);
      const gamma = Math.atan2(p.E[1] - p.C[1], p.E[0] - p.C[0]) - f.pitchReferenceBodyAngleDeg * Math.PI / 180;
      const c = Math.cos(gamma), s = Math.sin(gamma), [dy, dz] = f.toeOffsetFromFNeutralMm;
      const neutral = [foot.side * f.centerAbsXmm, foot.stationYmm + p.F[0] + dy * c - dz * s, p.F[1] + dy * s + dz * c];
      const center = add(rotate(r, neutral), [0, 0, h]), guide = rotate(r, [0, -s, c]);
      if (guide[2] < .25) throw new Error("案内軸が表示モデルの範囲外です");
      const gap = center[2] - f.toeRadiusMm, compression = Math.max(0, -gap / guide[2]);
      const compressed = add(center, scale(guide, compression)), axis = rotate(r, [0, c, s]), lane = [r[0], r[3], r[6]];
      let rocker = Math.atan2(-lane[2], cross(axis, lane)[2]);
      rocker = ((rocker + Math.PI / 2) % Math.PI + Math.PI) % Math.PI - Math.PI / 2;
      if (Math.abs(rocker) > f.rockerTravelDeg * Math.PI / 180 + 1e-12) throw new Error("ロッカーが機械ストッパーを超えます");
      const t = Math.min(Math.max(gap / packet.airborneRestClearanceMm, 0), 1);
      rocker *= 1 - t * t * (3 - 2 * t);
      const u = add(add(scale(lane, Math.cos(rocker)), scale(cross(axis, lane), Math.sin(rocker))), scale(axis, dot(axis, lane) * (1 - Math.cos(rocker))));
      const padMinimum = compressed[2] - f.toeRadiusMm * Math.sqrt(Math.max(0, 1 - u[2] ** 2))
        - (f.rockerHalfSpanMm + f.toeLaneWidthMm / 2) * Math.abs(u[2]);
      return { center: compressed, neutral, gamma, compression, rocker, padMinimum,
        normal: compression * f.springCountPerFoot * f.springRateNmm / guide[2] };
    });
    const planar = planarPose(packet.planarSamples, theta), rz = rotation([0, 0, 1], planar[2]);
    const body = [r[0], r[1], r[2], -z0 * r[2], r[3], r[4], r[5], -z0 * r[5],
      r[6], r[7], r[8], h - z0 * r[8], 0, 0, 0, 1];
    const world = multiply(displacement([planar[0], planar[1], 0]), multiply(rz, body));
    const groups = packet.motionGroups.map((m, index) => {
      if (m.kind === "body") return identity();
      if (m.kind === "shaft" || m.kind === "crank") return rotation([1, 0, 0], theta * m.speed, [0, m.axisYz[0], z0 + m.axisYz[1]]);
      const p = current.get(m.phase), initial = reference.get(m.phase);
      if (m.kind === "joint") {
        const delta = displacement([0, ...sub(p[m.node], initial[m.node])]);
        return m.node === "A" ? multiply(rotation([1, 0, 0], theta, [0, m.station + p.A[0], z0 + p.A[1]]), delta) : delta;
      }
      const [a, b] = packet.rigids[m.kind === "link" ? m.link : "CEF"];
      const angle = Math.atan2(p[b][1] - p[a][1], p[b][0] - p[a][0]) - Math.atan2(initial[b][1] - initial[a][1], initial[b][0] - initial[a][0]);
      const before = [0, initial[a][0] + m.station, initial[a][1] + z0], now = [0, p[a][0] + m.station, p[a][1] + z0];
      let delta = multiply(displacement(sub(now, before)), rotation([1, 0, 0], angle, before));
      if (m.kind === "foot") {
        const foot = feet[groupFeet[index]], c = Math.cos(foot.gamma), s = Math.sin(foot.gamma);
        const shift = [0, -s * foot.compression, c * foot.compression];
        if (["SLIDER", "ROCKER", "ROCKER_PIN", "SPRING"].includes(m.piece)) delta = multiply(displacement(shift), delta);
        if (m.piece === "ROCKER") {
          const pivot = add(foot.neutral, [0, 0, z0]);
          delta = multiply(rotation([0, c, s], foot.rocker, add(pivot, shift)), delta);
        }
      }
      return delta;
    });
    for (const foot of feet) foot.worldCenter = transformPoint(multiply(displacement([planar[0], planar[1], 0]), rz), foot.center);
    return { theta, phase, cycle, body: world, groups, feet, planar,
      forwardMm: cycle * packet.forwardPerCycleMm - sample(packet.planarSamples, phase)[1],
      seconds: theta / TAU * cycleSeconds, inputDegUnwrapped: theta * packet.inputTurnsPerCrank * 180 / Math.PI,
      bodyParameters: [h, sx, sy], target: sample(packet.normalTargets, phase) };
  }
  return { at, cycleSeconds, packet };
}

export function coilMesh(foot, compression, segments = 164, sides = 8) {
  const length = foot.springFreeLengthMm - compression, wire = foot.springWireMm / 2;
  if (compression < -1e-8 || compression > foot.workingCompressionLimitMm + 1e-8 || length <= foot.springTotalTurns * foot.springWireMm) {
    throw new Error("ばねの自由長・密着長・作動範囲が一致しません");
  }
  const radius = (foot.springOuterDiameterMm - foot.springWireMm) / 2;
  const rise = (length - 2 * wire) / (TAU * foot.springTotalTurns), norm = Math.hypot(radius, rise);
  const positions = new Float32Array((segments + 1) * (sides + 1) * 3), indices = [];
  for (let i = 0; i <= segments; i++) {
    const t = i / segments * TAU * foot.springTotalTurns, c = Math.cos(t), s = Math.sin(t);
    for (let j = 0; j <= sides; j++) {
      const angle = j / sides * TAU, a = Math.cos(angle) * wire, b = Math.sin(angle) * wire;
      const offset = (i * (sides + 1) + j) * 3;
      positions.set([(radius + a) * c - b * rise / norm * s,
        (radius + a) * s + b * rise / norm * c, wire + rise * t - b * radius / norm], offset);
      if (i < segments && j < sides) {
        const n = i * (sides + 1) + j;
        indices.push(n, n + sides + 1, n + 1, n + 1, n + sides + 1, n + sides + 2);
      }
    }
  }
  return { positions, indices };
}
