# Disassembly annotation pipeline

A research prototype that processes a recorded video of a manual product teardown and generates structured disassembly annotations using Gemini's multimodal vision + audio model. Built for a TU Delft MSc graduation project on shared-use disassembly tools.

The annotation structure is based on the **Disassembly Map method** (De Fazio et al., 2021), capturing tool, connector type, force, reusability, and automation suitability per step.

See [DISASSEMBLY_PIPELINE_SPEC.md](DISASSEMBLY_PIPELINE_SPEC.md) for the full design rationale, or the [project page](https://floris-degroot.github.io/auto_disassembly_mapping/) for a step-by-step setup guide.

## How it works

You record yourself disassembling a product with OBS (top-down camera + audio) and use a **two-press SPACE pattern**: press SPACE when an action ends, narrate aloud what just happened, press SPACE when narration ends. The pipeline then:

1. Slices the video into one clip per step
2. Lets you keep/skip clips interactively
3. Sends each clip to Gemini for structured annotation (vision + speech)
4. Consolidates everything into a JSON + Markdown report

## Setup

```bash
pip install -r requirements.txt
brew install ffmpeg          # Windows: winget install Gyan.FFmpeg   Linux: sudo apt install ffmpeg
cp .env.example .env
```

I only tested this on macOS.

Then add your Gemini API key and OBS WebSocket password to `.env`:

- `GEMINI_API_KEY` — get one at [aistudio.google.com](https://aistudio.google.com)
- `OBS_WS_PASSWORD` — from OBS → Tools → WebSocket Server Settings

In OBS, also set your recording output folder to `data/raw/`.

## Running the pipeline

```bash
# 1. Start the hotkey logger (BEFORE starting OBS recording)
python 01_capture.py
#   asks for a product label first (Enter = default)
#   R     → starts OBS recording + timer
#   SPACE → end of action / end of narration (alternating)
#   ESC   → stops OBS, saves manifest

# 2. Cut the video into per-step clips
python 02_segment.py

# 3. Review clips, mark keep/skip
python 03_prune.py

# 4. Send clips to Gemini for annotation
python 04_analyze.py

# 5. Consolidate into a single log
python 05_consolidate.py
#   → data/output/disassembly_log.json
#   → data/output/disassembly_log.md

# 6. Archive the run (timestamped folder, clears working dirs)
python archive_run.py
```

## Variants

- **`04_analyze_no_narration.py`** — vision-only variant for controlled comparison. Trims clips to the action phase only and uses a narration-free prompt. For measuring how much the spoken annotation contributes to annotation quality. Writes to `data/output/no_narration/`, so it doesn't clash with the narrated run; consolidate it with `python 05_consolidate.py --no-narration`.

## Configuration

- **Product label** — entered when you start `01_capture.py` and saved in the manifest; the analysis scripts send it in the prompt and `05_consolidate.py` puts it in the log. Press Enter to use `DEFAULT_PRODUCT` from `config.py`. To change it after recording, edit `"product"` in `data/manifest/pruned_manifest.json`.
- `TARGET_COMPONENTS` (in `05_consolidate.py`) — primary/secondary components you're trying to recover
- `GEMINI_MODEL` (in `config.py`) — currently `gemini-2.5-flash` Cost for one long disassembly video was roughly around € 0.07

## Project structure

```
├── 01_capture.py              hotkey + OBS WebSocket logger
├── 02_segment.py              ffmpeg per-step segmentation
├── 03_prune.py                interactive keep/skip review
├── 04_analyze.py              Gemini vision + audio analysis
├── 04_analyze_no_narration.py vision-only variant
├── 05_consolidate.py          merges per-step JSON into log
├── archive_run.py             archives a run, clears working dirs
├── config.py                  shared config
├── prompts/                   Gemini prompt templates
├── data/                      working dirs (gitignored contents)
└── successful_runs/           archived runs (gitignored)
```

## Notes

- This is a research prototype, not production software.
- Each script is standalone and idempotent — re-run any stage without side effects.
- Run at your own risk, I dont know what might happen in your environment
- This is just a prototype, there is lots of room for improvement, but it did what it needed to do for me

## References

De Fazio, F., Bakker, C., Flipsen, B., & Balkenende, R. (2021). The Disassembly Map: A new method to enhance design for product repairability. *Journal of Cleaner Production, 320*, 128552. https://doi.org/10.1016/j.jclepro.2021.128552
