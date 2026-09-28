"""Local-only display of frozen r7 CAD and schema2 operations; no physics or CAD execution."""

from collections import Counter
import csv
import gzip
import hashlib
from html import escape
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import subprocess
from urllib.parse import quote
import zipfile

from viewer_data import export_glb

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "site/r7-source.json"
BASE = "docs/ver3/integrated_r7/"
CATEGORIES = {"printed": "印刷品", "purchased": "購入品", "cut_to_length": "切断加工品", "sheet_cut": "シート切出し品"}
TOOLS = {"HEX_1P5": "1.5 mm六角キー", "HEX_2P5": "2.5 mm六角キー", "HEX_3": "3 mm六角キー",
         "WRENCH_4": "4 mmスパナ", "WRENCH_5P5": "5.5 mmスパナ", "WRENCH_7": "7 mmスパナ",
         "NUT_DRIVER_4P5": "ENGINEER DN-03（対辺4.5 mmナットドライバー）"}
OP_NAMES = {"add": "追加", "remove": "一時取外し", "reinsert": "同じIDを再挿入"}
PATH_NAMES = {
    "frame_right_close": "右フレームを閉じる",
    "upper_pet_from_below": "上側PETをY−4 mmで下から上げる",
    "upper_pet_lateral_seat": "上側PETをY−4→0 mmへ着座",
    "left_pet_from_left": "左側PETの装着",
    "lower_pet_from_right": "右下側PETの装着",
    "rotor_into_front_basket": "別作業台：風車を前バスケットへ",
    "front_basket_and_rotor_lower": "風車部分組立をX＋4 mmで下降",
    "front_basket_axial_seat": "同じ高さでX＋4→0 mmへ着座",
    "input_shaft_insert": "入力軸を通す",
    "rear_cage_cap_insert": "後部ガードを着座",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_digest(value, *, sort=False):
    return digest(json.dumps(value, sort_keys=sort, separators=(",", ":")).encode())


class Snapshot:
    """Read one immutable local Git commit, never another worktree's changing files."""

    def __init__(self, *, use_git=None):
        self.source = json.loads(SOURCE.read_text())
        if (self.source["schemaVersion"] != 2 or self.source["localOnly"] == self.source["publicationAuthorized"]
                or not re.fullmatch(r"[a-f0-9]{40}", self.source["artifactCommit"])):
            raise ValueError("Only the reviewed r7 source contract is supported")
        if self.source["publicationAuthorized"] and not re.fullmatch(r"[a-f0-9]{40}", self.source.get("publicSourceCommit", "")):
            raise ValueError("Published r7 source links require an immutable existing commit")
        self.commit = self.source["artifactCommit"]
        self.use_git = self.source["localOnly"] if use_git is None else use_git
        if self.use_git:
            subprocess.run(["git", "cat-file", "-e", f"{self.commit}^{{commit}}"], cwd=ROOT, check=True)
        self.cache = {}
        for path_key, hash_key in (("contract", "contractSha256"), ("manifest", "manifestSha256")):
            if digest(self.read(self.source[path_key])) != self.source[hash_key]:
                raise ValueError(f"Frozen r7 {path_key} changed")
        self.contract = self.json(self.source["contract"])
        self.manifest = self.json(self.source["manifest"])
        for document in (self.contract, self.manifest):
            if any(document[key] != self.source[value] for key, value in (
                ("revisionId", "revisionId"), ("candidateRevision", "candidateRevision"),
                ("sourceCommit", "inputCommit"), ("sourceHash", "sourceHash"))):
                raise ValueError("The r7 candidate contract and source revision disagree")
            if document["manufacturingRelease"] is not False or document["qualifiedWalkingPrototypeCount"] != 0:
                raise ValueError("Re-review the r7 qualification status instead of changing the display")
        if (self.contract["schemaVersion"] != 2
                or self.contract["publicationAuthorized"] != self.source.get("upstreamPublicationAuthorized", False)
                or [design["id"] for design in self.contract["designs"]] != list("ABC")
                or {d["id"]: d["instanceCount"] for d in self.contract["designs"]} != self.source["expectedInstances"]):
            raise ValueError("Unsupported r7 schema/design inventory")
        if self.source["publicationAuthorized"] and self.contract.get("budgetConfirmationPending"):
            raise ValueError("R7 publication still awaits budget approval")
        self.files = {row["path"]: row for row in self.manifest["files"]}
        if len(self.files) != len(self.manifest["files"]):
            raise ValueError("Duplicate candidate manifest paths")
        for resource in self.contract["sourceFiles"] + self.contract["readOnlyExistingDependencies"]:
            self.verify(resource)
        self.verified = set()

    def read(self, path):
        parsed = PurePosixPath(path)
        if parsed.is_absolute() or ".." in parsed.parts or "\\" in path or ":" in path:
            raise ValueError(f"Invalid frozen source path: {path}")
        if path in self.cache:
            return self.cache[path]
        if self.use_git:
            data = subprocess.check_output(["git", "show", f"{self.commit}:{path}"], cwd=ROOT)
        else:
            local = (ROOT / path).resolve()
            if not local.is_relative_to(ROOT) or not local.is_file():
                raise ValueError(f"Missing version-pinned source: {path}")
            data = local.read_bytes()
        if len(data) < 1_000_000:
            self.cache[path] = data
        return data

    def json(self, path):
        return json.loads(self.read(path))

    def verify(self, resource):
        data = self.read(resource["path"])
        if len(data) != resource["bytes"] or digest(data) != resource["sha256"]:
            raise ValueError(f"Frozen source fingerprint differs: {resource['path']}")
        return data

    def checked(self, path):
        if path == self.source["manifest"]:
            data = self.read(path)
            if digest(data) != self.source["manifestSha256"]:
                raise ValueError("The root manifest fingerprint changed")
            self.verified.add(path)
            return data
        if path not in self.files:
            raise ValueError(f"Local r7 download is not in its manifest: {path}")
        data = self.verify(self.files[path])
        self.verified.add(path)
        return data


def vector(value):
    if not isinstance(value, list) or len(value) != 3 or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in value):
        raise ValueError("Expected a finite CAD-space 3-vector")
    return value


