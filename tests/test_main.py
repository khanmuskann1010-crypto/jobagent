from src.main import _validate_args


def test_validate_args_rejects_empty_keywords():
    assert _validate_args("   ", 25, 0) is not None


def test_validate_args_rejects_non_positive_max_results():
    assert _validate_args("marketing", 0, 0) is not None


def test_validate_args_rejects_out_of_range_min_score():
    assert _validate_args("marketing", 25, 11) is not None
    assert _validate_args("marketing", 25, -1) is not None


def test_validate_args_accepts_valid_input():
    assert _validate_args("marketing", 25, 5) is None
