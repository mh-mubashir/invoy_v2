# Invoy VLM Experiment Report
## Comparing Qwen2-VL 2B, Qwen2.5-VL 3B, and Qwen2-VL 7B for Screen Activity Tracking

---

## 1. Overview

This report evaluates three local Vision Language Models (VLMs) on the task of **desktop activity tracking**: given a sequence of 136 screenshots captured from a live workstation, each model produces (a) a natural-language description of the current activity and (b) a change description that explains what shifted since the previous frame.

The three models tested are:

| Model | Family | Parameters | Run label |
|-------|--------|-----------|-----------|
| **Qwen2-VL 2B** | Qwen2-VL | ~2B | `run_qwen2vl2b_gpu` |
| **Qwen2.5-VL 3B** | Qwen2.5-VL (newer arch) | ~3B | `run_qwen25vl3b_gpu` |
| **Qwen2-VL 7B** | Qwen2-VL | ~7B | `run_qwen2vl7b_gpu` |

The 7B model is treated as a **pseudo ground-truth reference** throughout. All three models processed the same 136 screenshot frames; no human annotations were used.

---

## 2. Evaluation Methodology

Since no human-labeled ground truth exists, evaluation relies on four complementary signal types:

### 2.1 Proxy Quality Metrics (heuristic, per frame)
Computed from the raw text output of each model:

| Metric | What it measures |
|--------|-----------------|
| **Token length** | How verbose the description is |
| **Specificity score** | Fraction of tokens that are concrete identifiers (app names, file extensions, UI terms) |
| **Hedging rate** | Fraction of tokens that express uncertainty (e.g. "maybe", "appears", "seems") |
| **Action-verb presence** | Whether the change description contains a concrete action verb |
| **State-transition language** | Whether the change description uses transition words ("changed", "moved from", "now") |
| **Vagueness rate** | Fraction of vague filler words in the change description |

### 2.2 Proxy Scores (0–5 scale)
Four aggregate dimensions derived from the metrics above:

| Score | Formula |
|-------|---------|
| **Activity Fidelity** | 60% specificity + 40% (1 − hedging) |
| **Activity Specificity** | Directly from specificity score × 5 |
| **Change Correctness** | 35% action-verb + 35% state-transition + 30% drift-alignment |
| **Change Usefulness** | 50% drift-alignment + 50% (1 − vagueness) |

### 2.3 Agreement with 7B Reference
For each frame, the 2B and 3B outputs are compared to the 7B output using:
- **TF-IDF cosine similarity** (captures overall semantic proximity)
- **ROUGE-L F1** (captures longest common sub-sequence of tokens)
- **Jaccard similarity** (set overlap of content tokens)

### 2.4 Drift-Alignment
A temporal signal: the visual drift between consecutive frames (1 − cosine similarity of TF-IDF representations) is computed per model. A model "aligns" on a given frame if its decision to report a change matches whether the visual drift exceeds the median drift. This is a proxy for **change detection recall**.

---

## 3. Results

### 3.1 Aggregate Metrics Table

| Metric | Qwen2-VL 2B | Qwen2.5-VL 3B | Qwen2-VL 7B |
|--------|:-----------:|:-------------:|:-----------:|
| **Token length (avg)** | 37.2 | 25.9 | **44.7** |
| **Specificity score** | **0.038** | 0.016 | 0.033 |
| **Hedging rate** | 0.013 | 0.010 | **0.006** |
| **Activity Fidelity /5** | **2.09** | 2.03 | 2.09 |
| **Activity Specificity /5** | **0.190** | 0.081 | 0.165 |
| **Change Correctness /5** | **2.80** | 2.58 | 2.68 |
| **Change Usefulness /5** | 3.71 | 3.75 | **3.88** |
| **Drift Alignment** | 48.5% | 50.0% | **55.1%** |
| **Cosine vs 7B** | **0.338** | 0.327 | — |
| **ROUGE-L vs 7B** | **0.292** | 0.285 | — |
| **Jaccard vs 7B** | **0.235** | 0.226 | — |

Bold = best value per row.

---

### 3.2 Key Findings

#### Finding 1: 7B produces the richest descriptions
The 7B model outputs an average of **44.7 tokens** per frame — 20% more than 2B and 73% more than 3B. Its descriptions tend to include richer context: not just the active application but what task the user appears to be doing within it. This is consistent with its larger capacity and is the primary quality advantage of the 7B model.

#### Finding 2: 2B beats 7B on raw specificity
Counterintuitively, the 2B model has the **highest specificity score (0.038)** — higher than 7B (0.033). This happens because smaller models often rely on surface-level keyword extraction rather than coherent reasoning: they latch on to visible file names, application names, and URLs very literally. The 7B model uses more fluent, narrative language which sometimes dilutes the keyword density even when the descriptions are semantically richer.

#### Finding 3: 3B underperforms despite newer architecture
Despite being from the newer Qwen2.5-VL family, the 3B model consistently scores lowest across most dimensions:
- Lowest token length (25.9 — half that of 7B)
- Lowest specificity (0.016 — less than half of 2B)
- Lowest change correctness (2.58/5)
- Lowest agreement with 7B on all three similarity metrics

This suggests that **architecture improvements in Qwen2.5 do not compensate for the parameter count reduction at this scale**, at least for this task. The 3B model tends to produce shorter, more abstract summaries that miss specific application and file context.

