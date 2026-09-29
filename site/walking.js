import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { createMotion, coilMesh, TAU } from "./r7-walk-math.js";

const $ = id => document.getElementById(id);
const { text: l, asset } = globalThis.RhinoLocale;
const checksum = async bytes => [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))].map(x => x.toString(16).padStart(2, "0")).join("");
const localAsset = path => {
  if (!/^assets\/(?:r7-[ABC]\.glb\.gz|r7-walk-[ABC]\.json|r7-walking-index\.json)$/.test(path)) throw new Error("許可されていない歩行アセットです");
  return path;
};
async function bytesAt(path, hash) {
  const response = await fetch(asset(localAsset(path)));
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  const bytes = await response.arrayBuffer();
  if (hash && await checksum(bytes) !== hash) throw new Error("歩行データのハッシュが一致しません");
  return { bytes, response };
}
const matrix = values => new THREE.Matrix4().set(...values.map((v, i) => [3, 7, 11].includes(i) ? v / 1000 : v));
const worldPoint = p => new THREE.Vector3(p[0], p[2], -p[1]).multiplyScalar(.001);

export function createWalkingViewer({ onError }) {
  const host = $("walk-canvas");
  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
  renderer.setClearColor("#edf1e9");
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.2;
  const canvas = renderer.domElement;
  canvas.tabIndex = 0;
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", l("r7全体の連続歩行3D。地面・風車・歯車・六脚を表示します。",
    "Whole-machine r7 continuous walking 3D, showing ground, rotor, gears and six legs."));
  canvas.setAttribute("aria-describedby", "walk-help");
  host.replaceChildren(canvas);
  const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(36, 1, .001, 30);
  scene.add(new THREE.HemisphereLight("#fff9e7", "#70867c", 2.7));
  for (const [position, intensity] of [[[1, 2, 1], 3], [[-2, 1, -.7], 1.8]]) {
    const light = new THREE.DirectionalLight("#ffffff", intensity);
    light.position.set(...position);
    scene.add(light);
  }
  const gridPositions = [], gridColors = [];
  for (let i = -100; i <= 100; i++) {
    const color = new THREE.Color(i % 5 === 0 ? "#9bae9b" : "#d2ddce");
    gridPositions.push(-1, .000001, i / 100, 1, .000001, i / 100, i / 100, .000001, -1, i / 100, .000001, 1);
    for (let j = 0; j < 4; j++) gridColors.push(...color.toArray());
  }
  const gridGeometry = new THREE.BufferGeometry();
  gridGeometry.setAttribute("position", new THREE.Float32BufferAttribute(gridPositions, 3));
  gridGeometry.setAttribute("color", new THREE.Float32BufferAttribute(gridColors, 3));
  const grid = new THREE.LineSegments(gridGeometry, new THREE.LineBasicMaterial({ vertexColors: true }));
  scene.add(grid);
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(3, 3), new THREE.MeshBasicMaterial({ color: "#eff2e7" }));
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = 0;
  scene.add(ground);
  const cadRoot = new THREE.Group(), bodyRoot = new THREE.Group(), overlay = new THREE.Group(), paths = new THREE.Group();
  cadRoot.rotation.x = -Math.PI / 2;
  bodyRoot.matrixAutoUpdate = false;
  cadRoot.add(bodyRoot);
  scene.add(cadRoot, overlay, paths);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = false;
  controls.minDistance = .06;
  controls.maxDistance = 4;
  controls.target.set(0, .18, 0);
  camera.position.set(.7, .45, .65);
  let motion, packet, records = [], batches = [], springs = [], geometries = new Set();
  let theta = 0, playing = false, pending = false, last = null, pose, previousPosition;
  let phaseCycle = 0, scrubbed = false;
  let box = new THREE.Box3(), pathCycle = null, lost = false;
  const markers = [], forces = [];
  for (let i = 0; i < 6; i++) {
    const marker = new THREE.Mesh(new THREE.SphereGeometry(.0024, 10, 6), new THREE.MeshBasicMaterial());
    const arrow = new THREE.ArrowHelper(new THREE.Vector3(0, 1, 0), new THREE.Vector3(), .03, "#276d35", .007, .003);
    overlay.add(marker, arrow);
    markers.push(marker);
    forces.push(arrow);
  }
  overlay.visible = false;

  function queue(delay) {
    if (pending || lost) return;
    pending = true;
    setTimeout(() => requestAnimationFrame(tick), delay);
  }
  function schedule() { queue(0); }
  function pause() {
    playing = false;
    last = null;
    $("walk-play").textContent = l("歩行を再生", "Play walking");
    $("walk-play").setAttribute("aria-pressed", "false");
    $("walk-stats").dataset.playing = "false";
    if (packet && !$("walk-workspace").inert) $("walk-status").textContent = l(
      `${packet.designId}案の連続歩行は停止中です。位相・速度・視点を操作できます。`,
      `Design ${packet.designId} continuous walking is paused. Adjust phase, speed and viewpoint.`);
    schedule();
  }
  function play() {
    if (!motion || lost) return;
    playing = !playing;
    if (playing) { scrubbed = false; phaseCycle = Math.floor(theta / TAU); }
    last = null;
    $("walk-play").textContent = playing ? l("歩行を一時停止", "Pause walking") : l("歩行を再生", "Play walking");
    $("walk-play").setAttribute("aria-pressed", String(playing));
    $("walk-status").textContent = playing
      ? l(`${packet.designId}案の連続歩行を再生中です。規定入力120 rpmの計算表示です。`,
        `Design ${packet.designId} continuous walking is playing. Calculated display with prescribed 120 rpm input.`)
      : l(`${packet.designId}案の連続歩行は停止中です。位相・速度・視点を操作できます。`,
        `Design ${packet.designId} continuous walking is paused. Adjust phase, speed and viewpoint.`);
    schedule();
  }
  function clearPaths() {
    for (const line of [...paths.children]) { paths.remove(line); line.geometry.dispose(); line.material.dispose(); }
    pathCycle = null;
  }
  function clear() {
    pause();
    clearPaths();
    for (const batch of batches) { bodyRoot.remove(batch); batch.material.dispose(); batch.dispose(); }
    for (const spring of springs) { bodyRoot.remove(spring.object); spring.object.material.dispose(); }
    for (const g of geometries) g.dispose();
    geometries = new Set(); batches = []; records = []; springs = [];
    motion = undefined; packet = undefined; previousPosition = undefined;
    overlay.visible = false;
  }
  function fit(direction = [1.35, .65, 1.5]) {
    if (!motion || box.isEmpty()) return;
    const center = box.getCenter(new THREE.Vector3()).add(previousPosition || new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    camera.aspect = host.clientWidth / Math.max(host.clientHeight, 1);
    const angle = Math.min(THREE.MathUtils.degToRad(camera.fov), 2 * Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * camera.aspect));
    const distance = size.length() / (2 * Math.sin(angle / 2)) * 1.06;
    controls.target.copy(center);
    camera.position.copy(center).add(new THREE.Vector3(...direction).normalize().multiplyScalar(distance));
    camera.updateProjectionMatrix();
    controls.update();
    schedule();
  }
  function transparency() {
    for (const batch of batches) {
      const material = batch.material, { guard, sheet } = batch.userData;
      const transparent = $("walk-guards").checked && guard;
      material.opacity = transparent ? .15 : sheet ? .28 : 1;
      material.transparent = material.opacity < 1;
      material.depthWrite = !material.transparent;
      material.needsUpdate = true;
    }
    schedule();
  }
  function pathLines(cycle) {
    clearPaths();
    if (!$("walk-paths").checked) return;
    const points = Array.from({ length: 6 }, () => []);
    for (let i = 0; i <= 120; i++) {
      const state = motion.at((cycle + i / 120) * TAU);
      state.feet.forEach((foot, j) => points[j].push(worldPoint(foot.worldCenter)));
    }
    for (let i = 0; i < 6; i++) {
      const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(points[i]),
        new THREE.LineBasicMaterial({ color: i % 2 ? "#a64f16" : "#286c64", transparent: true, opacity: .65 }));
      paths.add(line);
    }
    pathCycle = cycle;
  }
  function update() {
    pose = motion.at(theta);
    bodyRoot.matrix.copy(matrix(pose.body));
    bodyRoot.matrixWorldNeedsUpdate = true;
    const groupMatrices = pose.groups.map(matrix), scratch = new THREE.Matrix4();
    for (const record of records) {
      if (packet.motionGroups[record.group].kind !== "body" || !record.initialized) {
        scratch.multiplyMatrices(groupMatrices[record.group], record.base);
        record.batch.setMatrixAt(record.slot, scratch);
        record.initialized = true;
      }
    }
    for (const batch of batches) batch.instanceMatrix.needsUpdate = true;
    for (let index = 0; index < 6; index++) {
      const sameFoot = springs.filter(spring => spring.foot === index);
      if (!sameFoot.length) continue;
      const vertices = coilMesh(packet.foot, pose.feet[index].compression).positions;
      for (let i = 0; i < vertices.length; i++) vertices[i] *= .001;
      const geometry = sameFoot[0].object.geometry;
      geometry.attributes.position.array.set(vertices);
      geometry.attributes.position.needsUpdate = true;
      geometry.computeVertexNormals();
      for (const spring of sameFoot) {
        spring.object.matrix.multiplyMatrices(groupMatrices[spring.group], spring.base);
        spring.object.matrixWorldNeedsUpdate = true;
      }
    }
    const currentPosition = worldPoint([pose.planar[0], pose.planar[1], 0]);
    if (previousPosition && $("walk-follow").checked) {
      const delta = currentPosition.clone().sub(previousPosition);
      camera.position.add(delta);
      controls.target.add(delta);
    }
    previousPosition = currentPosition;
    for (const surface of [grid, ground]) {
      surface.position.x = Math.round(currentPosition.x / .05) * .05;
      surface.position.z = Math.round(currentPosition.z / .05) * .05;
    }
    overlay.visible = $("walk-forces").checked;
    const weight = pose.target[0], loaded = pose.feet.filter(foot => foot.normal > .02 * weight).length;
    pose.feet.forEach((foot, index) => {
      const point = worldPoint(foot.worldCenter);
      markers[index].position.copy(point);
      markers[index].material.color.set(foot.normal > 1e-8 ? "#276d35" : "#ac501b");
      forces[index].position.copy(point).setY(0);
      forces[index].visible = foot.normal > .02 * weight;
      const length = Math.max(.000001, foot.normal * .006);
      forces[index].setLength(length, Math.min(.006, length * .3), Math.min(.0025, length * .15));
    });
    if ($("walk-paths").checked && pathCycle !== pose.cycle) pathLines(pose.cycle);
    const phaseDegrees = pose.phase * 180 / Math.PI;
    if (!scrubbed) {
      phaseCycle = pose.cycle;
      $("walk-phase").value = String(phaseDegrees);
    }
    $("walk-phase-label").textContent = `${Number($("walk-phase").value).toFixed(1)}°`;
    $("walk-distance").textContent = l(`${pose.forwardMm.toFixed(1)} mm（${(pose.forwardMm / 10).toFixed(1)} cm）`,
      `${pose.forwardMm.toFixed(1)} mm (${(pose.forwardMm / 10).toFixed(1)} cm)`);
    $("walk-seconds").textContent = l(`${pose.seconds.toFixed(1)} 秒`, `${pose.seconds.toFixed(1)} s`);
    $("walk-crank").textContent = l(`${(60 / motion.cycleSeconds).toFixed(3)} rpm ／ ${pose.cycle}周期`,
      `${(60 / motion.cycleSeconds).toFixed(3)} rpm / ${pose.cycle} cycles`);
    $("walk-contact").textContent = l(`${loaded} / 6脚 ／ ${pose.inputDegUnwrapped.toFixed(1)}°`,
      `${loaded} / 6 feet / ${pose.inputDegUnwrapped.toFixed(1)}°`);
    $("walk-timing").textContent = l(
      `${packet.designId}案 · 規定入力120 rpm · ${Math.abs(packet.inputTurnsPerCrank)}:1 · 時間${$("walk-speed").value === "1" ? "倍率1×" : `圧縮${$("walk-speed").value}×`} · 1周期 ${motion.cycleSeconds.toFixed(0)}秒（規定時間）`,
      `Design ${packet.designId} · Prescribed input 120 rpm · ${Math.abs(packet.inputTurnsPerCrank)}:1 · ${$("walk-speed").value === "1" ? "1× prescribed time" : `${$("walk-speed").value}× time compression`} · 1 cycle ${motion.cycleSeconds.toFixed(0)} s (prescribed time)`);
    const stats = $("walk-stats");
    stats.dataset.phase = String(phaseDegrees);
    stats.dataset.seconds = String(pose.seconds);
    stats.dataset.forward = String(pose.forwardMm);
    stats.dataset.inputAngle = String(pose.inputDegUnwrapped);
    stats.dataset.drawn = String(records.length + springs.length);
    stats.dataset.playing = String(playing);
    stats.dataset.body = JSON.stringify(pose.body);
    stats.dataset.crank = JSON.stringify(pose.groups[packet.motionGroups.findIndex(m => m.kind === "crank")]);
    stats.textContent = l(`全${records.length + springs.length}点（うち12本は座を保持した手続きばね）／`
      + `最大圧縮 ${Math.max(...pose.feet.map(f => f.compression)).toFixed(3)} mm／`
      + `最小パッドZ ${Math.min(...pose.feet.map(f => f.padMinimum)).toFixed(6)} mm。`
      + `原モデルの荷重期間最大滑り ${packet.sourceSlipMaximumMm.toFixed(2)} mmは未解消。`,
      `${records.length + springs.length} total instances (including 12 procedural springs retaining their seats) / `
      + `maximum compression ${Math.max(...pose.feet.map(f => f.compression)).toFixed(3)} mm / `
      + `minimum pad Z ${Math.min(...pose.feet.map(f => f.padMinimum)).toFixed(6)} mm. `
      + `The source model's maximum loaded-episode slip of ${packet.sourceSlipMaximumMm.toFixed(2)} mm remains unresolved.`);
  }
  function tick(time) {
    pending = false;
    if (lost) return;
    try {
      if (motion) {
        if (playing && last !== null) theta += (time - last) / 1000 * Number($("walk-speed").value) * TAU / motion.cycleSeconds;
        last = playing ? time : null;
        update();
      }
      renderer.render(scene, camera);
      $("walk-stats").dataset.camera = JSON.stringify({ position: camera.position.toArray(), target: controls.target.toArray() });
      // Yield an input/compositor turn even when exact CAD rendering saturates a software GPU.
      if (playing) queue(32);
    } catch (error) {
      playing = false;
      last = null;
      $("walk-play").textContent = l("歩行を再生", "Play walking");
      $("walk-play").setAttribute("aria-pressed", "false");
      $("walk-stats").dataset.playing = "false";
      onError(error);
    }
  }
  const observer = new ResizeObserver(() => {
    if (!host.clientWidth || !host.clientHeight) return;
    camera.aspect = host.clientWidth / host.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(host.clientWidth, host.clientHeight, false);
    schedule();
  });
  observer.observe(host);
  controls.addEventListener("change", schedule);
  canvas.addEventListener("webglcontextlost", event => {
    event.preventDefault(); lost = true; pause();
    onError(new Error("WebGLコンテキストが失われました。復帰後に再読み込みできます"));
  });
  canvas.addEventListener("webglcontextrestored", () => { lost = false; schedule(); });
  document.addEventListener("visibilitychange", () => { if (document.hidden) pause(); });
  for (const video of document.querySelectorAll("video")) video.addEventListener("play", pause);
  matchMedia("(prefers-reduced-motion: reduce)").addEventListener("change", pause);
  $("walk-play").addEventListener("click", play);
  $("walk-reset").addEventListener("click", () => { pause(); theta = 0; phaseCycle = 0; scrubbed = false; clearPaths(); schedule(); });
  $("walk-cycle").addEventListener("click", () => { pause(); theta += TAU; phaseCycle = Math.floor(theta / TAU); scrubbed = false; schedule(); });
  $("walk-phase").addEventListener("input", () => { pause(); scrubbed = true; theta = phaseCycle * TAU + Number($("walk-phase").value) / 360 * TAU; schedule(); });
  $("walk-speed").addEventListener("change", () => { last = null; schedule(); });
  $("walk-three-quarter").addEventListener("click", () => fit());
  $("walk-side").addEventListener("click", () => fit([1, .18, .03]));
  $("walk-fit").addEventListener("click", () => fit(camera.position.clone().sub(controls.target).toArray()));
  $("walk-guards").addEventListener("change", transparency);
  $("walk-forces").addEventListener("change", schedule);
  $("walk-paths").addEventListener("change", () => { clearPaths(); schedule(); });
  canvas.addEventListener("keydown", event => {
    if (event.code === "Space") { event.preventDefault(); play(); return; }
    if (event.key === "Home") { event.preventDefault(); fit(); return; }
    const offset = camera.position.clone().sub(controls.target);
    const spherical = new THREE.Spherical().setFromVector3(offset);
    if (event.key === "ArrowLeft") spherical.theta -= .12;
    else if (event.key === "ArrowRight") spherical.theta += .12;
    else if (event.key === "ArrowUp") spherical.phi -= .12;
    else if (event.key === "ArrowDown") spherical.phi += .12;
    else if (["+", "="].includes(event.key)) spherical.radius *= .88;
    else if (event.key === "-") spherical.radius *= 1.12;
    else return;
    event.preventDefault(); spherical.makeSafe();
    spherical.radius = THREE.MathUtils.clamp(spherical.radius, .06, 4);
    camera.position.copy(controls.target).add(new THREE.Vector3().setFromSpherical(spherical));
    controls.update(); schedule();
  });

  async function load(design) {
    clear();
    if (lost) throw new Error("WebGLがまだ復帰していません");
    const catalog = JSON.parse(new TextDecoder().decode((await bytesAt("assets/r7-walking-index.json")).bytes));
    const entry = catalog.designs[design];
    if (!entry || catalog.revisionId !== "r7-floor2-walking-kinematic-v1") throw new Error("案または歩行版が不正です");
    const data = JSON.parse(new TextDecoder().decode((await bytesAt(entry.motionUrl, entry.motionSha256)).bytes));
    if (data.source.assemblySha256 !== entry.assemblySha256 || data.source.meshSha256 !== entry.meshSha256 || data.designId !== design) throw new Error("歩行とCADの出典が異なります");
    const result = await bytesAt(entry.modelUrl);
    let bytes = result.bytes;
    const transferHash = await checksum(bytes);
    if (transferHash === entry.transportSha256) {
      bytes = await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"))).arrayBuffer();
    } else if (!(result.response.headers.get("content-encoding")?.includes("gzip") && transferHash === entry.modelSha256)) {
      throw new Error("圧縮CADのハッシュが一致しません");
    }
    if (await checksum(bytes) !== entry.modelSha256) throw new Error("CADのハッシュが一致しません");
    const gltf = await new GLTFLoader().parseAsync(bytes, "");
    const objects = [], originalMaterials = new Set();
    gltf.scene.traverse(object => {
      if (!object.isMesh) return;
      geometries.add(object.geometry);
      for (const material of Array.isArray(object.material) ? object.material : [object.material]) originalMaterials.add(material);
      const meta = object.userData;
      if (meta.role !== "assembly" || data.instances[meta.instanceId]?.[0] !== meta.partId) throw new Error("未知の歩行インスタンスです");
      objects.push(object);
    });
    for (const material of originalMaterials) material.dispose();
    if (objects.length !== data.instanceCount || new Set(objects.map(o => o.userData.instanceId)).size !== objects.length) throw new Error("歩行部品の数量が一致しません");
    motion = createMotion(data); packet = data; theta = 0; phaseCycle = 0; last = null; scrubbed = false;
    const grouped = new Map(), springGeometry = new Map();
    const tint = { A: "#b57526", B: "#346da3", C: "#25816a" }[design];
    for (const object of objects) {
      const meta = object.userData, group = data.instances[meta.instanceId][1], m = data.motionGroups[group];
      if (m.piece === "SPRING") {
        const foot = data.footOrder.findIndex(f => f.stationYmm === m.station && f.side === m.side);
        if (!springGeometry.has(foot)) {
          const mesh = coilMesh(data.foot, 0), geometry = new THREE.BufferGeometry();
          geometry.setAttribute("position", new THREE.BufferAttribute(mesh.positions.map(x => x / 1000), 3));
          geometry.setIndex(mesh.indices); geometry.computeVertexNormals();
          springGeometry.set(foot, geometry); geometries.add(geometry);
        }
        const coil = new THREE.Mesh(springGeometry.get(foot), new THREE.MeshLambertMaterial({ color: "#798b93" }));
        coil.matrixAutoUpdate = false; coil.frustumCulled = false;
        bodyRoot.add(coil);
        springs.push({ object: coil, base: object.matrix.clone(), group, foot });
        continue;
      }
      if (!grouped.has(meta.partId)) grouped.set(meta.partId, []);
      grouped.get(meta.partId).push({ object, group, meta });
    }
    for (const members of grouped.values()) {
      const { meta, object } = members[0], sheet = meta.category === "sheet_cut";
      const guard = sheet || /P_(ROTOR_CAGE|GUARD)/.test(meta.partId);
      object.geometry.computeVertexNormals();
      const color = sheet ? "#9ac2be" : meta.category !== "printed" ? "#7e8e98"
        : /P_(CHASSIS|COMPOUND|SYNC|OUTPUT)/.test(meta.partId) ? tint
          : /P_(FOOT|LEG_AC|LEG_DE|ROTOR_CAGE)/.test(meta.partId) ? "#3c504b" : "#d9d6be";
      const material = new THREE.MeshLambertMaterial({ color, side: THREE.DoubleSide, forceSinglePass: true });
      const batch = new THREE.InstancedMesh(object.geometry, material, members.length);
      batch.frustumCulled = false; batch.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      batch.userData = { guard, sheet };
      bodyRoot.add(batch); batches.push(batch);
      members.forEach(({ object, group, meta }, slot) => records.push({ id: meta.instanceId, group, base: object.matrix.clone(), batch, slot }));
    }
    update();
    cadRoot.updateMatrixWorld(true);
    box = new THREE.Box3();
    for (const batch of batches) {
      batch.computeBoundingBox();
      box.union(batch.boundingBox.clone().applyMatrix4(bodyRoot.matrixWorld));
    }
    box.min.y = Math.min(0, box.min.y);
    box.expandByScalar(.012);
    $("walk-source").textContent = `${data.revisionId} / ${data.source.geometryRevision} / `
      + l("機械artifact ", "mechanical artifact ") + `${data.source.artifactCommit} / contact SHA256 ${data.source.contactFramesSha256}`;
    transparency(); fit(); schedule();
  }
  return { load, clear };
}
