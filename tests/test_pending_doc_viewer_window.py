"""承辦中公文點開後,切到「正確的」公文閱覽器分頁:
- 跳過殘留的 sessionTimeout.jsp(操作時間逾時警告)分頁
- 有文號時只接受 URL 帶對應 doSno 的分頁
- 點前清掉殘留非主分頁
(2026-10-13 實機:edoc 二次登入轉址多開一個逾時警告分頁,handle_opened_document
 挑「最後一個非主分頁」挑到它,找不到下載按鈕而中止)
"""
import pending_doc_handler as p


class _SwitchTo:
    def __init__(self, drv):
        self._d = drv

    def window(self, h):
        if h not in self._d.window_handles:
            raise RuntimeError(f"no such window {h}")
        self._d.current_window_handle = h

    def default_content(self):
        pass


class _FakeDriver:
    """handles:list of (handle, url);可用 later 在第 N 次讀 window_handles 後再長出分頁。"""

    def __init__(self, handles, main="main", later=None, later_after=2):
        self._urls = dict(handles)
        self._order = [h for h, _ in handles]
        self.current_window_handle = main
        self.switch_to = _SwitchTo(self)
        self._later = later or []
        self._later_after = later_after
        self._reads = 0
        self.closed = []

    @property
    def window_handles(self):
        self._reads += 1
        if self._later and self._reads > self._later_after:
            for h, u in self._later:
                if h not in self._urls:
                    self._urls[h] = u
                    self._order.append(h)
        return list(self._order)

    @property
    def current_url(self):
        return self._urls[self.current_window_handle]

    def close(self):
        h = self.current_window_handle
        self.closed.append(h)
        self._order.remove(h)
        del self._urls[h]


VIEWER = "https://edoc.gov.taipei/tcqb/oa/index.html?app=editor&doSno=1156010457&gbDocflowId=1&dialogType=1"
TIMEOUT = "https://edoc.gov.taipei/tcqb/home/sessionTimeout.jsp"
MAIN = "https://edoc.gov.taipei/tcqb/home/default.jsp#"


def test_pick_viewer_by_doc_no_even_if_timeout_tab_is_last():
    d = _FakeDriver([("main", MAIN), ("v", VIEWER), ("t", TIMEOUT)])
    assert p._find_doc_viewer_window(d, "main", "MWAA1156010457", timeout=1) == "v"


def test_timeout_tab_only_returns_none(monkeypatch):
    monkeypatch.setattr(p.time, "sleep", lambda s: None)
    d = _FakeDriver([("main", MAIN), ("t", TIMEOUT)])
    assert p._find_doc_viewer_window(d, "main", "MWAA1156010457", timeout=0.2) is None
    assert d.current_window_handle == "main"  # 失敗要切回主分頁


def test_wrong_doc_no_tab_is_rejected(monkeypatch):
    monkeypatch.setattr(p.time, "sleep", lambda s: None)
    other = VIEWER.replace("1156010457", "1156009999")
    d = _FakeDriver([("main", MAIN), ("o", other)])
    assert p._find_doc_viewer_window(d, "main", "MWAA1156010457", timeout=0.2) is None


def test_no_doc_no_prefers_new_tab_and_skips_timeout():
    d = _FakeDriver([("main", MAIN), ("t", TIMEOUT), ("v", VIEWER)])
    assert p._find_doc_viewer_window(d, "main", None, before_handles={"main", "t"}, timeout=1) == "v"


def test_viewer_tab_appearing_late_is_found(monkeypatch):
    monkeypatch.setattr(p.time, "sleep", lambda s: None)
    d = _FakeDriver([("main", MAIN), ("t", TIMEOUT)], later=[("v", VIEWER)], later_after=2)
    assert p._find_doc_viewer_window(d, "main", "MWAA1156010457", timeout=5) == "v"


def test_close_stale_windows_keeps_main():
    d = _FakeDriver([("main", MAIN), ("t", TIMEOUT), ("v", VIEWER)])
    assert p._close_stale_windows(d) == 2
    assert d.closed == ["t", "v"]
    assert d.window_handles == ["main"]
    assert d.current_window_handle == "main"


