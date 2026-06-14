"""document_closure 純函式測試(不需瀏覽器)。"""
import os
import stat

from document_closure.document_closure import _force_rmtree


def test_force_rmtree_removes_readonly_shell_dir(tmp_path):
    """回歸:KdApp zip 解壓後的「來文」殼層是 read-only 目錄,一般 shutil.rmtree
    在 Windows 會拋 WinError 5(實測 MWAA1156005762 因此整包刪不掉)。
    _force_rmtree 應清掉 read-only 後成功刪掉整包。"""
    root = tmp_path / "MWAA_x"
    root.mkdir()
    (root / "main.pdf").write_text("x", encoding="utf-8")
    shell = root / "來文"
    shell.mkdir()
    os.chmod(shell, stat.S_IREAD)  # read-only 空殼目錄(重現 bug)

    assert _force_rmtree(str(root)) is True
    assert not root.exists()


def test_force_rmtree_removes_readonly_file(tmp_path):
    """read-only 檔(如合併版.pdf)在 Windows 也會擋 rmtree;_force_rmtree 要能清掉。"""
    root = tmp_path / "MWAA_y"
    root.mkdir()
    f = root / "合併版.pdf"
    f.write_text("y", encoding="utf-8")
    os.chmod(f, stat.S_IREAD)

    assert _force_rmtree(str(root)) is True
    assert not root.exists()
