# Disassembly annotation pipeline — project spec

## Context

This is a research prototype for a TU Delft MSc graduation project on shared-use disassembly tools. The pipeline processes a recorded video of a manual product teardown (disposable vape, possibly electric toothbrush) and attempts to automatically generate structured disassembly annotations using an LLM vision model.

The core research question this prototype explores: **"How much disassembly knowledge can transfer through observation alone?"** — the gap between what the pipeline captures and what it misses motivates the design of physical tools with embedded sensing.

The annotation structure is based on the **Disassembly Map method** (De Fazio et al., 2021), which documents disassembly using four parameters: disassembly depth/sequence, disassembly time, type of tools, and fastener reusability.

## Architecture overview

```
[Record: OBS + hotkey logger]
         ↓
   .mp4 + step_manifest.json
         ↓
[Segment by step markers]  →  [Manual pruning / review]
         ↓
    per-step video clips
      ↙          ↘
[Gemini vision     [Acoustic peak
 + speech analysis]  detection] (optional)
      ↘          ↙
[Consolidate into step log]
         ↓
  structured JSON output
         ↓
[Human review + correction]
```

## Recording workflow (two-press pattern)

The user records themselves disassembling a product using OBS (top-down camera + audio). The hotkey logger runs alongside OBS and uses a **two-press SPACE pattern** to create clean segments:

1. **Perform the disassembly action** (camera captures the physical work)
2. **Press SPACE** → marks the end of the action phase
3. **Narrate observations** about the step just completed (connector type, tool, force, etc.)
4. **Press SPACE** → marks the end of the narration phase, start of next action

This produces alternating segment types per step:

- **Action segment**: the physical disassembly footage (video-primary)
- **Narration segment**: spoken annotation (audio-primary)

Both segments are valuable: the action footage feeds visual analysis, the narration feeds transcription. Gemini receives both together per step.

## Tech stack

- **Python 3.10+** (standard library + packages below)
- **ffmpeg** — video/audio segmentation (called via subprocess)
- **pynput** — keyboard listener for the hotkey logger
- **obsws-python** — OBS WebSocket client for remote record control
- **python-dotenv** — loads `.env` secrets into environment variables
- **google-genai** — Gemini API for vision + audio analysis (use `google-generativeai` package)
- **scipy** — optional, for acoustic peak detection
- **Gemini model**: use `gemini-2.0-flash` (multimodal: video + audio input, good balance of speed and capability)

The user has a Google AI Studio Pro subscription. API key will be set as environment variable `GEMINI_API_KEY`.

## Project structure

```
disassembly-pipeline/
├── README.md
├── requirements.txt
├── .env.example              # GEMINI_API_KEY, OBS_WS_PASSWORD
├── config.py                 # shared config (paths, model name, etc.)
├── 01_capture.py             # hotkey step logger (runs during recording)
├── 02_segment.py             # splits video by step manifest timestamps
├── 03_prune.py               # interactive review of clips (keep/skip)
├── 04_analyze.py             # sends clips to Gemini for annotation
├── 05_consolidate.py         # merges per-step annotations into full log
├── 06_peak_detect.py         # optional: acoustic transient detection
├── prompts/
│   └── step_analysis.txt     # the Gemini prompt template
├── data/
│   ├── raw/                  # user places .mp4 here
│   ├── manifest/             # step_manifest.json output
│   ├── clips/                # segmented per-step clips
│   └── output/               # final structured annotations
└── templates/
    └── disassembly_log.json  # empty template showing output schema
```

## Component specifications

### 01_capture.py — Hotkey step logger

**Purpose:** Listen for key presses during recording, control OBS via WebSocket, and log timestamps with phase labels.

**Behavior:**

- On start, connects to OBS WebSocket (`obsws_python`); credentials loaded from `.env` via `python-dotenv`
- **R** → starts OBS recording and the internal timer simultaneously
- Uses a **two-press alternating pattern** (only active after R):
    - First SPACE press → logs timestamp with phase `"end_action"` (physical step just finished)
    - Second SPACE press → logs timestamp with phase `"end_narration"` (spoken annotation just finished)
    - Pattern repeats: action, narration, action, narration...
- Display current state in terminal: `"[RECORDING ACTION — press SPACE when step is done]"` vs `"[NARRATE NOW — press SPACE when done speaking]"`
- On ESC or Ctrl+C, stop OBS recording, save the manifest and exit

**OBS WebSocket config** (set in `.env`): `OBS_WS_PASSWORD`. Host and port default to `localhost:4455` in `config.py`.

**Output:** `data/manifest/step_manifest.json`

```json
{
  "session_start": "2026-04-24T14:30:00",
  "steps": [
    {
      "step": 1,
      "action_start_s": 0.0,
      "action_end_s": 34.2,
      "narration_end_s": 48.7
    },
    {
      "step": 2,
      "action_start_s": 48.7,
      "action_end_s": 67.8,
      "narration_end_s": 81.3
    }
  ]
}
```

