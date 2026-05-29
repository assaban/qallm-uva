import { Upload, GaugeCircle, Wrench, RotateCw, Repeat, FileCheck2, CheckCircle2 } from "lucide-react";

/**
 * The step rail names the actual pipeline.
 *
 * Auto mode runs the real loop: Upload -> Baseline (round 0) -> Improvement
 * rounds (orch.run: repair -> verify -> judge, repeated) -> Report. It has
 * four phases.
 *
 * Manual mode exposes the same pipeline as inspectable stages, including a
 * single-pass repair preview, for teaching and debugging. It keeps the
 * finer-grained six-stage breakdown. Either way the labels describe what
 * the stage does, not the obsolete "RL" framing.
 */
type Step = { id: number; title: string; icon: any; blurb: string };

const AUTO_STEPS: Step[] = [
  { id: 1, title: "Upload", icon: Upload, blurb: "Bring in code" },
  { id: 2, title: "Baseline", icon: GaugeCircle, blurb: "Round 0, no repair" },
  { id: 3, title: "Improvement rounds", icon: Repeat, blurb: "Repair, verify, judge" },
  { id: 4, title: "Report", icon: FileCheck2, blurb: "Lineage and verdict" },
];

const MANUAL_STEPS: Step[] = [
  { id: 1, title: "Upload", icon: Upload, blurb: "Bring in code" },
  { id: 2, title: "Baseline", icon: GaugeCircle, blurb: "Static analysis" },
  { id: 3, title: "Repair preview", icon: Wrench, blurb: "One LLM pass" },
  { id: 4, title: "Re-analyse", icon: RotateCw, blurb: "Inspect the delta" },
  { id: 5, title: "Run pipeline", icon: Repeat, blurb: "Full loop, all rounds" },
  { id: 6, title: "Report", icon: FileCheck2, blurb: "Lineage and verdict" },
];

export default function StepRail({
  currentStep,
  onStepClick,
  mode = "manual",
}: {
  currentStep: number;
  onStepClick: (s: number) => void;
  mode?: "manual" | "auto";
}) {
  const steps = mode === "auto" ? AUTO_STEPS : MANUAL_STEPS;
  const cols = steps.length === 4 ? "md:grid-cols-4" : "md:grid-cols-6";
  return (
    <div className="rounded-2xl border border-slate-200 bg-white/70 p-3 shadow-sm backdrop-blur">
      <div className={`grid grid-cols-3 gap-2 ${cols}`}>
        {steps.map(s => {
          const Icon = s.icon;
          const done = currentStep > s.id;
          const active = currentStep === s.id;
          const canClick = s.id <= currentStep;
          return (
            <button key={s.id} onClick={() => canClick && onStepClick(s.id)} disabled={!canClick}
              className={`rounded-xl border p-2.5 text-left transition-all ${active ? "border-slate-900 bg-slate-900 text-white" : done ? "cursor-pointer border-slate-300 bg-slate-50 hover:bg-slate-100" : "border-slate-200 bg-white opacity-50"}`}>
              <div className="mb-1.5 flex items-center justify-between">
                <div className={`flex h-8 w-8 items-center justify-center rounded-lg ${active ? "bg-white/20" : "bg-slate-100"}`}><Icon className="h-4 w-4" /></div>
                {done && <CheckCircle2 className="h-4 w-4 text-emerald-500" />}
              </div>
              <div className="text-sm font-semibold">{s.title}</div>
              <div className={`mt-0.5 text-xs ${active ? "text-slate-300" : "text-slate-500"}`}>{s.blurb}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
