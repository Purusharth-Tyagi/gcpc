from enum import Enum
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.enquiry import Enquiry
from agent.eligibility import eligibility


class State(Enum):
    GREET = "greet"
    IDENTIFY = "identify"
    ENQUIRE = "enquire"
    ELIGIBILITY = "eligibility"
    OFFER = "offer"
    COLLECT = "collect"
    CONFIRM = "confirm"
    BOOK = "book"
    DONE = "done"
    ESCALATE = "escalate"


def handle_greet(enquiry: Enquiry) -> tuple[str, State]:
    """First turn — greet the caller."""
    prompt = "Namaste, this is the admissions helpline. How can I help you today?"
    return prompt, State.IDENTIFY


def handle_identify(enquiry: Enquiry, user_said: str) -> tuple[str, State]:
    """Ask for caller's name if we don't have it yet."""
    if enquiry.caller_name is None:
        return "Could I have your name please?", State.IDENTIFY
    # Name already captured, move on
    return "Great. What would you like to know about?", State.ENQUIRE

from agent.resolve_helpers import resolve_course, resolve_exam


def handle_enquire(enquiry: Enquiry, user_said: str) -> tuple[str, State]:
    """Fill course, then exam, then score — one slot at a time."""

    # Slot 1: course
    if enquiry.course is None:
        if user_said.strip() == "":
            return "Which course are you interested in?", State.ENQUIRE
        canonical, res = resolve_course(user_said)
        if canonical is None:
            return "Sorry, which course did you mean? Could you repeat that?", State.ENQUIRE
        enquiry.course = canonical
        enquiry.course_payload = res.payload
        return f"Got it — {canonical}. Which entrance exam did you take?", State.ENQUIRE

    # Slot 2: exam
    if enquiry.exam is None:
        if user_said.strip() == "":
            return "Which entrance exam did you take?", State.ENQUIRE
        canonical, res = resolve_exam(user_said)
        if canonical is None:
            return "Sorry, which exam did you mean?", State.ENQUIRE
        enquiry.exam = canonical
        return f"And what was your {canonical} score?", State.ENQUIRE

    # Slot 3: score
    if enquiry.score is None:
        try:
            enquiry.score = float(user_said.strip())
        except ValueError:
            return "Could you tell me your score as a number?", State.ENQUIRE
        return "Thanks, let me check that for you.", State.ELIGIBILITY

    # All slots filled — shouldn't normally reach here
    return "", State.ELIGIBILITY 

def handle_eligibility(enquiry: Enquiry) -> tuple[str, State]:
    """Run the eligibility guardrail. Never guess."""

    if enquiry.course_payload is None or enquiry.score is None:
        return ("I don't want to give you a wrong answer on that. "
                "Let me have a counsellor confirm it. Shall I book a callback?"), State.ESCALATE

    exam_key = None
    for k in enquiry.course_payload.get("cutoffs", {}):
        exam_key = k

    if exam_key is None:
        return ("I don't want to give you a wrong answer on that. "
                "Let me have a counsellor confirm it. Shall I book a callback?"), State.ESCALATE

    result = eligibility(enquiry.course_payload, exam_key, enquiry.score)

    if result == "likely":
        msg = f"Good news — with a score of {enquiry.score}, {enquiry.applicant_name or 'the applicant'} is likely eligible for {enquiry.course}. Would you like to book a campus visit?"
        return msg, State.OFFER
    elif result == "borderline":
        msg = f"With a score of {enquiry.score}, this is borderline for {enquiry.course}. I'd recommend a campus visit to discuss further. Shall I book one?"
        return msg, State.OFFER
    elif result == "below":
        msg = f"Based on the current cutoff, this score may not meet the requirement for {enquiry.course}. Would you like me to connect you to a counsellor?"
        return msg, State.ESCALATE
    else:
        return ("I don't want to give you a wrong answer on that. "
                "Let me have a counsellor confirm it. Shall I book a callback?"), State.ESCALATE

def handle_offer(enquiry: Enquiry, user_said: str) -> tuple[str, State]:
    """Caller was told they're eligible/borderline — ask if they want a visit."""
    said = user_said.strip().lower()
    yes_words = {"yes", "haan", "ji", "theek hai", "sure", "ok", "okay"}
    no_words = {"no", "nahi", "nope"}

    if any(w in said for w in yes_words):
        return "Great, what date would work for a campus visit?", State.COLLECT
    if any(w in said for w in no_words):
        return "No problem. Is there anything else I can help with?", State.DONE
    return "Would you like to book a campus visit — yes or no?", State.OFFER

def handle_collect(enquiry: Enquiry, user_said: str) -> tuple[str, State]:
    """Collect the visit date/time slot."""
    if enquiry.visit_slot is None:
        if user_said.strip() == "":
            return "What date and time works for you?", State.COLLECT
        enquiry.visit_slot = user_said.strip()
        return "", State.CONFIRM
    return "", State.CONFIRM

def handle_confirm(enquiry: Enquiry, user_said: str) -> tuple[str, State]:
    """Read back everything, wait for explicit yes."""
    from agent.readback import readback

    if user_said.strip() == "":
        return readback(enquiry), State.CONFIRM

    said = user_said.strip().lower()
    yes_words = {"yes", "haan", "ji", "theek hai", "sure", "go ahead"}

    if any(w in said for w in yes_words):
        return "", State.BOOK
    # anything ambiguous (including "no") — ask again, never assume
    return readback(enquiry), State.CONFIRM

import random

def handle_book(enquiry: Enquiry) -> tuple[str, State]:
    """Finalize the booking."""
    ref_id = f"REF{random.randint(1000, 9999)}"
    msg = f"You're all set. Your campus visit reference is {ref_id}. Thank you for calling!"
    return msg, State.DONE

if __name__ == "__main__":
    e = Enquiry(
        applicant_name="Aryan",
        course="B.Tech Computer Science and Engineering (AI & ML)",
        course_payload={"cutoffs": {"jee_main": 88.0}},
        exam="JEE Main",
        score=91.0
    )

    msg, state = handle_eligibility(e)
    print(f"Agent: {msg}")

    msg, state = handle_offer(e, "yes")
    print(f"Agent: {msg}")

    msg, state = handle_collect(e, "Saturday 11 AM")
    print(f"State after collect: {state.value}")

    msg, state = handle_confirm(e, "")
    print(f"Agent: {msg}")

    msg, state = handle_confirm(e, "haan")
    print(f"Next state: {state.value}")

    msg, state = handle_book(e)
    print(f"Agent: {msg}")
    print(f"Final state: {state.value}")