def plus(left, right):
    return [left[n] + right[n] for n in range(3)]


def path_point(path, distance):
    return plus([x * distance for x in path["direction"]], path["constantOffsetMm"])


def replay_contract(assembly, workflow, access):
    """Reconstruct every operation boundary, then match the recorded path inventory."""
    all_names = {item["name"] for item in assembly["instances"]}
    if len(all_names) != len(assembly["instances"]) or len(workflow["stages"]) != 12:
        raise ValueError("Expected unique r7 instances and twelve canonical stages")
    if workflow["schemaVersion"] != 2 or access["schemaVersion"] != 2 or not workflow["operationsAreOrdered"]:
        raise ValueError("R7 requires schema2 ordered operations, never first-cut steps")
    visible, ever = set(), set()
    boundaries, paths = {}, {}
    actual = {p["id"]: p for p in access["stages"]}
    if len(actual) != len(access["stages"]):
        raise ValueError("Duplicated recorded r7 path")
    for stage in workflow["stages"]:
        if stage["stopCrankDeg"] != 0 or stage["physicalAssemblyPerformed"] is not False:
            raise ValueError("Only the frozen, untested reference stop-angle0 is supported")
        sid = stage["id"]
        if sid in boundaries:
            raise ValueError("Duplicated canonical stage")
        states = {-1: set(visible)}
        for index, operation in enumerate(stage["orderedOperations"]):
            names, kind = set(operation["instances"]), operation["operation"]
            if len(names) != len(operation["instances"]) or not names <= all_names:
                raise ValueError("Unknown or duplicate operation instance")
            if kind == "add":
                if names & ever:
                    raise ValueError("Previously installed instances require reinsert")
                ever |= names
                visible |= names
            elif kind == "remove":
                if not names <= visible:
                    raise ValueError("Cannot remove an uninstalled instance")
                visible -= names
            elif kind == "reinsert":
                if not names <= ever or names & visible:
                    raise ValueError("Reinsert must restore the same previously removed IDs")
                visible |= names
            else:
                raise ValueError("Unknown ordered operation")
            states[index] = set(visible)
        if visible != set(stage["visibleAfter"]):
            raise ValueError("Canonical visibleAfter differs from operation inventory")
        for label, kind in (("add", "add"), ("remove", "remove"), ("reinsert", "reinsert")):
            listed = [name for op in stage["orderedOperations"] if op["operation"] == kind for name in op["instances"]]
            if Counter(listed) != Counter(stage[label]):
                raise ValueError("Stage summary differs from ordered operations")
        prepared = set(stage["prepareOnly"])
        if not prepared <= all_names or prepared & visible:
            raise ValueError("Prepared subassembly must be separate from installed inventory")
        bench_seen = set()
        for bench in stage.get("footFirstBenchSubassemblies", []):
            names = set(bench["instances"])
            if (not names or not names <= prepared or names & bench_seen or len(names) != len(bench["instances"])
                    or bench["attachOtherLegLinksAfterTightening"] is not True):
                raise ValueError("Foot-first bench groups must be disjoint declared preparation parts")
            bench_seen |= names
        checks = stage.get("pathChecks", [])
        if [p["id"] for p in checks] != stage["validatedPathIds"]:
            raise ValueError("Every stage path needs an explicit operation boundary")
        for definition in checks:
            if {"fixedNames", "excludedFixedNames"} & definition.keys():
                raise ValueError("Manual exclusion of installed obstacles is forbidden")
            boundary = definition["afterOperationIndex"]
            if boundary not in states:
                raise ValueError("Path references an unknown operation boundary")
            scene_kind = definition["sceneKind"]
            if scene_kind not in {"installed", "isolated_preassembly"}:
                raise ValueError("Unknown path scene")
            scene = states[boundary] if scene_kind == "installed" else prepared
            if scene_kind == "isolated_preassembly" and scene & states[boundary]:
                raise ValueError("Bench preassembly cannot include installed parts")
            moving = set(definition["movingNames"])
            if not moving or not moving <= scene or len(moving) != len(definition["movingNames"]):
                raise ValueError("Missing/duplicate moving assembly")
            fixed = scene - moving
            overrides = {}
            for override in definition["fixedPoseOverrides"]:
                names = set(override["instances"])
                if not names <= fixed or names & overrides.keys():
                    raise ValueError("Invalid fixed-part override")
                delta = vector(override["translationFromCadMm"])
                overrides.update({name: delta for name in names})
            for field in ("direction", "constantOffsetMm", "sceneOffsetMm"):
                vector(definition[field])
            if not definition["distancesMm"] or not all(math.isfinite(d) for d in definition["distancesMm"]):
                raise ValueError("Invalid path samples")
            row = {key: definition[key] for key in ("id", "sceneKind", "direction", "distancesMm",
                                                   "constantOffsetMm", "sceneOffsetMm", "continues")}
            row.update(workflowStageId=sid, afterOperationIndex=boundary, stopCrankDeg=stage["stopCrankDeg"],
                       movingNames=sorted(moving), fixedNames=sorted(fixed), sceneInventoryNames=sorted(scene),
                       fixedPoseOverridesByName=overrides)
            row["inventorySha256"] = json_digest(sorted(scene))
            row["pathDefinitionSha256"] = json_digest(row, sort=True)
            evidence = actual.get(row["id"])
            if not evidence or any(evidence.get(key) != value for key, value in row.items()):
                raise ValueError(f"Path evidence drops or changes an operation-boundary inventory: {row['id']}")
            if evidence["status"] != "PASS" or evidence["unintendedIntersections"]:
                raise ValueError("Do not display a failed path as a validated one")
            if row["continues"]:
                previous = paths.get(row["continues"])
                if not previous or any(previous[key] != row[key] for key in (
                    "movingNames", "fixedNames", "sceneInventoryNames", "fixedPoseOverridesByName", "sceneKind", "sceneOffsetMm")):
                    raise ValueError("Connected path segments changed their inventory")
                if any(abs(a - b) > 1e-10 for a, b in zip(path_point(previous, previous["distancesMm"][-1]),
                                                        path_point(row, row["distancesMm"][0]))):
                    raise ValueError("Discontinuous r7 path segments")
            if row["id"] in paths:
                raise ValueError("Duplicate r7 path ID")
            paths[row["id"]] = {**row, "clampReferenceContacts": evidence["clampReferenceContacts"],
                                "exactPairs": evidence["exactPairs"], "status": evidence["status"]}
        boundaries[sid] = states
    if set(paths) != set(actual) or visible != all_names or workflow["finalVisibleInstanceCount"] != len(all_names):
        raise ValueError("R7 path set or final inventory is incomplete")
    return boundaries, paths


