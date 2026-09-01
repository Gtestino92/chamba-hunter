from pathlib import Path

from chamba_hunter.commands.refresh_search import ATS_SYNC_MODULES, build_plan


def test_refresh_discovers_new_ats_and_syncs_hibob() -> None:
    plan = build_plan(
        skip_broad=False,
        skip_himalayas=False,
        skip_ats=False,
        skip_export=False,
        discover_known_ats_limit=25,
        discover_broad_ats_limit=10,
        himalayas_backfill_days=30,
        himalayas_overlap_hours=48,
        getonboard_max_pages=5,
        jobicy_max_jobs=100,
        wwr_max_jobs=300,
        jooble_max_pages_per_query=2,
        output=Path("output/chamba-shortlist.xlsx"),
    )

    modules = [step.module for step in plan]
    assert "discover_known_ats" in modules
    assert "discover_broad_ats" in modules
    assert "sync_hibob_jobs" in modules
    assert "sync_hibob_jobs" in ATS_SYNC_MODULES
    assert modules.index("discover_known_ats") < modules.index("sync_hibob_jobs")
