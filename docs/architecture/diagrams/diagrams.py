#!/usr/bin/env python3
"""The QALLM architecture diagrams, laid out explicitly."""
import sys, pathlib
from gen import *

OUT = pathlib.Path('out'); OUT.mkdir(exist_ok=True)
BL, BR = 12.0, 357.0          # band left / right

# =========================================================== 1. component view
def component() -> Diagram:
    d = Diagram("component", height=418)
    # --- presentation
    d.bands.append(Band(BL, 14, BR-BL, 44, "Presentation layer"))
    pres = [("CLI", 24, 52), ("Notebook", 96, 62), ("Web UI", 180, 56), ("REST API", 262, 64)]
    for t, x, w in pres:
        d.boxes.append(Box(t, x, 26, w, 24, t))
    # --- orchestration
    d.bands.append(Band(BL, 74, BR-BL, 46, "Orchestration layer"))
    d.boxes.append(Box("orch", 84, 84, 200, 30, "Orchestrator",
                       "session, round loop, budget cap, profile"))
    # --- pipeline, vertical so edge labels have room
    d.bands.append(Band(BL, 136, BR-BL, 240, "Assessment pipeline"))
    px, pw, ph, gap = 26, 104, 26, 20
    stages = ["Ingestion", "Analysis", "Verification", "Repair", "Judge"]
    ys = []
    y = 152
    for s in stages:
        d.boxes.append(Box(s, px, y, pw, ph, s)); ys.append(y); y += ph + gap
    # --- reporting
    d.bands.append(Band(BL, 384, BR-BL, 22, "Reporting"))
    # (kept as a caption line rather than three more boxes: see notes below)

    # --- edges: presentation bus into the orchestrator
    bus_y = 68
    d.edges.append(Edge([(50, 50), (50, bus_y)], head=False))
    d.edges.append(Edge([(127, 50), (127, bus_y)], head=False))
    d.edges.append(Edge([(294, 50), (294, bus_y)], head=False))
    d.edges.append(Edge([(50, bus_y), (294, bus_y)], head=False))
    d.edges.append(Edge([(184, bus_y), (184, 84)]))
    d.edges.append(Edge([(236, 38), (262, 38)]))          # Web UI -> REST API
    # orchestrator into the pipeline
    d.edges.append(Edge([(184, 114), (184, 126), (78, 126), (78, 152)]))
    # the pipeline chain
    labels = ["code units", "findings", "defects", "variant"]
    for i, lab in enumerate(labels):
        y0 = ys[i] + ph
        d.edges.append(Edge([(78, y0), (78, ys[i+1])], label=lab, lox=36))
    # judge verdict back to the orchestrator
    d.edges.append(Edge([(26, ys[4] + 13), (18, ys[4] + 13), (18, 132),
                         (206, 132), (206, 114)], label="verdict", lpos=0.72, loy=-1))

    # --- required interfaces: UML ball-and-stick, with the implementations
    #     drawn as boxes rather than named in a caption, so a reader can see
    #     which analysers and which providers actually exist.
    GX, GW = 158.0, 194.0           # implementation group frame
    def impl_row(names, x0, y, gap=5.0, h=13.0):
        out, x = [], x0
        for n in names:
            w = max(34.0, tw(n, FS_SM) + 9)
            out.append(Box(n, x, y, w, h, n, kind="plain")); x += w + gap
        return out, x - gap

    # StaticCodeAnalyzer, required by Analysis. Five implementations, two rows.
    cy1 = ys[1] + 13
    d.lolli.append(Lollipop(130, cy1, 20, "", dir="right"))
    d.bands.append(Band(GX, cy1 - 24, GW, 50, "StaticCodeAnalyzer"))
    r1, _ = impl_row(["Bandit", "Radon", "Ruff"], GX + 6, cy1 - 10)
    r2, _ = impl_row(["TruffleHog", "SonarQube"], GX + 6, cy1 + 8)
    d.boxes += r1 + r2

    # LLMModel, required by Verification and by Repair.
    cy2, cy3 = ys[2] + 13, ys[3] + 13
    d.lolli.append(Lollipop(130, cy2, 20, "", dir="right"))
    d.edges.append(Edge([(130, cy3), (140, cy3), (140, cy2)], head=False))
    d.bands.append(Band(GX, cy2 - 17, GW, 34, "LLMModel"))
    r3, _ = impl_row(["FedLLM", "OpenAI", "Anthropic", "Ollama"], GX + 6, cy2 - 4)
    d.boxes += r3

    # Judge, required by the judge stage.
    cy4 = ys[4] + 13
    d.lolli.append(Lollipop(130, cy4, 20, "", dir="right"))
    d.bands.append(Band(GX, cy4 - 17, GW, 34, "Judge"))
    r4, _ = impl_row(["lexicographic", "strict", "model"], GX + 6, cy4 - 4)
    d.boxes += r4

    d.notes.append((BL + 5, 396, "Reporter, metrics export and the provenance manifest are "
                                 "written by every stage.", "start"))
    return d

