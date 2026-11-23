import pytest
from app.analysis import DEFAULT_RULES, analyze_marks, validate_grade_ranges

def test_weighted_percentage_and_subject_pass_rules():
    result = analyze_marks([{"subject":"Math","obtained":80,"maximum":100,"passing":40},{"subject":"Lab","obtained":9,"maximum":10,"passing":8}])
    assert result["total_obtained"] == 89
    assert result["total_maximum"] == 110
    assert result["percentage"] == pytest.approx(89/110*100)
    assert result["passed"] is True

def test_high_overall_does_not_hide_failed_subject():
    result = analyze_marks([{"subject":"Strong","obtained":100,"maximum":100,"passing":40},{"subject":"Failed","obtained":10,"maximum":100,"passing":40}])
    assert result["percentage"] == pytest.approx(55)
    assert result["marks"][1]["passed"] is False
    assert result["passed"] is False

@pytest.mark.parametrize("row", [{"subject":"A","obtained":101,"maximum":100},{"subject":"A","obtained":-1,"maximum":100},{"subject":"A","obtained":1,"maximum":0}])
def test_reject_invalid_marks(row):
    with pytest.raises(ValueError): analyze_marks([row])

@pytest.mark.parametrize("row", [{"subject":"A","obtained":80,"maximum":101},{"subject":"A","obtained":40,"maximum":100,"passing":41}])
def test_subject_maximum_and_custom_pass_mark_are_capped(row):
    with pytest.raises(ValueError): analyze_marks([row])

def test_reject_duplicate_and_empty_subject():
    with pytest.raises(ValueError): analyze_marks([{"subject":"A","obtained":1,"maximum":10},{"subject":"a","obtained":1,"maximum":10}])
    with pytest.raises(ValueError): analyze_marks([])

def test_invalid_grade_ranges_rejected():
    with pytest.raises(ValueError): validate_grade_ranges([{"label":"A","min":0,"max":100},{"label":"B","min":90,"max":100}])
    assert validate_grade_ranges(DEFAULT_RULES["grade_ranges"])

def test_prediction_module_falls_back_without_enough_history():
    from app.prediction import train_if_suitable
    assert train_if_suitable([]) is None
