import { Upload, Search, Wrench, RotateCw, FlaskConical, TrendingUp, CheckCircle2 } from "lucide-react";

const steps = [
  { id: 1, title: "Upload", icon: Upload, blurb: "Bring in code" },
  { id: 2, title: "Analyse", icon: Search, blurb: "Static analysis" },
  { id: 3, title: "Repair", icon: Wrench, blurb: "LLM repair" },
  { id: 4, title: "Re-analyse", icon: RotateCw, blurb: "Verify improvement" },
  { id: 5, title: "Generate Tests", icon: FlaskConical, blurb: "RL test generation" },
  { id: 6, title: "RL Results", icon: TrendingUp, blurb: "Learning curve" },
];

export default function StepRail({ currentStep, onStepClick }: { currentStep: number; onStepClick: (s: number) => void }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white/70 p-3 shadow-sm backdrop-blur">
      <div className="grid grid-cols-3 gap-2 md:grid-cols-6">
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
