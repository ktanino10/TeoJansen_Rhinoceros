import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const CATEGORY = { printed: "印刷品", purchased: "購入品", cut_to_length: "購入・切断加工品" };
const DIRECTIONS = {
  isometric: [1.1, 0.75, 1.3], front: [0, 0, 1], back: [0, 0, -1],
  left: [-1, 0, 0], right: [1, 0, 0], top: [0, 1, 0.0001], bottom: [0, -1, 0.0001],
};
const focusPredicates = {
  connection: (record) => record.partId === "H_REX_HUB" || record.partId.startsWith("H_shaft_"),
  retention: (record) => /H_(COLLAR|endwasher|button|inner_spacer)/.test(record.partId),
  bearings: (record) => record.partId === "H_608" || record.partId === "P_BEARING_RETAINER",
  drivetrain: (record) => record.group === "drivetrain" || record.group === "rotor",
  legs: (record) => ["legs", "feet", "pivot", "crank"].includes(record.group),
  frame: (record) => record.partId.startsWith("P_FRAME_"),
  access: (record) => /P_FRAME_FRONT|P_INPUT_CARRIAGE|S_WINDOW/.test(record.partId),
  procurement: (record) => record.category !== "printed",
};
const $ = (id) => document.getElementById(id);

function paragraph(text, className = "") {
  const element = document.createElement("p");
  element.textContent = text;
  if (className) element.className = className;
  return element;
}

