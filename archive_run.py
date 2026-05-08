import glob
import json
import os
import shutil
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(__file__)
RUNS_DIR = os.path.join(BASE_DIR, "successful_runs")
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
CLIPS_DIR = os.path.join(BASE_DIR, "data", "clips")
MANIFEST_DIR = os.path.join(BASE_DIR, "data", "manifest")
OUTPUT_DIR = os.path.join(BASE_DIR, "data", "output")
PRUNED_MANIFEST_PATH = os.path.join(MANIFEST_DIR, "pruned_manifest.json")


def clean_dir(path):
    """Delete all files inside path, but keep the directory itself."""
    if not os.path.exists(path):
        return 0
    count = 0
    for entry in os.listdir(path):
        full = os.path.join(path, entry)
        if os.path.isfile(full):
            os.remove(full)
            count += 1
        elif os.path.isdir(full):
            shutil.rmtree(full)
            count += 1
    return count


def main():
    if not os.path.exists(PRUNED_MANIFEST_PATH):
        print(f"Pruned manifest not found: {PRUNED_MANIFEST_PATH}")
        sys.exit(1)

    with open(PRUNED_MANIFEST_PATH) as f:
        manifest = json.load(f)

    folder_name = datetime.now().strftime("%Y_%m_%d_%H%M_Disassembly")
    target = os.path.join(RUNS_DIR, folder_name)
    os.makedirs(target, exist_ok=True)
    print(f"Archiving to: {target}")

    # Original recorded video
    video_source = manifest.get("video_source")
    if video_source and os.path.exists(video_source):
        shutil.copy2(video_source, target)
        print(f"  Copied video: {os.path.basename(video_source)}")

    # Per-step clips
    if os.path.exists(CLIPS_DIR) and os.listdir(CLIPS_DIR):
        clips_dest = os.path.join(target, "clips")
        shutil.copytree(CLIPS_DIR, clips_dest, dirs_exist_ok=True)
        print(f"  Copied {len(os.listdir(clips_dest))} clip(s)")

    # Manifests
    manifests_dest = os.path.join(target, "manifest")
    if os.path.exists(MANIFEST_DIR) and os.listdir(MANIFEST_DIR):
        shutil.copytree(MANIFEST_DIR, manifests_dest, dirs_exist_ok=True)
        print(f"  Copied {len(os.listdir(manifests_dest))} manifest file(s)")

    # All outputs (per-step annotations + consolidated log)
    output_dest = os.path.join(target, "output")
    if os.path.exists(OUTPUT_DIR) and os.listdir(OUTPUT_DIR):
        shutil.copytree(OUTPUT_DIR, output_dest, dirs_exist_ok=True)
        print(f"  Copied {len(os.listdir(output_dest))} output file(s)")

    # Clean working directories so next run starts fresh
    print()
    print("Cleaning working directories...")
    for label, path in [("raw", RAW_DIR), ("clips", CLIPS_DIR), ("manifest", MANIFEST_DIR), ("output", OUTPUT_DIR)]:
        n = clean_dir(path)
        print(f"  {label}: removed {n} item(s)")

    print()
    print("Done. Working dirs are clean — ready for the next run.")


if __name__ == "__main__":
    main()
