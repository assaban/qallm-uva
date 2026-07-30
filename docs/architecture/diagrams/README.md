# Architecture diagrams

Sources for the architecture figures in the thesis and the defence deck.
Generated output is not committed; run `make`.

## Why these are hand-laid-out

Both auto-layout engines were tried first and both failed, in different ways that
are worth recording so nobody repeats the experiment.

**PlantUML** produced correct UML but placed the `StaticCodeAnalyzer` interface in
the right margin with an edge spanning 0.92 of the canvas diagonal, and stranded
the `Judge` interface unattached on the left. Crossing counts did not reveal this;
the useful metric turned out to be the longest edge as a fraction of the canvas
diagonal, because a single corner-to-corner edge is what makes a figure read as
spaghetti.

**Mermaid** fixed the edge lengths (longest edge 0.10 of the diagonal) but
produced generic boxes-in-tiers flowcharts rather than software engineering
diagrams: no component notation, no interface notation, no control over placement.

`gen.py` therefore draws from explicit coordinates. That buys three things an
auto-layout engine cannot give:

1. **Proper UML.** Component boxes carry the component icon; required interfaces
   are ball-and-stick with their implementations drawn as realization boxes.
2. **Every edge orthogonal by construction**, with waypoints chosen rather than
   solved for.
3. **Authored at final size.** 369pt wide, which is the thesis `\linewidth`, at a
   9pt base font, so the figure is included at scale 1.0 and the type on the page
   is exactly 9pt. The first TikZ attempt measured 3.0pt on the page.

## The check pass is the point

`gen.py` has a `check()` that asserts, for every diagram: no two boxes overlap
(except legitimate nesting), no text overflows its box, every edge segment is
orthogonal, and no edge passes through a box. `make check` runs it and exits
non-zero on failure.

This exists because the diagrams were authored in an environment where the
rendered image could not be viewed. It is not a formality: it caught six real
defects in the deployment diagram and eighteen in the component diagram during
development, each of which would have shipped as a visible flaw.

If you change a diagram, run `make check` before you trust it.

## Two backends, one geometry

`to_svg()` and `to_tikz()` emit the same coordinates. SVG for direct use in slides
or on the web; TikZ for LaTeX, where it beats an included image because it picks up
the document's fonts. An exact-size vector PDF is also produced from the SVG for
anyone who would rather use `\includegraphics`.

## The sequence diagram stays on PlantUML

`round.puml`. A sequence diagram is a solved layout problem and PlantUML renders
it well, so there was nothing to gain by drawing it by hand. Mermaid was measured
here too and lost: 5.6pt on the page against PlantUML's 10.2pt for identical
content.
