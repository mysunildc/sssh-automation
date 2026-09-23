"""ime_utils.ensure_english_ime 的單元測試。

這是 Win32 副作用程式碼,實機行為(打字不被中文 IME 攔截)以 Notepad 端到端驗證;
此處用 mock 把「該呼叫哪些 Win32 API、用什麼參數」的契約釘住,當作 regression guard。
"""
import unittest.mock as mock

import ime_utils


def _patch_win32(monkeypatch, *, foreground=0xABCD, hkl=0x4090409, ime_wnd=0x1111):
    """把 ime_utils 的 _user32 / _imm32 換成可斷言的 mock。"""
    u32 = mock.MagicMock(name="user32")
    imm = mock.MagicMock(name="imm32")
    u32.GetForegroundWindow.return_value = foreground
    u32.LoadKeyboardLayoutW.return_value = hkl
    imm.ImmGetDefaultIMEWnd.return_value = ime_wnd
    monkeypatch.setattr(ime_utils, "_user32", u32)
    monkeypatch.setattr(ime_utils, "_imm32", imm)
    return u32, imm


def test_loads_and_activates_english_us_layout(monkeypatch):
    u32, _ = _patch_win32(monkeypatch)

    ime_utils.ensure_english_ime(hwnd=0x9999)

    # 美式鍵盤 KLID 00000409 + KLF_ACTIVATE(0x1)
    u32.LoadKeyboardLayoutW.assert_called_once_with("00000409", 0x00000001)


def test_posts_input_lang_change_to_target_window(monkeypatch):
    u32, _ = _patch_win32(monkeypatch, hkl=0x4090409)

    ime_utils.ensure_english_ime(hwnd=0x9999)

    # WM_INPUTLANGCHANGEREQUEST = 0x0050,lParam = 載入的 HKL
    u32.PostMessageW.assert_called_once_with(0x9999, 0x0050, 0, 0x4090409)


def test_closes_ime_open_status_on_target_window(monkeypatch):
    u32, imm = _patch_win32(monkeypatch, ime_wnd=0x1111)

    ime_utils.ensure_english_ime(hwnd=0x9999)

    # 找該視窗的 IME 視窗,送 WM_IME_CONTROL(0x0283) + IMC_SETOPENSTATUS(0x0006) + 0(關閉=英數)
    imm.ImmGetDefaultIMEWnd.assert_called_once_with(0x9999)
    u32.SendMessageW.assert_called_once_with(0x1111, 0x0283, 0x0006, 0)


def test_defaults_to_foreground_window_when_hwnd_none(monkeypatch):
    u32, imm = _patch_win32(monkeypatch, foreground=0xABCD)

    ime_utils.ensure_english_ime()  # 不給 hwnd

    u32.GetForegroundWindow.assert_called_once_with()
    # 後續所有操作都針對前景視窗
    u32.PostMessageW.assert_called_once_with(0xABCD, 0x0050, 0, mock.ANY)
    imm.ImmGetDefaultIMEWnd.assert_called_once_with(0xABCD)


def test_returns_true_on_success(monkeypatch):
    _patch_win32(monkeypatch)
    assert ime_utils.ensure_english_ime(hwnd=0x9999) is True


def test_swallows_exceptions_and_returns_false(monkeypatch):
    u32, _ = _patch_win32(monkeypatch)
    u32.LoadKeyboardLayoutW.side_effect = OSError("boom")

    # 絕不能讓 IME 切換失敗中斷自動化主流程
    assert ime_utils.ensure_english_ime(hwnd=0x9999) is False


# ── interactive_desktop_state(2026-09-23 RDP 斷線事故) ──────────────────────
#
# RDP 斷線後 session 變 Disconnected,SendInput 一律 ERROR_ACCESS_DENIED;Selenium 不受
# 影響,所以流程會跑到「打路徑進 KdApp 對話框」才失敗。主流程啟動前用它先擋。

def test_desktop_state_active_is_ok(monkeypatch):
    monkeypatch.setattr(ime_utils, "_query_wts_connect_state", lambda: 0)  # WTSActive
    ok, reason = ime_utils.interactive_desktop_state()
    assert ok is True
    assert "Active" in reason


def test_desktop_state_disconnected_is_blocked_with_actionable_reason(monkeypatch):
    monkeypatch.setattr(ime_utils, "_query_wts_connect_state", lambda: 4)  # WTSDisconnected
    ok, reason = ime_utils.interactive_desktop_state()
    assert ok is False
    assert "Disconnected" in reason
    assert "SendInput" in reason and "連回" in reason  # 講原因 + 給解法


def test_desktop_state_unknown_does_not_block(monkeypatch):
    """查不到就不擋 — 寧可讓它跑到 SendInput 那步再被明確擋下,不要誤殺正常環境。"""
    monkeypatch.setattr(ime_utils, "_query_wts_connect_state", lambda: None)
    ok, reason = ime_utils.interactive_desktop_state()
    assert ok is True
    assert "無法判定" in reason
