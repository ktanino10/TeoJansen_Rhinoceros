const selector = document.getElementById("analysis-select");
const designs = [...document.querySelectorAll(".analysis-design")];
const choice = document.getElementById("analysis-choice");
const status = document.getElementById("analysis-status");
const dialog = document.getElementById("figure-dialog");
const viewport = document.getElementById("figure-viewport");
const zoomStatus = document.getElementById("figure-zoom-status");
let opener;
let figureImage;
let sourceWidth;

function showDesign(design, updateHash = false) {
  if (!["A", "B", "C"].includes(design)) throw new Error("Unknown calculation design");
  for (const section of designs) {
    const active = section.id === `analysis-${design}`;
    section.hidden = !active;
    section.open = active;
  }
  selector.value = design;
  status.textContent = `${design}案の条件付き解析を表示しています。三案とも未合格・実物未測定です。`;
  if (updateHash) history.replaceState(null, "", `#analysis-${design}`);
}

function designFromHash() {
  const match = location.hash.match(/^#(?:analysis|structure|linkage|fluid|interface|procurement)-([ABC])$/);
  if (match) showDesign(match[1]);
}
choice.hidden = false;
showDesign("A");
designFromHash();
selector.addEventListener("change", () => showDesign(selector.value, true));
window.addEventListener("hashchange", designFromHash);

function zoom(value) {
  if (!figureImage) throw new Error("No calculation figure is open");
  const width = value === "fit" ? Math.min(sourceWidth, viewport.clientWidth) : sourceWidth * Number(value);
  figureImage.style.width = `${width}px`;
  zoomStatus.textContent = `画像の表示倍率：${Math.round(width / sourceWidth * 100)}%。横・縦にスクロールできます。図の変形拡大倍率は変更していません。`;
}

for (const button of document.querySelectorAll("[data-enlarge]")) {
  button.hidden = false;
  button.addEventListener("click", () => {
    if (!/^assets\/calculation-[A-Za-z0-9-]+\.svg$/.test(button.dataset.enlarge)) throw new Error("Invalid calculation figure path");
    opener = button;
    sourceWidth = Number(button.dataset.width);
    document.getElementById("figure-dialog-title").textContent = button.dataset.title;
    document.getElementById("dialog-svg").href = button.dataset.enlarge;
    figureImage = document.createElement("img");
    figureImage.width = sourceWidth;
    figureImage.height = Number(button.dataset.height);
    figureImage.alt = `${button.dataset.title}の拡大表示。元SVGと同じ計算図です。`;
    figureImage.addEventListener("error", () => {
      zoomStatus.textContent = "拡大図を読み込めませんでした。元SVGまたは本文の原典リンクをご確認ください。";
    });
    figureImage.src = button.dataset.enlarge;
    viewport.replaceChildren(figureImage);
    dialog.showModal();
    zoom("1");
    viewport.scrollTop = 0;
    viewport.scrollLeft = 0;
    document.getElementById("close-figure").focus();
  });
}
for (const button of document.querySelectorAll("[data-zoom]")) {
  button.addEventListener("click", () => zoom(button.dataset.zoom));
}
document.getElementById("close-figure").addEventListener("click", () => dialog.close());
dialog.addEventListener("close", () => {
  viewport.replaceChildren();
  figureImage = null;
  opener?.focus();
});
