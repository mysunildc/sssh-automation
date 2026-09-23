"""SendInput 被拒(桌面不接受實體輸入)的防呆(2026-09-23 RDP 斷線事故)。

RDP 斷線後 session 進入 Disconnected,SendInput 一律回 0、GetLastError=5。Selenium/CDP
不受影響,所以流程會一路成功到「把路徑打進 KdApp 對話框」才失敗,原本要等 10s 後誤報
「路徑可能無效」。這裡測純邏輯:_send_inputs 回傳值、以及 _handle_export_dialog 在第一個
SendInput 被拒時立即中止(不等 10s)。
"""
import pending_doc_handler as p


def _fake_send_input(sent, err):
    """讓 _user32.SendInput 回 sent、get_last_error 回 err。"""
    def _apply(monkeypatch):
        monkeypatch.setattr(p._user32, "SendInput", lambda n, arr, size: sent)
        monkeypatch.setattr(p.ctypes, "get_last_error", lambda: err)
    return _apply


def test_send_inputs_returns_true_when_all_sent(monkeypatch):
    monkeypatch.setattr(p._user32, "SendInput", lambda n, arr, size: n)
    assert p._send_inputs([p._key_event(vk=0x41)]) is True


def test_send_inputs_returns_false_and_names_desktop_when_access_denied(monkeypatch, capsys):
    _fake_send_input(sent=0, err=5)(monkeypatch)
    assert p._send_inputs([p._key_event(vk=0x41), p._key_event(vk=0x41)]) is False
    out = capsys.readouterr().out
    assert "ERROR_ACCESS_DENIED" in out and "RDP" in out  # 要講出真正原因,不是只印錯誤碼


def test_send_inputs_returns_false_on_other_error(monkeypatch, capsys):
    _fake_send_input(sent=1, err=87)(monkeypatch)
    assert p._send_inputs([p._key_event(vk=0x41), p._key_event(vk=0x41)]) is False
    assert "GetLastError=87" in capsys.readouterr().out


def test_export_dialog_aborts_immediately_when_input_denied(monkeypatch, capsys):
    """第一個 Ctrl+A 就被拒 → 直接 False,不進入 10s 等待、不繼續打路徵。"""
    monkeypatch.setattr(p, "_find_dialog_hwnd", lambda title, timeout: 0x1234)
    monkeypatch.setattr(p, "_bring_to_front", lambda hwnd: None)
    monkeypatch.setattr(p, "ensure_english_ime", lambda hwnd=None: True)
    monkeypatch.setattr(p.time, "sleep", lambda s: None)
    _fake_send_input(sent=0, err=5)(monkeypatch)
    typed = []
    monkeypatch.setattr(p, "_send_text_vk", lambda text: typed.append(text) or False)
    waited = []
    monkeypatch.setattr(p._user32, "IsWindow", lambda h: waited.append(1) or 1)

    assert p._handle_export_dialog(r"C:\dl", timeout=1) is False
    assert typed == [], "被拒後不該再繼續打路徑"
    assert waited == [], "被拒後不該進入等對話框關閉的 10s 迴圈"
    assert "連回" in capsys.readouterr().out  # 要給使用者解法
