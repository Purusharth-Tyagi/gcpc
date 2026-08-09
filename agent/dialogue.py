from enum import Enum
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.enquiry import Enquiry
from agent.eligibility import eligibility
from agent.llm import extract_query


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
        clean_query = extract_query(user_said, "course")
        canonical, res = resolve_course(clean_query)
        if canonical is None:
            enquiry.resolve_fail_count += 1
            if enquiry.resolve_fail_count >= 3:
                return "Let me connect you to a counsellor for this.", State.ESCALATE
            return "Sorry, which course did you mean? Could you repeat that?", State.ENQUIRE
        enquiry.course = canonical
        enquiry.course_payload = res.payload
        return f"Got it — {canonical}. Which entrance exam did you take?", State.ENQUIRE

    # Slot 2: exam
    if enquiry.exam is None:
        if user_said.strip() == "":
            return "Which entrance exam did you take?", State.ENQUIRE
        clean_query = extract_query(user_said, "exam")
        canonical, res = resolve_exam(clean_query)
        if canonical is None:
            enquiry.resolve_fail_count += 1
            if enquiry.resolve_fail_count >= 3:
                return "Let me connect you to a counsellor for this.", State.ESCALATE
            return "Sorry, which exam did you mean?", State.ENQUIRE
        enquiry.exam = canonical
        return f"And what was your {canonical} score?", State.ENQUIRE

    # Slot 3: score
    if enquiry.score is None:
        match = re.search(r"\d+\.?\d*", user_said)
        if match is None:
            return "Could you tell me your score as a number?", State.ENQUIRE
        enquiry.score = float(match.group())
        return "Thanks, let me check that for you.", State.ELIGIBILITY

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

def check_scope_fence(user_said: str) -> bool:
    """Scholarship, reservation category, fee waivers — always escalate."""
    said = user_said.lower()
    words_in_text = set(said.replace(",", " ").replace(".", " ").split())
    fence_words = {"scholarship", "reservation", "quota", "waiver",
                   "category", "concession", "sc", "st", "obc", "ews"}
    return len(words_in_text & fence_words) > 0


def check_wants_human(user_said: str) -> bool:
    """Caller explicitly asks for a person."""
    said = user_said.lower()
    human_words = {"human", "person", "counsellor", "representative", "talk to someone"}
    return any(w in said for w in human_words)



def check_wants_human(user_said: str) -> bool:
    """Caller explicitly asks for a person."""
    said = user_said.lower()
    human_words = {"human", "person", "counsellor", "representative", "talk to someone"}
    return any(w in said for w in human_words)

def classify_repair_target(user_said: str) -> str | None:
    """Guess which slot the caller is correcting. Keyword fallback."""
    said = user_said.lower()

    score_words = {"percentile", "score", "marks"}
    exam_words = {"cuet", "jee", "cet", "exam"}
    course_words = {"course", "branch", "cse", "ece", "btech", "b.tech"}
    slot_words = {"saturday", "sunday", "monday", "tuesday", "wednesday",
                  "thursday", "friday", "time", "date", "slot"}

    if any(w in said for w in score_words) or any(ch.isdigit() for ch in said):
        return "score"
    if any(w in said for w in exam_words):
        return "exam"
    if any(w in said for w in course_words):
        return "course"
    if any(w in said for w in slot_words):
        return "visit_slot"
    return None

def handle_repair(enquiry: Enquiry, user_said: str, repair_count: int) -> tuple[str, State, int]:
    """Clear the targeted slot and go back to collecting it. Cap at 3 loops."""
    repair_count += 1

    if repair_count > 3:
        return ("I'm having trouble getting this right. Let me connect you "
                "to a counsellor."), State.ESCALATE, repair_count

    target = classify_repair_target(user_said)

    if target is None:
        return ("Sorry, which part should I change — the course, the score, "
                "or the visit time?"), State.CONFIRM, repair_count

    if target == "course":
        enquiry.course = None
        enquiry.course_payload = None
        return "No problem, which course did you mean?", State.ENQUIRE, repair_count
    if target == "exam":
        enquiry.exam = None
        return "Got it, which exam was it?", State.ENQUIRE, repair_count
    if target == "score":
        enquiry.score = None
        return "Okay, what was the correct score?", State.ENQUIRE, repair_count
    if target == "visit_slot":
        enquiry.visit_slot = None
        return "Sure, what date/time works instead?", State.COLLECT, repair_count

    return "Let's try that again.", State.CONFIRM, repair_count 

