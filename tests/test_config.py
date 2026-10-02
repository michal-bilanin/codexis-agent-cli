from codexis_docs.config import index_path


def test_index_path_defaults_to_home_directory(monkeypatch, tmp_path):
    monkeypatch.delenv("CODEXIS_DOCS_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    assert index_path() == tmp_path / ".codexis-docs" / "index.db"


def test_index_path_honours_codexis_docs_home(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEXIS_DOCS_HOME", str(tmp_path / "custom"))

    assert index_path() == tmp_path / "custom" / "index.db"
