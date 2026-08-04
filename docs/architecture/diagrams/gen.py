#!/usr/bin/env python3
"""Hand-authored architecture diagrams for the QALLM thesis.

Why this exists rather than PlantUML or Mermaid: both auto-layout engines
produced either corner-to-corner edges (PlantUML placed an interface in the
right margin with an edge spanning 0.92 of the canvas diagonal) or generic
boxes-in-tiers flowcharts that do not read as software engineering diagrams
(Mermaid). Layout here is explicit, so every edge is orthogonal by construction
and the notation is proper UML: component boxes carry the component icon,
provided interfaces are drawn as ball-and-socket.

Diagrams are authored AT FINAL SIZE (369pt wide = the thesis \\linewidth) with a
9pt base font, so they are included at scale 1.0 and the type on the page is
exactly 9pt. No resizebox, no shrinking.

Two backends emit the same geometry: SVG for direct use, TikZ for LaTeX.
A check pass asserts no box overlaps, no text overflow, and no edge crossing a
box, so the result is verifiable without looking at it.
"""
from __future__ import annotations
import math, sys
from dataclasses import dataclass, field

W = 369.0                      # thesis \linewidth in pt
FS = 9.0                       # base font size in pt
FS_SM = 7.4                    # secondary line inside a box
FS_LBL = 7.6                   # edge labels
FS_BAND = 7.8                  # band captions
CHAR = 0.545                   # mean glyph width / font size for Helvetica

INK   = "#1F2933"
COMP_F, COMP_S, COMP_T = "#EEF1FA", "#4C5BA8", "#1A2A6C"
BAND_F, BAND_S, BAND_T = "#F7F8FA", "#C2CAD4", "#5A6875"
NODE_F, NODE_S, NODE_T = "#F0F7F2", "#5F8A72", "#1B5E32"
STORE_F, STORE_S, STORE_T = "#FFF9EC", "#A08A6A", "#4E3A22"
EDGE = "#465360"

def tw(s: str, fs: float) -> float:
    """Approximate rendered width of a string."""
    return len(s) * fs * CHAR

@dataclass
class Box:
    id: str; x: float; y: float; w: float; h: float
    title: str = ""; sub: str = ""
    kind: str = "component"     # component | node | store | plain
    def cx(self): return self.x + self.w / 2
    def cy(self): return self.y + self.h / 2
    def top(self): return (self.cx(), self.y)
    def bot(self): return (self.cx(), self.y + self.h)
    def lft(self): return (self.x, self.cy())
    def rgt(self): return (self.x + self.w, self.cy())

@dataclass
class Band:
    x: float; y: float; w: float; h: float; label: str

@dataclass
class Edge:
    pts: list            # orthogonal waypoints
    label: str = ""
    style: str = "solid" # solid | dashed
    head: bool = True
    lpos: float = 0.5    # 0..1 along the polyline for the label
    lox: float = 0.0     # label offset x, to sit a label beside a vertical arrow
    loy: float = 0.0

@dataclass
class Lollipop:
    """UML provided interface: stick plus ball, with the interface name."""
    x: float; y: float; length: float; name: str; dir: str = "down"

@dataclass
class Diagram:
    name: str; height: float
    bands: list = field(default_factory=list)
    boxes: list = field(default_factory=list)
    edges: list = field(default_factory=list)
    lolli: list = field(default_factory=list)
    notes: list = field(default_factory=list)   # (x, y, text, anchor)

# --------------------------------------------------------------------------- checks
def check(d: Diagram) -> list[str]:
    errs = []
    for i, a in enumerate(d.boxes):
        fs = FS_SM if a.kind == "plain" else FS
        need = max(tw(a.title, fs), tw(a.sub, FS_SM)) + 9
        if need > a.w + 0.5:
            errs.append(f"{d.name}: text overflows {a.id} (needs {need:.0f}pt, has {a.w:.0f}pt)")
        minh = 24 if a.sub else (12 if a.kind == "plain" else 16)
        if a.h < minh:
            errs.append(f"{d.name}: {a.id} too short for its text")
        if a.x < 2 or a.x + a.w > W - 2:
            errs.append(f"{d.name}: {a.id} outside canvas")
        for b in d.boxes[i+1:]:
            if (a.x < b.x + b.w and b.x < a.x + a.w
                    and a.y < b.y + b.h and b.y < a.y + a.h):
                # nesting is legitimate: a component drawn inside a node
                if _contains(a, b) or _contains(b, a):
                    continue
                errs.append(f"{d.name}: {a.id} overlaps {b.id}")
    for e in d.edges:
        for (x1, y1), (x2, y2) in zip(e.pts, e.pts[1:]):
            if abs(x1 - x2) > 0.51 and abs(y1 - y2) > 0.51:
                errs.append(f"{d.name}: non-orthogonal segment in edge '{e.label or '?'}'")
            # segment must not pass through a box interior
            for b in d.boxes:
                if _seg_hits(x1, y1, x2, y2, b):
                    errs.append(f"{d.name}: edge '{e.label or '?'}' crosses {b.id}")
    return errs

