"""document_closure 純函式測試(不需瀏覽器)。"""
import os
import stat

from document_closure.document_closure import (
    _force_rmtree, _doc_no_to_sno, _switch_to_doc_viewer_window,
    _close_stale_viewer_windows, _click_attachment_archive_and_close,
    _handle_pincode_popup, _pincode_popup_state,
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


def test_popup_state_detects_completed_popup():
    d = _FakePinPopupDriver({"done": True, "why": "body 含「完成」",
                             "tail": "公文文號：MWAA1156009472更新SI檔完成"})
    state, why = _pincode_popup_state(d)
    assert state == "done" and "完成" in why


def test_popup_state_pending_signing_failed():
    d = _FakePinPopupDriver({"done": False, "why": "尚未完成", "tail": ""})
    assert _pincode_popup_state(d)[0] == "pending"
    d2 = _FakePinPopupDriver({"done": False, "failed": True, "why": "body 含失敗/錯誤字樣", "tail": "密碼錯誤"})
    assert _pincode_popup_state(d2)[0] == "failed"
    d3 = _FakePinPopupDriver({"done": False, "signing": True, "why": "進行中", "tail": "取得pincode資料"})
    assert _pincode_popup_state(d3)[0] == "signing"


def test_handle_pincode_popup_treats_auto_signed_as_success_and_closes(monkeypatch):
    """完成態:沒有可見 input → 不再報錯,視為成功並主動關掉 popup、切回主分頁。"""
    import taipeion_login_selenium
    monkeypatch.setattr(taipeion_login_selenium, "_read_pin", lambda: "000000")
    monkeypatch.setattr(dc.time, "sleep", lambda s: None)
    d = _FakePinPopupDriver({"done": True, "why": "pinCode 已填且輸入框/確定鈕皆隱藏",
                             "tail": "更新SI檔完成"})

    assert _handle_pincode_popup(d, popup_timeout=1, close_timeout=1) is True
    assert "popup" in d.closed, "完成態要主動關掉 popup"
    assert d.current_window_handle == "main"


def test_handle_pincode_popup_still_fails_when_no_input_and_not_done(monkeypatch):
    """真的沒 input 也沒完成訊號 → 維持 False(popup 保留供手動處理),不可誤判成功。"""
    import taipeion_login_selenium
    monkeypatch.setattr(taipeion_login_selenium, "_read_pin", lambda: "000000")
    monkeypatch.setattr(dc.time, "sleep", lambda s: None)
    # 讓 15s 的找 input 迴圈立刻到期
    t = iter([0, 0, 0, 0, 100, 100, 100, 100, 100])
    monkeypatch.setattr(dc.time, "time", lambda: next(t, 100))
    d = _FakePinPopupDriver({"done": False, "why": "尚未完成", "tail": ""})

    assert _handle_pincode_popup(d, popup_timeout=1, close_timeout=1) is False
    assert d.closed == [], "沒完成就不能替使用者關掉 popup"


# ── pinCode popup「記住 PIN → 自動簽章進行中」不可提早關窗(2026-10-07 MWAA1156009939 連失 28 輪) ─
#
# 記住 PIN 模式下,popup 一開始就「#pinCode 有值、輸入框/確定鈕隱藏」,但 body 還停在
# 「執行中請勿關閉此視窗 … 已取得憑證卡號 / 取得pincode資料」= 簽章**進行中**。
# 舊判定把這個狀態當完成態、立刻關窗 → 簽章被中斷、公文留在待結案,整輪白做。
# 唯一一輪成功(第 29 輪)正是程式沒找到 popup、放著不動讓它自己跑完。

class _FakeSigningPopupDriver(_FakePinPopupDriver):
    """done JS 依序回傳 states;耗盡後停在最後一個。self_close_after=N 表示第 N 次
    查詢後 popup 自己關掉(模擬 KdApp 簽完自動關窗)。"""

    def __init__(self, states, self_close_after=None):
        super().__init__(states[0])
        self._states = list(states)
        self._calls = 0
        self._self_close_after = self_close_after

    def execute_script(self, script, *args):
        if script is dc._PINCODE_DONE_JS:
            self._calls += 1
            if self._self_close_after is not None and self._calls >= self._self_close_after:
                if "popup" not in self.closed:
                    self.closed.append("popup")   # 視窗自己消失,不經 driver.close()
                    self.current_window_handle = "main"
            idx = min(self._calls - 1, len(self._states) - 1)
            return self._states[idx]
        return None


_SIGNING = {"done": False, "signing": True, "why": "自動簽章進行中(記住 PIN)",
            "tail": "已取得憑證卡號\n取得pincode資料"}
_FINISHED = {"done": True, "signing": False, "why": "body 含「更新SI檔完成/簽章完成」",
             "tail": "公文文號：MWAA1156009939更新SI檔完成"}


def test_handle_pincode_popup_does_not_close_while_auto_signing(monkeypatch):
    """進行中 → 不能關窗;等到 body 出現「更新SI檔完成」才關。"""
    import taipeion_login_selenium
    monkeypatch.setattr(taipeion_login_selenium, "_read_pin", lambda: "000000")
    monkeypatch.setattr(dc.time, "sleep", lambda s: None)
    d = _FakeSigningPopupDriver([_SIGNING, _SIGNING, _SIGNING, _FINISHED])

    assert _handle_pincode_popup(d, popup_timeout=1, close_timeout=5) is True
    assert d._calls >= 4, "必須一路等到完成態,不能在進行中就關窗"
    assert d.closed == ["popup"] and d.current_window_handle == "main"


def test_handle_pincode_popup_auto_signing_popup_closes_itself(monkeypatch):
    """進行中、之後 popup 自己關掉 → 視為成功,程式從未主動 close()。"""
    import taipeion_login_selenium
    monkeypatch.setattr(taipeion_login_selenium, "_read_pin", lambda: "000000")
    monkeypatch.setattr(dc.time, "sleep", lambda s: None)
    d = _FakeSigningPopupDriver([_SIGNING], self_close_after=3)

    assert _handle_pincode_popup(d, popup_timeout=1, close_timeout=5) is True
    assert d.current_window_handle == "main"


def _monotonic_clock(monkeypatch, step=0.1):
    """單調遞增的假時鐘:每次 time.time() 前進 step 秒,不依賴呼叫次數。"""
    import itertools
    c = itertools.count(0.0, step)
    monkeypatch.setattr(dc.time, "time", lambda: next(c))


def test_handle_pincode_popup_auto_signing_never_finishes_returns_false(monkeypatch):
    """進行中但 sign_timeout 內仍沒完成訊號 → False、popup 保留,不可替使用者關掉。"""
    import taipeion_login_selenium
    monkeypatch.setattr(taipeion_login_selenium, "_read_pin", lambda: "000000")
    monkeypatch.setattr(dc.time, "sleep", lambda s: None)
    _monotonic_clock(monkeypatch)
    d = _FakeSigningPopupDriver([_SIGNING])

    assert _handle_pincode_popup(d, popup_timeout=1, close_timeout=1, sign_timeout=2) is False
    assert d.closed == []
    assert d._calls > 5, "signing 要把等待拉長到 sign_timeout,不是 15s 找 input 的短迴圈"


# ── 存查成功驗證:畫面還停在存查表單 ≠ 公文消失(2026-10-07 誤報 30 輪) ──────────
#
# 點「確定存檔」後畫面是存查表單,清單根本沒顯示 → 「可見列找不到 doc_no」恆真,
# 舊 verify 每輪都報「存查成功」,連寫標記、發公告。要認得「還在表單上」= 未成功,
# 並以 sidebar「待結案(N)」真的下降為成功依據。

class _FakeVerifyDriver(_FakeViewerDriver):
    def __init__(self, listing_states, sidebar_counts):
        super().__init__({"main": "https://edoc.gov.taipei/tcqb/home/default.jsp"}, "main")
        self._listing = list(listing_states)
        self._counts = list(sidebar_counts)
        self.in_frame = False

    def execute_script(self, script, *args):
        if script is dc._FIND_DOC_IN_VISIBLE_ROW_JS:
            return self._listing.pop(0) if len(self._listing) > 1 else self._listing[0]
        return None

    def find_elements(self, by, xpath):
        return []

    def next_count(self):
        return self._counts.pop(0) if len(self._counts) > 1 else self._counts[0]


def _patch_sidebar_count(monkeypatch, driver):
    import document_system
    monkeypatch.setattr(document_system, "_get_sidebar_paren_count",
                        lambda d, label, timeout=10: driver.next_count())


def test_verify_archive_fails_while_form_still_shown(monkeypatch):
    monkeypatch.setattr(dc.time, "sleep", lambda s: None)
    t = iter([0, 0, 0, 100, 100, 100])
    monkeypatch.setattr(dc.time, "time", lambda: next(t, 100))
    d = _FakeVerifyDriver([{"state": "form"}], sidebar_counts=[2])
    _patch_sidebar_count(monkeypatch, d)

    assert dc._verify_archive_success_by_listing(d, "MWAA1156009952", timeout=1,
                                                 count_before=2) is False


def test_verify_archive_success_when_sidebar_count_dropped(monkeypatch):
    """表單已消失(過渡態,清單還沒畫出來)+ sidebar 數下降 → 成功。"""
    monkeypatch.setattr(dc.time, "sleep", lambda s: None)
    d = _FakeVerifyDriver([{"state": "none", "found": False}], sidebar_counts=[2, 1])
    _patch_sidebar_count(monkeypatch, d)

    assert dc._verify_archive_success_by_listing(d, "MWAA1156009952", timeout=5,
                                                 count_before=2) is True


def test_verify_archive_success_when_listing_shown_without_doc(monkeypatch):
    """清單已顯示且 doc_no 不在可見列(sidebar 數還沒刷新)→ 成功。"""
    monkeypatch.setattr(dc.time, "sleep", lambda s: None)
    d = _FakeVerifyDriver([{"state": "listing", "found": False}], sidebar_counts=[2])
    _patch_sidebar_count(monkeypatch, d)

    assert dc._verify_archive_success_by_listing(d, "MWAA1156009952", timeout=5,
                                                 count_before=2) is True


def test_verify_archive_fails_when_doc_still_in_listing(monkeypatch):
    monkeypatch.setattr(dc.time, "sleep", lambda s: None)
    t = iter([0, 0, 0, 100, 100, 100])
    monkeypatch.setattr(dc.time, "time", lambda: next(t, 100))
    d = _FakeVerifyDriver([{"state": "listing", "found": True}], sidebar_counts=[2])
    _patch_sidebar_count(monkeypatch, d)

    assert dc._verify_archive_success_by_listing(d, "MWAA1156009952", timeout=1,
                                                 count_before=2) is False


def test_handle_pincode_popup_auto_signing_then_failed_returns_false_without_closing(monkeypatch):
    """進行中 → 出現失敗字樣(無完成詞、視窗沒自關)→ 等到 sign_timeout 回 False、不關窗。
    failed 不能提早退出:regex 掃整個 body,popup 的「取消」鈕字樣也會命中。"""
    import taipeion_login_selenium
    monkeypatch.setattr(taipeion_login_selenium, "_read_pin", lambda: "000000")
    monkeypatch.setattr(dc.time, "sleep", lambda s: None)
    _monotonic_clock(monkeypatch)
    failed = {"done": False, "signing": False, "failed": True, "why": "body 含失敗/錯誤字樣",
              "tail": "密碼不正確"}
    d = _FakeSigningPopupDriver([_SIGNING, failed])

    assert _handle_pincode_popup(d, popup_timeout=1, close_timeout=1, sign_timeout=2) is False
    assert d.closed == [] and d.current_window_handle == "main"


def test_verify_archive_fails_when_doc_in_listing_even_if_sidebar_dropped(monkeypatch):
    """清單上還看得到 doc_no → 即使 sidebar 數字下降(可能是上一輪的補刷新)也不算成功。"""
    monkeypatch.setattr(dc.time, "sleep", lambda s: None)
    t = iter([0, 0, 0, 100, 100, 100])
    monkeypatch.setattr(dc.time, "time", lambda: next(t, 100))
    d = _FakeVerifyDriver([{"state": "listing", "found": True}], sidebar_counts=[1])
    _patch_sidebar_count(monkeypatch, d)

    assert dc._verify_archive_success_by_listing(d, "MWAA1156009952", timeout=1,
                                                 count_before=2) is False


def test_verify_archive_fails_when_form_shown_even_if_sidebar_dropped(monkeypatch):
    """count_before 可能含上一輪未刷新的舊值:畫面還在存查表單時,sidebar 下降也不算成功。"""
    monkeypatch.setattr(dc.time, "sleep", lambda s: None)
    t = iter([0, 0, 0, 100, 100, 100])
    monkeypatch.setattr(dc.time, "time", lambda: next(t, 100))
    d = _FakeVerifyDriver([{"state": "form"}], sidebar_counts=[1])
    _patch_sidebar_count(monkeypatch, d)

    assert dc._verify_archive_success_by_listing(d, "MWAA1156009952", timeout=1,
                                                 count_before=2) is False
