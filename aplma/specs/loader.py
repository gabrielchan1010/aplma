"""Spec loader."""
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

DEFAULT_SPEC_PATH: Path = Path(__file__).parent / "financial_indebtedness.yaml"


class ExtractionSpec(BaseModel):
    spec_version: str
    covenant_type: str
    description: str

    search_terms: list[str] = Field(default_factory=list)
    definition_openings: dict[str, list[str]] = Field(default_factory=dict)
    restriction_heading: list[str] = Field(default_factory=list)
    page_finding_instructions: str = Field(default="")

    navigation_hint: str = Field(default="")
    heading_search_terms: list[str] = Field(default_factory=list)
    structural_anchors: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _normalise_lawyer_facing_keys(self) -> "ExtractionSpec":
        if self.search_terms and not self.heading_search_terms:
            self.heading_search_terms = list(self.search_terms)
        elif self.heading_search_terms and not self.search_terms:
            self.search_terms = list(self.heading_search_terms)

        if self.page_finding_instructions and not self.navigation_hint:
            self.navigation_hint = self.page_finding_instructions
        elif self.navigation_hint and not self.page_finding_instructions:
            self.page_finding_instructions = self.navigation_hint

        if not self.structural_anchors:
            anchors: dict[str, list[str]] = {}
            fi = self.definition_openings.get("financial_indebtedness")
            permitted = self.definition_openings.get("permitted_financial_indebtedness")
            if fi:
                anchors["fi_definition"] = list(fi)
            if permitted:
                anchors["permitted_fi_definition"] = list(permitted)
            if self.restriction_heading:
                anchors["restriction_heading_suffix"] = list(self.restriction_heading)
            self.structural_anchors = anchors

        if not self.definition_openings and self.structural_anchors:
            fi = self.structural_anchors.get("fi_definition")
            permitted = self.structural_anchors.get("permitted_fi_definition")
            if fi:
                self.definition_openings["financial_indebtedness"] = list(fi)
            if permitted:
                self.definition_openings["permitted_financial_indebtedness"] = list(permitted)
        if not self.restriction_heading:
            restriction = self.structural_anchors.get("restriction_heading_suffix")
            if restriction:
                self.restriction_heading = list(restriction)

        return self


def load_spec(spec_path: str | Path) -> ExtractionSpec:
    spec_path = Path(spec_path)
    if not spec_path.exists():
        raise FileNotFoundError(f"Spec file not found: {spec_path}")
    with spec_path.open() as f:
        raw = yaml.safe_load(f)
    return ExtractionSpec.model_validate(raw)
