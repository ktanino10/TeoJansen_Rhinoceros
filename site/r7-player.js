export function r7State(guide, stageIndex, frameIndex) {
  if (guide.schemaVersion !== 2 || guide.canonicalStageCount !== 12 || typeof guide.revision.localOnly !== "boolean") {
    throw new Error("r7候補のschema2契約が一致しません");
  }
  const stage = guide.steps[stageIndex];
  const frame = stage?.frames[frameIndex];
  if (!frame) throw new Error("存在しないr7操作境界です");
  const shown = guide.inventories[frame.inventory];
  const installed = guide.inventories[frame.installedInventory];
  if (!shown || !installed || frame.stopCrankDeg !== 0
    || [...shown, ...installed, ...frame.focusIds, ...frame.removed].some((id) => !guide.instances[id])) {
    throw new Error("r7の部品在庫または停止角が不正です");
  }
  if (new Set(shown).size !== shown.length || new Set(installed).size !== installed.length) {
    throw new Error("r7の部品在庫が重複しています");
  }
  for (const [id, offset] of Object.entries(frame.offsets)) {
    if (!shown.includes(id) || offset.length !== 3 || !offset.every(Number.isFinite)) {
      throw new Error("r7の一時姿勢が不正です");
    }
  }
  if (frame.kind === "path-sample") {
    const path = guide.paths[frame.pathId];
    if (!path || path.inventorySha256 !== frame.inventorySha256
      || path.pathDefinitionSha256 !== frame.pathDefinitionSha256
      || shown.join("\0") !== path.sceneInventoryNames.join("\0")) {
      throw new Error("r7の経路と操作境界在庫が一致しません");
    }
  }
  return { stage, frame, shown, installed };
}

export function frameEvidence(state, guide) {
  const { stage, frame, shown, installed } = state;
  return {
    revision: guide.revision.revisionId,
    candidateCommit: guide.revision.canonicalCommit,
    stage: stage.id,
    frame: frame.id,
    kind: frame.kind,
    stopCrankDeg: frame.stopCrankDeg,
    scene: frame.sceneKind || (["preparation", "foot-bench"].includes(frame.kind) ? "isolated_preassembly" : "installed"),
    displayedIds: shown,
    installedOnMachineIds: installed,
    removedSameIds: frame.removed,
    movingIds: frame.movingIds || [],
    fixedIds: frame.fixedIds || [],
    temporaryOffsetsMm: frame.offsets,
    handSupportedIds: stage.temporarilyHandSupported,
    footFirstBenchSubassemblies: stage.footFirstBenchSubassemblies || [],
    pathId: frame.pathId || null,
    sampledDistanceMm: frame.distanceMm ?? null,
    inventorySha256: frame.inventorySha256 || null,
    pathDefinitionSha256: frame.pathDefinitionSha256 || null,
    clampReferenceContacts: frame.clampReferenceContacts || [],
  };
}
