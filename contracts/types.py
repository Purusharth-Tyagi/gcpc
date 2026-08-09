"""FROZEN AT H1. Changing this after H1 means telling all four people."""
from dataclasses import dataclass, field


@dataclass
class Resolution:
    code: str                 # catalog id, e.g. "c01"
    canonical: str            # exactly what the agent should SAY
    phoneme: str | None       # Rime brace string, e.g. "{g1az0iyab1ad}"
    score: float
    band: str                 # "accept" | "confirm" | "reject"
    phoneme_for: str | None = None
    # ^ WHICH SUBSTRING of canonical the phoneme replaces. Defaults to the whole
    # canonical. Without it, replacing "Ghaziabad Campus, Block C" with
    # "{g1az0iyab1ad}" makes the agent say only "Ghaziabad" and silently drop
    # the rest. A: replace phoneme_for, never canonical.
    payload: dict = field(default_factory=dict)
    alternates: list[str] = field(default_factory=list)


@dataclass
class Intent:
    name: str
    confidence: float
