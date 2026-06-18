import { useEffect, useState } from "react";
import { getRoundDiff, type RoundDiff, type RoundFileDiff } from "../api";

// Colour a unified-diff line GitHub-style by its leading marker.
function diffLineClass(line: string): string {
  if (line.startsWith("+") && !line.startsWith("+++")) return "bg-emerald-50 text-emerald-800";
  if (line.startsWith("-") && !line.startsWith("---")) return "bg-rose-50 text-rose-800";
  if (line.startsWith("@@")) return "bg-sky-50 text-sky-700";
  if (line.startsWith("+++") || line.startsWith("---")) return "text-slate-400";
  return "text-slate-600";
}

function UnifiedDiff({ unified }: { unified: string }) {
  if (!unified) return <div className="px-3 py-2 text-xs text-slate-400">No changes.</div>;
  return (
    <pre className="overflow-auto rounded bg-white font-mono text-[11px] leading-relaxed">
      {unified.split("\n").map((line, i) => (
        <div key={i} className={`px-3 ${diffLineClass(line)}`}>{line || "\u00A0"}</div>
      ))}
    </pre>
  );
}

function RawDiff({ file }: { file: RoundFileDiff }) {
  return (
    <div className="grid grid-cols-2 gap-2">
      <div>
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
          before (round {"<"}parent{">"})
        </div>
        <pre className="max-h-96 overflow-auto rounded bg-slate-50 px-2 py-1.5 font-mono text-[11px] leading-relaxed text-slate-700">
          {file.old_text || "(absent)"}
        </pre>
      </div>
      <div>
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">after</div>
        <pre className="max-h-96 overflow-auto rounded bg-slate-50 px-2 py-1.5 font-mono text-[11px] leading-relaxed text-slate-700">
          {file.new_text || "(absent)"}
        </pre>
      </div>
    </div>
  );
}

export default function RoundDiffView({ sessionId }: { sessionId: string }) {
  const [data, setData] = useState<RoundDiff | null>(null);
  const [reason, setReason] = useState<string | null>(null);
  const [toRound, setToRound] = useState<number | null>(null);
  // null means "immediate parent" (to_round - 1); a number is an explicit base.
  const [fromRound, setFromRound] = useState<number | null>(null);
  const [mode, setMode] = useState<"unified" | "raw">("unified");
  const [openFile, setOpenFile] = useState<string | null>(null);

  // First load: discover rounds, default to the latest round vs its parent.
  useEffect(() => {
    let live = true;
    getRoundDiff(sessionId, 1)
      .then((res) => {
        if (!live) return;
        if (!res.available || !res.rounds?.length) {
          setReason(res.reason ?? "No round diff available yet.");
          return;
        }
        const latest = res.rounds[res.rounds.length - 1];
        setToRound(latest);
      })
      .catch(() => live && setReason("Could not load round diff."));
    return () => {
      live = false;
    };
  }, [sessionId]);

  // Reload when either selected round changes. fromRound null => parent.
  useEffect(() => {
    if (toRound === null) return;
    let live = true;
    getRoundDiff(sessionId, toRound, fromRound ?? undefined)
      .then((res) => {
        if (!live) return;
        if (res.available) {
          setData(res);
          setOpenFile(res.files.find((f) => f.changed)?.label ?? res.files[0]?.label ?? null);
        } else setReason(res.reason ?? "No round diff available.");
      })
      .catch(() => live && setReason("Could not load round diff."));
    return () => {
      live = false;
    };
  }, [sessionId, toRound, fromRound]);

  if (reason) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <h3 className="text-sm font-semibold text-slate-700">Round diff</h3>
        <p className="mt-1 text-xs text-slate-400">{reason}</p>
      </div>
    );
  }
  if (!data || toRound === null) {
    return <div className="rounded-xl border border-slate-200 bg-white p-4 text-xs text-slate-400">Loading round diff…</div>;
  }

  const allRounds = data.rounds; // every round present, including 0
  const laterRounds = allRounds.filter((r) => r > 0); // the "to" side needs a parent to exist
  // Valid bases for the chosen "to" round: any round strictly below it.
  const baseChoices = allRounds.filter((r) => r < (toRound ?? 0));
  const active = data.files.find((f) => f.label === openFile) ?? data.files[0];

  // Keep the explicit base valid if the later round moves below it.
  const onChangeTo = (next: number) => {
    setToRound(next);
    if (fromRound !== null && fromRound >= next) setFromRound(null); // revert to parent
  };

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-slate-700">Round diff</h3>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <label className="text-slate-500">Compare</label>
          <select
            value={fromRound === null ? "parent" : String(fromRound)}
            onChange={(e) => setFromRound(e.target.value === "parent" ? null : Number(e.target.value))}
            className="rounded-md border border-slate-200 px-1.5 py-0.5"
            title="Base round to diff against"
          >
            <option value="parent">parent (R{(toRound ?? 1) - 1})</option>
            {baseChoices.map((r) => (
              <option key={r} value={r}>R{r}</option>
            ))}
          </select>
          <span className="text-slate-400">→</span>
          <select
            value={toRound}
            onChange={(e) => onChangeTo(Number(e.target.value))}
            className="rounded-md border border-slate-200 px-1.5 py-0.5"
            title="Later round to compare"
          >
            {laterRounds.map((r) => (
              <option key={r} value={r}>R{r}</option>
            ))}
          </select>
          <span className="ml-1 text-slate-400">
            ({fromRound === null ? (toRound ?? 1) - 1 : fromRound} vs {toRound})
          </span>
          <div className="ml-2 flex overflow-hidden rounded-md border border-slate-200">
            <button onClick={() => setMode("unified")} className={`px-2 py-0.5 font-medium ${mode === "unified" ? "bg-slate-900 text-white" : "bg-white text-slate-600"}`}>Unified</button>
            <button onClick={() => setMode("raw")} className={`px-2 py-0.5 font-medium ${mode === "raw" ? "bg-slate-900 text-white" : "bg-white text-slate-600"}`}>Raw</button>
          </div>
        </div>
      </div>

      {/* File tabs: source.py and each test file, with a changed indicator. */}
      <div className="mt-3 flex flex-wrap gap-1.5 text-[11px]">
        {data.files.map((f) => (
          <button
            key={f.label}
            onClick={() => setOpenFile(f.label)}
            className={`rounded-md border px-2 py-0.5 font-mono ${active?.label === f.label ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white text-slate-600"}`}
          >
            {f.kind === "code" ? "⚙ " : "✓ "}{f.label}
            {f.changed && <span className={`ml-1 ${active?.label === f.label ? "text-amber-300" : "text-amber-500"}`}>●</span>}
          </button>
        ))}
      </div>

      <div className="mt-3">
        {active ? (
          mode === "unified" ? <UnifiedDiff unified={active.unified} /> : <RawDiff file={active} />
        ) : (
          <div className="text-xs text-slate-400">No artefacts to compare.</div>
        )}
      </div>
    </div>
  );
}
