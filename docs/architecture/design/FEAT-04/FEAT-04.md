# FEAT-04: Prompt Construction Module (Test Case Agent)

## 1. Requirement Analysis
* [cite_start]**Context**: Stage 3 - RL-Based Verification.
* [cite_start]**Goal**: Construct "Evidence Bundles" that provide the LLM with sufficient context to generate high-quality test cases.
* **Oracle Support**: The prompt must guide the LLM toward:
    * [cite_start]**Crash Oracles**: Unhandled runtime exceptions.
    * [cite_start]**Property Oracles**: Invariants from docstrings/hints.
    * [cite_start]**Metamorphic Oracles**: Domain-general relations.

## 2. Technical Scope
* Implement `EvidenceBundle` to pair source code with its `StructuredDiagnostics` (from Stage 2).
* Implement `PromptConstructor` with templates for different oracle strategies.

## 3. Definition of Done (DoD)
- [ ] Logic implemented in `src/qallm/stage2_lre/prompter.py`.
- [ ] Unit tests verify prompt string composition.