# ========================================================== 2. deployment view
def deployment() -> Diagram:
    d = Diagram("deployment", height=372)
    d.bands.append(Band(BL, 14, BR-BL, 44, "Researcher workstation"))
    for t, x, w in [("Browser", 30, 62), ("Terminal", 148, 64), ("JupyterLab", 258, 76)]:
        d.boxes.append(Box(t, x, 26, w, 24, t))

    d.bands.append(Band(BL, 78, BR-BL, 208, "Docker host"))
    d.boxes.append(Box("proxy", 24, 96, 150, 30, "qallm-reverse-proxy",
                       "nginx:alpine, HTTP on 80", kind="node"))
    d.boxes.append(Box("api", 24, 150, 200, 30, "qallm-api",
                       "qallm:latest, 8000 internal only", kind="node"))
    d.boxes.append(Box("tools", 30, 188, 150, 16,
                       "Bandit, Radon, Ruff, TruffleHog", kind="plain"))
    d.boxes.append(Box("out", 236, 156, 52, 18, "outputs/", kind="store"))
    d.boxes.append(Box("up", 296, 156, 52, 18, "uploads/", kind="store"))
    d.boxes.append(Box("sonar", 24, 222, 150, 30, "qallm-sonarqube",
                       "SonarQube, 9000, embedded H2", kind="node"))
    d.boxes.append(Box("ollama", 196, 222, 142, 30, "qallm-ollama",
                       "11434, opt-in profile", kind="node"))

    d.bands.append(Band(BL, 300, BR-BL, 44, "External model endpoints"))
    for t, x, w in [("EGI FedLLM", 30, 84), ("OpenAI", 148, 60), ("Anthropic", 250, 74)]:
        d.boxes.append(Box(t, x, 312, w, 24, t, kind="plain"))

    d.edges.append(Edge([(61, 50), (61, 74), (99, 74), (99, 96)], label="HTTPS 443", lox=-2))
    d.edges.append(Edge([(180, 50), (180, 138), (124, 138), (124, 150)], label="CLI", lox=14))
    d.edges.append(Edge([(296, 50), (296, 142), (180, 142), (180, 150)], label="cell magic", lox=0, loy=-1))
    d.edges.append(Edge([(99, 126), (99, 150)], label="HTTP 8000", lox=32))
    d.edges.append(Edge([(80, 204), (80, 222)], label="5th analyser", lox=36))
    d.edges.append(Edge([(210, 180), (210, 212), (267, 212), (267, 222)], label="optional", lox=0, loy=-1))
    d.edges.append(Edge([(224, 178), (352, 178), (352, 306), (178, 306), (178, 312)],
                        label="HTTPS", lpos=0.22, lox=10, loy=-1))
    d.notes.append((BL + 5, 352, "Four of the five analysers run in-process inside qallm-api; "
                                 "SonarQube alone requires its own service.", "start"))
    d.notes.append((BL + 5, 362, "Generated code runs inside qallm-api as a non-root user in a "
                                 "timeout-bounded subprocess.", "start"))
    return d