#### Finding 4: Hedging decreases as model size increases
The hedging rate follows a clear size-ordered pattern: 2B (0.013) > 3B (0.010) > 7B (0.006). Larger models express more confident, declarative descriptions. Smaller models compensate for uncertainty by using qualifiers ("appears to be", "seems like"), which also hurts fidelity scores.

#### Finding 5: Change detection is universally weak
All three models struggle with drift-alignment — their change detection aligns with actual visual drift only about **48–55% of the time**. No model significantly outperforms random on this metric. This is the most important takeaway: detecting *when* a meaningful task switch occurs is harder than describing *what* is currently on screen, and none of these model sizes are sufficient for reliable change detection from screenshots alone.

#### Finding 6: All models diverge significantly from each other
The pairwise cosine similarity between any two models averages only **0.31–0.34** — far below what would indicate consistent interpretation. Even the two smaller models (2B and 3B) only agree at 0.315 cosine similarity with each other, despite observing identical screenshots. This reflects the open-ended nature of the task: there is no single "correct" description, and models decompose the same visual scene into very different textual framings.

#### Finding 7: 2B is marginally closer to 7B than 3B
Across all three similarity metrics (cosine, ROUGE-L, Jaccard), the 2B model is slightly closer to the 7B reference than 3B is. The margin is small (e.g. cosine 0.338 vs 0.327) but consistent. This suggests that models within the **same family (Qwen2-VL)** share more stylistic and vocabulary patterns than models from different generations, even when the latter is larger.

---

## 4. Visualizations Summary

All plots are saved to `eval_reports/three_model_plots/`.

| Plot | File | What to look for |
|------|------|-----------------|
| Quality metrics bar | `01_quality_metrics_bar.png` | 2B's higher specificity vs 3B's conciseness gap |
| Proxy scores bar | `02_proxy_scores_bar.png` | 7B leads on change usefulness; 2B leads on specificity |
| Cosine vs 7B time series | `03_cosine_vs_7b_timeseries.png` | Both smaller models track 7B similarly; neither consistently better |
| Activity length violin | `04_activity_length_violin.png` | 3B has a tight low-token distribution; 7B is spread high |
| Specificity box plot | `05_specificity_box.png` | 2B has the highest and widest specificity range |
| Drift time series | `06_drift_timeseries.png` | All models show similar drift patterns — task switches visible as spikes |
| Change alignment bar | `07_change_alignment_bar.png` | 7B at 55%, others below 50% — all near chance |
| Radar overview | `08_radar_overall.png` | No model dominates all axes; 7B wins on drift-dependent metrics |
| Pairwise heatmap | `09_pairwise_heatmap.png` | All inter-model similarities ~0.31–0.34 — high divergence |
| 2B vs 3B scatter | `10_scatter_2b_vs_3b_cosine.png` | Points cluster near the diagonal — similar agreement levels with 7B |
| Similarity vs 7B bar | `11_similarity_vs_7b_bar.png` | 2B consistently closer to 7B than 3B across all three metrics |

---

## 5. Discussion

### When to use 2B
The 2B model is the strongest of the two small models for this task. It produces more specific descriptions and stays closer to the 7B reference. It is an appropriate choice when:
- GPU memory is constrained (fits in ~5 GB VRAM)
- Description specificity matters more than fluency
- The Qwen2-VL family is already in use

### When to use 3B
The 3B model produces the most concise outputs. If the downstream consumer of descriptions needs brevity (e.g. summaries for a compact UI, or feeding into a second LLM with tight context limits), 3B may be preferred. However, it sacrifices specificity and alignment with the larger reference model.

### When 7B is necessary
The 7B model is the clear choice when:
- Description richness and fluency are important
- Change detection alignment matters (55% vs ~49% for smaller models)
- The task requires confident, non-hedging descriptions

### Limitations of this evaluation
1. **No human ground truth** — all metrics are proxies. Specificity heuristics reward keyword density, not semantic accuracy.
2. **Same screenshots, same task** — the dataset is one continuous session. Performance may differ on other types of desktop activity.
3. **Change detection proxy is coarse** — drift-alignment uses a median threshold; real change detection would require labeled task-switch events.
4. **No latency / throughput measured** — for production use, inference speed and VRAM usage are equally important dimensions not captured here.

---

## 6. Conclusion

Across 136 real-world desktop screenshots:

- **Qwen2-VL 7B** is the best model for activity tracking quality: most verbose, lowest hedging, best drift alignment, highest change usefulness. It should be the default when resources allow.
- **Qwen2-VL 2B** is the better compact option: higher specificity than both 3B and 7B, and marginally closer to the 7B reference. A reasonable trade-off at one-quarter the parameter count.
- **Qwen2.5-VL 3B** underperforms its newer architecture label. Its descriptions are too terse and lose specificity, making it the weakest of the three for this specific task despite being the most recent model family.
- **Change detection remains the hardest sub-task** across all model sizes. A post-processing layer (e.g. a temporal classifier on top of the raw descriptions) would likely improve this significantly regardless of which VLM is used.

---

*Generated: 2026-04-01 | Dataset: 136 frames, single workstation session | Evaluation: `evaluate_three_models.py`*