def display_sequence(assembly, workflow, access):
    boundaries, paths = replay_contract(assembly, workflow, access)
    inventories, interned, steps, ever = {}, {}, [], set()

    def inventory(names):
        key = tuple(sorted(names))
        if key not in interned:
            identity = f"inventory-{len(interned)}"
            interned[key] = identity
            inventories[identity] = list(key)
        return interned[key]

    empty = inventory([])
    steps.append({"id": "empty", "title": "未配置（12工程の前）", "frames": [
        {"id": "empty", "label": "未配置", "kind": "empty", "inventory": empty,
         "installedInventory": empty, "focusIds": [], "removed": [], "offsets": {}, "stopCrankDeg": 0}],
        "tools": [], "cautions": "部品をまだ配置していません。次は正規工程01です。",
        "defaultFrame": 0, "prepareOnly": [], "temporarilyHandSupported": [], "orderedOperations": []})
    for stage in workflow["stages"]:
        sid = stage["id"]
        states = boundaries[sid]
        frames = []

        def frame(label, kind, installed, *, shown=None, focus=(), offsets=None, path=None, distance=None, removed=None):
            frame_data = {"id": f"{sid}:{len(frames)}", "label": label, "kind": kind,
                          "inventory": inventory(installed if shown is None else shown),
                          "installedInventory": inventory(installed), "focusIds": sorted(focus),
                          "removed": sorted(ever - set(installed) if removed is None else removed),
                          "offsets": offsets or {}, "stopCrankDeg": stage["stopCrankDeg"]}
            if path:
                frame_data.update(pathId=path["id"], distanceMm=distance, sceneKind=path["sceneKind"],
                                  movingIds=path["movingNames"], fixedIds=path["fixedNames"],
                                  inventorySha256=path["inventorySha256"], pathDefinitionSha256=path["pathDefinitionSha256"],
                                  pathDirection=path["direction"], continues=path["continues"],
                                  clampReferenceContacts=path["clampReferenceContacts"], validatedSample=True)
            frames.append(frame_data)

        frame("工程の開始在庫", "stage-start", states[-1])
        for position, operation in enumerate(stage["orderedOperations"]):
            kind, names = operation["operation"], set(operation["instances"])
            if kind == "add":
                ever |= names
            installed = states[position]
            checks = [paths[p["id"]] for p in stage.get("pathChecks", []) if p["afterOperationIndex"] == position]
            # A path-bound addition appears directly at its first recorded sample, not falsely seated first.
            if not checks or kind == "remove":
                pending = next((paths[p["id"]] for p in stage.get("pathChecks", [])
                                if p["afterOperationIndex"] > position and names & set(p["movingNames"])), None)
                offsets = {}
                if pending and kind in {"add", "reinsert"}:
                    start = plus(path_point(pending, pending["distancesMm"][0]), pending["sceneOffsetMm"])
                    offsets = {name: start for name in set(pending["movingNames"]) & installed}
                frame(f"操作{position + 1} · {OP_NAMES[kind]} {len(names)}点"
                      + ("（次の経路の開始位置に仮置き・経路標本ではない）" if offsets else ""),
                      kind, installed, focus=names & installed, offsets=offsets)
            for path in checks:
                if path["fixedPoseOverridesByName"]:
                    staged = {**path["fixedPoseOverridesByName"]}
                    moving_start = plus(path_point(path, path["distancesMm"][0]), path["sceneOffsetMm"])
                    staged.update({name: moving_start for name in path["movingNames"]})
                    frame("主軸をX−53 mmへ一時退避（部品を消さない）", "temporary-pose", installed,
                          shown=path["sceneInventoryNames"], focus=path["fixedPoseOverridesByName"], offsets=staged)
                for distance in path["distancesMm"]:
                    offsets = {name: plus(path["sceneOffsetMm"], path["fixedPoseOverridesByName"].get(name, [0, 0, 0]))
                               for name in path["fixedNames"]}
                    moving_delta = plus(path_point(path, distance), path["sceneOffsetMm"])
                    offsets.update({name: moving_delta for name in path["movingNames"]})
                    offsets = {name: delta for name, delta in offsets.items() if delta != [0, 0, 0]}
                    frame(f"{PATH_NAMES[path['id']]} · 標本 {distance:g} mm", "path-sample", installed,
                          shown=path["sceneInventoryNames"], focus=path["movingNames"], offsets=offsets,
                          path=path, distance=distance)
                successor = next((p for p in checks if p["continues"] == path["id"]), None)
                if not successor and path["fixedPoseOverridesByName"]:
                    frame("PET着座後、主軸を元の位置へ戻す", "temporary-pose-restored", installed,
                          focus=path["fixedPoseOverridesByName"])
        prepared = stage["prepareOnly"]
        for bench in stage.get("footFirstBenchSubassemblies", []):
            names = bench["instances"]
            frame(f"先に足モジュールを締結：Y={bench['stationYmm']:g} mm／"
                  f"{'左' if bench['side'] < 0 else '右'} · DN-03でナイロンナット、後で脚リンク",
                  "foot-bench", set(stage["visibleAfter"]), shown=names, focus=names)
        if prepared and not stage.get("pathChecks"):
            frame("別作業台の準備部品（完成参照座標・本体へ未装着）", "preparation",
                  set(stage["visibleAfter"]), shown=prepared, focus=prepared)
        frame("工程完了の本体在庫", "stage-complete", set(stage["visibleAfter"]),
              focus=set(stage["add"]) | set(stage["reinsert"]))
        default_frame = len(frames) - 1
        if prepared:
            default_frame = len(frames) - 2
        steps.append({"id": sid, "title": stage["titleJa"], "frames": frames, "defaultFrame": default_frame,
                      "tools": stage["requiredTools"], "cautions": stage["noteJa"],
                      "prepareOnly": prepared, "temporarilyHandSupported": stage.get("temporarilyHandSupported", []),
                      "temporaryPoseOperations": stage.get("temporaryPoseOperations", []),
                      "orderedOperations": stage["orderedOperations"], "fasteningTorqueNm": stage["fasteningTorqueNm"],
                      "additionalToolRequirement": stage.get("additionalToolRequirement"),
                      "collarClocking": stage.get("collarClocking"),
                      "footFirstBenchSubassemblies": stage.get("footFirstBenchSubassemblies", []),
                      "clockingAlreadyIncludedInCadTransforms": stage.get("clockingAlreadyIncludedInCadTransforms", False)})
    return {"steps": steps, "inventories": inventories, "paths": paths, "completeStep": 12, "canonicalStageCount": 12}


