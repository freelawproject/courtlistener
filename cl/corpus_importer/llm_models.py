from pydantic import BaseModel


class CaseNameExtractionResponse(BaseModel):
    """Represents the structured output extracted from an opinion document
    by the LLM case name extraction task"""

    is_opinion: bool
    case_name_short: str | None = None
    case_name: str | None = None
    case_name_full: str | None = None
    case_name_match: bool = False
    needs_ocr: bool = False
    error: str | None = None
