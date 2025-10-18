from pydantic import BaseModel, Field, constr


class DocketItem(BaseModel):
    unique_id: constr(max_length=20) = Field(
        ..., description="Unique identifier for the case."
    )
    cleaned_nums: list[constr(max_length=200)] = Field(
        ..., description="A list of cleaned and standardized docket numbers."
    )

    class Config:
        extra = "forbid"  # equivalent to additionalProperties=false


class CleanDocketNumber(BaseModel):
    docket_numbers: list[DocketItem] = Field(
        ..., description="A list of extracted items."
    )

    class Config:
        extra = "forbid"  # equivalent to additionalProperties=false
