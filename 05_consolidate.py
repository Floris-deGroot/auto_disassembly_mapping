import glob
import json
import os
import sys
from datetime import date

PRUNED_MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "data", "manifest", "pruned_manifest.json")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data", "output")
LOG_JSON_PATH = os.path.join(OUTPUT_DIR, "disassembly_log.json")
LOG_MD_PATH = os.path.join(OUTPUT_DIR, "disassembly_log.md")

PRODUCT = "small electronic device"
OPERATOR = ""
TARGET_COMPONENTS = {
    "primary": ["Lithium battery"],
    "secondary": ["PCB", "Charging port"],
}


def load_annotations():
    pattern = os.path.join(OUTPUT_DIR, "step_*_annotation.json")
    paths = sorted(glob.glob(pattern))
    if not paths:
        print(f"No annotation files found in {OUTPUT_DIR}")
        print("Run 04_analyze.py first.")
        sys.exit(1)

    annotations = []
    for path in paths:
        with open(path) as f:
            annotations.append(json.load(f))
    return annotations


def count_tool_changes(steps):
    changes = 0
    prev_tool = None
    for step in steps:
        tool = step.get("tool_observed", {}).get("type")
        if prev_tool is not None and tool != prev_tool:
            changes += 1
        prev_tool = tool
    return changes


def distribution(steps, *keys):
    counts = {}
    for step in steps:
        val = step
        for key in keys:
            val = val.get(key, {}) if isinstance(val, dict) else None
        if isinstance(val, str):
            counts[val] = counts.get(val, 0) + 1
    return counts


def penalty_counts(steps):
    totals = {}
    for step in steps:
        for penalty, flagged in step.get("penalties", {}).items():
            if flagged:
                totals[penalty] = totals.get(penalty, 0) + 1
    return totals


def confidence_summary(steps):
    fields = ["tool_observed", "action_type", "connector_type", "force_estimate", "automation_suitability"]
    summary = {}
    for field in fields:
        counts = {"high": 0, "medium": 0, "low": 0}
        for step in steps:
            conf = step.get(field, {}).get("confidence")
            if conf in counts:
                counts[conf] += 1
        summary[field] = counts
    return summary


def total_duration(pruned_manifest, annotations):
    step_nums = {a["step_number"] for a in annotations}
    clips = [c for c in pruned_manifest.get("clips", []) if c["step"] in step_nums]
    return round(sum(c["duration_s"] for c in clips), 1)


def build_markdown(annotations):
    lines = [
        f"# Disassembly log — {PRODUCT}",
        f"**Date:** {date.today()}  **Operator:** {OPERATOR}",
        "",
        "| Step | Component | Connector | Tool | Force | Reusable | Robot difficulty |",
        "|------|-----------|-----------|------|-------|----------|-----------------|",
    ]
    for a in annotations:
        step = a.get("step_number", "?")
        component = a.get("component_removed", {}).get("name", "?")
        connector = a.get("connector_type", {}).get("type", "?")
        tool = a.get("tool_observed", {}).get("type", "?")
        force = a.get("force_estimate", {}).get("level", "?")
        reusable = "yes" if a.get("connector_survived", {}).get("reusable") else "no"
        difficulty = a.get("automation_suitability", {}).get("rating", "?")
        lines.append(f"| {step} | {component} | {connector} | {tool} | {force} | {reusable} | {difficulty} |")

    lines += [
        "",
        "## Descriptions",
        "",
    ]
    for a in annotations:
        step = a.get("step_number", "?")
        desc = a.get("description", "")
        narration = a.get("narration_transcript", "")
        uncertainties = a.get("model_uncertainties", [])
        lines.append(f"### Step {step}")
        lines.append(f"{desc}")
        if narration:
            lines.append(f"> *Operator: \"{narration}\"*")
        if uncertainties:
            lines.append("")
            lines.append("**Model uncertainties:**")
            for u in uncertainties:
                lines.append(f"- {u}")
        lines.append("")

    return "\n".join(lines)


def main():
    print("=== Consolidating disassembly annotations ===")
    print()

    # Load pruned manifest for metadata
    if not os.path.exists(PRUNED_MANIFEST_PATH):
        print(f"Pruned manifest not found: {PRUNED_MANIFEST_PATH}")
        sys.exit(1)
    with open(PRUNED_MANIFEST_PATH) as f:
        pruned_manifest = json.load(f)

    annotations = load_annotations()
    annotations.sort(key=lambda a: a.get("step_number", 0))
    print(f"Loaded {len(annotations)} annotation(s)")

    duration = total_duration(pruned_manifest, annotations)
    video_source = os.path.basename(pruned_manifest.get("video_source", ""))

    log = {
        "metadata": {
            "product": PRODUCT,
            "date": str(date.today()),
            "operator": OPERATOR,
            "target_components": TARGET_COMPONENTS,
            "total_steps": len(annotations),
            "total_duration_s": duration,
            "video_source": video_source,
        },
        "steps": annotations,
        "summary": {
            "tool_changes": count_tool_changes(annotations),
            "connector_distribution": distribution(annotations, "connector_type", "type"),
            "penalty_counts": penalty_counts(annotations),
            "automation_suitability_distribution": distribution(annotations, "automation_suitability", "rating"),
            "model_confidence_summary": confidence_summary(annotations),
        },
        "dependencies": {
            "note": "To be filled during human review",
            "sequential": [],
            "independent": [],
            "multiple": [],
        },
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(LOG_JSON_PATH, "w") as f:
        json.dump(log, f, indent=2)
    print(f"JSON log   → {LOG_JSON_PATH}")

    md = build_markdown(annotations)
    with open(LOG_MD_PATH, "w") as f:
        f.write(md)
    print(f"Markdown   → {LOG_MD_PATH}")

    print()
    print(f"Steps: {len(annotations)}  |  Duration: {duration}s  |  Tool changes: {log['summary']['tool_changes']}")
    print(f"Connector distribution: {log['summary']['connector_distribution']}")
    print(f"Penalties: {log['summary']['penalty_counts']}")


if __name__ == "__main__":
    main()