def test_handle_opened_document_uses_matching_tab(monkeypatch):
    d = _FakeDriver([("main", MAIN), ("v", VIEWER), ("t", TIMEOUT)])
    seen = {}

    def fake_download(driver):
        seen["url"] = driver.current_url
        return True, None

    monkeypatch.setattr(p, "_download_and_extract", fake_download)
    monkeypatch.setattr(p.time, "sleep", lambda s: None)
    assert p.handle_opened_document(d, expect_doc_no="MWAA1156010457") is True
    assert seen["url"] == VIEWER


def test_handle_opened_document_fails_without_viewer(monkeypatch):
    d = _FakeDriver([("main", MAIN), ("t", TIMEOUT)])
    called = []
    monkeypatch.setattr(p, "_download_and_extract", lambda drv: called.append(1) or (True, None))
    monkeypatch.setattr(p.time, "sleep", lambda s: None)
    assert p.handle_opened_document(d, expect_doc_no="MWAA1156010457", timeout=0.2) is False
    assert called == []


def test_close_session_timeout_tabs_only_closes_timeout_pages():
    d = _FakeDriver([("main", MAIN), ("t", TIMEOUT), ("v", VIEWER)])
    assert p.close_session_timeout_tabs(d) == 1
    assert d.closed == ["t"]
    assert d.window_handles == ["main", "v"]
    assert d.current_window_handle == "main"


def test_close_session_timeout_tabs_nothing_to_close():
    d = _FakeDriver([("main", MAIN)])
    assert p.close_session_timeout_tabs(d) == 0
    assert d.current_window_handle == "main"


def test_no_doc_no_waits_for_new_tab_before_falling_back(monkeypatch):
    """沒文號時,點前就存在的分頁不能第一輪就拿來用,要等新分頁出現。"""
    monkeypatch.setattr(p.time, "sleep", lambda s: None)
    stale = VIEWER.replace("1156010457", "1156009999")
    d = _FakeDriver([("main", MAIN), ("s", stale)], later=[("v", VIEWER)], later_after=2)
    assert p._find_doc_viewer_window(d, "main", None, before_handles={"main", "s"}, timeout=5) == "v"


def test_no_doc_no_falls_back_to_old_tab_only_after_timeout(monkeypatch):
    monkeypatch.setattr(p.time, "sleep", lambda s: None)
    stale = VIEWER.replace("1156010457", "1156009999")
    d = _FakeDriver([("main", MAIN), ("s", stale)])
    assert p._find_doc_viewer_window(d, "main", None, before_handles={"main", "s"}, timeout=0.2) == "s"
    assert d.current_window_handle == "s"


def test_dosno_match_is_exact_not_prefix(monkeypatch):
    monkeypatch.setattr(p.time, "sleep", lambda s: None)
    longer = VIEWER.replace("doSno=1156010457", "doSno=11560104570")
    d = _FakeDriver([("main", MAIN), ("x", longer)])
    assert p._find_doc_viewer_window(d, "main", "MWAA1156010457", timeout=0.2) is None
    assert p._url_has_dosno(VIEWER, "1156010457")
    assert not p._url_has_dosno(longer, "1156010457")


def test_pending_doc_stops_immediately_when_viewer_not_found(monkeypatch):
    """handle_opened_document 回 False → 不再等 10s 看 sidebar,直接停並回 False。"""
    import document_system as ds
    d = _FakeDriver([("main", MAIN), ("t", TIMEOUT)])
    sleeps = []
    monkeypatch.setattr(ds.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(ds, "_get_sidebar_paren_count", lambda drv, label, **kw: 1)
    monkeypatch.setattr(ds, "_switch_to_frame_with_xpath", lambda drv, xp, name: True)
    monkeypatch.setattr(ds, "_click_first_document_in_pending", lambda drv, label: "MWAA1156010457")
    monkeypatch.setattr(p, "handle_opened_document", lambda drv, **kw: False)
    banners = []
    monkeypatch.setattr(ds, "_print_stop_banner", lambda r, a: banners.append(r))
    assert ds.pending_doc(d) is False
    assert sleeps == []
    assert "MWAA1156010457" in banners[0] and "未填字未送出" in banners[0]