# ================================================ 3. verification subsystem
def verification() -> Diagram:
    d = Diagram("verification", height=372)
    d.bands.append(Band(BL, 14, BR-BL, 52, "Generation"))
    d.boxes.append(Box("loop", 24, 30, 118, 28, "Test generation loop"))
    d.boxes.append(Box("gen", 158, 30, 82, 28, "Generator"))
    d.boxes.append(Box("hyp", 256, 30, 90, 28, "Hypothesis"))

    d.bands.append(Band(BL, 86, BR-BL, 52, "Admission"))
    d.boxes.append(Box("val", 24, 102, 118, 28, "AST validator"))
    d.boxes.append(Box("store", 178, 102, 118, 28, "Suite store"))

    d.bands.append(Band(BL, 158, BR-BL, 46, "Execution"))
    d.boxes.append(Box("exe", 24, 172, 118, 24, "Executor"))

    d.bands.append(Band(BL, 224, BR-BL, 108, "Adjudication"))
    d.boxes.append(Box("cr", 24, 240, 118, 26, "Confirm / refute"))
    d.boxes.append(Box("mut", 178, 240, 140, 26, "Mutation scorer"))
    d.boxes.append(Box("vf", 24, 292, 118, 26, "Verified fix"))
    d.boxes.append(Box("rw", 178, 292, 140, 26, "Reward"))

    d.edges.append(Edge([(142, 44), (158, 44)], label="prompt", lox=0, loy=-1))
    d.edges.append(Edge([(240, 44), (256, 44)], head=True))
    d.edges.append(Edge([(199, 58), (199, 74), (83, 74), (83, 102)], label="candidates", lox=30))
    d.edges.append(Edge([(301, 58), (301, 78), (120, 78), (120, 102)], head=True))
    d.edges.append(Edge([(142, 116), (178, 116)], label="admitted", lox=0, loy=-1))
    d.edges.append(Edge([(237, 130), (237, 146), (83, 146), (83, 172)], label="suite", lox=26))
    d.edges.append(Edge([(83, 196), (83, 240)], label="behaviour", lox=32))
    d.edges.append(Edge([(120, 196), (120, 214), (247, 214), (247, 240)], label="strength", lox=0, loy=-1))
    d.edges.append(Edge([(142, 253), (178, 253)], label="", head=True))
    d.edges.append(Edge([(83, 266), (83, 292)], label="re-test", lox=26))
    d.edges.append(Edge([(247, 266), (247, 292)], label="outcomes", lox=32))
    d.notes.append((BL + 5, 346, "Reward supplies the measured outcome of a round to the next "
                                 "prompt; the return edge is omitted here and shown in the", "start"))
    d.notes.append((BL + 5, 356, "sequence diagram, because drawn to scale it would span the "
                                 "whole figure.", "start"))
    return d

# --------------------------------------------------------------------------- main
if __name__ == "__main__":
    ok = True
    for fn in (component, deployment, verification):
        d = fn()
        errs = check(d)
        status = "OK" if not errs else f"{len(errs)} PROBLEM(S)"
        print(f"{d.name:14s} {W:.0f} x {d.height:.0f} pt  "
              f"({W/72*2.54:.1f} x {d.height/72*2.54:.1f} cm)   {status}")
        for e in errs:
            print("   !", e); ok = False
        (OUT / f"qallm-{d.name}.svg").write_text(to_svg(d))
        (OUT / f"qallm-{d.name}.tikz.tex").write_text(to_tikz(d))
    print("\nfont on page: 9.0pt (authored at final size, included at scale 1.0)")
    sys.exit(0 if ok else 1)
