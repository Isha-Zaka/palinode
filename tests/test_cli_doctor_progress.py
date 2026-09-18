"""Human-readable full doctor output reports progress as checks complete."""
from __future__ import annotations

import importlib
import json

from click.testing import CliRunner

from palinode.diagnostics.types import CheckResult


doctor_module = importlib.import_module("palinode.cli.doctor")


def _result(name: str) -> CheckResult:
    return CheckResult(name=name, severity="info", passed=True, message="complete")


def test_full_text_doctor_prints_each_result_before_the_runner_returns(monkeypatch):
    """A slow later check cannot make the text CLI look silently hung."""
    printed: list[str] = []
    first = _result("first")
    second = _result("second")

    monkeypatch.setattr(
        doctor_module.console,
        "print",
        lambda value="", **_kwargs: printed.append(str(value)),
    )

    def fake_run_all(ctx, *, tag=None, timeout_s=15.0, on_result=None):
        assert on_result is not None
        on_result(first)
        assert any("first: complete" in value for value in printed)
        on_result(second)
        return [first, second]

    monkeypatch.setattr("palinode.diagnostics.runner.run_all", fake_run_all)

    result = CliRunner().invoke(doctor_module.doctor)

    assert result.exit_code == 0
    assert printed.index("Palinode Diagnostics") < next(
        index for index, value in enumerate(printed) if "first: complete" in value
    )
    assert any("second: complete" in value for value in printed)


def test_full_json_doctor_remains_one_machine_readable_document(monkeypatch):
    """Progress output is deliberately limited to the human text mode."""
    only = _result("only")

    def fake_run_all(ctx, *, tag=None, timeout_s=15.0, on_result=None):
        assert on_result is None
        return [only]

    monkeypatch.setattr("palinode.diagnostics.runner.run_all", fake_run_all)

    result = CliRunner().invoke(doctor_module.doctor, ["--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == [
        {
            "name": "only",
            "severity": "info",
            "passed": True,
            "message": "complete",
            "remediation": None,
            "linked_issue": None,
        }
    ]
