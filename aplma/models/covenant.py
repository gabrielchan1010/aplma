from typing import Optional

from pydantic import BaseModel, Field


class GroundedSpan(BaseModel):
    page_number: int = Field(description="1-based physical PDF page")
    extraction_text: str = Field(description="The text the model reported as the source quote")
    verbatim: bool = Field(default=True, description="True iff extraction_text appears literally in the fetched source content")
    char_start: Optional[int] = Field(default=None)
    char_end: Optional[int] = Field(default=None)


class FinancialIndebtednessDefinition(BaseModel):
    """The 'Financial Indebtedness means:' defined term — Clause 1.1."""
    clause_ref: str = Field(description="Parent clause containing this definition")
    definition_text: str = Field(description="Verbatim text of the definition")
    grounding: Optional[GroundedSpan] = Field(default=None)


class FinancialIndebtednessRestriction(BaseModel):
    """The General-Covenants sub-clause that prohibits incurring Financial Indebtedness."""
    clause_ref: str = Field(description="Clause number of the restriction sub-clause")
    restriction_text: str = Field(description="Verbatim text of the prohibition sub-clause")
    grounding: Optional[GroundedSpan] = Field(default=None)


class PermittedFinancialIndebtednessCarveOut(BaseModel):
    """A single sub-item under the 'Permitted Financial Indebtedness means:' defined term."""
    carve_out_text: str = Field(description="Verbatim text of this sub-item")
    grounding: Optional[GroundedSpan] = Field(default=None)


class FinancialIndebtednessCovenant(BaseModel):
    """All three components of the Financial Indebtedness covenant."""
    fi_definition: Optional[FinancialIndebtednessDefinition] = Field(default=None)
    restriction: Optional[FinancialIndebtednessRestriction] = Field(default=None)
    permitted_carve_outs: list[PermittedFinancialIndebtednessCarveOut] = Field(default_factory=list)