def _contains(outer: Box, inner: Box) -> bool:
    return (outer.x <= inner.x and outer.y <= inner.y
            and outer.x + outer.w >= inner.x + inner.w
            and outer.y + outer.h >= inner.y + inner.h)

def _seg_hits(x1, y1, x2, y2, b: Box) -> bool:
    pad = 1.5
    bx1, by1, bx2, by2 = b.x + pad, b.y + pad, b.x + b.w - pad, b.y + b.h - pad
    if abs(y1 - y2) <= 0.51:                       # horizontal
        if not (by1 < y1 < by2): return False
        lo, hi = sorted((x1, x2))
        return lo < bx2 and bx1 < hi
    if abs(x1 - x2) <= 0.51:                       # vertical
        if not (bx1 < x1 < bx2): return False
        lo, hi = sorted((y1, y2))
        return lo < by2 and by1 < hi
    return False

# --------------------------------------------------------------------------- svg
def to_svg(d: Diagram) -> str:
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}pt" height="{d.height}pt" '
         f'viewBox="0 0 {W} {d.height}" font-family="Helvetica,Arial,sans-serif">',
         '<defs>',
         f'<marker id="ah" markerWidth="7" markerHeight="7" refX="6.2" refY="2.6" orient="auto">'
         f'<path d="M0,0 L6.4,2.6 L0,5.2 z" fill="{EDGE}"/></marker>',
         '</defs>',
         f'<rect width="{W}" height="{d.height}" fill="#FFFFFF"/>']
    for b in d.bands:
        o.append(f'<rect x="{b.x}" y="{b.y}" width="{b.w}" height="{b.h}" rx="3" '
                 f'fill="{BAND_F}" stroke="{BAND_S}" stroke-width="0.6"/>')
        o.append(f'<text x="{b.x+5}" y="{b.y+9.4}" font-size="{FS_BAND}" font-style="italic" '
                 f'fill="{BAND_T}">{b.label}</text>')
    for e in d.edges:
        pts = " ".join(f"{x},{y}" for x, y in e.pts)
        dash = ' stroke-dasharray="3.2,2.4"' if e.style == "dashed" else ""
        head = ' marker-end="url(#ah)"' if e.head else ""
        o.append(f'<polyline points="{pts}" fill="none" stroke="{EDGE}" '
                 f'stroke-width="0.85"{dash}{head}/>')
        if e.label:
            lx, ly = _label_at(e)
            wpx = tw(e.label, FS_LBL)
            o.append(f'<rect x="{lx-wpx/2-1.6}" y="{ly-FS_LBL+1.2}" width="{wpx+3.2}" '
                     f'height="{FS_LBL+1.4}" fill="#FFFFFF" opacity="0.95"/>')
            o.append(f'<text x="{lx}" y="{ly}" font-size="{FS_LBL}" fill="{EDGE}" '
                     f'text-anchor="middle">{e.label}</text>')
    for b in d.boxes:
        f, s, t = {"component": (COMP_F, COMP_S, COMP_T), "node": (NODE_F, NODE_S, NODE_T),
                   "store": (STORE_F, STORE_S, STORE_T),
                   "plain": ("#FFFFFF", BAND_S, INK)}[b.kind]
        o.append(f'<rect x="{b.x}" y="{b.y}" width="{b.w}" height="{b.h}" rx="2.2" '
                 f'fill="{f}" stroke="{s}" stroke-width="1"/>')
        if b.kind == "component":     # UML component icon, top right
            ix, iy = b.x + b.w - 13, b.y + 3.4
            o.append(f'<rect x="{ix}" y="{iy}" width="9" height="6.4" fill="{f}" '
                     f'stroke="{s}" stroke-width="0.7"/>')
            for dy in (1.3, 3.6):
                o.append(f'<rect x="{ix-2.6}" y="{iy+dy}" width="4" height="1.9" fill="{f}" '
                         f'stroke="{s}" stroke-width="0.6"/>')
        if b.sub:
            o.append(f'<text x="{b.cx()}" y="{b.y+b.h/2-0.6}" font-size="{FS}" fill="{t}" '
                     f'text-anchor="middle" font-weight="600">{b.title}</text>')
            o.append(f'<text x="{b.cx()}" y="{b.y+b.h/2+8.6}" font-size="{FS_SM}" fill="{t}" '
                     f'text-anchor="middle" opacity="0.85">{b.sub}</text>')
        else:
            bfs = FS_SM if b.kind == "plain" else FS
            wt = "500" if b.kind == "plain" else "600"
            o.append(f'<text x="{b.cx()}" y="{b.cy()+bfs*0.35}" font-size="{bfs}" fill="{t}" '
                     f'text-anchor="middle" font-weight="{wt}">{b.title}</text>')
    for L in d.lolli:
        if L.dir == "right":
            x2 = L.x + L.length
            o.append(f'<line x1="{L.x}" y1="{L.y}" x2="{x2-3.1}" y2="{L.y}" stroke="{COMP_S}" '
                     f'stroke-width="0.85"/>')
            o.append(f'<circle cx="{x2-1.1}" cy="{L.y}" r="3.1" fill="#FFFFFF" '
                     f'stroke="{COMP_S}" stroke-width="0.95"/>')
            o.append(f'<text x="{x2+5.4}" y="{L.y+2.7}" font-size="{FS_SM}" fill="{COMP_T}" '
                     f'text-anchor="start" font-family="monospace">{L.name}</text>')
        else:
            y2 = L.y + L.length
            o.append(f'<line x1="{L.x}" y1="{L.y}" x2="{L.x}" y2="{y2-3.1}" stroke="{COMP_S}" '
                     f'stroke-width="0.85"/>')
            o.append(f'<circle cx="{L.x}" cy="{y2-1.1}" r="3.1" fill="#FFFFFF" '
                     f'stroke="{COMP_S}" stroke-width="0.95"/>')
            o.append(f'<text x="{L.x}" y="{y2+9.4}" font-size="{FS_SM}" fill="{COMP_T}" '
                     f'text-anchor="middle" font-family="monospace">{L.name}</text>')
    for (x, y, txt, anc) in d.notes:
        o.append(f'<text x="{x}" y="{y}" font-size="{FS_SM}" fill="{BAND_T}" '
                 f'font-style="italic" text-anchor="{anc}">{txt}</text>')
    o.append('</svg>')
    return "\n".join(o)

