# Architecture diagrams. Everything is generated; never hand-edit output.
#
#   make            SVG + TikZ + exact-size PDF + PNG for every diagram
#   make check      run the layout assertions only
#   make sequence   rebuild the sequence diagram (PlantUML)
#
# The three structural diagrams are hand-laid-out in diagrams.py, not produced by
# an auto-layout engine. See README.md for why.
PY       ?= python3
CHROME   ?= google-chrome
PLANTUML ?= plantuml.jar
OUT      := out

.PHONY: all check sequence clean
all: check pdf png sequence

check:
	$(PY) diagrams.py

pdf: check
	@for f in component deployment verification; do \
	  $(PY) - $$f <<-'EOS' ;\
	import re,sys,pathlib ;\
	n=sys.argv[1]; s=pathlib.Path(f"out/qallm-{n}.svg").read_text() ;\
	m=re.search(r'width="([\d.]+)pt" height="([\d.]+)pt"', s) ;\
	pathlib.Path(f"out/wrap-{n}.html").write_text('<!doctype html><html><head><meta charset="utf-8"><style>@page{size:%spt %spt;margin:0}html,body{margin:0;padding:0}svg{display:block}</style></head><body>%s</body></html>' % (m.group(1), m.group(2), s)) ;\
	EOS \
	  $(CHROME) --headless --no-sandbox --disable-gpu --no-pdf-header-footer \
	    --print-to-pdf=$(OUT)/qallm-$$f.pdf "file://$(CURDIR)/$(OUT)/wrap-$$f.html" ; \
	  rm -f $(OUT)/wrap-$$f.html ; \
	done

png: check
	@for f in component deployment verification; do \
	  $(CHROME) --headless --no-sandbox --disable-gpu --hide-scrollbars \
	    --force-device-scale-factor=4 --window-size=1476,1800 \
	    --screenshot=$(OUT)/qallm-$$f.png "file://$(CURDIR)/$(OUT)/qallm-$$f.svg" ; \
	done

sequence:
	$(PY) mkstyle.py 40 > _style.iuml
	java -jar $(PLANTUML) -tlatex round.puml

clean:
	rm -rf $(OUT) _style.iuml round.tex