def handle_confirm(enquiry: Enquiry, user_said: str) -> tuple[str, State]:
    """Read back everything, wait for explicit yes. Anything else triggers repair."""
    from agent.readback import readback

    if user_said.strip() == "":
        return readback(enquiry), State.CONFIRM

    said = user_said.strip().lower()
    yes_words = {"yes", "haan", "ji", "theek hai", "sure", "go ahead"}

    if any(w in said for w in yes_words):
        return "", State.BOOK

    # Not a yes — treat as a correction attempt
    return "REPAIR_NEEDED", State.CONFIRM
import re
import random

def handle_book(enquiry: Enquiry) -> tuple[str, State]:
    """Finalize the booking."""
    ref_id = f"REF{random.randint(1000, 9999)}"
    msg = f"You're all set. Your campus visit reference is {ref_id}. Thank you for calling!"
    return msg, State.DONE

def handle_turn(enquiry: Enquiry, current_state: State, user_said: str) -> tuple[str, State]:
    """Single entry point — routes to the right handler based on current state."""
    # Global escalation checks — run before any state-specific logic
    if current_state not in (State.GREET, State.DONE, State.ESCALATE):
        if check_scope_fence(user_said):
            return ("That's something our counsellors handle directly. "
                    "Let me connect you."), State.ESCALATE
        if check_wants_human(user_said):
            return "Sure, connecting you to a counsellor now.", State.ESCALATE

    if current_state == State.GREET:
        return handle_greet(enquiry)

    if current_state == State.IDENTIFY:
        if enquiry.caller_name is None and user_said.strip():
            enquiry.caller_name = user_said.strip()
            return "And who is the applicant — your child's name?", State.IDENTIFY
        if enquiry.applicant_name is None and user_said.strip():
            enquiry.applicant_name = user_said.strip()
            return "Great. What would you like to know about?", State.ENQUIRE
        return handle_identify(enquiry, user_said)

    if current_state == State.CONFIRM:
        msg, new_state = handle_confirm(enquiry, user_said)
        if msg == "REPAIR_NEEDED":
            repair_msg, repair_state, enquiry._repair_count = handle_repair(
                enquiry, user_said, getattr(enquiry, "_repair_count", 0)
            )
            return repair_msg, repair_state
        return msg, new_state
    if current_state == State.ENQUIRE:
        return handle_enquire(enquiry, user_said)

    if current_state == State.ELIGIBILITY:
        return handle_eligibility(enquiry)

    if current_state == State.OFFER:
        return handle_offer(enquiry, user_said)

    if current_state == State.COLLECT:
        return handle_collect(enquiry, user_said)


    if current_state == State.BOOK:
        return handle_book(enquiry)

    if current_state == State.DONE:
        return "Thank you, have a great day!", State.DONE

    if current_state == State.ESCALATE:
        return "I'm connecting you to a counsellor, one moment.", State.ESCALATE

    return "Sorry, something went wrong.", State.ESCALATE

if __name__ == "__main__":
    e = Enquiry()
    state = State.GREET

    caller_turns = ["", "Ramesh", "Aryan", "",
                     "cse mein interest hai",
                     "JEE main diya tha",
                     "91 percentile mila tha",
                     "", "yes", "Saturday 11 AM", "", "haan", ""]

    for said in caller_turns:
        msg, state = handle_turn(e, state, said)
        print(f"[{state.value}] Agent: {msg}")
        if state == State.DONE:
            break