def _label_at(e: Edge):
    segs = list(zip(e.pts, e.pts[1:]))
    total = sum(math.dist(a, b) for a, b in segs)
    want, run = total * e.lpos, 0.0
    for (x1, y1), (x2, y2) in segs:
        L = math.dist((x1, y1), (x2, y2))
        if run + L >= want:
            t = (want - run) / L if L else 0
            return (x1 + (x2 - x1) * t + e.lox,
                    y1 + (y2 - y1) * t - 2.6 + e.loy)
        run += L
    return e.pts[-1][0] + e.lox, e.pts[-1][1] - 2.6 + e.loy

# --------------------------------------------------------------------------- tikz
def to_tikz(d: Diagram) -> str:
    """Same geometry as TikZ. y is flipped so the picture sits upright."""
    H = d.height
    def P(x, y): return f"({x:.1f}pt,{H-y:.1f}pt)"
    o = [f"% GENERATED by svg/gen.py -- do not edit; edit gen.py and re-run.",
         f"\\begin{{tikzpicture}}[x=1pt,y=1pt,line width=0.85pt,",
         f"  every node/.style={{inner sep=0pt,outer sep=0pt}}]",
         f"\\definecolor{{qink}}{{HTML}}{{{INK[1:]}}}",
         f"\\definecolor{{qcf}}{{HTML}}{{{COMP_F[1:]}}}\\definecolor{{qcs}}{{HTML}}{{{COMP_S[1:]}}}",
         f"\\definecolor{{qct}}{{HTML}}{{{COMP_T[1:]}}}\\definecolor{{qbf}}{{HTML}}{{{BAND_F[1:]}}}",
         f"\\definecolor{{qbs}}{{HTML}}{{{BAND_S[1:]}}}\\definecolor{{qbt}}{{HTML}}{{{BAND_T[1:]}}}",
         f"\\definecolor{{qnf}}{{HTML}}{{{NODE_F[1:]}}}\\definecolor{{qns}}{{HTML}}{{{NODE_S[1:]}}}",
         f"\\definecolor{{qnt}}{{HTML}}{{{NODE_T[1:]}}}\\definecolor{{qsf}}{{HTML}}{{{STORE_F[1:]}}}",
         f"\\definecolor{{qss}}{{HTML}}{{{STORE_S[1:]}}}\\definecolor{{qst}}{{HTML}}{{{STORE_T[1:]}}}",
         f"\\definecolor{{qe}}{{HTML}}{{{EDGE[1:]}}}"]
    for b in d.bands:
        o.append(f"\\draw[fill=qbf,draw=qbs,line width=0.6pt,rounded corners=3pt] "
                 f"{P(b.x,b.y)} rectangle {P(b.x+b.w,b.y+b.h)};")
        o.append(f"\\node[anchor=west,text=qbt] at {P(b.x+5,b.y+6.6)} "
                 f"{{\\fontsize{{{FS_BAND}}}{{{FS_BAND*1.2:.1f}}}\\selectfont\\itshape {b.label}}};")
    for e in d.edges:
        dash = ",dash pattern=on 3.2pt off 2.4pt" if e.style == "dashed" else ""
        arrow = "-{Stealth[length=3.6pt,width=2.8pt]}" if e.head else "-"
        path = " -- ".join(P(x, y) for x, y in e.pts)
        o.append(f"\\draw[{arrow},draw=qe{dash}] {path};")
        if e.label:
            lx, ly = _label_at(e)
            o.append(f"\\node[fill=white,inner sep=0.8pt,text=qe] at {P(lx,ly-2.4)} "
                     f"{{\\fontsize{{{FS_LBL}}}{{{FS_LBL*1.2:.1f}}}\\selectfont {e.label}}};")
    for b in d.boxes:
        f, s, t = {"component": ("qcf","qcs","qct"), "node": ("qnf","qns","qnt"),
                   "store": ("qsf","qss","qst"), "plain": ("white","qbs","qink")}[b.kind]
        o.append(f"\\draw[fill={f},draw={s},line width=1pt,rounded corners=2.2pt] "
                 f"{P(b.x,b.y)} rectangle {P(b.x+b.w,b.y+b.h)};")
        if b.kind == "component":
            ix, iy = b.x + b.w - 13, b.y + 3.4
            o.append(f"\\draw[fill={f},draw={s},line width=0.7pt] {P(ix,iy)} rectangle {P(ix+9,iy+6.4)};")
            for dy in (1.3, 3.6):
                o.append(f"\\draw[fill={f},draw={s},line width=0.6pt] "
                         f"{P(ix-2.6,iy+dy)} rectangle {P(ix+1.4,iy+dy+1.9)};")
        if b.sub:
            o.append(f"\\node[text=%s] at %s {{\\fontsize{{{FS}}}{{{FS*1.2:.1f}}}\\selectfont"
                     f"\\bfseries {b.title}}};" % (t, P(b.cx(), b.y+b.h/2-3.6)))
            o.append(f"\\node[text=%s] at %s {{\\fontsize{{{FS_SM}}}{{{FS_SM*1.2:.1f}}}\\selectfont"
                     f" {b.sub}}};" % (t, P(b.cx(), b.y+b.h/2+5.6)))
        else:
            bfs = FS_SM if b.kind == "plain" else FS
            bold = "" if b.kind == "plain" else "\\bfseries "
            o.append(f"\\node[text=%s] at %s {{\\fontsize{{{bfs}}}{{{bfs*1.2:.1f}}}\\selectfont"
                     f"{bold}{b.title}}};" % (t, P(b.cx(), b.cy())))
    for L in d.lolli:
        if L.dir == "right":
            x2 = L.x + L.length
            o.append(f"\\draw[draw=qcs,line width=0.85pt] {P(L.x,L.y)} -- {P(x2-3.1,L.y)};")
            o.append(f"\\draw[fill=white,draw=qcs,line width=0.95pt] {P(x2-1.1,L.y)} circle (3.1pt);")
            o.append(f"\\node[anchor=west,text=qct] at {P(x2+5.4,L.y)} "
                     f"{{\\fontsize{{{FS_SM}}}{{{FS_SM*1.2:.1f}}}\\selectfont\\texttt{{{L.name}}}}};")
        else:
            y2 = L.y + L.length
            o.append(f"\\draw[draw=qcs,line width=0.85pt] {P(L.x,L.y)} -- {P(L.x,y2-3.1)};")
            o.append(f"\\draw[fill=white,draw=qcs,line width=0.95pt] {P(L.x,y2-1.1)} circle (3.1pt);")
            o.append(f"\\node[text=qct] at {P(L.x,y2+6.6)} "
                     f"{{\\fontsize{{{FS_SM}}}{{{FS_SM*1.2:.1f}}}\\selectfont\\texttt{{{L.name}}}}};")
    for (x, y, txt, anc) in d.notes:
        a = {"middle": "", "start": "anchor=west,", "end": "anchor=east,"}[anc]
        o.append(f"\\node[{a}text=qbt] at {P(x,y-2.6)} "
                 f"{{\\fontsize{{{FS_SM}}}{{{FS_SM*1.2:.1f}}}\\selectfont\\itshape {txt}}};")
    o.append("\\end{tikzpicture}%")
    return "\n".join(o)
