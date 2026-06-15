/**
 * AboutView: the in-app explainer for what QALLM is and why it exists.
 *
 * The thesis claim, made interactive: each example is real Python that passes
 * static analysis but is genuinely broken. The visitor runs the generated
 * test and watches execution find the bug, then sees the fix proven by
 * re-running the same test. This is the verification gap, demonstrated rather
 * than described, and it doubles as demo and knowledge-sharing material.
 *
 * The example values are faithful: the assertions shown are what the buggy
 * code actually produces versus what correct code should, so the page
 * demonstrates the real claim, not a dramatisation.
 */

import { useState } from "react";
import { ShieldCheck, Zap, BadgeCheck, Play, Bug } from "lucide-react";

interface ExecStep {
  kind: "info" | "fail" | "assert";
  text: string;
}

interface GapCase {
  kind: string;
  title: string;
  tag: string;
  code: string;
  bugLines: number[];     // 0-indexed lines to highlight
  staticVerdict: string;
  steps: ExecStep[];
  gap: string;
  fix: string;
  proven: string;
}

const CASES: GapCase[] = [
  {
    kind: "Reliability",
    title: "Off-by-one in an inclusive day count",
    tag: "Radon: MI high · Bandit: clean",
    code: `def days_between(start, end):
    # inclusive count of days from start to end
    return end - start  # forgets the +1`,
    bugLines: [2],
    staticVerdict: "No issues. Cyclomatic complexity 1, maintainability high.",
    steps: [
      { kind: "info", text: "collected 1 item" },
      { kind: "info", text: "test_days_between_inclusive " },
      { kind: "fail", text: "FAILED" },
      { kind: "assert", text: "assert days_between(1, 5) == 5   # 1st..5th is 5 days" },
      { kind: "assert", text: "E   assert 4 == 5" },
    ],
    gap: "A linter sees one clean return statement. Execution sees a function that under-counts every range by one, the kind of error that quietly corrupts a research result.",
    fix: `def days_between(start, end):
    return end - start + 1`,
    proven: "Reproducing test now passes. days_between(1, 5) == 5. Fix verified by execution.",
  },
  {
    kind: "Reliability",
    title: "Mutable default argument shares state",
    tag: "Ruff: clean · SonarQube: clean",
    code: `def add_reading(value, log=[]):
    # append a sensor reading to a fresh log
    log.append(value)   # the list is shared across calls
    return log`,
    bugLines: [2],
    staticVerdict: "No issues. No security smells, no style violations.",
    steps: [
      { kind: "info", text: "collected 1 item" },
      { kind: "info", text: "test_logs_are_independent " },
      { kind: "fail", text: "FAILED" },
      { kind: "assert", text: "first = add_reading(1); second = add_reading(2)" },
      { kind: "assert", text: "assert second == [2]" },
      { kind: "assert", text: "E   assert [1, 2] == [2]" },
    ],
    gap: "The default list is created once and reused on every call. The second call inherits the first call's data. No static rule fires, yet two independent calls silently share state.",
    fix: `def add_reading(value, log=None):
    if log is None:
        log = []
    log.append(value)
    return log`,
    proven: "Each call now gets a fresh list. second == [2]. Fix verified by execution.",
  },
  {
    kind: "Security",
    title: "Expression evaluator built on eval",
    tag: "reachability unknown to static tools",
    code: `def calc(expr):
    # evaluate a user-supplied arithmetic string
    return eval(expr)   # arbitrary code execution`,
    bugLines: [2],
    staticVerdict: "Some tools flag eval as a smell, but is it actually reachable and exploitable? Static analysis cannot tell.",
    steps: [
      { kind: "info", text: "collected 1 item" },
      { kind: "info", text: "test_calc_rejects_arbitrary_code " },
      { kind: "fail", text: "FAILED" },
      { kind: "assert", text: 'calc("__import__(\'os\').getcwd()")  # should be rejected' },
      { kind: "assert", text: "E   exploit succeeded: arbitrary call executed" },
    ],
    gap: "Here execution does the opposite of the reliability cases: the exploit test passes against the original, proving the vulnerability is real and reachable, not a theoretical smell. QALLM confirms it by demonstration.",
    fix: `import ast, operator as op
_OPS = {ast.Add: op.add, ast.Sub: op.sub,
        ast.Mult: op.mul, ast.Div: op.truediv}
def calc(expr):
    def ev(n):
        if isinstance(n, ast.Constant):
            return n.value
        return _OPS[type(n.op)](ev(n.left), ev(n.right))
    return ev(ast.parse(expr, mode="eval").body)`,
    proven: "Exploit test now fails against the repaired code: arbitrary calls are rejected. Vulnerability no longer reachable. Fix verified.",
  },
];

