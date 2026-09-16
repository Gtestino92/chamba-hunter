from pathlib import Path
import subprocess

import pytest

from chamba_hunter.commands import (
    refresh_startups,
)


DOWNSTREAM_MODULES = (
    "canonicalize_job_leads",
    "classify_argentina_eligibility",
    "classify_job_occupations",
    "classify_job_skills",
    "classify_job_seniority",
    "match_jobs",
    "prioritize_jobs",
)

ATS_MODULE_FRAGMENTS = (
    "discover_known_ats",
    "discover_broad_ats",
    "sync_greenhouse_jobs",
    "sync_lever_jobs",
    "sync_ashby_jobs",
    "sync_workable_jobs",
    "sync_smartrecruiters_jobs",
    "sync_bamboohr_jobs",
    "sync_hiringroom_jobs",
    "sync_teamtailor_jobs",
    "sync_hibob_jobs",
    "sync_successfactors_jobs",
)


def _settings(
    *,
    deep: bool = False,
    yc_limit: int | None = None,
    hn_limit: int | None = None,
) -> refresh_startups.StartupRefreshSettings:
    return refresh_startups.resolve_settings(
        deep=deep,
        yc_limit=yc_limit,
        hn_limit=hn_limit,
    )


def _build_plan(
    *,
    skip_yc: bool = False,
    skip_hn: bool = False,
    skip_export: bool = False,
    yc_limit: int | None = 50,
    hn_limit: int | None = 100,
    output: Path = Path(
        "output/chamba-shortlist.xlsx"
    ),
) -> list[refresh_startups.RefreshStep]:
    return refresh_startups.build_plan(
        skip_yc=skip_yc,
        skip_hn=skip_hn,
        skip_export=skip_export,
        yc_limit=yc_limit,
        hn_limit=hn_limit,
        output=output,
    )


def _modules(
    plan: list[refresh_startups.RefreshStep],
) -> list[str]:
    return [
        step.module
        for step in plan
    ]


def _step(
    plan: list[refresh_startups.RefreshStep],
    module: str,
) -> refresh_startups.RefreshStep:
    return [
        step
        for step in plan
        if step.module == module
    ][0]


def test_routine_settings_use_routine_defaults() -> None:
    settings = _settings()

    assert settings.search_depth == "ROUTINE"
    assert settings.yc_limit == 50
    assert settings.hn_limit == 100


def test_deep_settings_use_unlimited_defaults() -> None:
    settings = _settings(
        deep=True,
    )

    assert settings.search_depth == "DEEP"
    assert settings.yc_limit is None
    assert settings.hn_limit is None


def test_explicit_source_limits_override_routine_defaults() -> None:
    settings = _settings(
        yc_limit=10,
        hn_limit=20,
    )

    assert settings.yc_limit == 10
    assert settings.hn_limit == 20


def test_explicit_source_limits_override_deep_defaults() -> None:
    settings = _settings(
        deep=True,
        yc_limit=25,
        hn_limit=50,
    )

    assert settings.yc_limit == 25
    assert settings.hn_limit == 50


def test_zero_source_limits_mean_unlimited() -> None:
    settings = _settings(
        yc_limit=0,
        hn_limit=0,
    )

    assert settings.yc_limit is None
    assert settings.hn_limit is None


def test_negative_source_limits_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        refresh_startups.sys,
        "argv",
        [
            "refresh_startups",
            "--yc-limit",
            "-1",
        ],
    )

    with pytest.raises(
        SystemExit
    ):
        refresh_startups.main()

    monkeypatch.setattr(
        refresh_startups.sys,
        "argv",
        [
            "refresh_startups",
            "--hn-limit",
            "-1",
        ],
    )

    with pytest.raises(
        SystemExit
    ):
        refresh_startups.main()


def test_routine_build_plan_contains_bounded_source_limits() -> None:
    plan = _build_plan()

    assert _step(
        plan,
        "acquire_yc_jobs",
    ).arguments == (
        "--limit",
        "50",
    )
    assert _step(
        plan,
        "acquire_hn_jobs",
    ).arguments == (
        "--limit",
        "100",
    )


def test_deep_build_plan_contains_unlimited_sources() -> None:
    plan = _build_plan(
        yc_limit=None,
        hn_limit=None,
    )

    assert _step(
        plan,
        "acquire_yc_jobs",
    ).arguments == ()
    assert _step(
        plan,
        "acquire_hn_jobs",
    ).arguments == ()


def test_skip_yc_removes_only_yc_acquisition() -> None:
    modules = _modules(
        _build_plan(
            skip_yc=True,
        )
    )

    assert "acquire_yc_jobs" not in modules
    assert "acquire_hn_jobs" in modules
    assert DOWNSTREAM_MODULES[0] in modules