def part_name(part):
    fixed = {"H_INPUT_SHAFT": "既製6D入力軸", "H_INPUT_HUB": "金属6Dハブ", "H_INPUT_BEARING": "入力軸受",
             "H_INPUT_COLLAR": "入力カラー", "H_INPUT_SPACER": "入力鋼スペーサー", "H_NMB1680": "下流NMB軸受",
             "H_MAIN_HEX100": "100 mm主六角軸", "H_INTER_HEX58": "58 mm中間六角軸",
             "H_FOOT_SPRING": "市販足ばね", "H_NYLOCK4": "M4緩み止めナット", "H_LOCK_NUT_M2": "M2ナイロン緩み止めナット",
             "P_CHASSIS_L": "左フレーム", "P_CHASSIS_R": "右フレーム",
             "P_ROTOR": "16枚羽風車", "P_ROTOR_CAGE_FRONT": "前バスケット", "P_ROTOR_CAGE_CAP": "後部ガード",
             "P_INPUT_PINION": "入力ピニオン", "P_OUTPUT_WHEEL": "減速出力歯車",
             "P_SYNC_DRIVE": "同期主歯車", "P_SYNC_IDLER": "同期アイドラー"}
    if part in fixed:
        return fixed[part]
    for prefix, label in (("H_BOLT_", "ボルト"), ("H_NUT_", "ナット"), ("H_WASHER_", "座金"),
                          ("H_SLEEVE_", "平滑金属スリーブ"), ("P_CRANK_JOURNAL_", "クランク・丸ジャーナル"),
                          ("P_CAP_", "外輪保持キャップ"), ("P_MAIN_INNER_", "主軸内側止め"), ("P_INTER_", "中間軸止め"),
                          ("P_IDLER_", "アイドラー保持部"), ("P_COMPOUND_", "複合歯車"),
                          ("P_LEG_", "脚リンク"), ("P_FOOT_", "足案内・ロッカー"),
                          ("P_LAYER_SPACER_", "リンク層スペーサー"), ("P_PIN_TAIL_", "軸方向抜け止め"),
                          ("S_GUARD_", "PETガード")):
        if part.startswith(prefix):
            return f"{label} · {part[len(prefix):]}"
    raise ValueError(f"Add a reviewed r7 part label: {part}")


