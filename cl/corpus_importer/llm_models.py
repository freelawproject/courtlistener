from pydantic import BaseModel


class CaseNameExtractionResponse(BaseModel):
    """Represents the structured output extracted from an opinion document
    by the LLM case name extraction task"""

    case_name: str | None = None
    case_name_full: str | None = None
