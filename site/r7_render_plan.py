"""Display timing only for canonical schema2 states; no mechanical time model."""

FPS = 24
STAGE_NAMES = [
    "UNPLACED",
    "LEFT FRAME / BEARING RETENTION",
    "OPEN DRIVETRAIN / LEFT CRANKS",
    "CLOSE RIGHT FRAME / THEN FASTEN",
    "UPPER PET / Y -4 TO 0 / SHAFTS X -53",
    "SIDE PET / STEEL WASHER RETENTION",
    "SEPARATE BENCH PREASSEMBLY",
    "LOWER AT X +4 / THEN SEAT AT X 0",
    "INSERT INPUT SHAFT / SET COLLARS",
    "REAR GUARD / THEN JOINT FASTENERS",
    "RIGHT CRANKS / POSITIVE JOURNALS",
    "PREPARE SIX LEGS AND PASSIVE FEET",
    "INSTALL LINK LAYERS AND METAL PINS",
]


def timeline(guide, reverse=False):
    states = [(index, stage, frame) for index, stage in enumerate(guide["steps"]) for frame in stage["frames"]]
    if reverse:
        states.reverse()
    entries = []
    current = 1
    for index, stage, state in states:
        duration = {"path-sample": 4, "stage-start": 24, "stage-complete": 24, "preparation": 36, "empty": 24}.get(state["kind"], 12)
        displayed = guide["inventories"][state["inventory"]]
        installed = guide["inventories"][state["installedInventory"]]
        isolated = state["kind"] in ("preparation", "foot-bench") or state.get("sceneKind") == "isolated_preassembly"
        path = state.get("pathId")
        legend = ("SEPARATE BENCH: NOT INSTALLED" if isolated else
                  ("SOURCE PATH SAMPLE / STOPPED CRANK 0 DEG" if path else "OPERATION INVENTORY / REFERENCE POSITIONS"))
        counters = f"INSTALLED {len(installed)}/{guide['model']['instanceCount']} | SCENE {len(displayed)} | REMOVED {len(state['removed'])}"
        if path:
            counters += f" | MOVING {len(state['movingIds'])} / FIXED {len(state['fixedIds'])}"
        notes = [legend, counters]
        if stage["temporarilyHandSupported"] or stage["prepareOnly"]:
            notes.append("HAND / TEMPORARY SUPPORT REQUIRED")
        if state.get("clampReferenceContacts"):
            notes.append("D-HUB CLAMP CONTACT: OPENING / FIT UNKNOWN")
        entries.append({
            "timelineFrame": current, "lastFrame": current + duration - 1, "durationFrames": duration,
            "stageIndex": index, "stateId": state["id"], "stageTitle": STAGE_NAMES[index],
            "subtitleJa": f"{'分解参照（逆順）' if reverse else '組立参照'} · {stage['title']} / {state['label']}",
            "notes": notes, "state": state, "displayedIds": displayed, "installedIds": installed,
        })
        current += duration
    return {"fps": FPS, "reverseReference": reverse, "frameEnd": current - 1, "entries": entries,
            "timeMeaning": "Illustrative review timing only. No physical assembly speed, input RPM or walking is simulated.",
            "motionMeaning": "Constant-held canonical boundaries and finite path samples. No interpolated path is newly validated."}


def subtitle_vtt(plan):
    def stamp(frame):
        seconds = frame / plan["fps"]
        hours, rest = divmod(seconds, 3600)
        minutes, rest = divmod(rest, 60)
        return f"{int(hours):02}:{int(minutes):02}:{rest:06.3f}"
    cues = ["WEBVTT", ""]
    for entry in plan["entries"]:
        cues += [f"{stamp(entry['timelineFrame'] - 1)} --> {stamp(entry['lastFrame'])}",
                 entry["subtitleJa"], "説明用時間・停止姿勢。有限経路標本／実組立・実歩行は未確認。", ""]
    return "\n".join(cues)
