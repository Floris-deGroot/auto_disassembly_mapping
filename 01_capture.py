import json
import os
import time
from datetime import datetime
from pynput import keyboard
import obsws_python as obs

from config import OBS_HOST, OBS_PORT, OBS_PASSWORD, DEFAULT_PRODUCT

MANIFEST_DIR = os.path.join(os.path.dirname(__file__), "data", "manifest")
MANIFEST_PATH = os.path.join(MANIFEST_DIR, "step_manifest.json")

start_time = None
session_start_iso = None
product = DEFAULT_PRODUCT
steps = []
phase = "action"  # alternates: "action" -> "narration" -> "action" ...
step_number = 0
current_action_start = 0.0
current_action_end = None
recording = False
obs_client = None


def elapsed():
    return time.monotonic() - start_time


def save_manifest():
    os.makedirs(MANIFEST_DIR, exist_ok=True)
    data = {
        "session_start": session_start_iso,
        "product": product,
        "steps": steps,
    }
    with open(MANIFEST_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\nManifest saved → {MANIFEST_PATH}  ({len(steps)} complete steps)")


def on_press(key):
    global phase, step_number, current_action_start, current_action_end
    global start_time, session_start_iso, recording

    # R — start recording
    if not recording and hasattr(key, "char") and key.char == "r":
        try:
            obs_client.start_record()
        except Exception as e:
            print(f"OBS error: {e}")
            return

        start_time = time.monotonic()
        session_start_iso = datetime.now().isoformat(timespec="seconds")
        recording = True
        print("  OBS recording started.")
        print()
        print("[RECORDING ACTION — press SPACE when step is done]")
        return

    # Only respond to SPACE/ESC once recording has started
    if not recording:
        return

    if key == keyboard.Key.space:
        t = elapsed()

        if phase == "action":
            current_action_end = t
            step_number += 1
            phase = "narration"
            print(f"\n  Step {step_number}: action ended at {t:.1f}s")
            print("[NARRATE NOW — press SPACE when done speaking]")

        else:
            steps.append({
                "step": step_number,
                "action_start_s": round(current_action_start, 3),
                "action_end_s": round(current_action_end, 3),
                "narration_end_s": round(t, 3),
            })
            print(f"  Step {step_number}: narration ended at {t:.1f}s — step complete")
            current_action_start = t
            phase = "action"
            print("\n[RECORDING ACTION — press SPACE when step is done]")

    elif key == keyboard.Key.esc:
        try:
            obs_client.stop_record()
            print("  OBS recording stopped.")
        except Exception as e:
            print(f"OBS error stopping recording: {e}")
        save_manifest()
        return False  # stops the listener


def main():
    global obs_client, product

    print("=== Disassembly step logger ===")
    product = input(f"Product label [{DEFAULT_PRODUCT}]: ").strip() or DEFAULT_PRODUCT
    print(f"Product: {product}")
    print()
    print(f"Connecting to OBS at {OBS_HOST}:{OBS_PORT} ...", end=" ", flush=True)
    try:
        obs_client = obs.ReqClient(host=OBS_HOST, port=OBS_PORT, password=OBS_PASSWORD)
        print("connected.")
    except Exception as e:
        print(f"\nFailed to connect to OBS: {e}")
        print("Make sure OBS is open and WebSocket server is enabled.")
        return

    print()
    print("R     = start OBS recording + timer")
    print("SPACE = mark end of action / end of narration")
    print("ESC   = stop OBS recording, save manifest, quit")
    print()
    print("[Press R to start recording]")

    with keyboard.Listener(on_press=on_press) as listener:
        try:
            listener.join()
        except KeyboardInterrupt:
            listener.stop()
            if recording:
                try:
                    obs_client.stop_record()
                except Exception:
                    pass
            save_manifest()


if __name__ == "__main__":
    main()
