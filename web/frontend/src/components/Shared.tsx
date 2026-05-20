import type { LucideIcon } from "lucide-react";
import { ChevronRight } from "lucide-react";

export function StatCard({ label, value, hint, icon: Icon }: { label: string; value: string | number; hint?: string; icon: LucideIcon }) {
  return (
    <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div>
        <div className="text-sm text-slate-500">{label}</div>
        <div className="mt-0.5 text-2xl font-semibold tracking-tight">{value}</div>
        {hint && <div className="mt-0.5 text-xs text-slate-500">{hint}</div>}
      </div>
      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-100">
        <Icon className="h-5 w-5 text-slate-600" />
      </div>
    </div>
  );
}

export function NextBar({ step, maxStep, onPrev, onNext, nextLabel, nextDisabled }: {
  step: number; maxStep: number; onPrev: () => void; onNext: () => void; nextLabel?: string; nextDisabled?: boolean;
}) {
  return (
    <div className="sticky bottom-0 z-20 mt-6 flex items-center justify-between rounded-2xl border border-slate-200 bg-white/85 p-3 shadow-lg backdrop-blur">
      <button onClick={onPrev} disabled={step <= 1} className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium disabled:opacity-30">Back</button>
      <span className="text-sm text-slate-500">Step {step} of {maxStep}</span>
      <button onClick={onNext} disabled={nextDisabled || step >= maxStep} className="flex items-center gap-1.5 rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-30">
        {nextLabel || "Next"} <ChevronRight className="h-4 w-4" />
      </button>
    </div>
  );
}
