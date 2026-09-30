import json
import os
import subprocess
import sys
import tempfile

SEGMENTS_MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "data", "manifest", "segments_manifest.json")
PRUNED_MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "data", "manifest", "pruned_manifest.json")


def extract_thumbnail(clip_path, duration, out_path):
    midpoint = duration / 2
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(midpoint),
        "-i", clip_path,
        "-vframes", "1",
        "-q:v", "2",
        out_path,
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0


def open_file(path):
    """Open a file in the system default app (tested on macOS; Windows/Linux untested)."""
    if sys.platform == "win32":
        os.startfile(path)
        return
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([opener, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def prompt_user(step_num):
    while True:
        choice = input("  [y] keep  [s] skip  [r] review clip : ").strip().lower()
        if choice in ("y", "s", "r"):
            return choice
        print("  Please enter y, s, or r.")


def main():
    if not os.path.exists(SEGMENTS_MANIFEST_PATH):
        print(f"Segments manifest not found: {SEGMENTS_MANIFEST_PATH}")
        print("Run 02_segment.py first.")
        sys.exit(1)

    with open(SEGMENTS_MANIFEST_PATH) as f:
        manifest = json.load(f)

    clips = manifest["clips"]
    print(f"=== Clip review — {len(clips)} clips ===")
    print("For each clip: [y] keep  [s] skip  [r] open in video player")
    print()

    results = []

    with tempfile.TemporaryDirectory() as tmpdir:
        for clip in clips:
            n = clip["step"]
            clip_path = clip["clip_path"]
            duration = clip["duration_s"]

            print(f"Step {n:02d} — {duration:.1f}s  ({clip_path})")

            # Extract and open thumbnail
            thumb_path = os.path.join(tmpdir, f"step_{n:02d}_thumb.jpg")
            if extract_thumbnail(clip_path, duration, thumb_path):
                open_file(thumb_path)
            else:
                print("  (thumbnail extraction failed)")

            # Input loop — allow re-review
            while True:
                choice = prompt_user(n)
                if choice == "r":
                    open_file(clip_path)
                else:
                    break

            status = "keep" if choice == "y" else "skip"
            print(f"  → {status}")
            print()

            results.append({**clip, "status": status})

    kept = sum(1 for r in results if r["status"] == "keep")
    skipped = sum(1 for r in results if r["status"] == "skip")

    output = {
        "session_start": manifest.get("session_start"),
        "product": manifest.get("product"),
        "video_source": manifest.get("video_source"),
        "clips": results,
    }
    with open(PRUNED_MANIFEST_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Done — {kept} kept, {skipped} skipped")
    print(f"Pruned manifest → {PRUNED_MANIFEST_PATH}")


if __name__ == "__main__":
    main()
