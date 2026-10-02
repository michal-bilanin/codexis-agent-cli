from codexis_docs.cli import main


def test_search_without_lang_is_a_usage_error(capsys):
    assert main(["search", "foo"]) == 2
    assert "--lang" in capsys.readouterr().err


def test_search_with_unsupported_lang_is_a_usage_error(capsys):
    assert main(["search", "foo", "--lang", "de"]) == 2
    assert "invalid choice: 'de'" in capsys.readouterr().err


def test_search_with_non_positive_limit_is_a_usage_error(capsys):
    assert main(["search", "foo", "--lang", "cs", "--limit", "0"]) == 2
    assert "argument --limit: must be a positive integer" in capsys.readouterr().err
