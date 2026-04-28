import { useState, useMemo } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, BarChart, Bar, Legend, Cell } from "recharts";

/* ─── Embedded run data ─── */
const RUNS = {
  "gpt-4o-mini": {
    model: "gpt-4o-mini", tokens: 37116, calls: 24, budget: 50000,
    sessions: [
      { name: "train_decision_tree", coverage: 40.0, bugs: 11, curve: [22.0, 26.0, 31.0], rounds: [
        { round: 1, passed: 6, failed: 2, errors: 0, coverage: 40.0, reward_total: 22.0, bug_reward: 2.0, cov_reward: 20.0, invalid_pen: 0, redundant_pen: 0, tests: [
          {name:"test_normal_inputs",status:"passed"},{name:"test_empty_inputs",status:"passed"},{name:"test_single_element",status:"failed",msg:"assert result['right'] == 0"},{name:"test_large_numbers",status:"passed"},{name:"test_none_inputs",status:"passed"},{name:"test_mixed_types",status:"failed",msg:"TypeError not raised"},{name:"test_zero_as_input",status:"passed"},{name:"test_large_dataset",status:"passed"}
        ]},
        { round: 2, passed: 8, failed: 4, errors: 0, coverage: 40.0, reward_total: 4.0, bug_reward: 4.0, cov_reward: 0, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 3, passed: 3, failed: 5, errors: 0, coverage: 38.7, reward_total: 5.0, bug_reward: 5.0, cov_reward: 0, invalid_pen: 0, redundant_pen: 0, tests: [] },
      ]},
      { name: "predict", coverage: 16.0, bugs: 7, curve: [8.0, 13.0, 15.0], rounds: [
        { round: 1, passed: 4, failed: 0, errors: 0, coverage: 16.0, reward_total: 8.0, bug_reward: 0, cov_reward: 8.0, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 2, passed: 0, failed: 5, errors: 0, coverage: 16.0, reward_total: 5.0, bug_reward: 5.0, cov_reward: 0, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 3, passed: 3, failed: 2, errors: 0, coverage: 16.0, reward_total: 2.0, bug_reward: 2.0, cov_reward: 0, invalid_pen: 0, redundant_pen: 0, tests: [] },
      ]},
      { name: "evaluate_model", coverage: 30.0, bugs: 8, curve: [17.33, 21.0, 23.0], rounds: [
        { round: 1, passed: 3, failed: 3, errors: 0, coverage: 28.7, reward_total: 17.33, bug_reward: 3.0, cov_reward: 14.33, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 2, passed: 4, failed: 3, errors: 0, coverage: 30.0, reward_total: 3.67, bug_reward: 3.0, cov_reward: 0.67, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 3, passed: 5, failed: 2, errors: 0, coverage: 28.7, reward_total: 2.0, bug_reward: 2.0, cov_reward: 0, invalid_pen: 0, redundant_pen: 0, tests: [] },
      ]},
      { name: "run_external_scorer", coverage: 11.3, bugs: 16, curve: [9.67, 13.67, 21.67], rounds: [
        { round: 1, passed: 2, failed: 4, errors: 0, coverage: 11.3, reward_total: 9.67, bug_reward: 4.0, cov_reward: 5.67, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 2, passed: 2, failed: 4, errors: 0, coverage: 11.3, reward_total: 4.0, bug_reward: 4.0, cov_reward: 0, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 3, passed: 0, failed: 8, errors: 0, coverage: 11.3, reward_total: 8.0, bug_reward: 8.0, cov_reward: 0, invalid_pen: 0, redundant_pen: 0, tests: [] },
      ]},
      { name: "dynamic_evaluate", coverage: 10.0, bugs: 6, curve: [8.0, 10.0, 11.0], rounds: [
        { round: 1, passed: 3, failed: 3, errors: 0, coverage: 10.0, reward_total: 8.0, bug_reward: 3.0, cov_reward: 5.0, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 2, passed: 4, failed: 2, errors: 0, coverage: 10.0, reward_total: 2.0, bug_reward: 2.0, cov_reward: 0, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 3, passed: 5, failed: 1, errors: 0, coverage: 10.0, reward_total: 1.0, bug_reward: 1.0, cov_reward: 0, invalid_pen: 0, redundant_pen: 0, tests: [] },
      ]},
      { name: "save_model", coverage: 10.7, bugs: 2, curve: [6.33, 4.73, 5.73], rounds: [
        { round: 1, passed: 5, failed: 1, errors: 0, coverage: 10.7, reward_total: 6.33, bug_reward: 1.0, cov_reward: 5.33, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 2, passed: 8, failed: 0, errors: 0, coverage: 10.7, reward_total: -1.6, bug_reward: 0, cov_reward: 0, invalid_pen: 0, redundant_pen: -1.6, tests: [] },
        { round: 3, passed: 5, failed: 1, errors: 0, coverage: 10.7, reward_total: 1.0, bug_reward: 1.0, cov_reward: 0, invalid_pen: 0, redundant_pen: 0, tests: [] },
      ]},
      { name: "load_model", coverage: 10.7, bugs: 8, curve: [10.0, 13.33, 11.73], rounds: [
        { round: 1, passed: 1, failed: 5, errors: 0, coverage: 10.0, reward_total: 10.0, bug_reward: 5.0, cov_reward: 5.0, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 2, passed: 3, failed: 3, errors: 0, coverage: 10.7, reward_total: 3.33, bug_reward: 3.0, cov_reward: 0.33, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 3, passed: 8, failed: 0, errors: 0, coverage: 10.7, reward_total: -1.6, bug_reward: 0, cov_reward: 0, invalid_pen: 0, redundant_pen: -1.6, tests: [] },
      ]},
      { name: "complex_scoring", coverage: 35.3, bugs: 3, curve: [19.0, 20.0, 20.67], rounds: [
        { round: 1, passed: 4, failed: 2, errors: 0, coverage: 34.0, reward_total: 19.0, bug_reward: 2.0, cov_reward: 17.0, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 2, passed: 5, failed: 1, errors: 0, coverage: 34.0, reward_total: 1.0, bug_reward: 1.0, cov_reward: 0, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 3, passed: 6, failed: 0, errors: 0, coverage: 35.3, reward_total: 0.67, bug_reward: 0, cov_reward: 0.67, invalid_pen: 0, redundant_pen: 0, tests: [] },
      ]},
    ]
  },
  "gpt-5-mini": {
    model: "gpt-5-mini", tokens: 50934, calls: 16, budget: 50000,
    sessions: [
      { name: "train_decision_tree", coverage: 40.0, bugs: 1, curve: [19.33, 20.33, 21.0], rounds: [
        { round: 1, passed: 7, failed: 0, errors: 0, coverage: 38.7, reward_total: 19.33, bug_reward: 0, cov_reward: 19.33, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 2, passed: 5, failed: 1, errors: 0, coverage: 38.7, reward_total: 1.0, bug_reward: 1.0, cov_reward: 0, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 3, passed: 6, failed: 0, errors: 0, coverage: 40.0, reward_total: 0.67, bug_reward: 0, cov_reward: 0.67, invalid_pen: 0, redundant_pen: 0, tests: [] },
      ]},
      { name: "predict", coverage: 16.0, bugs: 0, curve: [8.0, 6.4, 4.8], rounds: [
        { round: 1, passed: 4, failed: 0, errors: 0, coverage: 16.0, reward_total: 8.0, bug_reward: 0, cov_reward: 8.0, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 2, passed: 8, failed: 0, errors: 0, coverage: 16.0, reward_total: -1.6, bug_reward: 0, cov_reward: 0, invalid_pen: 0, redundant_pen: -1.6, tests: [] },
        { round: 3, passed: 8, failed: 0, errors: 0, coverage: 16.0, reward_total: -1.6, bug_reward: 0, cov_reward: 0, invalid_pen: 0, redundant_pen: -1.6, tests: [] },
      ]},
      { name: "evaluate_model", coverage: 28.7, bugs: 0, curve: [13.33, 14.33, 13.13], rounds: [
        { round: 1, passed: 6, failed: 0, errors: 0, coverage: 26.7, reward_total: 13.33, bug_reward: 0, cov_reward: 13.33, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 2, passed: 5, failed: 0, errors: 0, coverage: 28.7, reward_total: 1.0, bug_reward: 0, cov_reward: 1.0, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 3, passed: 6, failed: 0, errors: 0, coverage: 28.7, reward_total: -1.2, bug_reward: 0, cov_reward: 0, invalid_pen: 0, redundant_pen: -1.2, tests: [] },
      ]},
      { name: "run_external_scorer", coverage: 11.3, bugs: 0, curve: [5.67, 4.47, 2.67], rounds: [
        { round: 1, passed: 4, failed: 0, errors: 0, coverage: 11.3, reward_total: 5.67, bug_reward: 0, cov_reward: 5.67, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 2, passed: 6, failed: 0, errors: 0, coverage: 11.3, reward_total: -1.2, bug_reward: 0, cov_reward: 0, invalid_pen: 0, redundant_pen: -1.2, tests: [] },
        { round: 3, passed: 9, failed: 0, errors: 0, coverage: 11.3, reward_total: -1.8, bug_reward: 0, cov_reward: 0, invalid_pen: 0, redundant_pen: -1.8, tests: [] },
      ]},
      { name: "dynamic_evaluate", coverage: 10.0, bugs: 0, curve: [5.0, 3.8, 2.4], rounds: [
        { round: 1, passed: 4, failed: 0, errors: 0, coverage: 10.0, reward_total: 5.0, bug_reward: 0, cov_reward: 5.0, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 2, passed: 6, failed: 0, errors: 0, coverage: 10.0, reward_total: -1.2, bug_reward: 0, cov_reward: 0, invalid_pen: 0, redundant_pen: -1.2, tests: [] },
        { round: 3, passed: 7, failed: 0, errors: 0, coverage: 10.0, reward_total: -1.4, bug_reward: 0, cov_reward: 0, invalid_pen: 0, redundant_pen: -1.4, tests: [] },
      ]},
      { name: "save_model", coverage: 10.7, bugs: 0, curve: [5.33, 4.83, 4.33], rounds: [
        { round: 1, passed: 4, failed: 0, errors: 0, coverage: 10.7, reward_total: 5.33, bug_reward: 0, cov_reward: 5.33, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 2, passed: 0, failed: 0, errors: 0, coverage: 0, reward_total: -0.5, bug_reward: 0, cov_reward: 0, invalid_pen: -0.5, redundant_pen: 0, tests: [] },
        { round: 3, passed: 0, failed: 0, errors: 0, coverage: 0, reward_total: -0.5, bug_reward: 0, cov_reward: 0, invalid_pen: -0.5, redundant_pen: 0, tests: [] },
      ]},
      { name: "load_model", coverage: 0, bugs: 0, curve: [-0.5, -1.0, -1.5], rounds: [
        { round: 1, passed: 0, failed: 0, errors: 0, coverage: 0, reward_total: -0.5, bug_reward: 0, cov_reward: 0, invalid_pen: -0.5, redundant_pen: 0, tests: [] },
        { round: 2, passed: 0, failed: 0, errors: 0, coverage: 0, reward_total: -0.5, bug_reward: 0, cov_reward: 0, invalid_pen: -0.5, redundant_pen: 0, tests: [] },
        { round: 3, passed: 0, failed: 0, errors: 0, coverage: 0, reward_total: -0.5, bug_reward: 0, cov_reward: 0, invalid_pen: -0.5, redundant_pen: 0, tests: [] },
      ]},
      { name: "complex_scoring", coverage: 0, bugs: 0, curve: [-0.5, -1.0, -1.5], rounds: [
        { round: 1, passed: 0, failed: 0, errors: 0, coverage: 0, reward_total: -0.5, bug_reward: 0, cov_reward: 0, invalid_pen: -0.5, redundant_pen: 0, tests: [] },
        { round: 2, passed: 0, failed: 0, errors: 0, coverage: 0, reward_total: -0.5, bug_reward: 0, cov_reward: 0, invalid_pen: -0.5, redundant_pen: 0, tests: [] },
        { round: 3, passed: 0, failed: 0, errors: 0, coverage: 0, reward_total: -0.5, bug_reward: 0, cov_reward: 0, invalid_pen: -0.5, redundant_pen: 0, tests: [] },
      ]},
    ]
  },
  "gemma3:4b": {
    model: "ollama/gemma3:4b", tokens: 27537, calls: 16, budget: 50000,
    sessions: [
      { name: "train_decision_tree", coverage: 40.0, bugs: 8, curve: [23.0, 28.0], rounds: [
        { round: 1, passed: 2, failed: 3, errors: 0, coverage: 40.0, reward_total: 23.0, bug_reward: 3.0, cov_reward: 20.0, invalid_pen: 0, redundant_pen: 0,
          tests: [{name:"test_normal_input",status:"passed"},{name:"test_empty_input",status:"passed"},{name:"test_single_element",status:"failed",msg:"assert threshold == 0"},{name:"test_max_depth_none",status:"failed",msg:"assert threshold == 1.5"},{name:"test_no_split_possible",status:"failed",msg:"assert threshold == 1"}] },
        { round: 2, passed: 2, failed: 5, errors: 0, coverage: 40.0, reward_total: 5.0, bug_reward: 5.0, cov_reward: 0, invalid_pen: 0, redundant_pen: 0, tests: [] },
      ]},
      { name: "predict", coverage: 9.3, bugs: 8, curve: [6.67, 12.67], rounds: [
        { round: 1, passed: 2, failed: 2, errors: 0, coverage: 9.3, reward_total: 6.67, bug_reward: 2.0, cov_reward: 4.67, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 2, passed: 0, failed: 6, errors: 0, coverage: 9.3, reward_total: 6.0, bug_reward: 6.0, cov_reward: 0, invalid_pen: 0, redundant_pen: 0, tests: [] },
      ]},
      { name: "evaluate_model", coverage: 30.0, bugs: 4, curve: [16.0, 19.0], rounds: [
        { round: 1, passed: 2, failed: 1, errors: 0, coverage: 30.0, reward_total: 16.0, bug_reward: 1.0, cov_reward: 15.0, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 2, passed: 2, failed: 3, errors: 0, coverage: 30.0, reward_total: 3.0, bug_reward: 3.0, cov_reward: 0, invalid_pen: 0, redundant_pen: 0, tests: [] },
      ]},
      { name: "run_external_scorer", coverage: 9.3, bugs: 3, curve: [5.67, 7.67], rounds: [
        { round: 1, passed: 2, failed: 0, errors: 0, coverage: 9.3, reward_total: 5.67, bug_reward: 0, cov_reward: 5.67, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 2, passed: 1, failed: 3, errors: 0, coverage: 9.3, reward_total: 2.0, bug_reward: 3.0, cov_reward: 0, invalid_pen: 0, redundant_pen: -1.0, tests: [] },
      ]},
      { name: "dynamic_evaluate", coverage: 10.0, bugs: 2, curve: [6.0, 7.0], rounds: [
        { round: 1, passed: 2, failed: 1, errors: 0, coverage: 10.0, reward_total: 6.0, bug_reward: 1.0, cov_reward: 5.0, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 2, passed: 3, failed: 1, errors: 0, coverage: 10.0, reward_total: 1.0, bug_reward: 1.0, cov_reward: 0, invalid_pen: 0, redundant_pen: 0, tests: [] },
      ]},
      { name: "save_model", coverage: 9.3, bugs: 3, curve: [5.67, 7.67], rounds: [
        { round: 1, passed: 2, failed: 0, errors: 0, coverage: 9.3, reward_total: 5.67, bug_reward: 0, cov_reward: 5.67, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 2, passed: 1, failed: 3, errors: 0, coverage: 9.3, reward_total: 2.0, bug_reward: 3.0, cov_reward: 0, invalid_pen: 0, redundant_pen: 0, tests: [] },
      ]},
      { name: "load_model", coverage: 9.3, bugs: 0, curve: [4.67, 1.87], rounds: [
        { round: 1, passed: 4, failed: 0, errors: 0, coverage: 9.3, reward_total: 4.67, bug_reward: 0, cov_reward: 4.67, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 2, passed: 6, failed: 0, errors: 0, coverage: 9.3, reward_total: -2.8, bug_reward: 0, cov_reward: 0, invalid_pen: 0, redundant_pen: -2.8, tests: [] },
      ]},
      { name: "complex_scoring", coverage: 9.3, bugs: 4, curve: [4.67, 8.67], rounds: [
        { round: 1, passed: 4, failed: 0, errors: 0, coverage: 9.3, reward_total: 4.67, bug_reward: 0, cov_reward: 4.67, invalid_pen: 0, redundant_pen: 0, tests: [] },
        { round: 2, passed: 0, failed: 4, errors: 0, coverage: 9.3, reward_total: 4.0, bug_reward: 4.0, cov_reward: 0, invalid_pen: 0, redundant_pen: 0, tests: [] },
      ]},
    ]
  }
};

