"""Parse RECAP uploads without depending on Django models.

Keep this module importable before Django setup: spawn/forkserver workers
import it when unpickling the parser functions submitted to their pools.
"""

from typing import Any

from juriscraper.pacer import (
    ACMSAttachmentPage,
    ACMSDocketReport,
    AppellateDocketReport,
    CaseQuery,
    ClaimsRegister,
    DocketHistoryReport,
    DocketReport,
)


def parse_docket_text(court_id: str, text: str) -> dict[str, Any]:
    """Parse PACER docket HTML into structured data."""
    report = DocketReport(court_id)
    report._parse_text(text)
    return report.data


def parse_claims_register_text(court_id: str, text: str) -> dict[str, Any]:
    """Parse PACER claims register HTML into structured data."""
    report = ClaimsRegister(court_id)
    report._parse_text(text)
    return report.data


def parse_docket_history_text(court_id: str, text: str) -> dict[str, Any]:
    """Parse PACER docket history HTML into structured data."""
    report = DocketHistoryReport(court_id)
    report._parse_text(text)
    return report.data


def parse_case_query_page_text(court_id: str, text: str) -> dict[str, Any]:
    """Parse PACER case query HTML into structured data."""
    report = CaseQuery(court_id)
    report._parse_text(text)
    return report.data


def parse_appellate_text(court_id: str, text: str) -> dict[str, Any]:
    """Parse PACER appellate docket HTML into structured data."""
    report = AppellateDocketReport(court_id)
    report._parse_text(text)
    return report.data


def parse_acms_attachment_json(court_id: str, json: str) -> dict[str, Any]:
    """Parse ACMS attachment JSON into structured data."""
    report = ACMSAttachmentPage(court_id)
    report._parse_text(json)
    return report.data


def parse_acms_json(court_id: str, json: str) -> dict[str, Any]:
    """Parse ACMS docket JSON into structured data."""
    report = ACMSDocketReport(court_id)
    report._parse_text(json)
    return report.data
