# E1 headline results, first pass analysis

Analysis of the first completed E1 run (`runs/e1_rq1_headline`, commit 1c54122,
ENVRI corpus). This is the RQ1-only pass (`--confirm` off). A second E1 run is
in progress under the current code; this records what the first run shows and
flags what to watch in the second.

## Protocol (from the manifest)

ENVRI corpus, 1843 input notebooks, correctness oracle, 5 rounds, samples 1,
mutation confidence on, feedback strategy, FedLLM (gpt-oss-120b), `--confirm`
off. Run was on a dirty tree at commit 1c54122 (predates the repaired-source
confidence fix and the errored-unit surfacing).

## Headline counts (the real RQ1 result)

Of 1843 input notebooks: 1640 analysed successfully, 203 (11.0 percent) errored
and were dropped. Across the 1640 successful notebooks there were 767 with at
least one execution-testable function, 3688 execution-testable functions in
total, and 679 execution-only defects, that is, defects that passed static
analysis but failed under execution. That is a defect in roughly 18 percent of
execution-testable functions that static analysis missed entirely, and 241
notebooks where execution surfaced at least one defect static analysis did not.
Static analysis raised 1956 findings over the same corpus.

This is the verification gap made concrete on real research code: static
analysers, which never run the code, missed hundreds of real defects that one
execution pass surfaced.

## Why the aggregate gap rate of 1.0 must NOT be reported as the result

The aggregate `verification_gap_rate` is 1.0 with a CI of [1.0, 1.0]. This is a
degenerate artifact, not a finding. The rate is defined as
`execution_only_bugs / (confirmed_findings + execution_only_bugs)`, and in an
RQ1-only run (`--confirm` off) `confirmed_findings` is always 0, so the rate
collapses to `bugs / bugs = 1.0` whenever any bug exists. The per-session values
confirm this is purely structural: of the 1640 sessions, 1372 have a null rate
(no execution-testable function, correctly undefined, not zero) and the 268
defined ones are spread across the range (160 at 1.0, 27 at 0.0, and many in
between). The flat aggregate 1.0 is the degenerate denominator, nothing more.

The meaningful gap RATE comes from the `--confirm` run (E2), where
`confirmed_findings` is populated. For RQ1, report the counts above. For the
rate with a real denominator and CI, use E2.

## Two issues to fix or watch in the second run

Errored notebooks (11 percent loss). 203 notebooks errored and were dropped;
186 of them with the same `'str' object has no attribute 'get'` error, plus a
handful of malformed-JSON notebooks. The single recurring error is an ingestion
bug worth fixing so the corpus is not silently reduced by a ninth. Either way,
the errored count must be surfaced in the aggregate denominator (per the
independent audit) so a reader can tell "clean" from "could not be measured";
right now the 11 percent simply vanished.

Confidence labels (pre-fix). The confidence distribution is 10 high, 669
unknown. This run predates the repaired-source confidence fix, so the unknowns
are expected and not informative. The second run, under current code, should
show a real high/low/medium spread. Re-score over artefacts if needed.

## What to do with the second E1 run

Confirm the counts reproduce (they should; the count path was correct in both
builds). Check the confidence distribution is no longer dominated by unknown.
Check the errored-notebook count: if the ingestion bug is fixed, the loss should
drop sharply; if not, surface the count in the aggregate. Then run E2 (the
`--confirm` pass) for the meaningful gap rate, the confirmation rate, and the
verified-fix rate, which are the numbers the thesis headline and RQ2/RQ3 need.