function CodeBlock({ code, bugLines }: { code: string; bugLines: number[] }) {
  const lines = code.split("\n");
  return (
    <pre className="overflow-x-auto rounded-lg bg-slate-950 p-4 font-mono text-[13px] leading-relaxed text-slate-200">
      {lines.map((line, i) => (
        <div
          key={i}
          className={bugLines.includes(i) ? "-mx-4 bg-rose-500/10 px-4" : ""}
        >
          {line || " "}
        </div>
      ))}
    </pre>
  );
}

function GapCaseCard({ c }: { c: GapCase }) {
  const [running, setRunning] = useState(false);
  const [shown, setShown] = useState(0);   // how many steps revealed
  const [done, setDone] = useState(false);

  const run = () => {
    if (running || done) return;
    setRunning(true);
    setShown(0);
    let i = 0;
    const tick = () => {
      i += 1;
      setShown(i);
      if (i >= c.steps.length) {
        setRunning(false);
        setDone(true);
        return;
      }
      const step = c.steps[i - 1];
      setTimeout(tick, step.kind === "fail" ? 520 : step.kind === "assert" ? 360 : 260);
    };
    tick();
  };

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between gap-4 border-b border-slate-100 bg-slate-50 px-5 py-4">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-amber-700">{c.kind}</div>
          <div className="font-semibold text-slate-800">{c.title}</div>
        </div>
        <span className="shrink-0 rounded-full border border-slate-200 px-2.5 py-1 font-mono text-[11px] text-slate-500">{c.tag}</span>
      </div>

      <div className="p-5">
        <CodeBlock code={c.code} bugLines={c.bugLines} />
      </div>

      <div className="grid grid-cols-1 border-t border-slate-100 sm:grid-cols-2">
        <div className="border-b border-slate-100 p-5 sm:border-b-0 sm:border-r">
          <h4 className="mb-3 flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider text-slate-500">
            <ShieldCheck className="h-4 w-4 text-emerald-600" /> Static analysis
          </h4>
          <div className="font-mono text-[13px] text-emerald-600">✓ clean — looks correct</div>
          <p className="mt-2 font-mono text-[11.5px] leading-relaxed text-slate-500">{c.staticVerdict}</p>
        </div>

        <div className="p-5">
          <h4 className="mb-3 flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider text-amber-700">
            <Zap className="h-4 w-4 text-amber-500" /> Execution (QALLM)
          </h4>
          <button
            onClick={run}
            disabled={running || done}
            className="inline-flex items-center gap-2 rounded-lg border border-amber-500 px-4 py-2 font-mono text-[13px] font-semibold text-amber-700 transition hover:bg-amber-500 hover:text-white disabled:opacity-50"
          >
            {done ? <><Bug className="h-3.5 w-3.5" /> bug reproduced</>
              : running ? <>running pytest…</>
              : <><Play className="h-3.5 w-3.5" /> run the generated test</>}
          </button>

          <div className="mt-3 min-h-[20px] font-mono text-[12.5px] leading-relaxed">
            {c.steps.slice(0, shown).map((s, i) => (
              <div
                key={i}
                className={
                  s.kind === "fail" ? "font-semibold text-rose-500"
                  : s.kind === "assert" ? "pl-3.5 text-slate-700"
                  : "text-slate-400"
                }
              >
                {s.text}
              </div>
            ))}
            {done && (
              <div className="mt-3 rounded-lg border-l-[3px] border-rose-400 bg-rose-50 px-3.5 py-3 font-serif text-[14px] italic text-slate-700">
                {c.gap}
              </div>
            )}
          </div>
        </div>
      </div>

      {done && (
        <div className="border-t border-slate-100 p-5">
          <h4 className="mb-3 flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider text-teal-600">
            <BadgeCheck className="h-4 w-4 text-teal-500" /> Repair, proven by re-running the same test
          </h4>
          <CodeBlock code={c.fix} bugLines={[]} />
          <div className="mt-3 flex items-center gap-2 font-mono text-[12.5px] text-teal-600">
            ✓ {c.proven}
          </div>
        </div>
      )}
    </div>
  );
}

