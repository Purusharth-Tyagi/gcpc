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
    """First turn — greet the caller. Check memory if phone is known."""
    from retrieval.store import recall

    if enquiry.phone:
        past = recall(enquiry.phone, k=1)
        if past:
            record = past[0]
            applicant = record.get("applicant_name", "the applicant")
            course = record.get("course", "your enquiry")
            return (f"Welcome back! Calling about {course} for {applicant} again?"), State.IDENTIFY

    prompt = "Namaste, this is the admissions helpline. How can I help you today?"
    return prompt, State.IDENTIFY


def handle_identify(enquiry: Enquiry, user_said: str) -> tuple[str, State]:
    """Ask for caller's name if we don't have it yet."""
    if enquiry.caller_name is None:
        return "Could I have your name please?", State.IDENTIFY
    # Name already captured, move on
    return "Great. What would you like to know about?", State.ENQUIRE

from agent.resolve_helpers import resolve_course, resolve_exam


def _exam_shortcut(text: str) -> str | None:
    """Catch common ASR mishearings for exam names before resolver/LLM."""
    t = text.lower().replace(" ", "").replace(".", "")
    if any(x in t for x in ["jee", "jmeans", "jemeans", "pointentrance", "joinentrance"]):
        return "JEE Main"
    if any(x in t for x in ["cuet", "quiet", "cueit"]):
        return "CUET"
    if "neet" in t:
        return "NEET"
    return None


def handle_enquire(enquiry: Enquiry, user_said: str) -> tuple[str, State]:
    """Fill course, then exam, then score — one slot at a time."""

    if enquiry.course is None:
        if enquiry.pending_course_confirm is not None:
            said = user_said.strip().lower()
            if said in {"yes", "haan", "ji", "correct", "sahi hai"}:
                canonical, res = resolve_course(enquiry.pending_course_confirm)
                enquiry.course = enquiry.pending_course_confirm
                enquiry.course_payload = res.payload if res else {}
                enquiry.pending_course_confirm = None
                return f"Got it — {enquiry.course}. Which entrance exam did you take?", State.ENQUIRE
            else:
                enquiry.pending_course_confirm = None

        if user_said.strip() == "":
            return "Which course are you interested in?", State.ENQUIRE
        clean_query = extract_query(user_said, "course")
        if clean_query == "":
            enquiry.resolve_fail_count += 1
            if enquiry.resolve_fail_count >= 3:
                return "Let me connect you to a counsellor for this.", State.ESCALATE
            return "Sorry, which course are you interested in?", State.ENQUIRE
        canonical, res = resolve_course(clean_query)
        if canonical is not None:
            enquiry.course = canonical
            enquiry.course_payload = res.payload
            enquiry.resolve_fail_count = 0
            return f"Got it — {canonical}. Which entrance exam did you take?", State.ENQUIRE
        if res is not None and res.band == "confirm":
            enquiry.pending_course_confirm = res.canonical
            return f"Did you mean {res.canonical}? Say yes to confirm, or tell me the correct course.", State.ENQUIRE
        enquiry.resolve_fail_count += 1
        if enquiry.resolve_fail_count >= 3:
            return "Let me connect you to a counsellor for this.", State.ESCALATE
        return "Sorry, which course did you mean? Could you repeat that?", State.ENQUIRE

    # Slot 2: exam
    if enquiry.exam is None:
        if user_said.strip() == "":
            return "Which entrance exam did you take?", State.ENQUIRE
        shortcut = _exam_shortcut(user_said)
        if shortcut:
            enquiry.exam = shortcut
            return f"And what was your {shortcut} score?", State.ENQUIRE
        clean_query = extract_query(user_said, "exam")
        if clean_query == "":
            enquiry.resolve_fail_count += 1
            if enquiry.resolve_fail_count >= 3:
                return "Let me connect you to a counsellor for this.", State.ESCALATE
            return "Sorry, which exam did you mean?", State.ENQUIRE
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

_HINDI_WORDS = {
    "hai", "hain", "tha", "thi", "the", "aur", "kya", "kaise", "kaun",
    "kab", "kahan", "mera", "meri", "mere", "apka", "aapka", "humara",
    "nahi", "haan", "ji", "toh", "mein", "ka", "ki", "ke", "se", "ko",
    "wala", "wali", "diya", "liya", "gaya", "raha", "rahi", "rahe",
    "bhi", "yeh", "woh", "iska", "uska", "abhi", "phir", "sakte",
}


def detect_language(user_said: str) -> str:
    """Heuristic: count Devanagari chars + common Hindi function words.
    Runs in microseconds, good enough for a demo."""
    devanagari_count = sum(1 for ch in user_said if "\u0900" <= ch <= "\u097F")
    if devanagari_count > 0:
        return "hi"

    words = set(user_said.lower().split())
    hindi_word_count = len(words & _HINDI_WORDS)

    if hindi_word_count >= 2:
        return "hi"
    return "en"    

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
    # Set language from caller's early turns
    if user_said.strip() and enquiry.language == "en":
        detected = detect_language(user_said)
        if detected == "hi":
            enquiry.language = "hi"
    # Global escalation checks — run before any state-specific logic
    if current_state not in (State.GREET, State.DONE, State.ESCALATE):
        if check_scope_fence(user_said):
            return ("That's something our counsellors handle directly. "
                    "Let me connect you."), State.ESCALATE
        if check_wants_human(user_said):
            return "Sure, connecting you to a counsellor now.", State.ESCALATE

    
    # Smart bypass: if caller jumps straight to business, skip greeting/identify
    if current_state in (State.GREET, State.IDENTIFY):
        keywords = {"jee", "cuet", "percentile", "score", "course", "btech", "cse", "ai", "ml", "b.tech", "admission"}
        if any(w in user_said.lower() for w in keywords):
            current_state = State.ENQUIRE

    if current_state == State.GREET:
        return handle_greet(enquiry)

    if current_state == State.IDENTIFY:
        if enquiry.caller_name is None and user_said.strip():
            enquiry.caller_name = user_said.strip()
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
        return "You'll receive a call back from our counsellor shortly. Thank you for calling!", State.DONE

    return "Sorry, something went wrong.", State.ESCALATE

if __name__ == "__main__":
    e = Enquiry()
    state = State.GREET

    caller_turns = ["", "Ramesh", "Aryan", "",
                     "cse mein interest hai",
                     "yes",
                     "JEE main diya tha",
                     "91 percentile mila tha",
                     "", "yes", "Saturday 11 AM", "", "haan", ""]

    for said in caller_turns:
        msg, state = handle_turn(e, state, said)
        print(f"[{state.value}] Agent: {msg}")
        if state == State.DONE:
            break