# FEAT-03: Lifecycle-Aware Normalizer

## 1. Requirement Analysis
* [cite_start]**Goal**: Normalize raw static metrics into quality states based on the research software lifecycle[cite: 170].
* **Lifecycle Stages**:
    * [cite_start]**Initialization**: Focus on basic structure; high complexity is tolerated.
    * **Implementation**: Standard thresholds apply; security is prioritized.
    * [cite_start]**Publication**: Strict thresholds; reproducibility and maintenance are critical.
* [cite_start]**Research Traceability**: Aligns with the role- and lifecycle-aware metrics framework of Volentir et al.

## 2. Technical Scope
* Implement `LifecycleNormalizer` to map raw `mi` and `cc` values to categorical grades (A, B, C, F).
* Define a `DiagnosticReport` that bundles code, raw metrics, and normalized status.

## 3. Definition of Done (DoD)
- [ ] Successfully maps MI/CC scores to lifecycle-specific grades.
- [ ] Unit tests verify threshold logic for all three stages.