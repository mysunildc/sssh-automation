"""document_closure 純函式測試(不需瀏覽器)。"""
import os
import stat

from document_closure.document_closure import (
    _force_rmtree, _doc_no_to_sno, _switch_to_doc_viewer_window,
    _close_stale_viewer_windows,
)


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


# ── 公文閱覽器分頁必須對得上剛點的公文(2026-09-16 實機事故) ──────────────────
#
# 事故經過:第 2 輪點的是 MWAA1156009143,但 driver 切到的是上一輪殘留的
# doSno=1156009372 分頁,於是在「別件公文」上讀到「如擬」並下載,把 9372 的
# 內容當成 9143 的結案資料(後續讀不到 9143 結案目錄才中止)。

class _FakeViewerDriver:
    """模擬多分頁 driver:handles → url 的對應表。"""

    def __init__(self, handles_urls, current):
        self._urls = dict(handles_urls)
        self.current_window_handle = current
        self.closed = []

    @property
    def window_handles(self):
        return [h for h in self._urls if h not in self.closed]

    @property
    def current_url(self):
        return self._urls[self.current_window_handle]

    @property
    def title(self):
        return "公文簽核"

    class _SwitchTo:
        def __init__(self, d):
            self._d = d

        def window(self, h):
            self._d.current_window_handle = h

        def default_content(self):
            pass

    @property
    def switch_to(self):
        return _FakeViewerDriver._SwitchTo(self)

    def close(self):
        self.closed.append(self.current_window_handle)


def test_doc_no_to_sno_extracts_numeric_part():
    assert _doc_no_to_sno("MWAA1156009143") == "1156009143"
    assert _doc_no_to_sno("MWAA1156009372") == "1156009372"
    assert _doc_no_to_sno("") is None
    assert _doc_no_to_sno(None) is None
    assert _doc_no_to_sno("無數字") is None


def test_switch_to_viewer_picks_tab_matching_doc_no():
    """有多個分頁時,要挑 doSno 對得上的那一個,不是第一個非主分頁。"""
    d = _FakeViewerDriver({
        "main": "https://edoc.gov.taipei/tcqb/home/default.jsp",
        "stale": "https://edoc.gov.taipei/tcqb/oa/index.html?app=editor&doSno=1156009372",
        "want": "https://edoc.gov.taipei/tcqb/oa/index.html?app=editor&doSno=1156009143",
    }, current="main")

    assert _switch_to_doc_viewer_window(d, expect_doc_no="MWAA1156009143", timeout=0) is True
    assert d.current_window_handle == "want"


def test_switch_to_viewer_refuses_wrong_document():
    """只有別件公文的殘留分頁時,必須失敗並切回主分頁 —— 不可拿它代替。

    這正是事故的關鍵:舊版會直接切到 9372 分頁,在錯的公文上判定「如擬」並下載。
    """
    d = _FakeViewerDriver({
        "main": "https://edoc.gov.taipei/tcqb/home/default.jsp",
        "stale": "https://edoc.gov.taipei/tcqb/oa/index.html?app=editor&doSno=1156009372",
    }, current="main")

    assert _switch_to_doc_viewer_window(d, expect_doc_no="MWAA1156009143", timeout=0) is False
    assert d.current_window_handle == "main", "失敗時要留在主分頁"


def test_switch_to_viewer_refuses_session_timeout_tab():
    """逾時警告頁(sessionTimeout.jsp)也不是目標分頁。"""
    d = _FakeViewerDriver({
        "main": "https://edoc.gov.taipei/tcqb/home/default.jsp",
        "timeout": "https://edoc.gov.taipei/tcqb/home/sessionTimeout.jsp",
    }, current="main")

    assert _switch_to_doc_viewer_window(d, expect_doc_no="MWAA1156009143", timeout=0) is False


def test_switch_to_viewer_falls_back_when_no_doc_no():
    """沒給文號(或文號抽不出數字)時維持舊行為:切到任一非主分頁。"""
    d = _FakeViewerDriver({
        "main": "https://edoc.gov.taipei/tcqb/home/default.jsp",
        "any": "https://edoc.gov.taipei/tcqb/oa/index.html?app=editor&doSno=1156009372",
    }, current="main")

    assert _switch_to_doc_viewer_window(d, expect_doc_no=None, timeout=0) is True
    assert d.current_window_handle == "any"


def test_close_stale_viewer_windows_closes_only_non_main():
    d = _FakeViewerDriver({
        "main": "https://edoc.gov.taipei/tcqb/home/default.jsp",
        "stale1": "https://edoc.gov.taipei/tcqb/oa/index.html?app=editor&doSno=1156009372",
        "stale2": "https://edoc.gov.taipei/tcqb/home/sessionTimeout.jsp",
    }, current="main")

    assert _close_stale_viewer_windows(d) == 2
    assert sorted(d.closed) == ["stale1", "stale2"]
    assert d.current_window_handle == "main", "清完要切回主分頁"


def test_close_stale_viewer_windows_noop_when_only_main():
    d = _FakeViewerDriver(
        {"main": "https://edoc.gov.taipei/tcqb/home/default.jsp"}, current="main")
    assert _close_stale_viewer_windows(d) == 0
    assert d.closed == []
