"""servisign_utils.ensure_servisign 決策邏輯測試(不碰真實進程/WinSCard)。

實機行為(2026-09-16/23):TCGServiSign 主程式掉 → 56420 無人監聽 → 登入頁一直「重新檢測」。
這裡釘住:活著就不重啟、掉了會重啟、重啟失敗要講清楚、讀不到讀卡機時依 session 類型給
正確指引(RDP 語境 → 講重導機制與斷線重啟解法;console → 講讀卡機/卡片)。
"""
import servisign_utils as sv


def _patch(monkeypatch, *, listening, readers, console, restart_ok=True):
    calls = {"restart": 0}
    monkeypatch.setattr(sv, "servisign_listening", lambda *a, **k: listening)
    monkeypatch.setattr(sv, "list_smartcard_readers", lambda: readers)
    monkeypatch.setattr(sv, "_session_is_console", lambda: console)

    def _restart(wait_listen=15.0):
        calls["restart"] += 1
        return restart_ok, 1.2
    monkeypatch.setattr(sv, "restart_servisign", _restart)
    return calls


def test_alive_with_reader_is_ok_and_no_restart(monkeypatch):
    calls = _patch(monkeypatch, listening=True, readers=["CASTLES EZ100PU 0"], console=True)
    ok, reason = sv.ensure_servisign()
    assert ok is True and "EZ100PU" in reason
    assert calls["restart"] == 0


def test_dead_component_is_restarted_then_ok(monkeypatch):
    calls = _patch(monkeypatch, listening=False, readers=["CASTLES EZ100PU 0"], console=True)
    ok, reason = sv.ensure_servisign()
    assert ok is True and "自癒" in reason
    assert calls["restart"] == 1


def test_dead_component_no_auto_restart_reports(monkeypatch):
    calls = _patch(monkeypatch, listening=False, readers=[], console=True)
    ok, reason = sv.ensure_servisign(auto_restart=False)
    assert ok is False and "未監聽" in reason
    assert calls["restart"] == 0


def test_restart_failure_is_actionable(monkeypatch):
    _patch(monkeypatch, listening=False, readers=[], console=True, restart_ok=False)
    ok, reason = sv.ensure_servisign()
    assert ok is False
    assert "TCGServiSignMonitor.exe" in reason  # 告訴使用者該手動跑什麼


def test_no_reader_in_rdp_session_explains_redirection(monkeypatch):
    """RDP 語境讀不到 → 要講 Windows 重導機制 + 「中斷連線後重啟」解法,不能只說卡片壞。"""
    _patch(monkeypatch, listening=True, readers=[], console=False)
    ok, reason = sv.ensure_servisign()
    assert ok is False
    assert "RDP" in reason and "重導" in reason and "中斷連線" in reason


def test_no_reader_in_console_points_to_hardware(monkeypatch):
    _patch(monkeypatch, listening=True, readers=[], console=True)
    ok, reason = sv.ensure_servisign()
    assert ok is False
    assert "讀卡機" in reason and "HiCOS" in reason
    assert "RDP" not in reason  # console 下不要拿 RDP 的說法誤導


def test_taskkill_names_every_process_explicitly():
    """taskkill /IM 的萬用字元(TCGServiSign*.exe)實測殺不到任何東西 → 必須逐一列名。"""
    argv = sv.taskkill_argv()
    assert argv[:2] == ["taskkill", "/F"]
    ims = [argv[i + 1] for i, a in enumerate(argv) if a == "/IM"]
    assert ims == ["TCGServiSign.exe", "TCGServiSignMonitor.exe", "TCGServiSignWorker.exe"]
    assert not any("*" in a for a in argv)


def test_restart_refuses_to_stack_when_old_process_survives(monkeypatch):
    """殺不掉舊主程式(56420 一直在聽)→ 回 False,且不能再啟動一份 Monitor 疊上去。"""
    monkeypatch.setattr(sv.os.path, "isfile", lambda p: True)
    monkeypatch.setattr(sv.subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(sv, "servisign_listening", lambda *a, **k: True)  # 永遠還在聽
    monkeypatch.setattr(sv.time, "sleep", lambda s: None)
    started = []
    monkeypatch.setattr(sv.subprocess, "Popen", lambda *a, **k: started.append(a))
    # 讓 5s 等待立即到期
    t = iter([0, 0, 10, 10, 10, 10])
    monkeypatch.setattr(sv.time, "time", lambda: next(t, 10))
    ok, _ = sv.restart_servisign()
    assert ok is False
    assert started == [], "舊的沒死就不可以再啟動新 Monitor"


def test_expected_reader_substring_must_match(monkeypatch):
    _patch(monkeypatch, listening=True, readers=["Some Redirected Reader 0"], console=False)
    ok, reason = sv.ensure_servisign(expect_reader_substr="EZ100PU")
    assert ok is False and "EZ100PU" in reason