Each step has three timestamps: action starts (= previous step's narration end, or 0.0 for step 1), action ends (first SPACE), narration ends (second SPACE). The narration_end of step N equals the action_start of step N+1.

**Key detail:** Use `time.monotonic()` for timing, not wall clock. Convert to seconds elapsed since start.

---

### 02_segment.py — Video segmentation

**Purpose:** Split the recorded .mp4 into per-step clips using the manifest timestamps. Each step produces **one combined clip** (action + narration together) for Gemini analysis.

**Input:**

- Path to .mp4 file (argument or auto-detect from `data/raw/`)
- `data/manifest/step_manifest.json`

**Behavior:**

- For each step, extract one clip spanning from `action_start_s` to `narration_end_s`
- This combined clip contains both the action footage and the narration audio — Gemini will process both
- Name clips sequentially: `step_01.mp4`, `step_02.mp4`, etc.
- Log the total duration and the action/narration split point (action_end_s relative to clip start) in the output manifest — this lets downstream analysis know where the action ends and narration begins within each clip

**ffmpeg command pattern:**

```bash
ffmpeg -i input.mp4 -ss {action_start} -to {narration_end} -c copy -avoid_negative_ts 1 step_XX.mp4
```

Use `-c copy` for speed (no re-encoding). If this causes keyframe issues, fall back to re-encoding.

**Output:** Clips in `data/clips/` + updated manifest with clip paths, durations, and action/narration split points.

---

### 03_prune.py — Interactive clip review

**Purpose:** Let the user quickly review each clip and decide whether to include it in analysis.

**Behavior:**

- For each clip, display: step number, duration, and a thumbnail (extract frame at 50% with ffmpeg)
- Thumbnails are saved temporarily and displayed in terminal using a simple approach:
    - Option A (preferred): Open thumbnail images in the system default viewer one at a time
    - Option B: Just print the filename and duration, user decides based on memory
- User inputs `y` (keep), `s` (skip), or `r` (review — opens the clip in default video player)
- Produce a `pruned_manifest.json` that only includes kept clips

**Output:** `data/manifest/pruned_manifest.json` with a `status` field per step ("keep" or "skip").

---

### 04_analyze.py — Gemini vision + audio analysis

**Purpose:** Send each kept clip to Gemini for structured annotation.

**Behavior:**

- For each clip in the pruned manifest:
    1. Upload the video clip to Gemini using the File API (for files > inline limit)
    2. Send the uploaded file reference with the analysis prompt
    3. Parse the structured JSON response
    4. Save per-step annotation to `data/output/step_XX_annotation.json`
- Include rate limiting (sleep between calls) to stay within API limits
- Handle failures gracefully — log errors, continue to next clip

**Gemini API usage pattern:**

```python
import google.generativeai as genai

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.0-flash")

# Upload video file
video_file = genai.upload_file(path="data/clips/step_01.mp4")

# Wait for processing
import time
while video_file.state.name == "PROCESSING":
    time.sleep(2)
    video_file = genai.get_file(video_file.name)

# Generate analysis
response = model.generate_content(
    [video_file, prompt_text],
    generation_config=genai.GenerationConfig(
        response_mime_type="application/json"
    )
)
```

**Important:** After all steps are processed, clean up uploaded files with `genai.delete_file()`.

---

### Prompt template (prompts/step_analysis.txt)

This is the core prompt sent with each video clip. It should instruct Gemini to:

1. **Watch the video** and describe the disassembly action performed
2. **Listen to the audio** and transcribe any spoken narration by the operator
3. **Produce structured JSON** with the following fields:

```json
{
  "step_number": 1,
  "description": "Free-text description of what happened in this step",
  "narration_transcript": "What the operator said, if anything",

  "component_removed": {
    "name": "e.g., top housing cover",
    "description": "brief description if identifiable"
  },

  "tool_observed": {
    "type": "hands | spudger | pliers | screwdriver | heat_gun | knife | other | unidentifiable",
    "confidence": "high | medium | low"
  },

  "action_type": {
    "primary": "pulling | prying | twisting | cutting | unscrewing | peeling | sliding | other",
    "confidence": "high | medium | low"
  },

  "connector_type": {
    "type": "snap_fit | friction_fit | adhesive | screw | weld | crimp | unknown",
    "confidence": "high | medium | low",
    "reasoning": "Why this connector type was identified"
  },

  "force_estimate": {
    "level": "low | moderate | high | unknown",
    "visual_cues": "What visual evidence suggests this force level",
    "confidence": "high | medium | low"
  },

  "connector_survived": {
    "reusable": true,
    "notes": "e.g., snap-fit tab broke off"
  },

  "penalties": {
    "product_manipulation": false,
    "hidden_connector": false,
    "uncommon_tool": false,
    "non_reusable_connector": false
  },

  "automation_suitability": {
    "rating": "straightforward | feasible_with_sensing | very_difficult | impossible_without_redesign",
    "reasoning": "Why this rating, from visual observation",
    "confidence": "high | medium | low"
  },

  "acoustic_events": [
    {
      "timestamp_in_clip_s": 4.2,
      "description": "Sharp click sound, possibly snap-fit release"
    }
  ],

  "model_uncertainties": [
    "Could not determine if connector was adhesive or friction fit",
    "Force level unclear from video alone"
  ]
}
```

The prompt should emphasize:

- **Always include a confidence field** — knowing where the model is uncertain is as valuable as the annotation itself
- **Transcribe narration first** — the operator's spoken annotations are the most reliable data source, prioritize integrating those
- **Separate visual observation from inference** — if the model infers "adhesive" because it saw peeling motion, say so explicitly
- **Flag what's invisible** — force, haptic feedback, internal connector geometry are expected blind spots. Name them.

Draft the prompt to be clear and specific. Include the JSON schema in the prompt. Tell the model to respond ONLY with valid JSON, no markdown formatting.

---

### 05_consolidate.py — Merge into full disassembly log

**Purpose:** Combine all per-step annotations into a single structured document.

**Behavior:**

- Load all `step_XX_annotation.json` files in order
- Produce a unified disassembly log with:
    - Session metadata (date, product, target components)
    - Ordered list of all steps with their annotations
    - Summary statistics: total steps, tool changes, connector type distribution, penalty counts
    - A dependency structure section (initially empty — filled by human review)
- Optionally: send the full sequence to Gemini for a second-pass analysis asking it to infer step dependencies (sequential vs. independent) based on the descriptions

**Output:** `data/output/disassembly_log.json` and a human-readable `disassembly_log.md`

The markdown output should be formatted as a table for easy scanning:

```markdown
| Step | Component | Connector | Tool | Force | Reusable | Robot difficulty |
|------|-----------|-----------|------|-------|----------|-----------------|
| 1    | Top cap   | friction  | hands| low   | yes      | straightforward |
| 2    | Housing   | adhesive  | spudger | high | no    | very difficult  |
...
```

---

### 06_peak_detect.py — Acoustic event detection (optional)

**Purpose:** Detect sharp transient sounds in the audio track that may indicate mechanical events (snap-fit release, cracking, tool impact).

**Behavior:**

- Extract audio from each clip: `ffmpeg -i clip.mp4 -vn -acodec pcm_s16le -ar 16000 clip.wav`
- Load with scipy.io.wavfile
- Compute short-time energy envelope (window ~20ms)
- Use `scipy.signal.find_peaks` with prominence threshold to detect transients
- Classify peaks roughly by spectral characteristics:
    - High-frequency, short duration → snap/click
    - Lower-frequency, longer → crack/break
    - Very short, any frequency → tool impact/drop
- Output: list of acoustic events with timestamps for each clip

This is a nice-to-have. Build it last, keep it simple. Even just logging "transient detected at t=X.Xs" per clip is useful — the human or Gemini can interpret.

**Output:** `data/output/acoustic_events.json`

---

## Output schema (disassembly_log.json template)

```json
{
  "metadata": {
    "product": "Disposable vape [brand/model if known]",
    "date": "2026-04-24",
    "operator": "Floris",
    "target_components": {
      "primary": ["Lithium battery"],
      "secondary": ["PCB", "Charging port"]
    },
    "total_steps": 0,
    "total_duration_s": 0,
    "video_source": "filename.mp4"
  },
  "steps": [],
  "summary": {
    "tool_changes": 0,
    "connector_distribution": {},
    "penalty_counts": {},
    "automation_suitability_distribution": {},
    "model_confidence_summary": {}
  },
  "dependencies": {
    "note": "To be filled during human review",
    "sequential": [],
    "independent": [],
    "multiple": []
  }
}
```

## Running the pipeline

```bash
# 1. Start the hotkey logger before you start OBS recording
python 01_capture.py

# 2. After recording, place the .mp4 in data/raw/ then segment
python 02_segment.py data/raw/teardown.mp4

# 3. Review and prune clips
python 03_prune.py

# 4. Run Gemini analysis on kept clips
python 04_analyze.py

# 5. Consolidate into final output
python 05_consolidate.py

# Optional: acoustic peak detection
python 06_peak_detect.py
```

## Important notes for implementation

1. **Keep it simple.** This is a research prototype, not production software. Prioritize working code over elegant architecture. No frameworks, no complex abstractions.
    
2. **Each script is standalone and idempotent.** You should be able to re-run any script without side effects. Scripts read from the previous stage's output directory and write to their own.
    
3. **Error handling matters for the Gemini calls.** The API can fail, rate-limit, or return malformed responses. Wrap each call in try/except, log failures, and continue. A partial result is better than a crash.
    
4. **The prompt is the most important artifact.** Spend time crafting the Gemini prompt in `prompts/step_analysis.txt`. The quality of the structured output depends almost entirely on prompt quality.
    
5. **Print progress to terminal.** Each script should print what it's doing so the user can follow along. Use simple print statements, not logging frameworks.
    
6. **The human review step is intentionally manual.** Don't try to automate the dependency analysis or force estimation correction. The point of the prototype is to show what automation CAN and CANNOT capture — the human-filled gaps are a research finding, not a bug.
    
7. **Git-friendly.** Include a `.gitignore` that excludes `data/raw/`, `data/clips/`, `.env`, and any large files. The code, prompts, and output JSONs should be version-controlled.