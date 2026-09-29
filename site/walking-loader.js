const $ = id => document.getElementById(id);
const { text: l, translate: tr, selectDesign } = globalThis.RhinoLocale;
const design = $("walk-design"), button = $("walk-load");
const requested = new URL(location.href).searchParams.get("design");
if ([...design.options].some(option => option.value === requested)) design.value = requested;
let controller, loading = false;
button.hidden = false;

function failed(error) {
  console.warn("Continuous walking viewer stopped.", error);
  $("walk-error").textContent = l(`歩行3Dを表示できませんでした（${error.message}）。再読み込み、または下のMP4・正規資料をご利用ください。`,
    `Walking 3D could not load (${tr(error.message)}). Reload, or use the MP4 videos and canonical documents below.`);
  $("walk-error").hidden = false;
  $("walk-status").textContent = l("歩行3Dは停止しました。静的な説明と動画は引き続き利用できます。",
    "Walking 3D has stopped. Static explanations and videos remain available.");
}
async function load() {
  if (loading) return;
  loading = true;
  button.disabled = design.disabled = true;
  $("walk-error").hidden = true;
  $("walk-status").textContent = l(`${design.value}案の連続歩行モデルを読み込んでいます。`,
    `Loading the continuous-walking model for design ${design.value}.`);
  const workspace = $("walk-workspace");
  workspace.inert = true;
  workspace.setAttribute("aria-busy", "true");
  try {
    if (!controller) {
      const { createWalkingViewer } = await import("./assets/walking-engine.js");
      controller = createWalkingViewer({ onError: failed });
    }
    workspace.hidden = false;
    await controller.load(design.value);
    $("walk-status").textContent = l(`${design.value}案の連続歩行を読み込みました。停止中です。「歩行を再生」で開始します。`,
      `Design ${design.value} continuous walking loaded and paused. Choose “Play walking” to start.`);
    button.textContent = l("歩行3Dを再読み込み", "Reload walking 3D");
  } catch (error) {
    controller?.clear();
    workspace.hidden = true;
    failed(error);
  } finally {
    workspace.inert = false;
    workspace.setAttribute("aria-busy", "false");
    button.disabled = design.disabled = false;
    loading = false;
  }
}
button.addEventListener("click", load);
design.addEventListener("change", () => {
  selectDesign(design.value);
  if (controller) load();
});
