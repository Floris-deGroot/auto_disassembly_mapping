import json
import os
import sys
import time

from google import genai
from google.genai import types
from dotenv import load_dotenv
from config import GEMINI_MODEL, DEFAULT_PRODUCT

load_dotenv()

PRUNED_MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "data", "manifest", "pruned_manifest.json")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data", "output")
PROMPT_PATH = os.path.join(os.path.dirname(__file__), "prompts", "step_analysis.txt")

RATE_LIMIT_SLEEP = 5  # seconds between API calls
MAX_RETRIES = 3
RETRY_BACKOFF_S = [15, 45, 90]  # wait between retries


def load_prompt():
    with open(PROMPT_PATH) as f:
        return f.read()


def strip_fences(text):
    """Remove markdown code fences if Gemini wraps the JSON anyway."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    return text.strip()


def wait_for_file(client, video_file):
    print("    Waiting for Gemini to process upload...", end=" ", flush=True)
    while video_file.state.name == "PROCESSING":
        time.sleep(2)
        video_file = client.files.get(name=video_file.name)
    if video_file.state.name == "FAILED":
        raise RuntimeError(f"File processing failed: {video_file.name}")
    print("ready.")
    return video_file


def analyze_clip(client, model_name, clip, prompt_template, product):
    n = clip["step"]
    clip_path = clip["clip_path"]
    duration = clip["duration_s"]
    action_split = clip["action_split_s"]

    prompt = (prompt_template
        .replace("<<step_number>>", str(n))
        .replace("<<action_split_s>>", str(round(action_split, 1)))
        .replace("<<duration_s>>", str(round(duration, 1)))
        .replace("<<product>>", product)
    )

    print(f"  Uploading {os.path.basename(clip_path)} ...", end=" ", flush=True)
    video_file = client.files.upload(file=clip_path)
    print("uploaded.")

    video_file = wait_for_file(client, video_file)

    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            print(f"    Sending to Gemini (attempt {attempt + 1}/{MAX_RETRIES}) ...", end=" ", flush=True)
            response = client.models.generate_content(
                model=model_name,
                contents=[video_file, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                ),
            )
            print("done.")
            return video_file, response.text
        except Exception as e:
            msg = str(e)
            transient = any(s in msg for s in ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "high demand"))
            last_err = e
            if transient and attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF_S[attempt]
                print(f"transient error, retrying in {wait}s...")
                time.sleep(wait)
                continue
            print("failed.")
            raise

    raise last_err


def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY not set. Add it to your .env file.")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    if not os.path.exists(PRUNED_MANIFEST_PATH):
        print(f"Pruned manifest not found: {PRUNED_MANIFEST_PATH}")
        print("Run 03_prune.py first.")
        sys.exit(1)

    with open(PRUNED_MANIFEST_PATH) as f:
        manifest = json.load(f)

    product = manifest.get("product") or DEFAULT_PRODUCT
    prompt_template = load_prompt()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    clips = [c for c in manifest["clips"] if c.get("status") == "keep"]
    skipped = len(manifest["clips"]) - len(clips)
    print(f"=== Gemini analysis — {len(clips)} clips to process ({skipped} skipped) ===")
    print(f"Product: {product}")
    print()

    uploaded_files = []
    success_count = 0
    fail_count = 0

    for i, clip in enumerate(clips):
        n = clip["step"]
        out_path = os.path.join(OUTPUT_DIR, f"step_{n:02d}_annotation.json")

        if os.path.exists(out_path):
            print(f"Step {n:02d} ({i + 1}/{len(clips)}) — already annotated, skipping")
            print()
            continue

        print(f"Step {n:02d} ({i + 1}/{len(clips)})")

        try:
            video_file, response_text = analyze_clip(client, GEMINI_MODEL, clip, prompt_template, product)
            uploaded_files.append(video_file)

            annotation = json.loads(strip_fences(response_text))
            annotation["step_number"] = n

            out_path = os.path.join(OUTPUT_DIR, f"step_{n:02d}_annotation.json")
            with open(out_path, "w") as f:
                json.dump(annotation, f, indent=2)

            print(f"    Saved → {out_path}")
            success_count += 1

        except json.JSONDecodeError as e:
            print(f"    ERROR: invalid JSON from Gemini — {e}")
            raw_path = os.path.join(OUTPUT_DIR, f"step_{n:02d}_raw_response.txt")
            with open(raw_path, "w") as f:
                f.write(response_text)
            print(f"    Raw response saved → {raw_path}")
            fail_count += 1

        except Exception as e:
            print(f"    ERROR: {e}")
            fail_count += 1

        if i < len(clips) - 1:
            print(f"    Rate limit pause ({RATE_LIMIT_SLEEP}s)...")
            time.sleep(RATE_LIMIT_SLEEP)

        print()

    # Clean up uploaded files
    if uploaded_files:
        print(f"Cleaning up {len(uploaded_files)} uploaded file(s)...", end=" ", flush=True)
        for vf in uploaded_files:
            try:
                client.files.delete(name=vf.name)
            except Exception as e:
                print(f"\n  Warning: could not delete {vf.name}: {e}")
        print("done.")

    print()
    print(f"Finished — {success_count} succeeded, {fail_count} failed")
    print(f"Annotations in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
