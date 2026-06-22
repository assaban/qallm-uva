# RQ2 reframe: reliability confirmation from gap defects

## The problem (from the E2 run)

E2 (confirm on, full ENVRI corpus) returned confirmed = 0. Diagnosis: static
analysers never emit RELIABILITY findings (Bandit = SECURITY, Radon =
COMPLEXITY/MAINTAINABILITY, SonarQube = MAINTAINABILITY). The static-finding
confirm path can therefore only reach SECURITY findings, which are inconclusive
by design. The reliability defects have no static finding to confirm, because
static analysis missing them is the definition of the gap.

## The reframe (MD-006)

Treat each execution-only gap defect as a confirmed reliability defect: its
round-0 correctness test failed against the original code, which is the
reproduction. RQ3 re-runs that test against the repaired code; a pass is a
verified fix. Static-finding confirmation is kept and reported separately.

## Evidence (reliability_gap lab session)

- Reliability confirmations: 5 (the five seeded defects), was 0.
- Verified-fix: 4 fixed, 1 not fixed (accumulate), rate 0.8.
- The not-fixed case is a true negative: the reproducing test still fails on the
  repaired variant, consistent with the cross-evaluation.

A subtlety fixed along the way: the reproducing tests import the source under a
specific module name (source_<unit>_c0); the repaired source must be written
under that name or the test cannot import it and the fix verdict is spuriously
inconclusive. The module name is now derived from the test's import line.

## For the next full run

Re-run E2 (confirm on) from a CLEAN dev tree. Expect a real confirmation count
(the gap defects) and a real verified-fix rate. The static-finding side will
still be security-inconclusive, reported separately.

## Open, unrelated: the 186 errored notebooks

186 of 203 errored inputs fail with 'str' object has no attribute 'get'. The
NotebookAdapter guard (commit 8f9729f) was present in both run commits, so the
error is downstream of ingestion, inside orch.run(), not the parser. The exact
line needs a triggering notebook. The runner now logs the full traceback at
warning level (was debug), so the next run will surface the stack. Send a couple
of those tracebacks and the fix is quick.
