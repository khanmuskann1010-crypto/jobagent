from src.main import _validate_args


def test_validate_args_rejects_empty_company():
    assert _validate_args("   ", "") is not None


def test_validate_args_accepts_empty_url():
    assert _validate_args("Acme", "") is None


def test_validate_args_rejects_malformed_url():
    assert _validate_args("Acme", "not-a-url") is not None


def test_validate_args_accepts_valid_url():
    assert _validate_args("Acme", "https://acme.com") is None
