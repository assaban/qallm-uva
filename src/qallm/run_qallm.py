from qallm.orchestrator import QALLMOrchestrator
from qallm.stage1_qqe.normalizer import LifecycleStage

# Initialize for the 'Implementation' stage using Gemma
orchestrator = QALLMOrchestrator(stage=LifecycleStage.IMPLEMENTATION, llm_type="gemma")

# Test it on your own parser to see 'Dogfooding' in action
# results = orchestrator.execute_analysis("src/qallm/ingestion/parsers.py")
# results = orchestrator.execute_analysis("qallm-demo-case")
results = orchestrator.execute_analysis("qallm-demo-case/src/research_pipeline/pipeline.py")

for res in results:
    # print(res)
    print(f"Cell {res['cell']}: Status={res['lifecycle_status']}, Verified={res['verification']['success']}")