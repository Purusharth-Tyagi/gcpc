def eligibility(course_payload: dict, exam_id: str, score: float) -> str:
    """
    Returns: "likely" | "borderline" | "below" | "unknown"
    Never rounds in the applicant's favour.
    """
    cutoff = course_payload.get("cutoffs", {}).get(exam_id)
    if cutoff is None:
        return "unknown"
    if score >= cutoff + 3:
        return "likely"
    if score >= cutoff:
        return "borderline"
    return "below"


if __name__ == "__main__":
    course = {"cutoffs": {"jee_main": 88.0}}
    print(eligibility(course, "jee_main", 91))
    print(eligibility(course, "jee_main", 88))
    print(eligibility(course, "jee_main", 80))
    print(eligibility(course, "cuet", 91))