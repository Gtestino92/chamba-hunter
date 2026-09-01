from chamba_hunter.domain.enums import AtsDetectionMethod
from chamba_hunter.services.hibob_ats_detection_service import (
    _candidate_from_page,
    _direct_candidate,
)


def test_direct_hibob_careers_url_is_detected() -> None:
    candidate = _direct_candidate(
        "https://uala.careers.hibob.com/jobs"
    )
    assert candidate is not None
    assert candidate.tenant == "uala"
    assert candidate.method == AtsDetectionMethod.CAREERS_LINK


def test_custom_careers_page_can_link_to_hibob() -> None:
    candidate = _candidate_from_page(
        page_url="https://www.example.com/careers",
        html=(
            '<a href="https://uala.careers.hibob.com/jobs/abc-123">'
            "Software Engineer"
            "</a>"
        ),
    )
    assert candidate is not None
    assert candidate.tenant == "uala"
    assert candidate.method == AtsDetectionMethod.HTML_LINK
