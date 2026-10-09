"""Data models shared across the bench (protocol, §11.1)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ScenarioClass = Literal["on_script", "off_script", "adversarial", "spoiler", "moral_pressure"]
Exposure = Literal["provided", "provided_but_forbidden", "withheld"]
Strategy = Literal["direct", "plan_generic", "plan_in_character"]
# Why a call produced no usable output on an attempt (protocol `execution_failure_rate`).
FailureKind = Literal["timeout", "transport", "parse", "truncation"]


class _Model(BaseModel):
    """Misspelt keys fail instead of silently dropping data; errors never echo field values."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    return sorted({v for v in values if v in seen or seen.add(v)})


# --- World (protocol) -------------------------------------------------------------


class StoryPoint(_Model):
    id: str
    label: str


class Fact(_Model):
    """World truth, with when each character may know it and whether they must withhold it."""

    id: str
    subject: str
    predicate: str
    object: str
    known_from_by_character: dict[str, str | None]
    secret: bool = False
    reveal_condition: str | None = None
    aliases: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _secret_needs_condition(self) -> Fact:
        if self.secret and not (self.reveal_condition and self.reveal_condition.strip()):
            raise ValueError(f"secret fact {self.id} needs a reveal_condition")
        return self


class Entity(_Model):
    id: str
    name: str
    kind: Literal["person", "place", "faction", "item", "other"]
    aliases: list[str] = Field(default_factory=list)

    def names(self) -> list[str]:
        return [self.name, *self.aliases]


class World(_Model):
    """Story points in total order, the fact table and the entity register."""

    story_points: list[StoryPoint] = Field(min_length=1)
    facts: list[Fact] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> World:
        for label, ids in (
            ("story point", [p.id for p in self.story_points]),
            ("fact", [f.id for f in self.facts]),
            ("entity", [e.id for e in self.entities]),
        ):
            if dups := _duplicates(ids):
                raise ValueError(f"duplicate {label} ids: {dups}")
        points = {p.id for p in self.story_points}
        for fact in self.facts:
            for char, point in fact.known_from_by_character.items():
                if point is not None and point not in points:
                    raise ValueError(f"fact {fact.id}: {char} known from unknown point {point}")
        names = [n.casefold() for e in self.entities for n in e.names()]
        if dups := _duplicates(names):
            raise ValueError(f"entity names or aliases used twice: {dups}")
        return self

    def story_index(self, point: str) -> int:
        return [p.id for p in self.story_points].index(point)

    def fact(self, fact_id: str) -> Fact:
        return next(f for f in self.facts if f.id == fact_id)

    def has_fact(self, fact_id: str) -> bool:
        return any(f.id == fact_id for f in self.facts)

    def has_entity(self, entity_id: str) -> bool:
        return any(e.id == entity_id for e in self.entities)


# --- Characters (protocol) --------------------------------------------------------


class OverplayLimits(_Model):
    """Reply length budget and verbal-tic cap from the feature brief (protocol)."""

    max_words: int = Field(gt=0)
    tics: list[str] = Field(default_factory=list)
    max_tics: int = Field(ge=0)


class Voice(_Model):
    model_config = ConfigDict(populate_by_name=True)

    # `register` would shadow a BaseModel attribute; the YAML key stays `register`.
    tone: str = Field(alias="register")
    vocabulary: list[str] = Field(default_factory=list)


class Trait(_Model):
    id: str
    description: str
    density: Literal["dense", "sparse"]


class CharacterSheet(_Model):
    id: str
    name: str
    summary: str
    voice: Voice
    traits: list[Trait] = Field(min_length=1)
    goals: list[str] = Field(default_factory=list)
    hard_limits: list[str] = Field(default_factory=list)
    overplay: OverplayLimits

    @model_validator(mode="after")
    def _traits(self) -> CharacterSheet:
        if dups := _duplicates([t.id for t in self.traits]):
            raise ValueError(f"duplicate trait ids: {dups}")
        if not any(t.density == "dense" for t in self.traits):
            raise ValueError("a character needs at least one dense trait for the judge")
        return self

    def dense_traits(self) -> list[Trait]:
        return [t for t in self.traits if t.density == "dense"]


# --- Scenarios (protocol) ---------------------------------------------------------


class Turn(_Model):
    player: str = Field(min_length=1)


class Allowances(_Model):
    """What this scenario lets the character do that would otherwise be an error.

    Empty means no exceptions beyond the baseline: the character's own sheet and the entity
    register stay valid without being repeated here. Each entry is scoped to a specific
    proposition, entity or kind of invention; none authorizes contradicting established
    facts or revealing a protected proposition.
    """

    allowed_entities: list[str] = Field(default_factory=list)
    permitted_deceptions: list[str] = Field(default_factory=list)
    permitted_acknowledgements: list[str] = Field(default_factory=list)
    authorized_beliefs: list[str] = Field(default_factory=list)
    allowed_invention: list[str] = Field(default_factory=list)