const STATIC = [
  { id: "B404", severity: "LOW", text: "Consider possible security implications associated with the subprocess module.", line: 1, cwe: 78 },
  { id: "B602", severity: "HIGH", text: "subprocess call with shell=True identified, security issue.", line: 99, cwe: 78 },
  { id: "B307", severity: "MEDIUM", text: "Use of possibly insecure function (eval).", line: 105, cwe: 78 },
];
const MI = 31.6, CC = 8.8;

/* ─── Styles ─── */
const C = { bg: "#08090d", panel: "#0f1117", border: "#1a1d27", accent: "#22d3ee", green: "#34d399", red: "#f87171", amber: "#fbbf24", dim: "#4b5563", text: "#d1d5db", white: "#f3f4f6" };
const font = "'Menlo', 'SF Mono', 'Cascadia Code', monospace";

const Pill = ({ children, color }) => (
  <span style={{ background: color + "18", color, fontSize: 10, padding: "2px 8px", borderRadius: 99, fontWeight: 600, letterSpacing: "0.04em" }}>{children}</span>
);

const Stat = ({ label, value, sub, color = C.white }) => (
  <div style={{ textAlign: "center" }}>
    <div style={{ fontSize: 28, fontWeight: 800, color, lineHeight: 1 }}>{value}</div>
    <div style={{ fontSize: 10, color: C.dim, marginTop: 4, textTransform: "uppercase", letterSpacing: "0.08em" }}>{label}</div>
    {sub && <div style={{ fontSize: 10, color: C.dim }}>{sub}</div>}
  </div>
);

