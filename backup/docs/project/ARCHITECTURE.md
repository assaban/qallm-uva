# QALLM v0.2.0: Merged Architecture

## Thesis Section → Code Module Mapping

| Thesis Section | Module | Files | LOC | What It Does |
|---|---|---|---|---|
| Stage 1: Jupyter Preprocessing (§3.4) | `qallm.ingestion` | `parsers.py` | 79 | Parse .ipynb/.py, strip magic commands, extract CodeUnits |
| Stage 2: Static Analysis (§3.4) | `qallm.analysis` | `metrics.py`, `normalizer.py` | 78 | Bandit + Radon, lifecycle-aware thresholds (EOSC) |
| Stage 3: RL Verification (§3.4) | `qallm.verification` | 8 files | 1,159 | **Core thesis contribution** |
| LLM Providers | `qallm.llm` | 4 files | 300 | OpenAI, Anthropic, Ollama (Gemma) with token tracking |
| Orchestrator + Config | root | `orchestrator.py`, `config.py` | 174 | Wires stages 1-4 together |
| Reporting | `qallm.utils` | `reporter.py`, `signatures.py` | 41 | JSON audit trail for reproducibility |

## Verification Module Breakdown (Stage 3)

| File | LOC | Purpose |
|---|---|---|
| `models.py` | 164 | Data classes: FunctionInfo, GeneratedTest, ExecutionResult, RewardBreakdown, RoundResult, TestGenerationSession |
| `prompts.py` | 274 | Oracle-specific prompts (crash, property, metamorphic) + feedback prompt for RL loop |
| `loop.py` | 265 | **The RL feedback loop**: generate → execute → score → feedback × N rounds |
| `sandbox.py` | 174 | CodeExtractor (AST-validated LLM output parsing) + DependencyMapper (sibling module copying) |
| `executor.py` | 153 | Subprocess sandbox: runs pytest + coverage.py, parses JSON reports |
| `reward.py` | 121 | 4-component reward: bug_found (+1.0), coverage_gain (+0.5), invalid_test (-0.5), redundant_test (-0.2) |
| `generator.py` | 99 | Calls LLM with oracle prompt, uses CodeExtractor, validates output |
| `extractor.py` | 107 | AST-based function extraction from source code |

## What Was Kept From Each Repo

### From `qallm-uva` (simplified)
- Ingestion module (clean, simple)
- StaticAnalyzer (Bandit + Radon via subprocess)
- LifecycleNormalizer (EOSC lifecycle stages)
- QualityReporter (timestamped JSON audit)
- Demo case

### From `qallm` (original)
- TestGenerationLoop (the RL feedback loop)
- Executor (subprocess sandbox with coverage.py integration)
- Reward function (4-component scoring from thesis proposal Figure 2)
- Data models (FunctionInfo → TestGenerationSession)
- Oracle-specific prompts (crash, property, metamorphic)
- Feedback prompt (translates reward signal into natural language)
- LLM providers with TokenTracker (cost tracking for thesis benchmarking)
- Function extractor (AST-based)

### New (built during merge)
- CodeExtractor: multi-strategy AST-validated extraction (fixes P0 LLM Chatter)
- DependencyMapper: sibling module copying (fixes P0 Import Hallucinations)
- Simplified config (replaced pydantic Settings with plain os.getenv)
- Merged orchestrator (wires all stages, saves sessions as JSON)

### Removed (bloat)
- FastAPI web server (576 LOC cli.py + routes + templates + static)
- Repair service (356 LOC)
- Session/workspace management
- Registry patterns (analyzer registry, normalizer registry, LLM registry)
- All HTML/CSS/JS
- pydantic dependency for config

## Totals
- **Source**: 26 Python files, 2,088 LOC
- **Tests**: 10 test files, 36 tests, all passing
- **Reduction**: 63% fewer LOC than original (2,088 vs 5,697), 64% fewer files (26 vs 73)

## Usage

```bash
# Run with OpenAI
export OPENAI_API_KEY=sk-...
qallm qallm-demo-case/src/research_pipeline/pipeline.py --llm openai --rounds 5 --oracle crash

# Run with local Gemma via Ollama
qallm notebook.ipynb --llm ollama --model gemma3:4b --rounds 3

# Run with Anthropic Claude
export ANTHROPIC_API_KEY=sk-ant-...
qallm my_project/ --llm anthropic --oracle property --rounds 7
```
