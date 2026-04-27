# FEAT-05: Iterative Verification Loop

## 1. Requirement Analysis
* **Goal**: Implement the Stage 3 RL-based verification loop (Generate -> Execute -> Reward -> Refine).
* **Multi-LLM Support**: Integrate OpenAI (GPT-4), Anthropic (Claude 3.5), and Google (Gemma 2/3).
* **Research Traceability**: This loop measures the 'Verification Gap' by attempting to trigger runtime failures that static analysis missed.

## 2. Technical Scope
* **Client Factory**: A unified interface to swap between LLM providers.
* **Execution Sandbox**: A subprocess runner to safely execute generated pytest files.
* **Reward Function**: Calculates the 'Quality Delta' based on coverage and discovered defects.

## 3. Definition of Done (DoD)
- [ ] Successfully calls an LLM and receives a Python test suite.
- [ ] Executes the suite and captures 'Pass/Fail' and 'Coverage' data.
- [ ] Saves the final verification artifact to the `outputs/` directory.