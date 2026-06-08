"""Lab fixture: complexity and maintainability findings.

These carry findings about the *source* (high cyclomatic complexity, poor
maintainability) rather than runtime behaviour. They should classify as
"not execution testable" in confirm/refute, exercising that branch. Expected
findings are documented in MANIFEST.md.
"""


def deeply_nested(a, b, c, d, e):
    """High cyclomatic complexity via nested branching.

    FINDING (complexity): many branches; Radon should rate this poorly. The
    function is correct, so execution finds no bug; the finding is about
    structure, not behaviour (not execution-testable).
    """
    total = 0
    if a > 0:
        if b > 0:
            if c > 0:
                if d > 0:
                    if e > 0:
                        total += 1
                    else:
                        total -= 1
                else:
                    total += 2
            else:
                total += 3
        else:
            total += 4
    else:
        total += 5
    return total


def cryptic(x):
    """Poor maintainability: single-letter names, no structure.

    FINDING (maintainability): low maintainability index. Behaviour is
    correct (doubles then offsets), so there is no runtime defect to confirm.
    """
    q = x * 2
    z = q + 1
    w = z - 1
    return w + q - x
