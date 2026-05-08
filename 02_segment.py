import glob
import json
import os
import subprocess
import sys

MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "data", "manifest", "step_manifest.json")
CLIPS_DIR = os.path.join(os.path.dirname(__file__), "data", "clips")
RAW_DIR = os.path.join(os.path.dirname(__file__), "data", "raw")
SEGMENTS_MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "data", "manifest", "segments_manifest.json")


def find_video():
    mp4s = glob.glob(os.path.join(RAW_DIR, "*.mp4"))
    if not mp4s:
        print(f"No .mp4 found in {RAW_DIR}")
        sys.exit(1)
    if len(mp4s) > 1:
        print(f"Multiple .mp4s found, using most recent: {sorted(mp4s)[-1]}")
    return sorted(mp4s)[-1]


def cut_clip(input_path, start, end, output_path, re_encode=False):
    if re_encode:
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-ss", str(start),
            "-to", str(end),
            output_path,
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-ss", str(start),
            "-to", str(end),
            "-c", "copy",
            "-avoid_negative_ts", "1",
            output_path,
        ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def main():
    # Resolve input video
    if len(sys.argv) > 1:
        video_path = sys.argv[1]
        if not os.path.exists(video_path):
            print(f"File not found: {video_path}")
            sys.exit(1)
    else:
        video_path = find_video()

    print(f"Video: {video_path}")

    # Load manifest
    if not os.path.exists(MANIFEST_PATH):
        print(f"Manifest not found: {MANIFEST_PATH}")
        sys.exit(1)

    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    steps = manifest["steps"]
    print(f"Manifest loaded — {len(steps)} steps")

    os.makedirs(CLIPS_DIR, exist_ok=True)

    clips = []
    for step in steps:
        n = step["step"]
        start = step["action_start_s"]
        action_end = step["action_end_s"]
        end = step["narration_end_s"]
        duration = round(end - start, 3)
        action_duration = round(action_end - start, 3)

        clip_name = f"step_{n:02d}.mp4"
        clip_path = os.path.join(CLIPS_DIR, clip_name)

        print(f"  Step {n}: {start:.1f}s → {end:.1f}s ({duration:.1f}s total, action ends at +{action_duration:.1f}s) ...", end=" ", flush=True)

        success = cut_clip(video_path, start, end, clip_path)
        if not success:
            print("keyframe issue, retrying with re-encode ...", end=" ", flush=True)
            success = cut_clip(video_path, start, end, clip_path, re_encode=True)

        if success:
            print("done")
            clips.append({
                "step": n,
                "clip_path": clip_path,
                "action_start_s": start,
                "action_end_s": action_end,
                "narration_end_s": end,
                "duration_s": duration,
                "action_split_s": action_duration,  # offset within clip where narration begins
                "status": "keep",
            })
        else:
            print("FAILED — skipping")

    # Write segments manifest
    output = {
        "session_start": manifest.get("session_start"),
        "video_source": video_path,
        "clips": clips,
    }
    with open(SEGMENTS_MANIFEST_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nDone — {len(clips)}/{len(steps)} clips written to {CLIPS_DIR}")
    print(f"Segments manifest → {SEGMENTS_MANIFEST_PATH}")


if __name__ == "__main__":
    main()
