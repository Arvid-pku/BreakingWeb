"""Static analysis tests for scripts/run_gmail_sweep.sh.

These tests parse the shell script and verify structural correctness
without executing it.
"""

import re
from pathlib import Path

import pytest

SWEEP_SCRIPT = Path("scripts/run_gmail_sweep.sh")


@pytest.fixture
def script_text():
    return SWEEP_SCRIPT.read_text()


class TestH4HeredocSysArgv:
    """Bug H4: Heredoc python blocks that use sys.argv must pass arguments
    via `python3 -` (with dash) so that shell arguments reach sys.argv."""

    def test_all_heredoc_blocks_with_sysargv_use_dash(self, script_text):
        """Every `python3 << ...` heredoc that references sys.argv must use
        `python3 -` so that positional arguments are forwarded."""
        # Find all python3 heredoc invocations (python3 ... << 'DELIM' or << DELIM)
        # Capture everything from python3 to the heredoc delimiter, then the body
        heredoc_pattern = re.compile(
            r"(python3\s+.*?)\s*<<\s*'?(\w+)'?\s*\n(.*?)\n\2",
            re.DOTALL,
        )
        for match in heredoc_pattern.finditer(script_text):
            invocation = match.group(1).strip()
            delimiter = match.group(2)
            body = match.group(3)

            if "sys.argv" in body:
                assert (
                    "python3 -" in invocation or "python3  -" in invocation
                ), (
                    f"Heredoc block (delimiter={delimiter}) references sys.argv "
                    f"but invocation does not use 'python3 -': {invocation!r}"
                )

    def test_merge_heredoc_passes_rundir(self, script_text):
        """The merge section's PYEOF heredoc must pass $RUNDIR as an argument."""
        # Find the PYEOF heredoc invocation line
        pyeof_match = re.search(r"(python3\s+.*?)\s*<<\s*'?PYEOF'?", script_text)
        assert pyeof_match is not None, "Could not find PYEOF heredoc in script"
        invocation = pyeof_match.group(1)
        assert "python3 -" in invocation, (
            f"PYEOF heredoc invocation must use 'python3 -' to accept args: {invocation!r}"
        )
        # Verify $RUNDIR is passed as an argument
        full_line = script_text[pyeof_match.start() : pyeof_match.end()]
        assert "$RUNDIR" in full_line or "${RUNDIR}" in full_line, (
            f"PYEOF heredoc must pass $RUNDIR as argument: {full_line!r}"
        )


class TestH7SmokeTestHarness:
    """Bug H7: The smoke test invocation must include the harness flag
    so that non-default harnesses (e.g. browser-use) are used."""

    def _extract_smoke_test_block(self, script_text: str) -> str:
        """Extract the smoke test section of the script."""
        # Find from "SMOKE TEST" marker to the smoke check
        start = script_text.find("# ── Smoke test")
        end = script_text.find("# Check smoke results")
        assert start != -1, "Could not find smoke test section"
        assert end != -1, "Could not find smoke check section"
        return script_text[start:end]

    def test_harness_flag_defined_before_smoke_invocation(self, script_text):
        """HARNESS_FLAG must be defined in the smoke test section."""
        smoke_block = self._extract_smoke_test_block(script_text)
        assert "HARNESS_FLAG" in smoke_block, (
            "Smoke test section must define HARNESS_FLAG variable"
        )

    def test_harness_flag_used_in_smoke_invocation(self, script_text):
        """The smoke test python invocation must include $HARNESS_FLAG."""
        smoke_block = self._extract_smoke_test_block(script_text)
        # Find the agent_eval invocation within the smoke block
        assert "breakingweb.agent_eval" in smoke_block, (
            "Smoke test must invoke breakingweb.agent_eval"
        )
        # Check that HARNESS_FLAG appears in the invocation
        assert "$HARNESS_FLAG" in smoke_block or "${HARNESS_FLAG}" in smoke_block, (
            "Smoke test invocation must include $HARNESS_FLAG"
        )

    def test_harness_flag_checks_harness_variable(self, script_text):
        """HARNESS_FLAG definition must reference the HARNESS variable."""
        smoke_block = self._extract_smoke_test_block(script_text)
        # Find the HARNESS_FLAG assignment block
        assert re.search(
            r'HARNESS_FLAG.*\n.*\$HARNESS|HARNESS_FLAG.*--harness.*\$HARNESS',
            smoke_block,
        ), "HARNESS_FLAG must be set based on $HARNESS variable"
