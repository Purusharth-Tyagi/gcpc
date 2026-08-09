"""H1:15 unblock. Push this BEFORE you build anything real.
Three people are blocked until it exists. Delete once store.py works."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from contracts.types import Resolution, Intent

_M = {
    "cse": Resolution("c01", "B.Tech Computer Science and Engineering (AI & ML)",
                      "{b1i tEk s1i 1Es 1i}", 0.95, "accept",
                      {"fees_per_year": 185000, "seats": 120, "duration_years": 4,
                       "cutoffs": {"jee_main": 88.0}}),
    "jee": Resolution("jee_main", "JEE Main", "{J1i 1i 1i m1eyn}", 0.95, "accept",
                      {"score_type": "percentile", "score_min": 0, "score_max": 100}),
}

def resolve(text, kind, filters=None):
    for k, v in _M.items():
        if k in text.lower():
            return v
    return None

def route(text):
    return Intent("eligibility", 0.9) if "eligib" in text.lower() else Intent("unknown", 0.0)

def recall(phone, k=3):
    return []

