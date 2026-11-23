"""Optional scikit-learn baseline. Import only when training is requested."""
from collections import defaultdict

VERSION = "baseline-rf-1"
MIN_STUDENTS = 20
MIN_SEQUENCES = 100
MAX_VALIDATION_MAE = 10.0  # percentage points; release gate, not a claimed result

def _features(previous, semester):
    values = [float(row["percentage"]) for row in previous]
    return [values[-1], sum(values) / len(values), len(values), float(semester), float(previous[-1].get("semester", semester))]

def train_if_suitable(history):
    """Train and evaluate by held-out student groups. Return None unless suitable.

    Each row requires student_key, percentage, semester, and assessment_date.
    No demographic or other protected attributes are used.
    """
    grouped = defaultdict(list)
    for row in history:
        try:
            score = float(row["percentage"])
            if 0 <= score <= 100:
                grouped[str(row["student_key"])].append({**row, "percentage": score})
        except (KeyError, TypeError, ValueError):
            continue
    x, y, groups = [], [], []
    for key, attempts in grouped.items():
        attempts.sort(key=lambda row: row["assessment_date"])
        if len(attempts) < 3:
            continue
        for index in range(2, len(attempts)):
            x.append(_features(attempts[:index], attempts[index]["semester"]))
            y.append(attempts[index]["percentage"])
            groups.append(key)
    if len(set(groups)) < MIN_STUDENTS or len(y) < MIN_SEQUENCES:
        return None

    # sklearn imports stay out of ordinary app requests.
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.dummy import DummyRegressor
    from sklearn.model_selection import GroupShuffleSplit
    from sklearn.metrics import mean_absolute_error, r2_score
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=37)
    train_idx, test_idx = next(splitter.split(x, y, groups))
    candidate = RandomForestRegressor(n_estimators=150, min_samples_leaf=3, random_state=37, n_jobs=1)
    baseline = DummyRegressor(strategy="mean")
    candidate.fit([x[i] for i in train_idx], [y[i] for i in train_idx])
    baseline.fit([x[i] for i in train_idx], [y[i] for i in train_idx])
    test_x, actual = [x[i] for i in test_idx], [y[i] for i in test_idx]
    predicted = candidate.predict(test_x)
    baseline_mae = mean_absolute_error(actual, baseline.predict(test_x))
    mae = mean_absolute_error(actual, predicted)
    r2 = r2_score(actual, predicted) if len(actual) > 1 else float("nan")
    result = {"available": False, "reason": "The baseline did not pass held-out validation.", "version": VERSION,
              "students": len(set(groups)), "sequences": len(y), "mae": mae, "baseline_mae": baseline_mae, "r2": r2}
    if mae > MAX_VALIDATION_MAE or mae >= baseline_mae:
        return result
    candidate.fit(x, y)
    result.update(available=True, model=candidate, limitations="Estimate from prior assessment percentages; evaluated on held-out students.")
    result.pop("reason", None)
    return result

def predict_next(validated_model, prior_attempts, semester):
    if not validated_model or not validated_model.get("available") or len(prior_attempts) < 2:
        return None
    estimate = float(validated_model["model"].predict([_features(prior_attempts, semester)])[0])
    return max(0.0, min(100.0, estimate))
