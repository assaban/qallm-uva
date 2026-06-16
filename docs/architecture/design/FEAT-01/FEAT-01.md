# FEAT-01: Jupyter Preprocessing Adapter

## 1. Requirement Analysis
* [cite_start]**Context**: Thesis Stage 1 - Preprocessing.
* **Goal**: Transform `.ipynb` (JSON) into a structured Python representation suitable for execution-based testing.
* **Research Traceability**:
    - [cite_start]**Extraction**: Filter only `cell_type == "code"`.
    - [cite_start]**Normalization**: Strip Jupyter-specific magic commands (`%matplotlib`, `!pip`).
    - [cite_start]**Mapping**: Must preserve cell order and index for per-cell reporting in Stage 4.

## 2. Technical Scope
* [cite_start]Implement `NotebookAdapter` using the standard Python `json` library.
* Create a regex-based `MagicStripper` to clean source code without altering line counts (to maintain traceback accuracy).

## 3. Definition of Done (DoD)
- [ ] [cite_start]Successfully parses Li's (2025) dataset sample.
- [ ] [cite_start]Strips all magic patterns identified in the proposal.
- [ ] Logic documented in `FEAT-01-logic.puml`.