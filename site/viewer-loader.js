const start = document.getElementById("load-viewer");
const design = document.getElementById("design-select");
const status = document.getElementById("viewer-status");
const errorBox = document.getElementById("viewer-error");
const workspace = document.getElementById("viewer-workspace");
const fallback = document.getElementById("viewer-fallback");
const requested = new URL(location.href).searchParams;
const catalogUrl = document.body.dataset.viewerCatalog || "assets/viewer-index.json";
if (["A", "B", "C"].includes(requested.get("design"))) design.value = requested.get("design");
let controller;
let loading = false;
start.hidden = false;

async function openDesign() {
  if (loading) return;
  loading = true;
  design.disabled = true;
  start.disabled = true;
  errorBox.hidden = true;
  status.textContent = `${design.value}案の3Dを読み込んでいます。`;
  workspace.setAttribute("aria-busy", "true");
  workspace.inert = true;
  try {
    if (!controller) {
      const { createViewer } = await import("./assets/viewer-engine.js");
      controller = createViewer({ catalogUrl });
    }
    workspace.hidden = false;
    await controller.load(design.value, requested.get("focus"));
    fallback.hidden = true;
    start.textContent = "この案を再読み込み";
    status.textContent = `${design.value}案を表示しました。マウス・タッチ・キーボードで操作できます。`;
  } catch (error) {
    console.warn("3D viewer could not load.", error);
    if (controller) controller.clear();
    workspace.hidden = true;
    fallback.hidden = false;
    errorBox.textContent = `3Dを表示できませんでした（${error.message}）。静止画・STEP原本・下の組立手順をご利用ください。再読み込みもできます。`;
    errorBox.hidden = false;
    status.textContent = "3Dは未表示です。静的資料は引き続き利用できます。";
  } finally {
    workspace.setAttribute("aria-busy", "false");
    workspace.inert = false;
    loading = false;
    design.disabled = false;
    start.disabled = false;
  }
}
start.addEventListener("click", openDesign);
design.addEventListener("change", () => {
  if (controller) openDesign();
});