def build_candidate(output, snapshot=None, *, public_links=False):
    snapshot = snapshot or Snapshot()
    source = snapshot.source
    guides, assets, downloads = {}, {}, {}

    def copy_resource(path):
        if public_links:
            data = snapshot.checked(path)
            route = "raw" if Path(path).suffix.lower() in {".step", ".fcstd", ".csv", ".svg"} else "blob"
            link = f"https://github.com/ktanino10/TeoJansen_Rhinoceros/{route}/{source['publicSourceCommit']}/{quote(path, safe='/')}"
            downloads[link] = {"source": path, "source_commit": source["publicSourceCommit"],
                               "bytes": len(data), "sha256": digest(data), "localOnly": False}
            return link
        destination_name = "r7-files/" + path
        destination = output / destination_name
        if destination_name not in downloads:
            data = snapshot.checked(path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            downloads[destination_name] = {"source": path, "source_commit": snapshot.commit,
                                           "bytes": len(data), "sha256": digest(data), "localOnly": True}
        return destination_name

    def read_resource(resource):
        snapshot.verify(resource)
        snapshot.verified.add(resource["path"])
        return snapshot.json(resource["path"])

    comparison = json.loads(snapshot.checked(BASE + "comparison.json"))
    summaries = {row["design"]: row for row in comparison["rows"]}
    for design in snapshot.contract["designs"]:
        ident = design["id"]
        assembly = read_resource(design["assembly"])
        workflow = read_resource(design["stages"])
        access_entry = next(p for p in design["validationFiles"] if p["path"].endswith("/assembly_access.json"))
        access = read_resource(access_entry)
        library = json.loads(gzip.decompress(snapshot.verify(design["mesh"])))
        bom_bytes = snapshot.verify(design["bom"])
        bom = {row["part_id"]: row for row in csv.DictReader(io.StringIO(bom_bytes.decode()))}
        if set(bom) != set(assembly["parts"]) or set(library) != set(bom):
            raise ValueError(f"{ident}: r7 mesh/part/BOM catalogs differ")
        counts = Counter(item["part_id"] for item in assembly["instances"])
        if len(assembly["instances"]) != design["instanceCount"] or not set(counts) <= set(bom):
            raise ValueError(f"{ident}: r7 instance count or part identity differs")
        for part, definition in assembly["parts"].items():
            if int(bom[part]["quantity"]) != counts[part] or definition["category"] != bom[part]["category"]:
                raise ValueError(f"{ident}: r7 BOM count/category mismatch at {part}")
            if definition["category"] not in CATEGORIES or library[part]["category"] != definition["category"]:
                raise ValueError(f"{ident}: r7 category is unsupported")
        for document in (assembly, workflow, access):
            if document["revisionId"] != source["revisionId"] or document["designId"] != ident:
                raise ValueError(f"{ident}: mixed r7 documents")
        if workflow["nativeSha256"] != design["native"]["sha256"] or access["nativeSha256"] != design["native"]["sha256"]:
            raise ValueError(f"{ident}: r7 stage/path native hashes disagree")
        sequence = display_sequence(assembly, workflow, access)
        normalized = {"id": ident, "parts": assembly["parts"], "instances": assembly["instances"]}
        raw_path = output / "assets" / f"r7-{ident}.glb"
        model = export_glb(normalized, library, raw_path,
                           {"revisionId": source["revisionId"], "canonicalCommit": snapshot.commit},
                           coupon_ids=(), max_model_bytes=12_000_000)
        transport = gzip.compress(raw_path.read_bytes(), compresslevel=9, mtime=0)
        filename = f"assets/r7-{ident}.glb.gz"
        (output / filename).write_bytes(transport)
        raw_path.unlink()
        if len(transport) > 7_000_000:
            raise ValueError("One r7 transfer exceeds the local candidate 7 MB per-model guard")
        model["transportBytes"] = len(transport)
        model["transportSha256"] = digest(transport)
        model["compression"] = "gzip"
        guide = {"schemaVersion": 2, "design": ident, "revision": {
            "revisionId": source["revisionId"], "candidateRevision": source["candidateRevision"],
            "label": "r7統合候補・実機未検証" + ("" if public_links else "・ローカル表示"), "canonicalCommit": snapshot.commit,
            "inputCommit": source["inputCommit"], "sourceHash": source["sourceHash"], "localOnly": not public_links},
            "model": model, "modelUrl": filename, **sequence,
            "parts": {part: {"name": part_name(part), "category": definition["category"],
                             "description": definition["spec"], "quantity": counts[part],
                             "vertices": model["parts"][part]["vertices"], "triangles": model["parts"][part]["triangles"],
                             "sku": definition.get("sku")}
                      for part, definition in assembly["parts"].items()},
            "instances": {item["name"]: {"partId": item["part_id"], "group": item["group"],
                                       "displayLabel": assembly.get("nativeLabelOverrides", {}).get(item["name"], item["name"])}
                          for item in assembly["instances"]},
            "links": {}, "summary": summaries[ident], "manufacturingRelease": False,
            "qualifiedWalkingPrototypeCount": 0, "referenceCrankDeg": design["crankReferenceDeg"],
            "mainShaftPhasesDeg": design["mainShaftPhasesDeg"],
            "signedInputRevolutionsPerCrank": design["signedInputRevolutionsPerCrank"],
            "referencePose": assembly["assemblyReference"], "renderingLimits": snapshot.contract["renderingLimits"],
            "accessScope": access["scope"], "inputCollarClocking": assembly["inputCollarClocking"]}
        for field in ("nonContactFloorClearance", "nativeFloorEnvelopes", "rockerPinToolAccess"):
            if field in design:
                resource = design[field]
                snapshot.verify(resource)
                guide.setdefault("evidence", {})[field] = resource
        for key, original in (
            ("cad", design["step"]["path"]), ("native", design["native"]["path"]),
            ("bom", design["bom"]["path"]), ("access", access_entry["path"]),
            ("canonical", design["assembly"]["path"]), ("stages", design["stages"]["path"]),
            ("assembly", BASE + "ASSEMBLY_ja.md"), ("readme", BASE + f"{ident}/README_ja.md"),
            ("section", BASE + f"{ident}/assembly_layout.svg"), ("purchase", design["purchaseLots"]["path"]),
            ("print", design["printAndSheetTemplates"]["path"]),
        ):
            guide["links"][key] = copy_resource(original)
        stls = [name for name in snapshot.files if name.startswith(f"STL/Ver.3/integrated_r7/{ident}/") and name.endswith(".stl")]
        if not stls:
            raise ValueError(f"{ident}: missing local STL resource set")
        if public_links:
            for name in stls:
                snapshot.checked(name)
            guide["links"]["stl"] = f"https://github.com/ktanino10/TeoJansen_Rhinoceros/tree/{source['publicSourceCommit']}/STL/Ver.3/integrated_r7/{ident}"
        else:
            zip_name = f"r7-files/print-{ident}.zip"
            with zipfile.ZipFile(output / zip_name, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for name in sorted(stls):
                    info = zipfile.ZipInfo(PurePosixPath(name).name, (2026, 9, 28, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(info, snapshot.checked(name))
            downloads[zip_name] = {"source": stls, "source_commit": snapshot.commit, "localOnly": True,
                                   "bytes": (output / zip_name).stat().st_size, "sha256": digest((output / zip_name).read_bytes())}
            guide["links"]["stl"] = zip_name
        if design.get("contactFrames"):
            frames = read_resource(design["contactFrames"])
            if (frames["sourceCommit"] != source["inputCommit"] or frames["sourceHash"] != source["sourceHash"]
                    or frames["assemblySha256"] != design["assembly"]["sha256"] or frames["frameCount"] != 73):
                raise ValueError("Canonical contact-frame source does not match this candidate")
            guide["contactFrames"] = {"url": copy_resource(design["contactFrames"]["path"]),
                                      "sha256": design["contactFrames"]["sha256"], "unavailable": frames["unavailableComponents"],
                                      "prescribedTiming": frames["prescribedTiming"], "frameCount": frames["frameCount"]}
        group_filters = {
            "connection": lambda item: item["part_id"] in {"H_INPUT_HUB", "H_INPUT_SHAFT", "H_MAIN_HEX100", "H_INTER_HEX58"},
            "retention": lambda item: item["group"] in {"bearing_caps", "bearings"},
            "bearings": lambda item: item["group"] == "bearings",
            "drivetrain": lambda item: item["group"] in {"input", "reducer", "synchronization", "mainshafts"},
            "legs": lambda item: item["group"] in {"legs", "feet", "cranks"},
            "frame": lambda item: item["group"] in {"frame", "frame_splice"},
            "access": lambda item: item["group"] in {"guards", "frame", "bearing_caps"},
            "procurement": lambda item: assembly["parts"][item["part_id"]]["category"] != "printed",
        }
        guide["focusGroups"] = {key: [item["name"] for item in assembly["instances"] if predicate(item)]
                                for key, predicate in group_filters.items()}
        guide_file = f"assets/r7-assembly-{ident}.json"
        (output / guide_file).write_text(json.dumps(guide, ensure_ascii=False, separators=(",", ":")) + "\n")
        for name, origin in ((filename, design["mesh"]["path"]), (guide_file, design["stages"]["path"])):
            data = (output / name).read_bytes()
            assets[name] = {"source": origin, "source_commit": snapshot.commit, "bytes": len(data),
                            "sha256": digest(data), "loading": "on-demand", "localOnly": not public_links}
        guides[ident] = guide
    common_links = {key: copy_resource(BASE + name) for key, name in (
        ("contract", "integration_contract.json"), ("manifest", "manifest.json"), ("readme", "README_ja.md"),
        ("review", "REVIEW_ja.md"), ("comparison", "comparison.json"), ("comparisonCsv", "comparison.csv"),
        ("baseline", "baseline_A_same_model.json"), ("slicing", "slicing_status.json"),
        ("accessories", "common/accessories.json"), ("sharedLots", "purchase_lots.json"),
        ("slicingReport", "SLICING_ja.md"), ("contactFrames", "CONTACT_FRAMES_ja.md"),
        ("floorCorrection", "FLOOR_CORRECTION_ja.md"), ("stockTools", "stock_fasteners_and_tools.json"),
        ("cSlicing", "C/SLICING_ja.md"))}
    catalog = {"schemaVersion": 2, "localOnly": not public_links, "revision": guides["A"]["revision"], "links": common_links,
               "designs": {ident: {"guideUrl": f"assets/r7-assembly-{ident}.json", "guideSha256": assets[f"assets/r7-assembly-{ident}.json"]["sha256"],
                                  "modelUrl": guide["modelUrl"], "bytes": guide["model"]["transportBytes"],
                                  "instances": guide["model"]["instanceCount"], "parts": len(guide["parts"])}
                           for ident, guide in guides.items()}}
    filename = "assets/r7-viewer-index.json"
    (output / filename).write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")) + "\n")
    assets[filename] = {"source": source["contract"], "source_commit": snapshot.commit, "localOnly": not public_links,
                        "bytes": (output / filename).stat().st_size, "sha256": digest((output / filename).read_bytes())}
    return guides, catalog, assets, downloads
