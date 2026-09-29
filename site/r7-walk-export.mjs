import { readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import { createMotion, TAU } from "./r7-walk-math.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
function option(name, fallback) { const i = args.indexOf(name); return i < 0 ? fallback : args[i + 1]; }
const design = option("--design", "C"), preview = args.includes("--preview");
if (!["A", "B", "C"].includes(design)) throw new Error("Unknown design");
const fps = preview ? 15 : 24, timeFactor = 16, cycles = preview ? 1 : 4;
const raw = await readFile(path.join(root, `docs/ver3/r7_walking_v1/motion_${design}.json`));
const packet = JSON.parse(raw), motion = createMotion(packet);
const duration = cycles * motion.cycleSeconds / timeFactor, count = Math.ceil(duration * fps) + 1;
const stride = 16 * (1 + packet.motionGroups.length) + 6 * 6 + 4;
const values = new Float64Array(count * stride);
for (let frame = 0; frame < count; frame++) {
  const seconds = Math.min(frame / fps, duration) * timeFactor, theta = seconds / motion.cycleSeconds * TAU;
  const pose = motion.at(theta);
  values.set([...pose.body, ...pose.groups.flat(),
    ...pose.feet.flatMap(foot => [foot.compression, foot.rocker, foot.normal, ...foot.worldCenter]),
    theta, seconds, pose.forwardMm, pose.inputDegUnwrapped], frame * stride);
}
const folder = path.join(root, "site/dist/r7-walk-state");
await mkdir(folder, { recursive: true });
const prefix = `${preview ? "preview_" : ""}${design}`;
const binary = Buffer.from(values.buffer);
await writeFile(path.join(folder, `${prefix}.bin`), binary);
await writeFile(path.join(folder, `${prefix}.json`), JSON.stringify({
  schemaVersion: 1, revisionId: packet.revisionId, designId: design, fps, timeFactor, cycles,
  frameCount: count, strideFloat64: stride, binary: `${prefix}.bin`, littleEndian: true,
  durationSeconds: count / fps, prescribedSeconds: cycles * motion.cycleSeconds,
  motionSha256: createHash("sha256").update(raw).digest("hex"),
  binarySha256: createHash("sha256").update(binary).digest("hex"),
  layout: "row-major mm: body16, group16 each; six feet(compression,rocker,normal,worldXYZ); theta,seconds,forward,inputDeg",
  evaluator: "site/r7-walk-math.js", evaluatorSha256: createHash("sha256").update(await readFile(path.join(root, "site/r7-walk-math.js"))).digest("hex"),
}, null, 2) + "\n");
console.log(`${design}: ${count} exact analytical frames, ${(binary.length / 1e6).toFixed(2)} MB temporary group matrices; ${cycles} cycles at ${timeFactor}x`);