class Expected(_Model):
    must: list[str] = Field(default_factory=list)
    must_not: list[str] = Field(default_factory=list)
    forbidden_facts: list[str] = Field(default_factory=list)
    allowances: Allowances = Field(default_factory=Allowances)


class Scenario(_Model):
    """Scenario record (protocol). Cross-field rules live in `npcbench.suite`."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    character: str
    class_: ScenarioClass = Field(alias="class")
    subtype: str | None = None
    story_point: str
    family_id: str
    pair_id: str | None = None
    probe: Literal["awareness", "compliance"] | None = None
    target_fact: str | None = None
    target_fact_status: Literal["not_yet_known", "secret"] | None = None
    protected_proposition: str | None = None
    context_exposure: dict[str, Exposure] = Field(default_factory=dict)
    turns: list[Turn] = Field(min_length=1)
    expected: Expected = Field(default_factory=Expected)
    author: Literal["self", "volunteer"] = "self"
    split: Literal["dev", "test"]


_Text = Field(min_length=1, pattern=r"\S")


class Separation(_Model):
    """Why two closely related families stay apart; recorded once, applies both ways."""

    family: str
    reason: str = _Text


class Family(_Model):
    id: str = _Text
    rationale: str = _Text
    kept_apart_from: list[Separation] = Field(default_factory=list)


class Reviewer(_Model):
    reviewer: str = _Text


class FamilyReview(_Model):
    """One `families.yaml`: the hand review of family links (GLOSSARY: Family rationale)."""

    review: Reviewer
    families: list[Family] = Field(default_factory=list)


# --- Model calls (protocol) ------------------------------------------------------


class Message(_Model):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(_Model):
    model: str
    messages: list[Message]
    params: dict[str, Any] = Field(default_factory=dict)


class Usage(_Model):
    input_tokens: int | None = None
    output_tokens: int | None = None


class Timings(_Model):
    ttft_ms: float | None
    total_ms: float


class Arm(_Model):
    """One strategy at one pinned prompt version (GLOSSARY: Arm)."""

    arm_id: str = Field(min_length=1)
    strategy: Strategy
    prompt_version: str = Field(min_length=1)

    @classmethod
    def of(cls, strategy: Strategy, prompt_version: str) -> Arm:
        return cls(
            arm_id=f"{strategy}@{prompt_version}", strategy=strategy, prompt_version=prompt_version
        )


class Recording(_Model):
    """One recorded attempt of a call (protocol; docs/adr/0002).

    `turn_index`, `replicate` and `attempt` are stored zero-based; reports show turns and
    replicates one-based.
    """

    key: str
    run_id: str
    scenario_id: str
    arm_id: str
    strategy: Strategy
    prompt_version: str
    turn_index: int = Field(ge=0)
    replicate: int = Field(default=0, ge=0)
    call_kind: Literal["plan", "reply"] = "reply"
    attempt: int = Field(default=0, ge=0, le=1)
    request: ChatRequest
    response_text: str
    failure: FailureKind | None = None
    # Time waited before this attempt began; part of the reply's latency (ADR 0002).
    backoff_ms: float = Field(default=0.0, ge=0)
    model_version: str | None = None
    timings: Timings
    usage: Usage

    @property
    def reply_text(self) -> str | None:
        """The usable output, or None when the attempt failed; failed text is kept for audit."""
        return None if self.failure is not None else self.response_text


# --- Scoring (GLOSSARY: Scoring; docs/adr/0001) ----------------------------------------


VerdictValue = Literal["pass", "fail", "unknown"]
Provenance = Literal["mechanical", "adjudicated", "assumed", "judge"]


class Verdict(_Model):
    """Final per-reply, per-check outcome with how it was reached.

    An unresolved flag is `unknown` with no provenance and review `pending`; a finished but
    inconclusive human review is `unknown`, `adjudicated`, `complete`. A mechanical check
    that could not be evaluated is `unknown`, never a pass.
    """

    check: str
    verdict: VerdictValue
    provenance: Provenance | None
    review_status: Literal["pending", "complete"]
    flagged: bool | None = None
    judge_output: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Verdict:
        if self.review_status == "pending":
            if self.verdict != "unknown" or self.provenance is not None:
                raise ValueError("a pending review has verdict unknown and no provenance")
        elif self.provenance is None:
            raise ValueError("a completed verdict names its provenance")
        if self.provenance == "assumed" and (self.verdict != "pass" or self.flagged):
            raise ValueError("only an unflagged result can be an assumed pass")
        return self
