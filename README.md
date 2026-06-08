# LivingScreen

**Benchmarking Living-Screen-Native GUI Agents on Short-Video Platforms**

[📄 Paper](https://arxiv.org/html/2606.04701v1) · [💻 Code & Data](https://github.com/BITHLP/LivingScreen) · **English** | [简体中文](README.zh-CN.md)

---

GUI agents today assume a **static screen** — the world is frozen between two actions. Real interfaces like short-video apps break this: content keeps playing, and a competent user must decide **what to watch and for how long**. We formalize this as **Living-Screen-Native GUI agents** and release **LivingScreen**, the first benchmark instantiating it on short-video platforms.

<p align="center"><img src="assets/intro.png" width="85%"></p>
<p align="center"><em>Living-screen-native agents (top-right) occupy the only quadrant combining an autonomously evolving environment with native agent action — a regime short-video platforms inhabit but existing benchmarks overlook.</em></p>

## Highlights

- **New setting.** A *living-screen-native* agent operates on a screen evolving in **continuous time** and actively decides **which visual slice to observe** — turning information acquisition into an endogenous, cost-bearing decision rather than a fixed data feed.
- **Faithful environment.** A browser-based replica of a modern short-video app, exposed to agents via a **Playwright** action API. Agents see only rendered screenshots / recordings — no DOM or raw video files.
- **Three-tier task suite.** **L1** atomic GUI action → **L2** cross-source understanding → **L3** closed-loop application.
- **Dual-axis metrics.** Jointly score **accuracy** and **information efficiency**.
- **499 tasks** over **1,528 unique videos**, avg **5.62 videos / feed**.

<p align="center"><img src="assets/data.png" width="100%"></p>

## Tasks & Metrics

| Tier | What it tests | Sub-categories |
|------|---------------|----------------|
| **L1 — GUI action** | Elementary GUI primitives | interaction (like / collect / comment / report), navigation (swipe / seek) |
| **L2 — Understanding** | Integrating evidence across a feed | contextual & event association, feature analysis, spatiotemporal aggregation, robust evaluation |
| **L3 — Application** | Closed-loop browse → decide → operate | fact-checking, content moderation, preference simulation |

| Metric | Meaning | Goal |
|--------|---------|------|
| **SR** Success Rate | Task accuracy (env-graded for L1/L3, option-match for L2) | ↑ |
| **NS** Number of Steps | Tool calls per episode (*operational* cost) | ↓ |
| **WR** Watch Ratio | Fraction of feed runtime recorded via `watch` (*observational* cost) | ↓ |

## Key Findings

- **Hard for frontier models.** No evaluated MLLM reaches the human cost-accuracy frontier.
- **Over- and under-observation.** The dominant failure mode: models systematically watch far more or far less than needed — a visual-channel analogue of over-/under-thinking. Humans cheaply *glance* first, then commit; models lack this scouting step.
- **A capability gap, not awareness.** Prompt interventions shift behavior but fail to improve SR — observation control is a genuine capability deficit.

This positions **observation control** as a new axis of GUI-agent capability, alongside action grounding and content understanding.

## Running

### 1. Environment

Python 3.10+ / Playwright (Chromium headless).

```bash
uv sync
uv run --no-project python -m playwright install chromium
```

### 2. Data

LivingScreen reuses publicly available short-video datasets. Place video files under
`static/data/<dataset_name>/` — the relative paths in `data/*.json` reference this folder.

| Dataset | Source |
|---|---|
| **FakeSV** | [github.com/ICTMCG/FakeSV](https://github.com/ICTMCG/FakeSV) |
| **LiveBot** | [github.com/lancopku/livebot](https://github.com/lancopku/livebot) |
| **Video-SafetyBench** | [huggingface.co/datasets/BAAI/Video-SafetyBench](https://huggingface.co/datasets/BAAI/Video-SafetyBench) |

At runtime `utils.feed2data` converts each task's raw metadata list into the feed rendered
by the Flask backend.

### 3. Model adapter (`llms.py`)

`main_threaded.py` looks up model classes from `llms.py` by name (string). Any class that
exposes a `chat(messages, tools=None, temperature=…, max_tokens=…, top_p=…, extra_body=…)`
method works — the return value is consumed by `agent.GUIAgent` exactly like an
`openai.chat.completions` response.

### 4. Run

```bash
uv run main_threaded.py -t cross_source_understanding --logs logs/cross_source_understanding --max-steps 30
```

Use `--sample-n <N>` for a quick smoke test. Each episode writes `<log_dir>/<task_id>/log.json`
(instruction, conversation, result) plus per-step screenshots, so you can trace behavior
afterwards.

## Citation

```bibtex
@article{livingscreen2026,
  title   = {Benchmarking Living-Screen-Native GUI Agents on Short-Video Platforms},
  journal = {arXiv preprint arXiv:2606.04701},
  year    = {2026}
}
```
