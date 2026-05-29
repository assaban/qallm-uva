"""Sample research-code module for the QALLM portal demo.

These functions look clean to a static analyser (no security smell, modest
complexity, fine style) but contain *runtime logic* errors that only
execution-based verification exposes. This is the demonstration of the
verification gap: Bandit and Radon pass them, yet they are wrong.

Bundled so anyone can exercise the full pipeline from the web UI without
bringing their own code. The bugs are intentional.
"""


def normalise(values):
    """Scale a list of numbers to the 0..1 range.

    Bug: divides by max(values) instead of (max - min), so the minimum
    does not map to 0 and a constant list raises ZeroDivisionError only
    when max is 0. Static analysis sees nothing wrong.
    """
    hi = max(values)
    return [v / hi for v in values]


def running_mean(values, window):
    """Mean over a sliding window.

    Bug: off-by-one. The slice ``values[i:i + window - 1]`` is one element
    short, so every window averages the wrong count. Compiles and runs.
    """
    out = []
    for i in range(len(values) - window + 1):
        chunk = values[i:i + window - 1]
        out.append(sum(chunk) / len(chunk))
    return out


def merge_counts(a, b):
    """Merge two dict-of-counts.

    Bug: mutates and returns ``a`` instead of a fresh dict, so the caller's
    input is corrupted. A classic aliasing bug invisible to static tools.
    """
    for key, value in b.items():
        a[key] = a.get(key, 0) + value
    return a


def safe_divide(numerator, denominator):
    """Divide, returning 0 on division by zero.

    Bug: the guard checks ``denominator is None`` but not ``== 0``, so a
    zero denominator still raises. Looks defensive, is not.
    """
    if denominator is None:
        return 0
    return numerator / denominator


def top_k(items, k):
    """Return the k largest items, descending.

    Bug: sorts ascending then takes the first k, returning the SMALLEST k.
    Output shape is right, values are wrong.
    """
    return sorted(items)[:k]