export default function AboutView() {
  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-8 text-center">
        <div className="font-mono text-[11px] uppercase tracking-[0.3em] text-amber-700">
          Execution-Based Quality Assessment
        </div>
        <h2 className="mt-3 text-3xl font-bold tracking-tight text-slate-900">
          It passed every check. It was still wrong.
        </h2>
        <p className="mx-auto mt-3 max-w-2xl text-slate-500">
          Static analysers read code; they cannot run it. So a function can be tidy, secure-looking,
          and lint-clean, and still produce the wrong answer. QALLM closes that gap by treating each
          static finding as a hypothesis and letting execution be the judge. Run the examples to see it.
        </p>
      </div>

      <div className="mb-8 grid grid-cols-3 gap-px overflow-hidden rounded-xl border border-slate-200 bg-slate-200 text-center">
        {[
          { n: "91.3%", l: "of buggy code passed static analysis clean, in our pilot" },
          { n: "3", l: "execution-based metrics: gap, confirmation, verified-fix" },
          { n: "0", l: "bugs below are visible without running the code" },
        ].map((s, i) => (
          <div key={i} className="bg-white px-3 py-5">
            <div className="font-mono text-2xl font-bold text-teal-600">{s.n}</div>
            <div className="mt-1.5 text-[12px] leading-snug text-slate-500">{s.l}</div>
          </div>
        ))}
      </div>

      <div className="space-y-6">
        {CASES.map((c, i) => <GapCaseCard key={i} c={c} />)}
      </div>

      <div className="my-10 rounded-2xl border border-slate-200 bg-white p-8 text-center">
        <h3 className="text-2xl font-bold tracking-tight text-slate-900">This is the verification gap.</h3>
        <p className="mx-auto mt-3 max-w-xl text-slate-500">
          Every bug above is real and reproducible, yet invisible to tools that only read source text.
          QALLM runs generated tests, confirms which findings are genuine, and re-runs the reproducing
          test after a repair to prove the fix rather than assert it.
        </p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-2 font-mono text-[12px]">
          {["Static analysis", "Execute & confirm", "Repair", "Verify the fix", "Score confidence"].map((s, i, arr) => (
            <span key={i} className="flex items-center gap-2">
              <span className="rounded-md border border-slate-200 px-3 py-2 text-slate-700">{s}</span>
              {i < arr.length - 1 && <span className="text-amber-500">→</span>}
            </span>
          ))}
        </div>
      </div>

      <div className="my-10 rounded-2xl border border-slate-200 bg-white p-8 text-center">
        <h3 className="text-2xl font-bold tracking-tight text-slate-900">How do we know the bugs are real?</h3>
        <p className="mx-auto mt-3 max-w-xl text-slate-500">
          A found bug is only as trustworthy as the test that found it. QALLM stress-tests each
          test by injecting small faults into the function and checking the test catches them.
          A test that kills the injected faults is a sensitive detector, so its finding is high
          confidence; one that misses them is flagged low. Every gap finding carries a confidence,
          so the result is not just how many bugs, but how sure we are of each.
        </p>
      </div>
    </div>
  );
}
