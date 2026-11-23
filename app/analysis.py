"""Pure academic calculations shared by pages and reports."""
DEFAULT_RULES = {"grade_ranges": [{"label":"F","min":0,"max":49.9999},{"label":"D","min":50,"max":59.9999},{"label":"C","min":60,"max":69.9999},{"label":"B","min":70,"max":79.9999},{"label":"A","min":80,"max":100}], "subject_pass_percent":40, "overall_pass_percent":40, "weak_threshold":50}
MAX_SUBJECT_MARKS = 100
MAX_CUSTOM_PASS_MARK = 40

def validate_grade_ranges(ranges):
    if not isinstance(ranges, list) or not ranges: raise ValueError("At least one grade range is required.")
    try:
        ordered = sorted(ranges, key=lambda r: float(r["min"]))
    except (KeyError, TypeError, ValueError):
        raise ValueError("Every grade range needs a numeric minimum and maximum.")
    if float(ordered[0]["min"]) != 0 or float(ordered[-1]["max"]) != 100: raise ValueError("Grade ranges must cover 0 through 100.")
    previous = -0.0001
    labels = set()
    for r in ordered:
        low, high = float(r["min"]), float(r["max"])
        label = str(r.get("label", "")).strip().casefold()
        import math
        if not label or label in labels or not math.isfinite(low) or not math.isfinite(high) or low < 0 or high > 100 or low > high or low <= previous: raise ValueError("Grade ranges must have unique labels and be valid and non-overlapping.")
        labels.add(label)
        previous = high
    for a,b in zip(ordered, ordered[1:]):
        if abs(float(a["max"]) + 0.0001 - float(b["min"])) > 0.00011: raise ValueError("Grade ranges must not leave gaps.")
    return ordered

def grade_for(value, ranges):
    for r in ranges:
        if float(r["min"]) <= value <= float(r["max"]): return r["label"]
    return "—"

def analyze_marks(rows, rules=None):
    rules = rules or DEFAULT_RULES
    ranges = validate_grade_ranges(rules["grade_ranges"])
    marks, names = [], set()
    for row in rows:
        name = str(row.get("subject", "")).strip()
        if not name or name.casefold() in names: raise ValueError("Subject names are required and must be unique in an assessment.")
        names.add(name.casefold())
        try:
            obtained, maximum = float(row["obtained"]), float(row["maximum"])
            raw_passing = row.get("passing")
            passing = float(raw_passing) if raw_passing not in (None, "") else maximum * float(rules["subject_pass_percent"]) / 100
        except (TypeError, ValueError, KeyError): raise ValueError("Enter numeric marks, maximum marks and passing marks for each subject.")
        import math
        if not all(math.isfinite(value) for value in (obtained, maximum, passing)) or maximum <= 0 or maximum > MAX_SUBJECT_MARKS or obtained < 0 or obtained > maximum or passing < 0 or passing > maximum or (raw_passing not in (None, "") and passing > MAX_CUSTOM_PASS_MARK):
            raise ValueError(f"Marks for {name} are outside the valid range. Maximum marks cannot exceed 100 and a custom pass mark cannot exceed 40.")
        marks.append({"subject":name,"obtained":obtained,"maximum":maximum,"passing":passing,"percentage":obtained/maximum*100})
    if not marks: raise ValueError("Add at least one subject before analyzing.")
    total, maximum = sum(x["obtained"] for x in marks), sum(x["maximum"] for x in marks)
    overall = total / maximum * 100
    mean = sum(x["percentage"] for x in marks) / len(marks)
    for x in marks:
        x["grade"] = grade_for(x["percentage"], ranges)
        x["passed"] = x["obtained"] >= x["passing"]
        x["relative"] = "stronger" if x["percentage"] >= mean else "needs focus"
        if not x["passed"]: x["recommendation"] = f"Prioritize revision: below passing marks by {x['passing']-x['obtained']:.1f}."
        elif x["percentage"] < float(rules["weak_threshold"]): x["recommendation"] = "Schedule focused practice; below the configured focus threshold."
        else: x["recommendation"] = "Maintain this result with regular review."
    return {"total_obtained":total,"total_maximum":maximum,"percentage":overall,"grade":grade_for(overall,ranges),"passed":overall >= float(rules["overall_pass_percent"]) and all(x["passed"] for x in marks),"marks":marks,"suggestions":[x["recommendation"] for x in marks if not x["passed"] or x["percentage"] < float(rules["weak_threshold"])],"rules":rules}
