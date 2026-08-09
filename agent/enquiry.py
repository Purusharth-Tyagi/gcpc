from dataclasses import dataclass


@dataclass
class Enquiry:
    caller_name: str | None = None
    phone: str | None = None
    applicant_name: str | None = None      # often the caller's child, not the caller
    course: str | None = None              # resolved canonical only
    exam: str | None = None                # resolved canonical only
    score: float | None = None
    language: str = "en"                   # en | hi
    visit_slot: str | None = None