async function jsonAt(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

function assertLocalAsset(path) {
  if (!/^assets\/(?:assembly-[ABC]\.json|ver3-[ABC]\.glb)$/.test(path)) {
    throw new Error("3Dデータの参照先が許可された配信ファイルではありません");
  }
  return path;
}

export function createViewer() {
  const host = $("canvas-host");
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: "low-power" });
  } catch (cause) {
    throw new Error("この環境ではWebGLを利用できません", { cause });
  }
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setClearColor("#edf1e9");
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.25;
  renderer.localClippingEnabled = true;
  const canvas = renderer.domElement;
  canvas.tabIndex = 0;
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", "CAD由来の3D模型。矢印キーで回転、Shiftと矢印で移動できます。");
  canvas.setAttribute("aria-describedby", "canvas-help");
  host.replaceChildren(canvas);

  const scene = new THREE.Scene();
  scene.add(new THREE.HemisphereLight("#fff8e8", "#708a81", 2.8));
  const key = new THREE.DirectionalLight("#fff4d8", 3);
  key.position.set(1, 2, 2);
  scene.add(key);
  const fill = new THREE.DirectionalLight("#dceeff", 2);
  fill.position.set(-2, 1, -1);
  scene.add(fill);
  const modelGroup = new THREE.Group();
  scene.add(modelGroup);
  const arrows = new THREE.Group();
  scene.add(arrows);
  const grid = new THREE.GridHelper(1.2, 24, "#a4b9aa", "#d2ded1");
  scene.add(grid);
  const camera = new THREE.PerspectiveCamera(38, 1, 0.0005, 20);
  camera.position.set(0.7, 0.7, 0.8);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = false;
  controls.autoRotate = false;
  controls.screenSpacePanning = true;
  controls.rotateSpeed = 0.75;
  controls.zoomSpeed = 0.8;
  const clipPlane = new THREE.Plane(new THREE.Vector3(1, 0, 0), 0);
  const raycaster = new THREE.Raycaster();
  const batches = new Map();
  let records = [];
  let guide;
  let index;
  let stepIndex = 0;
  let completeMode = true;
  let inspectionId = "";
  let selectedPart = "";
  let selectedInstance = "";
  let highlighted = new Set();
  let visible = new Set();
  let couponParts = new Set();
  let fullBox = new THREE.Box3();
  let framePending = false;
  let contextLost = false;

  function render() {
    if (framePending || contextLost) return;
    framePending = true;
    requestAnimationFrame(() => {
      framePending = false;
      if (contextLost) return;
      renderer.render(scene, camera);
      const diagnostics = $("camera-stats");
      diagnostics.dataset.drawn = String([...batches.values()].reduce((sum, batch) => sum + batch.count, 0));
      diagnostics.dataset.angle = String(controls.getAzimuthalAngle());
      diagnostics.dataset.polar = String(controls.getPolarAngle());
      diagnostics.dataset.distance = String(camera.position.distanceTo(controls.target));
      diagnostics.dataset.target = JSON.stringify(controls.target.toArray());
      if (!fullBox.isEmpty()) {
        const projected = [];
        for (const x of [fullBox.min.x, fullBox.max.x]) {
          for (const y of [fullBox.min.y, fullBox.max.y]) {
            for (const z of [fullBox.min.z, fullBox.max.z]) projected.push(new THREE.Vector3(x, y, z).project(camera));
          }
        }
        diagnostics.dataset.bounds = JSON.stringify([
          Math.min(...projected.map((point) => point.x)), Math.max(...projected.map((point) => point.x)),
          Math.min(...projected.map((point) => point.y)), Math.max(...projected.map((point) => point.y)),
          Math.min(...projected.map((point) => point.z)), Math.max(...projected.map((point) => point.z)),
        ]);
      }
      diagnostics.textContent = `視点角 ${THREE.MathUtils.radToDeg(controls.getAzimuthalAngle()).toFixed(1)}° / `
        + `${THREE.MathUtils.radToDeg(controls.getPolarAngle()).toFixed(1)}° · 描画 ${renderer.info.render.calls} batches`;
    });
  }
  controls.addEventListener("change", render);
  const observer = new ResizeObserver(() => {
    if (!host.clientWidth || !host.clientHeight) return;
    camera.aspect = host.clientWidth / host.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(host.clientWidth, host.clientHeight, false);
    render();
  });
  observer.observe(host);

  canvas.addEventListener("webglcontextlost", (event) => {
    event.preventDefault();
    contextLost = true;
    $("viewer-error").textContent = "WebGLコンテキストが失われました。静止画・STEP原本・静的組立手順をご利用ください。復帰後に再読み込みできます。";
    $("viewer-error").hidden = false;
    $("viewer-fallback").hidden = false;
    $("viewer-workspace").hidden = true;
    $("viewer-status").textContent = "3D描画が停止しました。実物や元データは変更していません。";
  });
  canvas.addEventListener("webglcontextrestored", () => {
    contextLost = false;
    $("viewer-status").textContent = "WebGLが復帰しました。「この案を再読み込み」で表示をやり直せます。";
  });

  function clearArrows() {
    for (const child of [...arrows.children]) {
      arrows.remove(child);
      child.line.geometry.dispose();
      child.line.material.dispose();
      child.cone.material.dispose();
    }
  }

  function clear() {
    clearArrows();
    for (const batch of batches.values()) {
      modelGroup.remove(batch);
      batch.material.dispose();
      batch.dispose();
    }
    batches.clear();
    for (const geometry of new Set(records.map((record) => record.geometry))) geometry.dispose();
    records = [];
    guide = undefined;
    visible.clear();
    selectedPart = "";
    selectedInstance = "";
    render();
  }

  function fit(box = fullBox, direction) {
    const targetBox = box.isEmpty() ? fullBox : box;
    const center = targetBox.getCenter(new THREE.Vector3());
    const radius = Math.max(targetBox.getSize(new THREE.Vector3()).length() / 2, 0.003);
    camera.aspect = host.clientWidth / Math.max(host.clientHeight, 1);
    const vertical = THREE.MathUtils.degToRad(camera.fov);
    const horizontal = 2 * Math.atan(Math.tan(vertical / 2) * camera.aspect);
    const offset = direction ? new THREE.Vector3(...direction)
      : camera.position.clone().sub(controls.target);
    if (offset.lengthSq() < 0.000001) offset.set(...DIRECTIONS.isometric);
    offset.normalize();
    const right = new THREE.Vector3().crossVectors(camera.up, offset).normalize();
    const up = new THREE.Vector3().crossVectors(offset, right).normalize();
    let distance = radius;
    for (const x of [targetBox.min.x, targetBox.max.x]) {
      for (const y of [targetBox.min.y, targetBox.max.y]) {
        for (const z of [targetBox.min.z, targetBox.max.z]) {
          const point = new THREE.Vector3(x, y, z).sub(center);
          distance = Math.max(distance, point.dot(offset) + Math.abs(point.dot(right)) / Math.tan(horizontal / 2),
            point.dot(offset) + Math.abs(point.dot(up)) / Math.tan(vertical / 2));
        }
      }
    }
    distance *= 1.1;
    controls.target.copy(center);
    camera.position.copy(center).add(offset.multiplyScalar(distance));
    controls.minDistance = Math.max(radius * 0.06, 0.001);
    controls.maxDistance = Math.max(radius * 30, 2);
    camera.near = Math.max(radius / 1000, 0.00001);
    camera.far = Math.max(radius * 80, 10);
    camera.updateProjectionMatrix();
    controls.update();
    render();
  }

  function zoom(factor) {
    const offset = camera.position.clone().sub(controls.target);
    offset.setLength(THREE.MathUtils.clamp(offset.length() * factor, controls.minDistance, controls.maxDistance));
    camera.position.copy(controls.target).add(offset);
    controls.update();
    render();
  }

  function boxFor(predicate) {
    const box = new THREE.Box3();
    for (const record of records.filter(predicate)) {
      if (!record.geometry.boundingBox) record.geometry.computeBoundingBox();
      box.union(record.geometry.boundingBox.clone().applyMatrix4(record.matrix));
    }
    return box;
  }

  function colorFor(record, style) {
    if (style === "selected") return "#a3399c";
    if (style === "added") return "#e6ad41";
    if (style === "previous") return "#c6d5c8";
    if (record.category === "purchased") return "#778a94";
    if (record.partId.startsWith("S_WINDOW")) return "#adcbd2";
    if (record.partId === "S_SOLE") return "#384641";
    if (record.category === "cut_to_length") return "#aaa99a";
    if (record.partId.startsWith("P_FRAME") || record.partId.startsWith("P_GUARD")) {
      return { A: "#b77729", B: "#366fad", C: "#24816c" }[guide.design];
    }
    if (record.partId === "P_SHOE") return "#486663";
    return "#e6dfc8";
  }

  function batchFor(record, style) {
    const key = `${record.partId}:${style}`;
    if (batches.has(key)) return batches.get(key);
    const window = record.partId.startsWith("S_WINDOW");
    const opacity = style === "previous" ? 0.24 : (window && style === "original" ? 0.24 : 1);
    const material = new THREE.MeshStandardMaterial({
      color: colorFor(record, style), roughness: 0.55, metalness: record.category === "purchased" ? 0.45 : 0.05,
      transparent: opacity < 1, opacity, depthWrite: opacity === 1, side: THREE.DoubleSide, forceSinglePass: true,
    });
    const capacity = records.filter((item) => item.partId === record.partId).length;
    const batch = new THREE.InstancedMesh(record.geometry, material, capacity);
    batch.count = 0;
    batch.frustumCulled = false;
    batch.userData.members = [];
    modelGroup.add(batch);
    batches.set(key, batch);
    return batch;
  }

  function isVisible(record) {
    return record.role === "coupon" ? couponParts.has(record.partId) : visible.has(record.instanceId);
  }

  function drawModel() {
    for (const batch of batches.values()) {
      batch.count = 0;
      batch.userData.members = [];
    }
    for (const record of records) {
      if (!isVisible(record)) continue;
      let style = "original";
      if (selectedPart === record.partId && (!selectedInstance || selectedInstance === record.instanceId)) style = "selected";
      else if (highlighted.has(record.instanceId) || couponParts.has(record.partId)) style = "added";
      else if (!completeMode && $("fade-previous").checked) style = "previous";
      const batch = batchFor(record, style);
      batch.setMatrixAt(batch.count, record.matrix);
      batch.userData.members.push(record);
      batch.count += 1;
    }
    const center = (selectedPart ? boxFor((record) => isVisible(record) && record.partId === selectedPart) : fullBox)
      .getCenter(new THREE.Vector3());
    clipPlane.constant = -center.x;
    for (const batch of batches.values()) {
      batch.instanceMatrix.needsUpdate = true;
      if (Boolean(batch.material.clippingPlanes?.length) !== $("clip-section").checked) {
        batch.material.clippingPlanes = $("clip-section").checked ? [clipPlane] : [];
        batch.material.needsUpdate = true;
      }
      batch.computeBoundingSphere();
    }
    render();
  }

  function showPart() {
    $("part-select").value = selectedPart;
    $("fit-selection").disabled = !selectedPart;
    const description = $("part-description");
    description.replaceChildren();
    if (!selectedPart) {
      description.textContent = "部品はまだ選択されていません。";
      return;
    }
    const part = guide.parts[selectedPart];
    const heading = document.createElement("strong");
    heading.textContent = `${part.name} · ${selectedPart}`;
    description.append(heading,
      paragraph(`${CATEGORY[part.category]} / 正規組立数量 ${part.quantity} 点`
        + (part.quantity === 0 ? "（試験片・本体には組み込みません）" : "")),
      paragraph(selectedInstance ? `インスタンスID：${selectedInstance}` : `表示中の同じ部品：${records.filter((r) => r.partId === selectedPart && isVisible(r)).length} 点`),
      paragraph(part.description, "small-note"),
      paragraph(`原メッシュ ${part.vertices.toLocaleString()} 頂点 / ${part.triangles.toLocaleString()} 三角形。表示adapterによる形状の簡略化なし。`, "small-note"));
  }

  function selectPart(part, instance = "") {
    selectedPart = part;
    selectedInstance = instance;
    showPart();
    drawModel();
  }

  function tableOf(ids, coupons) {
    const quantities = new Map();
    for (const name of ids) {
      const part = guide.instances[name].partId;
      quantities.set(part, (quantities.get(part) || 0) + 1);
    }
    for (const part of coupons) quantities.set(part, 0);
    const container = $("stage-parts");
    container.replaceChildren();
    if (!quantities.size) {
      container.append(paragraph("この状態では部品を追加表示していません。", "small-note"));
      return;
    }
    const table = document.createElement("table");
    const head = table.createTHead().insertRow();
    for (const text of ["部品ID・名称", "数量", "区分"]) {
      const cell = document.createElement("th");
      cell.scope = "col";
      cell.textContent = text;
      head.append(cell);
    }
    const body = table.createTBody();
    for (const [ident, quantity] of [...quantities].sort()) {
      const part = guide.parts[ident];
      const row = body.insertRow();
      const title = document.createElement("th");
      title.scope = "row";
      title.textContent = ident;
      const name = document.createElement("small");
      name.textContent = part.name;
      title.append(name);
      row.append(title);
      row.insertCell().textContent = quantity;
      row.insertCell().textContent = CATEGORY[part.category];
    }
    container.append(table);
  }

  function arrowFor(description) {
    clearArrows();
    $("arrow-note").textContent = "";
    if (!description) return;
    const record = records.find((item) => item.instanceId === description.instance);
    if (!record || !isVisible(record)) return;
    const center = boxFor((item) => item === record).getCenter(new THREE.Vector3());
    const [x, y, z] = description.direction;
    const direction = new THREE.Vector3(x, z, -y).normalize();
    const length = Math.max(fullBox.getSize(new THREE.Vector3()).length() * 0.13, 0.045);
    const origin = center.clone().addScaledVector(direction, -length);
    const helper = new THREE.ArrowHelper(direction, origin, length, "#982d86", length * 0.18, length * 0.075);
    arrows.add(helper);
    $("arrow-note").textContent = description.label;
  }

  function applyStep({ fitCamera = true } = {}) {
    if (!guide) throw new Error("工程データがまだ読み込まれていません");
    const step = guide.steps[stepIndex];
    const introduced = new Set(guide.steps.slice(0, stepIndex + 1).flatMap((item) => item.add));
    const inspection = inspectionId ? guide.inspections.find((item) => item.id === inspectionId) : null;
    if (inspectionId && !inspection) throw new Error("未知の工具経路です");
    const hidden = new Set(inspection ? inspection.hidden : step.hidden);
    visible = new Set([...(inspection ? Object.keys(guide.instances) : introduced)].filter((name) => !hidden.has(name)));
    if (!inspection) for (const name of step.preview) visible.add(name);
    couponParts = new Set(inspection ? [] : step.coupons);
    highlighted = new Set(inspection ? inspection.highlight : (completeMode ? [] : step.add.concat(step.preview)));
    if (selectedPart && !records.some((r) => r.partId === selectedPart && isVisible(r))) {
      selectedPart = "";
      selectedInstance = "";
    }
    $("step-select").value = String(stepIndex);
    $("step-range").value = String(stepIndex);
    $("step-previous").disabled = stepIndex === 0;
    $("step-next").disabled = stepIndex === guide.completeStep;
    $("instance-count").textContent = `表示 ${visible.size} / ${guide.model.instanceCount} 点 · 試験片 ${couponParts.size} 種類`
      + (inspection ? " · 部分組立の工具確認" : ` · 工程 ${stepIndex} / ${guide.completeStep}`);
    $("instance-count").dataset.visible = String(visible.size);
    $("instance-count").dataset.coupons = String(couponParts.size);
    $("stage-title").textContent = inspection ? inspection.title
      : `${step.id} · ${completeMode ? "全完成の参照表示 / " : ""}${step.title}`;
    $("stage-operation").textContent = inspection ? inspection.operation : step.operation;
    $("stage-tools").textContent = `工具：${inspection ? inspection.tool : step.tools}`;
    $("stage-cautions").textContent = inspection ? inspection.cautions : step.cautions;
    $("temporary-note").textContent = hidden.size
      ? `工具空間のため、原典で一時的に外す／まだ取り付けない ${hidden.size} 点を非表示にしています。最終工程で戻します。`
      : (step.preview.length ? "仕分けの参照表示です。組付け済み数量ではありません。" : "");
    tableOf(inspection ? inspection.highlight : (step.add.length ? step.add : step.preview), couponParts);
    for (const option of $("part-select").options) {
      option.disabled = !!option.value && !records.some((r) => r.partId === option.value && isVisible(r));
    }
    showPart();
    drawModel();
    arrowFor(inspection ? inspection.arrow : (completeMode ? null : step.arrow));
    if (fitCamera) {
      const box = couponParts.size ? boxFor((r) => r.role === "coupon" && isVisible(r)) : fullBox;
      fit(box, DIRECTIONS[inspection ? inspection.view : (completeMode ? "isometric" : step.view)]);
    }
    render();
  }

  function goStep(value, complete = false) {
    const next = Number(value);
    if (!guide || !Number.isInteger(next) || next < 0 || next > guide.completeStep) throw new Error("工程番号が範囲外です");
    stepIndex = next;
    completeMode = complete;
    inspectionId = "";
    $("access-select").value = "";
    applyStep();
  }

  for (const button of document.querySelectorAll("[data-view]")) {
    button.addEventListener("click", () => fit(couponParts.size ? boxFor(isVisible) : fullBox, DIRECTIONS[button.dataset.view]));
  }
  $("fit-view").addEventListener("click", () => fit(couponParts.size ? boxFor(isVisible) : fullBox));
  $("reset-view").addEventListener("click", () => fit(couponParts.size ? boxFor(isVisible) : fullBox, DIRECTIONS.isometric));
  $("zoom-in").addEventListener("click", () => zoom(0.8));
  $("zoom-out").addEventListener("click", () => zoom(1.25));
  $("fit-selection").addEventListener("click", () => fit(boxFor((r) => isVisible(r) && r.partId === selectedPart
    && (!selectedInstance || r.instanceId === selectedInstance))));
  $("part-select").addEventListener("change", (event) => selectPart(event.target.value));
  $("clear-selection").addEventListener("click", () => selectPart(""));
  $("step-first").addEventListener("click", () => goStep(0));
  $("step-previous").addEventListener("click", () => goStep(stepIndex - 1));
  $("step-next").addEventListener("click", () => goStep(stepIndex + 1));
  $("step-complete").addEventListener("click", () => goStep(guide.completeStep, true));
  $("step-select").addEventListener("change", (event) => goStep(event.target.value));
  $("step-range").addEventListener("input", (event) => goStep(event.target.value));
  $("access-select").addEventListener("change", (event) => {
    inspectionId = event.target.value;
    completeMode = !inspectionId && stepIndex === guide.completeStep;
    applyStep();
  });
  $("fade-previous").addEventListener("change", drawModel);
  $("clip-section").addEventListener("change", drawModel);

  let pointerStart;
  canvas.addEventListener("pointerdown", (event) => {
    pointerStart = { x: event.clientX, y: event.clientY, pointer: event.pointerId };
  });
  canvas.addEventListener("pointerup", (event) => {
    if (!pointerStart || pointerStart.pointer !== event.pointerId
      || Math.hypot(event.clientX - pointerStart.x, event.clientY - pointerStart.y) > 5 || !guide) return;
    const rectangle = canvas.getBoundingClientRect();
    raycaster.setFromCamera(new THREE.Vector2(
      (event.clientX - rectangle.left) / rectangle.width * 2 - 1,
      -(event.clientY - rectangle.top) / rectangle.height * 2 + 1,
    ), camera);
    const hits = raycaster.intersectObjects([...batches.values()].filter((batch) => batch.count > 0), false);
    const hit = hits.find((item) => !$("clip-section").checked || clipPlane.distanceToPoint(item.point) >= 0);
    if (hit) {
      const record = hit.object.userData.members[hit.instanceId];
      selectPart(record.partId, record.instanceId || "");
    }
  });
  canvas.addEventListener("keydown", (event) => {
    if (event.key === "Home") { event.preventDefault(); fit(fullBox, DIRECTIONS.isometric); return; }
    if (["+", "=", "-", "_"].includes(event.key)) { event.preventDefault(); zoom(["-", "_"].includes(event.key) ? 1.2 : 1 / 1.2); return; }
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
    event.preventDefault();
    const horizontal = event.key === "ArrowLeft" ? -1 : event.key === "ArrowRight" ? 1 : 0;
    const vertical = event.key === "ArrowUp" ? 1 : event.key === "ArrowDown" ? -1 : 0;
    if (event.shiftKey) {
      const distance = camera.position.distanceTo(controls.target) * 0.035;
      const offset = new THREE.Vector3(horizontal, vertical, 0).applyQuaternion(camera.quaternion).multiplyScalar(distance);
      camera.position.add(offset);
      controls.target.add(offset);
    } else {
      const offset = camera.position.clone().sub(controls.target);
      const spherical = new THREE.Spherical().setFromVector3(offset);
      spherical.theta += horizontal * 0.14;
      spherical.phi = THREE.MathUtils.clamp(spherical.phi - vertical * 0.14, 0.0001, Math.PI - 0.0001);
      camera.position.copy(controls.target).add(new THREE.Vector3().setFromSpherical(spherical));
    }
    controls.update();
    render();
  });

  async function load(design, focus) {
    if (contextLost) throw new Error("WebGLコンテキストが失われています");
    if (!["A", "B", "C"].includes(design)) throw new Error("未知の比較案です");
    clear();
    index ||= await jsonAt("assets/viewer-index.json");
    if (index.schemaVersion !== 1 || !index.designs[design]) throw new Error("表示データの契約が一致しません");
    const entry = index.designs[design];
    const data = await jsonAt(assertLocalAsset(entry.guideUrl));
    if (data.schemaVersion !== 1 || data.design !== design || data.revision.revisionId !== index.revision.revisionId) {
      throw new Error("異なる版の工程データを混在できません");
    }
    const response = await fetch(assertLocalAsset(data.modelUrl));
    if (!response.ok) throw new Error(`GLB: HTTP ${response.status}`);
    const bytes = await response.arrayBuffer();
    const checksum = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))]
      .map((value) => value.toString(16).padStart(2, "0")).join("");
    if (checksum !== data.model.sha256 || bytes.byteLength !== data.model.bytes) {
      throw new Error("GLBの版またはハッシュが一致しません");
    }
    const gltf = await new GLTFLoader().parseAsync(bytes, "");
    gltf.scene.updateMatrixWorld(true);
    const loaded = [];
    const geometries = new Set();
    const materials = new Set();
    gltf.scene.traverse((object) => {
      if (!object.isMesh) return;
      const meta = object.userData;
      if (!["assembly", "coupon"].includes(meta.role) || !data.parts[meta.partId]) throw new Error("GLBに未知の部品があります");
      const part = data.parts[meta.partId];
      if (object.geometry.getAttribute("position").count !== part.vertices || object.geometry.index.count !== part.triangles * 3) {
        throw new Error(`CADメッシュの数量が一致しません：${meta.partId}`);
      }
      geometries.add(object.geometry);
      for (const material of Array.isArray(object.material) ? object.material : [object.material]) materials.add(material);
      loaded.push({ ...meta, geometry: object.geometry, matrix: object.matrixWorld.clone() });
    });
    const assembly = loaded.filter((record) => record.role === "assembly");
    if (assembly.length !== data.model.instanceCount || new Set(assembly.map((r) => r.instanceId)).size !== assembly.length
      || assembly.some((r) => data.instances[r.instanceId]?.partId !== r.partId)) {
      throw new Error("正規インスタンスの対応が一致しません");
    }
    for (const geometry of geometries) geometry.computeVertexNormals();
    for (const material of materials) material.dispose();
    records = loaded;
    guide = data;
    const [lo, hi] = guide.model.boundsMm;
    fullBox = new THREE.Box3(
      new THREE.Vector3(lo[0], lo[2], -hi[1]).multiplyScalar(0.001),
      new THREE.Vector3(hi[0], hi[2], -lo[1]).multiplyScalar(0.001),
    );
    grid.position.x = fullBox.getCenter(new THREE.Vector3()).x;
    $("step-select").replaceChildren();
    guide.steps.forEach((step, position) => {
      const option = new Option(`${step.id} · ${step.title}`, String(position));
      $("step-select").add(option);
    });
    $("step-range").max = String(guide.completeStep);
    $("part-select").replaceChildren(new Option("未選択", ""));
    for (const [part, definition] of Object.entries(guide.parts).sort()) {
      $("part-select").add(new Option(`${part} · ${definition.name}（${CATEGORY[definition.category]}）`, part));
    }
    $("access-select").replaceChildren(new Option("通常の組立表示", ""));
    for (const inspection of guide.inspections) $("access-select").add(new Option(inspection.title, inspection.id));
    $("section-source").href = guide.links.section;
    $("model-stats").textContent = `${design}案：正規 ${guide.model.instanceCount} 点・${Object.keys(guide.parts).length} 部品定義`
      + `（本体数量0の試験片2種類を含む）。原CAD外接寸法 X/Y/Z：${hi.map((value, i) => (value - lo[i]).toFixed(2)).join(" / ")} mm。`;
    $("source-stats").textContent = `${guide.revision.label} · ${guide.revision.revisionId} · ${guide.revision.canonicalCommit}`;
    canvas.setAttribute("aria-label", `Ver.3 ${design}案のCAD由来3D模型。${guide.model.instanceCount}点。矢印キーで回転、Shiftと矢印で移動。`);
    $("clip-section").checked = false;
    goStep(guide.completeStep, true);
    if (focus && focusPredicates[focus]) {
      highlighted = new Set(records.filter((r) => r.role === "assembly" && focusPredicates[focus](r)).map((r) => r.instanceId));
      $("stage-operation").textContent = `Matrixの対象「${focus}」を強調しています。組立工程を選ぶと、対応する工程表示へ切り替わります。`;
      drawModel();
    }
    renderer.setSize(host.clientWidth, host.clientHeight, false);
    fit(fullBox, DIRECTIONS.isometric);
    render();
  }
  return { load, clear };
}
