"""document_closure 純函式測試(不需瀏覽器)。"""
import os
import stat

from document_closure.document_closure import (
    _force_rmtree, _doc_no_to_sno, _switch_to_doc_viewer_window,
    _close_stale_viewer_windows, _click_attachment_archive_and_close,
    _handle_pincode_popup, _pincode_popup_signing_done,
)
import document_closure.document_closure as dc


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
            # 真 Selenium 切 window 會把 frame focus 重置回 top
            if hasattr(self._d, "in_frame"):
                self._d.in_frame = False

        def default_content(self):
            if hasattr(self._d, "in_frame"):
                self._d.in_frame = False

        def frame(self, ref):
            if hasattr(self._d, "in_frame"):
                self._d.in_frame = True

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


# ── 存查前的「附件歸檔」步驟(2026-09-18 使用者指定) ──────────────────────────
#
# 存查表單載入後要先點「附件歸檔」,系統另開 AOSDD017F_s09.jsp 分頁,不需輸入任何
# 東西,直接關掉回存查表單再填檔號。關分頁後一定要切回 dTreeContent frame,否則
# 後續填檔號會全部找不到元素。

_ARCHIVE_TAB_URL = ("https://edoc.gov.taipei/tcqb/tbkn/aosdd/"
                    "AOSDD017F_s09.jsp?showBack=N")


class _FakeArchiveDriver(_FakeViewerDriver):
    """在 _FakeViewerDriver 上加:frame 遍歷、點按鈕會開新分頁。

    模擬 edoc 的實際結構:按鈕在 dTreeContent iframe 內,top-level 找不到 ——
    這正是 2026-09-18 實機失敗的原因(函式原本只在呼叫端的 focus 下找)。
    """

    def __init__(self, button_xpath_hit=True, opens_tab=True):
        super().__init__(
            {"main": "https://edoc.gov.taipei/tcqb/home/default.jsp"}, current="main")
        self._button_hit = button_xpath_hit
        self._opens_tab = opens_tab
        self.clicked = 0
        self.in_frame = False  # False = top-level

    def find_elements(self, by, xpath):
        if "iframe" in xpath or "frame" in xpath:
            return [] if self.in_frame else ["dTreeContent"]
        # 按鈕只存在於 iframe 內
        if self._button_hit and self.in_frame and "附件歸檔" in xpath:
            return [_FakeButton(self)]
        return []

    def execute_script(self, script, *args):
        # 點按鈕 → 開附件歸檔分頁
        if args and isinstance(args[0], _FakeButton):
            self.clicked += 1
            if self._opens_tab:
                self._urls["archive_tab"] = _ARCHIVE_TAB_URL
        return None


class _FakeButton:
    def __init__(self, driver):
        self._d = driver

    def is_displayed(self):
        return True


def _patch_frame_switch(monkeypatch, result=True, record=None):
    """攔截 document_system._switch_to_frame_with_xpath(真的會找 DOM)。"""
    import document_system

    def _fake(driver, xpath, label, *a, **kw):
        if record is not None:
            record.append(label)
        return result

    monkeypatch.setattr(document_system, "_switch_to_frame_with_xpath", _fake)


def test_attachment_archive_opens_closes_and_returns_to_form(monkeypatch):
    frames = []
    _patch_frame_switch(monkeypatch, result=True, record=frames)
    d = _FakeArchiveDriver()

    assert _click_attachment_archive_and_close(d, open_timeout=2) is True
    assert d.clicked == 1, "要真的點到「附件歸檔」"
    assert "archive_tab" in d.closed, "附件歸檔分頁要被關掉"
    assert d.current_window_handle == "main", "要回到存查表單分頁"
    assert frames, "關分頁後必須重新切回存查表單 frame"


def test_attachment_archive_fails_when_button_missing(monkeypatch):
    _patch_frame_switch(monkeypatch)
    d = _FakeArchiveDriver(button_xpath_hit=False)
    assert _click_attachment_archive_and_close(d, open_timeout=1) is False


def test_attachment_archive_fails_when_tab_never_opens(monkeypatch):
    """點了但分頁沒開 → 回 False,且要留在主分頁(不可默默往下存查)。"""
    _patch_frame_switch(monkeypatch)
    d = _FakeArchiveDriver(opens_tab=False)
    assert _click_attachment_archive_and_close(d, open_timeout=1) is False
    assert d.current_window_handle == "main"


