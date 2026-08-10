#!/usr/bin/env python3
"""The improvement-round sequence diagram, hand-laid-out.

Replaces the PlantUML version, which broke in the thesis: PlantUML's LaTeX
backend fixes label coordinates using its own Helvetica metrics, but the
document renders those labels in CrimsonPro, so every label was wider than the
space reserved and the whole figure collided with itself.

Here the geometry and the text are computed together, and check() asserts that
no label overruns the span it sits on.
"""
import sys, pathlib
from gen import *

OUT = pathlib.Path('out'); OUT.mkdir(exist_ok=True)

def build() -> Diagram:
    d = Diagram("round", height=470)

    names = ["Orchestrator", "Analysis", "Verification", "Repair", "Judge"]
    widths = [max(34.0, tw(n, FS) + 12) for n in names]
    gap = (345.0 - sum(widths)) / (len(names) - 1)
    x, lanes = 12.0, {}
    for n, w in zip(names, widths):
        d.boxes.append(Box(n, x, 16, w, 20, n, kind="participant"))
        lanes[n] = x + w / 2
        x += w + gap

    TOP = 36.0
    y = [52.0]
    def msg(a, b, label, dashed=False):
        """One message. Label sits above the arrow, centred on the span."""
        x1, x2 = lanes[a], lanes[b]
        d.edges.append(Edge([(x1, y[0]), (x2, y[0])], label=label,
                            style="dashed" if dashed else "solid"))
        y[0] += 17.0

    def divider(label):
        y[0] += 5.0
        d.dividers.append(Divider(y[0], label))
        y[0] += 16.0

    divider("Round 0: baseline, no repair")
    msg("Orchestrator", "Analysis",     "analyse original")
    msg("Analysis",     "Orchestrator", "tagged findings", dashed=True)
    msg("Orchestrator", "Verification", "verify original")
    msg("Verification", "Orchestrator", "baseline behaviour", dashed=True)

    divider("Rounds 1 to N: repair, re-measure, judge")
    loop_top = y[0] + 3
    y[0] += 22
    msg("Orchestrator", "Repair",       "target finding or failure")
    msg("Repair",       "Orchestrator", "candidate variant", dashed=True)
    msg("Orchestrator", "Analysis",     "re-analyse")
    msg("Analysis",     "Orchestrator", "findings left", dashed=True)
    msg("Orchestrator", "Verification", "re-verify")
    msg("Verification", "Orchestrator", "pass, fail, no regression", dashed=True)
    msg("Orchestrator", "Judge",        "variant versus parent")
    alt_top = y[0] + 2
    y[0] += 21
    msg("Judge", "Orchestrator", "accept into lineage", dashed=True)
    alt_mid = y[0] - 4
    y[0] += 12
    msg("Judge", "Orchestrator", "abandon variant", dashed=True)
    alt_bot = y[0] - 3
    d.frames.append(Frame(20, alt_top, 325, alt_bot - alt_top, "alt", "improves parent"))
    d.dividers.append(Divider(alt_mid, "else: higher dimension regressed",
                              x1=24, x2=341, dashed=True))
    y[0] += 6
    d.frames.append(Frame(15, loop_top, 335, y[0] - 3 - loop_top, "loop",
                          "until accepted or budget spent"))
    y[0] += 6

    divider("Adjudication")
    msg("Orchestrator", "Verification", "confirm or refute each finding")
    msg("Verification", "Orchestrator", "verdict with confidence", dashed=True)
    msg("Orchestrator", "Verification", "re-test the demonstrated defect")
    msg("Verification", "Orchestrator", "fixed or not fixed", dashed=True)

    BOT = y[0] + 2.0
    for n in names:                       # lifelines, drawn to the closing boxes
        d.edges.append(Edge([(lanes[n], TOP), (lanes[n], BOT)],
                            style="dashed", head=False))
    for n, w in zip(names, widths):       # closing participant boxes
        d.boxes.append(Box(n + "_foot", lanes[n] - w / 2, BOT, w, 20, n,
                           kind="participant"))
    d.height = BOT + 30.0
    return d


def check_labels(d: Diagram) -> list[str]:
    """A message label must fit the span it is centred on."""
    errs = []
    for e in d.edges:
        if not e.label:
            continue
        span = abs(e.pts[-1][0] - e.pts[0][0])
        need = tw(e.label, FS_LBL)
        if need > span - 8:
            errs.append(f"label '{e.label}' needs {need:.0f}pt, span is {span:.0f}pt")
    return errs


if __name__ == "__main__":
    d = build()
    errs = check(d) + check_labels(d)
    print(f"round  {W:.0f} x {d.height:.0f} pt ({W/72*2.54:.1f} x {d.height/72*2.54:.1f} cm)"
          f"   {'OK' if not errs else str(len(errs)) + ' PROBLEM(S)'}")
    for e in errs:
        print("   !", e)
    (OUT / "qallm-round.svg").write_text(to_svg(d))
    (OUT / "qallm-round.tikz.tex").write_text(to_tikz(d))
    sys.exit(0 if not errs else 1)
