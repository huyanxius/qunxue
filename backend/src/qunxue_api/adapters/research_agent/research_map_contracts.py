"""Strict model-facing contracts for research-map tool arguments."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

ResearchMapNodeKind = Literal[
    "question",
    "theory",
    "claim",
    "evidence",
    "gap",
    "synthesis",
]
ResearchMapNodeStatus = Literal[
    "developing",
    "grounded",
    "open",
    "verified",
    "challenged",
    "complete",
]
ResearchMapRelationKind = Literal[
    "explains",
    "supports",
    "challenges",
    "derives",
    "refines",
]

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class ResearchMapNodeInput(BaseModel):
    """One canonical node; aliases are deliberately excluded from the tool schema."""

    model_config = ConfigDict(extra="forbid")

    id: Identifier
    kind: ResearchMapNodeKind
    title: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=240),
    ]
    summary: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1200)] | None = None
    status: ResearchMapNodeStatus = "developing"
    citation_ids: list[Identifier] = Field(default_factory=list, max_length=24)


class ResearchMapRelationInput(BaseModel):
    """One canonical relation between existing or same-patch nodes."""

    model_config = ConfigDict(extra="forbid")

    id: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
    ] | None = None
    source: Identifier
    target: Identifier
    relation: ResearchMapRelationKind
    label: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = None