def test_attachment_archive_fails_when_frame_switch_back_fails(monkeypatch):
    """分頁關了但切不回存查表單 frame → 必須回 False,不能繼續填檔號。"""
    _patch_frame_switch(monkeypatch, result=False)
    d = _FakeArchiveDriver()
    assert _click_attachment_archive_and_close(d, open_timeout=2) is False


# ── pinCode popup「記住 PIN → 自動簽章完成」完成態(2026-09-23 MWAA1156009472 誤報) ─────
#
# KdApp 勾過「記住 PIN」後 popup 不顯示輸入框、自動簽章,進度停在「…更新SI檔完成」且不自動關;
# 舊邏輯只找可見 input → 15s 後報「找不到 pinCode input」,但存查其實已成功。

class _FakePinPopupDriver(_FakeViewerDriver):
    """兩個分頁:main + 16888 popup。popup 的 DOM 狀態由 done_js_result 決定。"""

    def __init__(self, done_js_result, visible_input=False):
        super().__init__({
            "main": "https://edoc.gov.taipei/tcqb/home/default.jsp",
            "popup": "http://localhost:16888/doPostMsg",
        }, current="main")
        self._done = done_js_result
        self._visible_input = visible_input
        self.filled = []

    def execute_script(self, script, *args):
        if script is dc._PINCODE_DONE_JS:
            return self._done
        return None

    def find_elements(self, by, xpath):
        if self._visible_input and "pinCode" in xpath and self.current_window_handle == "popup":
            return [_FakeBtn()]
        return []


class _FakeBtn:
    def is_displayed(self):
        return True


def test_signing_done_detects_completed_popup():
    d = _FakePinPopupDriver({"done": True, "why": "body 含「完成」",
                             "tail": "公文文號：MWAA1156009472更新SI檔完成"})
    done, why = _pincode_popup_signing_done(d)
    assert done is True and "完成" in why


def test_signing_done_false_when_not_finished_or_failed():
    d = _FakePinPopupDriver({"done": False, "why": "尚未完成", "tail": ""})
    assert _pincode_popup_signing_done(d)[0] is False
    d2 = _FakePinPopupDriver({"done": False, "failed": True, "why": "body 含失敗/錯誤字樣", "tail": "密碼錯誤"})
    assert _pincode_popup_signing_done(d2)[0] is False


def test_handle_pincode_popup_treats_auto_signed_as_success_and_closes(monkeypatch):
    """完成態:沒有可見 input → 不再報錯,視為成功並主動關掉 popup、切回主分頁。"""
    import taipeion_login_selenium
    monkeypatch.setattr(taipeion_login_selenium, "_read_pin", lambda: "630124")
    monkeypatch.setattr(dc.time, "sleep", lambda s: None)
    d = _FakePinPopupDriver({"done": True, "why": "pinCode 已填且輸入框/確定鈕皆隱藏",
                             "tail": "更新SI檔完成"})

    assert _handle_pincode_popup(d, popup_timeout=1, close_timeout=1) is True
    assert "popup" in d.closed, "完成態要主動關掉 popup"
    assert d.current_window_handle == "main"


def test_handle_pincode_popup_still_fails_when_no_input_and_not_done(monkeypatch):
    """真的沒 input 也沒完成訊號 → 維持 False(popup 保留供手動處理),不可誤判成功。"""
    import taipeion_login_selenium
    monkeypatch.setattr(taipeion_login_selenium, "_read_pin", lambda: "630124")
    monkeypatch.setattr(dc.time, "sleep", lambda s: None)
    # 讓 15s 的找 input 迴圈立刻到期
    t = iter([0, 0, 0, 0, 100, 100, 100, 100, 100])
    monkeypatch.setattr(dc.time, "time", lambda: next(t, 100))
    d = _FakePinPopupDriver({"done": False, "why": "尚未完成", "tail": ""})

    assert _handle_pincode_popup(d, popup_timeout=1, close_timeout=1) is False
    assert d.closed == [], "沒完成就不能替使用者關掉 popup"