def test_skip_hn_removes_only_hn_acquisition() -> None:
    modules = _modules(
        _build_plan(
            skip_hn=True,
        )
    )

    assert "acquire_yc_jobs" in modules
    assert "acquire_hn_jobs" not in modules
    assert DOWNSTREAM_MODULES[0] in modules


def test_both_source_skips_retain_downstream_processing() -> None:
    modules = _modules(
        _build_plan(
            skip_yc=True,
            skip_hn=True,
        )
    )

    assert modules[: len(
        DOWNSTREAM_MODULES
    )] == list(
        DOWNSTREAM_MODULES
    )


def test_downstream_order_is_exact() -> None:
    modules = _modules(
        _build_plan(
            skip_yc=True,
            skip_hn=True,
            skip_export=True,
        )
    )

    assert modules == list(
        DOWNSTREAM_MODULES
    )


def test_matching_receives_apply_and_top_zero() -> None:
    plan = _build_plan()

    assert _step(
        plan,
        "match_jobs",
    ).arguments == (
        "--apply",
        "--top",
        "0",
    )


def test_priority_receives_apply_and_top_zero() -> None:
    plan = _build_plan()

    assert _step(
        plan,
        "prioritize_jobs",
    ).arguments == (
        "--apply",
        "--top",
        "0",
    )


def test_export_shortlist_is_last_by_default() -> None:
    plan = _build_plan()

    assert plan[-1].module == "export_shortlist"
    assert plan[-1].arguments[0] == "--output"
    assert Path(
        plan[-1].arguments[1]
    ) == Path(
        "output/chamba-shortlist.xlsx"
    )


def test_skip_export_removes_export_only() -> None:
    with_export = _modules(
        _build_plan()
    )
    without_export = _modules(
        _build_plan(
            skip_export=True,
        )
    )

    assert "export_shortlist" in with_export
    assert "export_shortlist" not in without_export
    assert without_export == with_export[:-1]


def test_custom_output_is_propagated() -> None:
    plan = _build_plan(
        output=Path(
            "output/custom.xlsx"
        ),
    )

    assert plan[-1].arguments[0] == "--output"
    assert Path(
        plan[-1].arguments[1]
    ) == Path(
        "output/custom.xlsx"
    )


def test_plan_only_mode_invokes_zero_subprocesses(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError(
            "plan-only mode must not execute subprocesses"
        )

    monkeypatch.setattr(
        refresh_startups.subprocess,
        "run",
        fail_if_called,
    )
    monkeypatch.setattr(
        refresh_startups.sys,
        "argv",
        [
            "refresh_startups",
        ],
    )

    refresh_startups.main()

    output = capsys.readouterr().out

    assert "Mode: PLAN ONLY" in output
    assert "Search depth: ROUTINE" in output
    assert "YC limit: 50" in output
    assert "HN limit: 100" in output
    assert "No commands were executed." in output


def test_apply_executes_subprocesses_in_exact_plan_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def capture_run(command, check):
        calls.append(
            command
        )
        return subprocess.CompletedProcess(
            command,
            0,
        )

    monkeypatch.setattr(
        refresh_startups.subprocess,
        "run",
        capture_run,
    )
    monkeypatch.setattr(
        refresh_startups.sys,
        "argv",
        [
            "refresh_startups",
            "--apply",
            "--skip-export",
        ],
    )

    refresh_startups.main()

    expected_plan = _build_plan(
        skip_export=True,
    )

    assert calls == [
        refresh_startups._command(
            step
        )
        for step in expected_plan
    ]


def test_non_zero_subprocess_result_stops_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fail_second(command, check):
        calls.append(
            command
        )
        return subprocess.CompletedProcess(
            command,
            1 if len(calls) == 2 else 0,
        )

    monkeypatch.setattr(
        refresh_startups.subprocess,
        "run",
        fail_second,
    )
    monkeypatch.setattr(
        refresh_startups.sys,
        "argv",
        [
            "refresh_startups",
            "--apply",
        ],
    )

    with pytest.raises(
        SystemExit
    ):
        refresh_startups.main()

    assert len(
        calls
    ) == 2


def test_no_ats_discovery_or_sync_modules_appear_in_plan() -> None:
    modules = _modules(
        _build_plan()
    )

    for fragment in ATS_MODULE_FRAGMENTS:
        assert fragment not in modules


def test_implementation_does_not_import_source_clients() -> None:
    source = Path(
        refresh_startups.__file__
    ).read_text(
        encoding="utf-8"
    )

    assert "chamba_hunter.sources" not in source
    assert "YcJobsClient" not in source
    assert "HnWhoIsHiringClient" not in source
