# Scope of work: making security findings confirm (not inconclusive)

A decision aid for whether to invest in turning security findings from
"inconclusive" into "confirmed" on the RQ2 path. Written so you can decide, not
to push a direction.

## The current behaviour

For a SECURITY finding (e.g. `eval(user_input)`, `subprocess.run(..., shell=True)`),
QALLM generates a targeted test whose job is to demonstrate the unsafe effect
actually occurs. A verdict of "confirmed" requires that test to PASS (the unsafe
behaviour was reachable). On the lab set, those tests instead error under the
sandbox, so they land "inconclusive". The reliability path is unaffected; this
is only about security findings.

## Why it is hard

The difficulty is not in QALLM's plumbing; it is the nature of demonstrating an
exploit safely and observably:

1. **Demonstrating eval/shell safely.** To "confirm" `eval(expr)` you must make
   it do something observable without doing something harmful. The test has to
   supply an input that proves arbitrary evaluation (e.g. evaluate `2+2` and
   assert `4`, or set a sentinel via a side effect) without ever running
   anything dangerous. That is a careful, finding-specific test design.
2. **The sandbox fights you, correctly.** The execution sandbox is built to
   contain code. A shell or filesystem side effect that an exploit test wants to
   observe is often exactly what the sandbox blocks or isolates, so the test
   errors rather than demonstrating the effect. Loosening the sandbox to let the
   exploit through is the opposite of what a security tool should do.
3. **The LLM must generate a sound exploit oracle.** The correctness oracle was
   hard enough to calibrate; a security-exploit oracle is harder, it must be
   safe, observable, and specific to the finding type (eval vs shell vs
   deserialization each differ).

## Scope of work (if pursued)

A realistic, bounded version, not "confirm any vulnerability":

- **A2 (small):** Restrict to two well-understood finding classes, `eval`/`exec`
  and `subprocess(..., shell=True)`. Add a dedicated security-oracle prompt that
  asks for a safe, observable demonstration (evaluate a benign arithmetic
  sentinel through the eval path; echo a unique token through the shell path and
  capture it). ~2 to 3 days including prompt iteration.
- **A3 (medium):** Add a controlled-observation channel in the sandbox: a
  per-run temp file or captured stdout the exploit test can write a sentinel to,
  so "the unsafe path executed" is observable without a real harmful effect.
  This is the load-bearing, risky part. ~3 to 5 days, plus careful review,
  because it touches the sandbox's isolation.
- **A4 (validation):** Re-calibrate on the lab security file (expect the 3
  mappable findings to confirm), and add tests so a future change cannot
  silently re-break it. ~1 to 2 days.

Total: roughly 1.5 to 2 weeks of focused work, most of the risk concentrated in
A3.

## Feasibility

Technically feasible for the narrow eval/shell classes. Not feasible as a
general "confirm any security finding" capability within the thesis timeline,
and not advisable to attempt generally. The narrow version is the only sensible
scope.

## Risk analysis

- **Sandbox integrity (high).** Any change that lets an exploit test observe a
  side effect risks weakening the isolation that protects the host running the
  experiments (especially on the VM). A bug here is a security risk in a
  security tool, the worst kind of irony. This is the dominant risk.
- **Re-calibration cost (medium).** A new oracle type means re-running and
  re-validating; it could surface its own false positives/negatives that need
  another calibration cycle, exactly the kind of cycle that consumed weeks
  earlier.
- **Scope creep (medium).** "Make security confirm" invites "what about
  deserialization, SSRF, path traversal", a long tail that does not end.
- **Opportunity cost (high right now).** The headline (E1, the ENVRI gap rate)
  is the thesis's central result and is reliability-driven. Time spent here is
  time not spent on the headline and the write-up.

## Benefit analysis

- **Marginal benefit to the thesis.** RQ2's strength is already demonstrable on
  the reliability path. A non-zero security-confirmation number is a nice-to-have,
  not load-bearing. The "security confirmation is often inconclusive" result is
  itself a clean, honest, defensible finding, arguably more interesting than a
  forced number, because it shows QALLM knows the limits of execution
  adjudication.
- **It does not move RQ1.** The verification gap (the headline) does not depend
  on security confirmation at all.

## Recommendation

**Do not pursue it for the thesis. Document the inconclusive result instead.**
The honest framing is strong: execution strongly adjudicates reliability defects
(where the verification gap lives), and is appropriately conservative about
security findings, demonstrating an exploit safely and observably is a hard
problem, and QALLM reports "inconclusive" rather than overclaiming. That is a
mature, examiner-friendly position. If, after the thesis, there is appetite to
extend QALLM, the narrow A2+A3+A4 scope above is the way to do it, with the
sandbox-integrity risk treated as the gating concern.

The decision rule: pursue only if a non-zero security-confirmation number is a
stated requirement from a supervisor. Absent that, the inconclusive finding is
the better use of the remaining time.
