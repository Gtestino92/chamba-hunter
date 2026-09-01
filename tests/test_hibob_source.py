from chamba_hunter.sources.hibob import (
    _job_posting,
    _parse_job_links,
    canonical_hibob_board_url,
    extract_hibob_job_id,
    hibob_tenant_from_url,
)


def test_hibob_tenant_and_canonical_board() -> None:
    url = "https://uala.careers.hibob.com/jobs"
    assert hibob_tenant_from_url(url) == "uala"
    assert canonical_hibob_board_url("uala") == url


def test_hibob_job_id_accepts_detail_and_apply_urls() -> None:
    job_id = "adc2f864-e427-4be5-a1b7-e69d29c6b365"
    assert (
        extract_hibob_job_id(
            f"https://uala.careers.hibob.com/jobs/{job_id}"
        )
        == job_id
    )
    assert (
        extract_hibob_job_id(
            f"https://uala.careers.hibob.com/jobs/{job_id}/apply"
        )
        == job_id
    )
    assert extract_hibob_job_id(
        "https://uala.careers.hibob.com/jobs"
    ) is None


def test_hibob_listing_deduplicates_apply_link() -> None:
    html = """
    <html><body>
      <a href="/jobs/backend-123"><span>Backend Engineer</span></a>
      <a href="/jobs/backend-123/apply">Apply now</a>
    </body></html>
    """
    jobs = _parse_job_links(
        board_url="https://uala.careers.hibob.com/jobs",
        html=html,
    )
    assert len(jobs) == 1
    assert jobs[0].external_id == "backend-123"
    assert jobs[0].title_hint == "Backend Engineer"
    assert jobs[0].job_url == (
        "https://uala.careers.hibob.com/jobs/backend-123"
    )


def test_hibob_job_posting_reads_json_ld_graph() -> None:
    posting = _job_posting(
        [
            """
            {
              "@context": "https://schema.org",
              "@graph": [
                {
                  "@type": "JobPosting",
                  "title": "Software Engineer"
                }
              ]
            }
            """
        ]
    )
    assert posting is not None
    assert posting["title"] == "Software Engineer"
