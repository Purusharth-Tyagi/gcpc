"""FROZEN AT H1. Changing this after H1 means telling all four people."""
from dataclasses import dataclass, field


@dataclass
class Resolution:
    code: str                 # catalog id, e.g. "c01"
    canonical: str            # exactly what the agent should say
    phoneme: str | None       # Rime brace string, e.g. "{b1i tEk s1i 1Es 1i}"
    score: float
    band: str                 # "accept" | "confirm" | "reject"
    payload: dict = field(default_factory=dict)
    alternates: list[str] = field(default_factory=list)


@dataclass
class Intent:
    name: str
    confidence: float

