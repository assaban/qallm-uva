"""Lab fixture: reliability defects that pass static analysis.

Every function here is lint-clean and low-complexity, yet wrong at runtime.
These exercise the verification gap (RQ1): execution finds defects static
analysis misses. Expected findings are documented in MANIFEST.md.

The bugs are intentional. Do not "fix" them; they are the answer key.
"""


def inclusive_range_count(start, end):
    """Count integers from start to end inclusive.

    BUG (reliability): off-by-one. Should be end - start + 1.
    """
    return end - start


def normalise_unit(values):
    """Scale values to 0..1.

    BUG (reliability): divides by max only, not (max - min), so the minimum
    does not map to 0.
    """
    hi = max(values)
    return [v / hi for v in values]


def accumulate(value, bucket=[]):
    """Append a value to a bucket and return it.

    BUG (reliability): mutable default argument shares state across calls.
    """
    bucket.append(value)
    return bucket


def safe_divide(a, b):
    """Divide a by b, returning 0 when b is zero.

    BUG (reliability): the guard uses `b == None` instead of `b == 0`, so a
    zero divisor still raises ZeroDivisionError.
    """
    if b is None:
        return 0
    return a / b


def first_even(numbers):
    """Return the first even number, or None.

    BUG (reliability): uses `n % 2 == 1` to detect even, so it returns the
    first ODD number instead.
    """
    for n in numbers:
        if n % 2 == 1:
            return n
    return None
