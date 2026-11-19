"""Public and historical column names retain one registry identity."""
import pytest

from textpicos.content import article_registry


@pytest.mark.parametrize("column", ["AI 上手坊", "AI上手坊", "手把手实验室", "hands-on-lab"])
def test_intellifuture_column_aliases_register_same_entry(tmp_path, monkeypatch, column):
    pending = tmp_path / "pending"
    pending.mkdir()
    catalogs = tmp_path / "catalogs"
    catalogs.mkdir()
    monkeypatch.setattr(article_registry, "PENDING", pending)
    monkeypatch.setattr(article_registry, "ARTIFACTS", catalogs)
    registry = catalogs / "intellifuture-hands-on-lab-registry.md"
    registry.write_text("| 日期 | slug | 标题 | 状态 |\n|---|---|---|---|\n")
    article = tmp_path / "2026-11-19-agent-starter.md"
    article.write_text("---\ntitle: Agent starter\nslug: agent-starter\ndate: 2026-11-19\n---\nFixture only.\n")
    result = article_registry.register(article, "pending", "intellifuture", column)
    assert result["column"] == "hands-on-lab"
    assert result["registry"] == str(registry)
    assert "| agent-starter | Agent starter | pending |" in registry.read_text()
    assert not article_registry.register(article, "pending", "intellifuture", column)["changed"]
