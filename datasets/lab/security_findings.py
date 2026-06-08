"""Lab fixture: security-relevant code.

These carry findings a static security analyser (Bandit) flags. Execution-based
confirmation (RQ2) decides which are genuinely reachable/exploitable. Expected
findings are documented in MANIFEST.md.

The issues are intentional. This file is an answer key, not production code.
"""

import subprocess


def evaluate_expression(expr):
    """Evaluate a user-supplied arithmetic expression.

    FINDING (security): uses eval on external input, arbitrary code execution.
    Execution can confirm by demonstrating an injected call runs.
    """
    return eval(expr)  # noqa: S307


def run_echo(user_input):
    """Echo user input via the shell.

    FINDING (security): shell=True with interpolated input, command injection.
    """
    subprocess.run(f"echo {user_input}", shell=True, check=False)  # noqa: S602


def build_query(table, user_id):
    """Build a SQL query string.

    FINDING (security): string-formatted SQL, injection. No execution oracle
    here (no DB), so this should classify as a finding that is not directly
    execution-confirmable in the lab set, useful for testing that path.
    """
    return f"SELECT * FROM {table} WHERE id = {user_id}"  # noqa: S608
