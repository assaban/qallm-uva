"""Lab fixture: correct, clean code (negative control).

These functions are correct, simple, and secure. A sound pipeline should find
no runtime defects and no security findings here. This is the negative control:
if QALLM reports bugs in this file, that is a false positive worth
investigating. Expected findings are documented in MANIFEST.md (none).
"""


def add(a, b):
    """Return the sum of two numbers."""
    return a + b


def clamp(value, low, high):
    """Constrain value to the [low, high] range."""
    if value < low:
        return low
    if value > high:
        return high
    return value


def word_count(text):
    """Count whitespace-separated words in a string."""
    return len(text.split())


def safe_mean(values):
    """Arithmetic mean, returning None for an empty input (no crash)."""
    if not values:
        return None
    return sum(values) / len(values)
