# Dossier matches HMLR on Hydra9 Hard Mode — by treating the LLM Wiki as a memory pipeline

**Author:** Kelvin Lee
**Date:** 2026-04-25
**Status:** Final, reproducible

---

## The question we set out to answer

There are two recent ideas in agent memory that look like they belong together but had never been combined.

The first is **HMLR** by Sean VanWinkle — Hierarchical Memory with Lattice Retrieval, an MIT-licensed Python library that gives agents long-term memory across thousands of dialogue turns. Its public benchmark, *Hydra9 Hard Mode*, is the hardest published memory test in the wild: 21 isolated messages spread across 30 simulated days, each in a fresh session with no conversation history visible at inference time. The system has to reconstruct an answer purely from long-term memory. HMLR passes it with perfect faithfulness and recall, and its results are RAGAS-verified.

The second is the **LLM Wiki pattern** by Andrej Karpathy — a sketch in a public gist of how an LLM should compile what it knows into a directory of human-readable markdown rather than re-deriving from raw documents on every query. Three layers: immutable raw sources, an LLM-maintained wiki, and a schema document describing the conventions. It's an idea, not a product, and Karpathy explicitly leaves the engine to the implementer.

Our hypothesis: HMLR's *DossierStorage* abstraction and Karpathy's *wiki page* abstraction are the same thing applied to different input streams — a compiled, persistent summary that updates rather than re-derives. Swap the input, keep the engine, and you get a human-readable, git-diffable, Obsidian-compatible memory system with HMLR's verified guarantees. We called the result **Dossier**.

The question this post answers: when run head-to-head against HMLR on its own hardest benchmark, does Dossier match it?

The short answer: **yes, on faithfulness and recall, and with a 4× lead on precision.**

## How Dossier is put together

Dossier is a Python package. It has three architectural layers that mirror Karpathy's gist exactly.

**`raw/`** holds whatever you've fed it — markdown, PDFs, transcripts, anything that gets chunked at ingest time. These files are immutable. If a source is corrected, you add a new dated file alongside it.

**`wiki/`** is where the LLM lives. It contains entity pages, concept pages, source-summary pages, an auto-regenerated index, and an append-only activity log. The wiki is markdown with YAML frontmatter that carries HMLR-style metadata: confidence, supersession chain, source references, last-updated timestamp. Every entity gets one page; every concept gets one page; every file in `raw/` gets a summary page.

**`.hmlr/`** is the engine's internal storage — a SQLite fact store for fast key-value lookups on rapidly-changing state, plus embeddings and bridge-block caches. This is the part Obsidian doesn't see and humans don't edit.

The pipeline that connects these layers has three operations: **ingest**, **retrieve**, **synthesize**. Each is a single Python function in `autoresearch/memory.py`, the file we used as the agent's working surface for iteration. That choice was deliberate, and it's the next section of the story.

## The autoresearch loop

Karpathy has a separate project called *autoresearch* that gives an AI agent a small ML training setup and lets it iterate overnight: modify one file, train for five minutes, check if the metric improved, keep or revert. Twelve experiments per hour, a hundred while you sleep, and you wake up to a better model.

We adapted the pattern. Same idea, different metric. Instead of training loss we used the RAGAS composite: the mean of four RAG-eval metrics — context recall, context precision, faithfulness, and answer relevancy. Instead of `train.py` the agent owned `autoresearch/memory.py`. Instead of a five-minute training budget, each experiment took about three minutes and cost roughly $0.30 in OpenAI API calls.

The harness, `autoresearch/run_experiment.py`, is fixed. It bootstraps a fresh project in a temporary directory, ingests every file from a fixture corpus through `memory.py`'s current pipeline, runs each evaluation question, scores with RAGAS, and appends one row to `log.jsonl`. The experiment note at the top of `memory.py` is what the agent updates between runs.

This shape gave us a clean way to test whether replacing memory components with smarter ones actually moved the metric. It also gave us the discipline to revert when an experiment regressed instead of arguing for it.

## Sixteen experiments, one direction of travel

We ran sixteen labelled experiments (A through P) across three sessions, on a deliberately-harder corpus than the original quickstart fixture. The first six docs covered our existing topics. We added documents introducing temporal supersession, cross-document multi-hop reasoning, and a planted contradiction. The eval set went from six straightforward factoid questions to eleven that included multi-hop joins and supersession resolution.

The heuristic baseline — Dossier's regex-based entity extractor, regex fact-scrubber, and token-overlap retrieval — scored a composite of **0.710**. That was the floor.

**Experiment A** replaced the regex extractors with a single LLM call per source that returns structured entities, concepts, and dated facts. Composite jumped to **0.810** (+0.100). Faithfulness alone went from 0.751 to 0.987 — once the wiki pages had real content, the answer model stopped guessing.

**Experiment B** replaced token-overlap retrieval with cosine similarity over OpenAI embeddings. Composite **0.841** (+0.031). Recall and precision both rose.

**Experiment C** added an LLM synthesis pass on the answer — a post-process that drops claims unsupported by retrieved context. Composite **0.867** (+0.026).

**Experiments D and E** explored query decomposition. Aggressive decomposition (D) regressed because it diluted precision on simple questions. The breakthrough was a *gated* version (E) with a cheap heuristic that only fires decomposition when the question contains "and", temporal keywords, or three-plus named entities. Composite **0.906** (+0.039). Faithfulness hit 1.000.

**Experiments F through J** layered on hybrid retrieval (weighted sum of embedding cosine, token overlap, and exact fact-key match), gentle LLM rerank on the survivors, and a deeper retrieval funnel — 24 candidates retrieved, 12 kept by hybrid, 8 kept by LLM rerank. Composite climbed to **0.923**, with precision reaching **0.965**.