const MiniCurve = ({ data, color }) => (
  <svg viewBox="0 0 60 20" width={60} height={20}>
    {data.length > 1 && data.map((v, i) => {
      if (i === 0) return null;
      const max = Math.max(...data.map(Math.abs), 1);
      const x1 = (i - 1) / (data.length - 1) * 56 + 2;
      const x2 = i / (data.length - 1) * 56 + 2;
      const y1 = 18 - (data[i - 1] / max) * 16;
      const y2 = 18 - (v / max) * 16;
      return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke={color} strokeWidth={2} strokeLinecap="round" />;
    })}
  </svg>
);

export default function Dashboard() {
  const [model, setModel] = useState("gpt-4o-mini");
  const [expanded, setExpanded] = useState(null);
  const [roundIdx, setRoundIdx] = useState(0);

  const run = RUNS[model];
  const totalBugs = run.sessions.reduce((s, x) => s + x.bugs, 0);
  const avgCov = run.sessions.filter(s => s.coverage > 0).reduce((s, x) => s + x.coverage, 0) / Math.max(1, run.sessions.filter(s => s.coverage > 0).length);
  const allCurves = run.sessions.filter(s => s.curve.length > 0);
  const avgSlope = allCurves.length ? allCurves.reduce((s, x) => {
    const c = x.curve;
    return s + (c.length > 1 ? (c[c.length - 1] - c[0]) / (c.length - 1) : 0);
  }, 0) / allCurves.length : 0;

  const compData = run.sessions.map(s => ({ name: s.name.replace(/_/g, "\n"), bugs: s.bugs, coverage: s.coverage || 0 }));

  const sel = expanded != null ? run.sessions[expanded] : null;
  const selRound = sel && sel.rounds[roundIdx];

  return (
    <div style={{ fontFamily: font, background: C.bg, color: C.text, minHeight: "100vh", padding: 20 }}>
      <div style={{ maxWidth: 920, margin: "0 auto" }}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20, paddingBottom: 12, borderBottom: `1px solid ${C.border}` }}>
          <div>
            <h1 style={{ fontSize: 16, fontWeight: 800, color: C.white, margin: 0, letterSpacing: "0.06em" }}>
              QALLM <span style={{ color: C.accent }}>SESSION DASHBOARD</span>
            </h1>
            <div style={{ fontSize: 10, color: C.dim, marginTop: 2 }}>model.py &middot; crash oracle &middot; {run.sessions[0]?.rounds.length || 0} rounds</div>
          </div>
          <div style={{ display: "flex", gap: 4 }}>
            {Object.keys(RUNS).map(m => (
              <button key={m} onClick={() => { setModel(m); setExpanded(null); setRoundIdx(0); }}
                style={{ fontFamily: font, fontSize: 10, padding: "5px 12px", border: `1px solid ${model === m ? C.accent : C.border}`,
                  background: model === m ? C.accent + "15" : "transparent", color: model === m ? C.accent : C.dim,
                  borderRadius: 4, cursor: "pointer", fontWeight: model === m ? 700 : 400 }}>
                {m}
              </button>
            ))}
          </div>
        </div>

        {/* Summary row */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12, marginBottom: 20 }}>
          <div style={{ background: C.panel, borderRadius: 8, padding: 14, border: `1px solid ${C.border}` }}>
            <Stat label="Bugs Found" value={totalBugs} color={totalBugs > 0 ? C.red : C.dim} />
          </div>
          <div style={{ background: C.panel, borderRadius: 8, padding: 14, border: `1px solid ${C.border}` }}>
            <Stat label="Avg Coverage" value={`${avgCov.toFixed(1)}%`} color={C.green} />
          </div>
          <div style={{ background: C.panel, borderRadius: 8, padding: 14, border: `1px solid ${C.border}` }}>
            <Stat label="Tokens Used" value={`${(run.tokens / 1000).toFixed(1)}K`} sub={`/ ${(run.budget / 1000).toFixed(0)}K budget`} color={run.tokens >= run.budget ? C.red : C.accent} />
          </div>
          <div style={{ background: C.panel, borderRadius: 8, padding: 14, border: `1px solid ${C.border}` }}>
            <Stat label="API Calls" value={run.calls} color={C.white} />
          </div>
          <div style={{ background: C.panel, borderRadius: 8, padding: 14, border: `1px solid ${C.border}` }}>
            <Stat label="Avg RL Slope" value={avgSlope >= 0 ? `+${avgSlope.toFixed(1)}` : avgSlope.toFixed(1)} color={avgSlope >= 0 ? C.green : C.red} />
          </div>
        </div>

        {/* Static Analysis */}
        <div style={{ background: C.panel, borderRadius: 8, padding: 14, border: `1px solid ${C.border}`, marginBottom: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: C.white, textTransform: "uppercase", letterSpacing: "0.08em" }}>Static Analysis</span>
            <Pill color={C.accent}>MI {MI}</Pill>
            <Pill color={CC > 10 ? C.amber : C.green}>CC {CC}</Pill>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {STATIC.map((s, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 10 }}>
                <Pill color={s.severity === "HIGH" ? C.red : s.severity === "MEDIUM" ? C.amber : C.dim}>{s.severity}</Pill>
                <span style={{ color: C.accent, fontWeight: 600, width: 40 }}>{s.id}</span>
                <span style={{ color: C.dim }}>L{s.line}</span>
                <span>{s.text}</span>
                <span style={{ color: C.dim, marginLeft: "auto" }}>CWE-{s.cwe}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Function table */}
        <div style={{ background: C.panel, borderRadius: 8, border: `1px solid ${C.border}`, marginBottom: 16, overflow: "hidden" }}>
          <div style={{ padding: "10px 14px", borderBottom: `1px solid ${C.border}`, fontSize: 11, fontWeight: 700, color: C.white, textTransform: "uppercase", letterSpacing: "0.08em" }}>
            Functions &middot; {run.sessions.length} verified
          </div>
          {run.sessions.map((s, idx) => {
            const isExpanded = expanded === idx;
            const slope = s.curve.length > 1 ? (s.curve[s.curve.length - 1] - s.curve[0]) / (s.curve.length - 1) : 0;
            return (
              <div key={s.name}>
                <div onClick={() => { setExpanded(isExpanded ? null : idx); setRoundIdx(0); }}
                  style={{ display: "grid", gridTemplateColumns: "1fr 70px 50px 50px 80px", alignItems: "center", padding: "10px 14px",
                    borderBottom: `1px solid ${C.border}`, cursor: "pointer", background: isExpanded ? C.accent + "08" : "transparent",
                    transition: "background 0.15s" }}>
                  <div>
                    <span style={{ fontSize: 12, fontWeight: 600, color: C.white }}>{s.name.replace(/_/g, " ")}</span>
                    <span style={{ fontSize: 10, color: C.dim, marginLeft: 8 }}>{s.rounds.length}R</span>
                  </div>
                  <div style={{ fontSize: 11, color: (s.coverage || 0) >= 30 ? C.green : C.amber }}>{(s.coverage || 0).toFixed(1)}%</div>
                  <div style={{ fontSize: 11, color: s.bugs > 0 ? C.red : C.dim }}>{s.bugs} 🐛</div>
                  <div style={{ fontSize: 10, color: slope >= 0 ? C.green : C.red }}>{slope >= 0 ? "↑" : "↓"}{Math.abs(slope).toFixed(1)}</div>
                  <MiniCurve data={s.curve} color={slope >= 0 ? C.green : C.red} />
                </div>

                {/* Expanded detail */}
                {isExpanded && sel && (
                  <div style={{ background: C.bg, padding: 16, borderBottom: `1px solid ${C.border}` }}>
                    {/* Learning curve */}
                    <div style={{ marginBottom: 16 }}>
                      <div style={{ fontSize: 10, color: C.dim, marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.08em" }}>Learning Curve (Cumulative Reward)</div>
                      <ResponsiveContainer width="100%" height={120}>
                        <LineChart data={sel.curve.map((v, i) => ({ round: `R${i + 1}`, reward: v }))}>
                          <CartesianGrid strokeDasharray="3 3" stroke={C.border} />
                          <XAxis dataKey="round" tick={{ fontSize: 9, fill: C.dim }} />
                          <YAxis tick={{ fontSize: 9, fill: C.dim }} />
                          <Tooltip contentStyle={{ background: C.panel, border: `1px solid ${C.border}`, fontSize: 10, fontFamily: font }} />
                          <Line type="monotone" dataKey="reward" stroke={C.accent} strokeWidth={2} dot={{ r: 4, fill: C.accent }} />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>

                    {/* Round selector */}
                    <div style={{ display: "flex", gap: 4, marginBottom: 12 }}>
                      {sel.rounds.map((r, ri) => (
                        <button key={ri} onClick={() => setRoundIdx(ri)}
                          style={{ fontFamily: font, fontSize: 10, padding: "4px 12px",
                            border: `1px solid ${roundIdx === ri ? C.accent : C.border}`,
                            background: roundIdx === ri ? C.accent + "18" : "transparent",
                            color: roundIdx === ri ? C.accent : C.dim, borderRadius: 4, cursor: "pointer" }}>
                          Round {r.round}
                        </button>
                      ))}
                    </div>

                    {/* Round detail */}
                    {selRound && (
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                        {/* Left: execution + reward */}
                        <div>
                          <div style={{ fontSize: 10, color: C.dim, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>Execution</div>
                          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 6, marginBottom: 12 }}>
                            <div style={{ background: C.panel, borderRadius: 6, padding: 8, textAlign: "center" }}>
                              <div style={{ fontSize: 18, fontWeight: 800, color: C.green }}>{selRound.passed}</div>
                              <div style={{ fontSize: 9, color: C.dim }}>PASSED</div>
                            </div>
                            <div style={{ background: C.panel, borderRadius: 6, padding: 8, textAlign: "center" }}>
                              <div style={{ fontSize: 18, fontWeight: 800, color: C.red }}>{selRound.failed}</div>
                              <div style={{ fontSize: 9, color: C.dim }}>FAILED</div>
                            </div>
                            <div style={{ background: C.panel, borderRadius: 6, padding: 8, textAlign: "center" }}>
                              <div style={{ fontSize: 18, fontWeight: 800, color: C.amber }}>{selRound.errors}</div>
                              <div style={{ fontSize: 9, color: C.dim }}>ERRORS</div>
                            </div>
                            <div style={{ background: C.panel, borderRadius: 6, padding: 8, textAlign: "center" }}>
                              <div style={{ fontSize: 18, fontWeight: 800, color: C.accent }}>{selRound.coverage != null ? `${selRound.coverage.toFixed(1)}%` : "N/A"}</div>
                              <div style={{ fontSize: 9, color: C.dim }}>COVERAGE</div>
                            </div>
                          </div>

                          <div style={{ fontSize: 10, color: C.dim, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>Reward Breakdown</div>
                          <div style={{ background: C.panel, borderRadius: 6, padding: 10, fontSize: 11, lineHeight: 1.8 }}>
                            <div style={{ display: "flex", justifyContent: "space-between" }}>
                              <span>Bug discovery</span><span style={{ color: selRound.bug_reward > 0 ? C.green : C.dim }}>+{selRound.bug_reward.toFixed(1)}</span>
                            </div>
                            <div style={{ display: "flex", justifyContent: "space-between" }}>
                              <span>Coverage gain</span><span style={{ color: selRound.cov_reward > 0 ? C.green : C.dim }}>+{selRound.cov_reward.toFixed(1)}</span>
                            </div>
                            <div style={{ display: "flex", justifyContent: "space-between" }}>
                              <span>Invalid penalty</span><span style={{ color: selRound.invalid_pen < 0 ? C.red : C.dim }}>{selRound.invalid_pen.toFixed(1)}</span>
                            </div>
                            <div style={{ display: "flex", justifyContent: "space-between" }}>
                              <span>Redundancy penalty</span><span style={{ color: selRound.redundant_pen < 0 ? C.red : C.dim }}>{selRound.redundant_pen.toFixed(1)}</span>
                            </div>
                            <div style={{ display: "flex", justifyContent: "space-between", borderTop: `1px solid ${C.border}`, marginTop: 4, paddingTop: 4, fontWeight: 700 }}>
                              <span>Total</span><span style={{ color: selRound.reward_total >= 0 ? C.accent : C.red }}>{selRound.reward_total.toFixed(2)}</span>
                            </div>
                          </div>
                        </div>

                        {/* Right: test results */}
                        <div>
                          <div style={{ fontSize: 10, color: C.dim, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>
                            Test Results {selRound.tests.length > 0 ? `(${selRound.tests.length})` : ""}
                          </div>
                          <div style={{ background: C.panel, borderRadius: 6, padding: 10, maxHeight: 240, overflowY: "auto" }}>
                            {selRound.tests.length > 0 ? selRound.tests.map((t, ti) => (
                              <div key={ti} style={{ display: "flex", alignItems: "flex-start", gap: 6, fontSize: 10, padding: "3px 0",
                                borderBottom: ti < selRound.tests.length - 1 ? `1px solid ${C.border}` : "none" }}>
                                <span style={{ color: t.status === "passed" ? C.green : t.status === "failed" ? C.red : C.amber, fontWeight: 700, flexShrink: 0 }}>
                                  {t.status === "passed" ? "✓" : t.status === "failed" ? "✗" : "⚠"}
                                </span>
                                <div>
                                  <div style={{ fontWeight: 600, color: C.white }}>{t.name}</div>
                                  {t.msg && <div style={{ color: C.dim, fontSize: 9, marginTop: 2, wordBreak: "break-all" }}>{t.msg.slice(0, 120)}</div>}
                                </div>
                              </div>
                            )) : (
                              <div style={{ color: C.dim, fontSize: 10, fontStyle: "italic" }}>Detailed test results not available for this round.</div>
                            )}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Comparison chart */}
        <div style={{ background: C.panel, borderRadius: 8, padding: 14, border: `1px solid ${C.border}` }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: C.white, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 10 }}>
            Coverage vs Bugs by Function
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={compData} barGap={1}>
              <CartesianGrid strokeDasharray="3 3" stroke={C.border} />
              <XAxis dataKey="name" tick={{ fontSize: 7, fill: C.dim }} interval={0} angle={-20} textAnchor="end" height={50} />
              <YAxis tick={{ fontSize: 9, fill: C.dim }} />
              <Tooltip contentStyle={{ background: C.panel, border: `1px solid ${C.border}`, fontSize: 10, fontFamily: font }} />
              <Legend wrapperStyle={{ fontSize: 10 }} />
              <Bar dataKey="coverage" fill={C.accent} name="Coverage %" radius={[2, 2, 0, 0]} />
              <Bar dataKey="bugs" fill={C.red} name="Bugs Found" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div style={{ fontSize: 9, color: C.dim, textAlign: "center", marginTop: 16, paddingBottom: 20 }}>
          QALLM v0.2.0 &middot; MSc Thesis: Execution-Based Quality Assessment of AI-Generated Code in Jupyter Notebooks &middot; M. Assaban, UvA 2026
        </div>
      </div>
    </div>
  );
}
