import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrieval.store import resolve


def resolve_course(query: str):
    """
    Returns (canonical_name, resolution) if accepted.
    Returns (None, resolution) if needs confirmation or rejected.
    """
    res = resolve(query, kind="course")
    if res is None or res.band == "reject":
        return None, None
    if res.band == "confirm":
        return None, res          # caller needs to confirm alternatives
    return res.canonical, res     # accepted


def resolve_exam(query: str):
    res = resolve(query, kind="exam")
    if res is None or res.band == "reject":
        return None, None
    if res.band == "confirm":
        return None, res
    return res.canonical, res


if __name__ == "__main__":
    name, res = resolve_course("cse")
    print("Course resolved:", name)

    name2, res2 = resolve_exam("jee")
    print("Exam resolved:", name2)

    name3, res3 = resolve_course("kuch random cheez jo match na ho")
    print("Random query result:", name3)