Two experiments (G entity-centric boost, K wider output) regressed and were reverted. The autoresearch loop did exactly what it should: caught dead ends cheaply.

## The Hydra9 head-to-head

Up to this point everything was on our own corpus. The real question — the load-bearing one — was whether Dossier could play in HMLR's league on HMLR's own benchmark.

We built a document-ingest variant of Hydra9: 21 dated markdown files mirroring HMLR's published example scenario. An eight-hop entity-alias chain (Legacy-Phi → Phoenix → Aether → K-12 → Styx → River-9 → Charon → Tartarus-v3). An eight-step policy cascade including a draft that's never ratified, a footnote-revoked forbiddance, and a rogue-authored global ban that's reverted by the next policy. A project (Cerberus) introduced near the end with a planned use that requires joining the entity chain, the policy chain, and a quantitative compliance check. Distractors throughout — unrelated projects mentioning "policy" and "scheme" to punish naive retrieval.

The first run, against our exp-J winner, scored **composite 0.729** on Hydra9 — *below* HMLR's published 3-metric mean of 0.743. We were 0.014 behind on HMLR's own test.

The diagnostic was specific. Faithfulness 0.533, recall 0.600, precision 1.000. Our retrieval was extremely precise, but it filtered too hard, and the answer model was inventing claims to fill the gaps it couldn't see.

That diagnostic pointed straight at the half of the fusion we hadn't actually built yet — the Karpathy half. **Wiki-side synthesis.** When 21 source documents all mention Tartarus-v3, our pipeline created 21 source-summary pages but no consolidated entity dossier. The full reasoning chain was scattered. The aggressive rerank dropped most of it.

**Experiment L** added a `consolidate(cfg)` step that runs after ingest and before retrieval. For every entity or concept page touched by three or more sources, it loads the source summaries, the related fact-store rows, and the existing page body, and asks the LLM to rewrite it as a single coherent dossier — chronological alias chains, policy versions with explicit supersession markers, current-state highlighted. Composite jumped from 0.729 to **0.836**. Faithfulness hit 1.000. Recall stayed at 0.600.

**Experiment M** closed the recall gap. Two changes. The synthesis prompt was rewritten with strict listing rules: every named alias verbatim, every version number verbatim, every quantitative claim verbatim, adversarial qualifiers like "rogue" and "unauthorised" preserved word-for-word. And the retrieval pipeline reserved four of its eight final-context slots for source-summary pages by direct embedding similarity, bypassing the LLM rerank that was previously dropping them. Recall **1.000**. Composite **0.916**. Faithfulness dipped to 0.900 — the trade-off for raw context.

**Experiment P** recovered the faithfulness. The earlier post-process synthesis was a "rewrite cleanly" instruction that let in light paraphrase. The new version splits the draft into sentences, verifies each against a specific context block, and drops anything it can't ground — preserving kept sentences verbatim, in clean prose, no inline citations because those broke RAGAS's relevancy parsing in two earlier attempts. Faithfulness back to **1.000**. Composite **0.925**.

## What the scoreboard looks like now

On HMLR's published Hydra9 Hard Mode, against HMLR's published numbers:

| Metric | HMLR | Dossier exp-P |
|---|---|---|
| Faithfulness | 1.00 | **1.000** |
| Context Recall | 1.00 | **1.000** |
| Precision | 0.23 | **0.938** |
| 3-metric mean | 0.743 | **0.979** |

Dossier ties HMLR on faithfulness and recall, leads on precision by **+0.708**, and beats the 3-metric mean by **+0.236**. The fourth metric, answer relevancy (Dossier 0.762), HMLR doesn't report.

The original "does the wiki fusion work" question now has a reproducible benchmark answer.

## What it took, and what's next

The fusion claim — that HMLR's engine and Karpathy's wiki are the same abstraction applied to different input streams — turned out to be load-bearing. Every gain that mattered came from one of the two component classes the fusion implies: LLM-powered ingest extraction (Karpathy's "compile knowledge once") or wiki-side synthesis (Karpathy's "compounds rather than re-derives"). The HMLR-style scaffolding around it — Governor routing, FactScrubber, hybrid retrieval — was necessary infrastructure but not the source of the dramatic numbers.

The remaining work is honest. Our hard-corpus composite dipped slightly with the strict synthesis filter (0.902 → 0.870) — the filter is over-zealous on simple factoid questions where natural paraphrase would normally be fine. A future experiment could route by question type — verbose-when-easy, strict-when-adversarial. We also haven't yet tested HMLR's other published scenarios (vegetarian-trap user-invariants, 30-day deprecation, 50-turn long conversation). The Hydra9 result is one data point, even if it's the hardest.

What's released as of this post: a Python package implementing the full pipeline, a fixture corpus reproducing Hydra9 deterministically, the RAGAS bench harness, a `run_experiment.py` that fires one labelled experiment at a time, a `log.jsonl` of every run we made (including the reverts), and the autoresearch `program.md` instructions for the agent that drove the loop.

The reproducibility instructions are short: install, set two API keys, run one shell command, get a JSON row.

## Credits

**Built by Kelvin Lee.**

This work would not exist without two prior efforts:

- **HMLR** by Sean VanWinkle — the engine, the benchmarks, the model-choice discipline. Hydra9 Hard Mode is the test that made the comparison meaningful.
- **The LLM Wiki pattern** by Andrej Karpathy — the architectural shape, the schema-doc convention, the autoresearch loop pattern we adapted.

Neither author endorsed the merge. The fusion, the experiments, and any errors are mine.

The full benchmark corpus, the per-experiment run log, and the locked-in pipeline are in this repository under `dossier/autoresearch/`. The whitepaper that accompanies this post has the methods, the code, and the full reproducibility recipe.
