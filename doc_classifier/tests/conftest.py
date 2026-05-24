"""共用 pytest fixtures。"""
import pytest
from pathlib import Path


@pytest.fixture
def fake_doc_download(tmp_path):
    """造一棵假 document_download/ 樹,含 3 個 MW 子目錄。回 root Path。

    結構:
      tmp_path/document_download/
        MW001/1140001_001A總結.claude-opus-4-7.md   (含 # action: 公告)
        MW002/1140002_001A總結.claude-opus-4-7.md   (含 # action: 存查)
        MW003/1140003_001A總結.claude-opus-4-7.md   (無 action,不該被收)
    """
    root = tmp_path / "document_download"
    root.mkdir()
    (root / "MW001").mkdir()
    (root / "MW001" / "1140001_001A總結.claude-opus-4-7.md").write_text(
        "# action: 公告\n\n發文日期:2026-05-20\n主旨:辦理校園資安宣導\n",
        encoding="utf-8",
    )
    (root / "MW002").mkdir()
    (root / "MW002" / "1140002_001A總結.claude-opus-4-7.md").write_text(
        "# action: 存查\n\n發文日期:2026-05-21\n主旨:函轉教育部來文\n",
        encoding="utf-8",
    )
    (root / "MW003").mkdir()
    (root / "MW003" / "1140003_001A總結.claude-opus-4-7.md").write_text(
        "發文日期:2026-05-22\n主旨:無 action 欄位的公文\n",
        encoding="utf-8",
    )
    return root


@pytest.fixture
def fake_training_dir(tmp_path):
    """造空 training_data/ 目錄。回 Path。"""
    d = tmp_path / "training_data"
    d.mkdir()
    return d
