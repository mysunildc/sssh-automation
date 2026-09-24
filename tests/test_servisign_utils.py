"""servisign_utils.ensure_servisign 決策邏輯測試(不碰真實進程/WinSCard/提權)。

實機(2026-09-16/23/24):TCGServiSign 主程式掉 → 56420 無人監聽 → 登入頁一直「重新檢測」;
RDP 語境下即使元件活著,只要它跑在使用者 session,winscard 就被重導、讀不到主機的卡;
以 SYSTEM 把主程式啟動到 session 0 後,同一 RDP 連線下登入頁就能偵測到卡。
這裡釘住兩條路徑的決策:RDP → session 0;console → Monitor 重啟 + WinSCard 實測。
"""
import servisign_utils as sv


def _patch(monkeypatch, *, console, listening, sessions, readers=(),
           restart_ok=True, s0_ok=True):
    calls = {"restart": 0, "s0": 0}
    monkeypatch.setattr(sv, "_session_is_console", lambda: console)
    monkeypatch.setattr(sv, "servisign_listening", lambda *a, **k: listening)
    monkeypatch.setattr(sv, "servisign_main_sessions", lambda: list(sessions))
    monkeypatch.setattr(sv, "list_smartcard_readers", lambda: list(readers))

    def _restart(wait_listen=15.0):
        calls["restart"] += 1
        return restart_ok, 1.2
    monkeypatch.setattr(sv, "restart_servisign", _restart)

    def _s0(wait=45.0):
        calls["s0"] += 1
        return (True, "3.5s") if s0_ok else (False, "UAC denied")
    monkeypatch.setattr(sv, "start_servisign_session0", _s0)
    return calls


# ── RDP 語境 ──────────────────────────────────────────────────────────────────

def test_rdp_component_in_session0_is_ok_without_touching_anything(monkeypatch):
    calls = _patch(monkeypatch, console=False, listening=True, sessions=[0])
    ok, reason = sv.ensure_servisign(expect_reader_substr="EZ100PU")
    assert ok is True and "session 0" in reason
    assert calls == {"restart": 0, "s0": 0}


def test_rdp_component_in_user_session_is_moved_to_session0(monkeypatch):
    """元件活著但跑在使用者 session(RDP 語境 → 讀卡被重導)→ 必須切到 session 0,不是 Monitor 重啟。"""
    calls = _patch(monkeypatch, console=False, listening=True, sessions=[2])
    ok, reason = sv.ensure_servisign()
    assert ok is True and "session 0" in reason
    assert calls["s0"] == 1 and calls["restart"] == 0


def test_rdp_dead_component_is_started_in_session0(monkeypatch):
    calls = _patch(monkeypatch, console=False, listening=False, sessions=[])
    ok, _ = sv.ensure_servisign()
    assert ok is True and calls["s0"] == 1


def test_rdp_does_not_use_winscard_of_this_process(monkeypatch):
    """RDP 下本程序的 winscard 也被重導、list 必為空 —— 不能因此判失敗(2026-09-24 曾誤 STOP)。"""
    _patch(monkeypatch, console=False, listening=True, sessions=[0], readers=[])
    ok, _ = sv.ensure_servisign(expect_reader_substr="EZ100PU")
    assert ok is True


def test_rdp_session0_failure_gives_disconnect_alternative(monkeypatch):
    _patch(monkeypatch, console=False, listening=True, sessions=[2], s0_ok=False)
    ok, reason = sv.ensure_servisign()
    assert ok is False
    assert "中斷連線" in reason and "console" in reason  # 提權失敗時的兩條替代路


def test_rdp_no_auto_restart_reports_without_acting(monkeypatch):
    calls = _patch(monkeypatch, console=False, listening=True, sessions=[2])
    ok, reason = sv.ensure_servisign(auto_restart=False)
    assert ok is False and "session 0" in reason
    assert calls["s0"] == 0


# ── console 語境 ──────────────────────────────────────────────────────────────

def test_console_alive_with_reader_is_ok(monkeypatch):
    calls = _patch(monkeypatch, console=True, listening=True, sessions=[2], readers=["CASTLES EZ100PU 0"])
    ok, reason = sv.ensure_servisign(expect_reader_substr="EZ100PU")
    assert ok is True and "EZ100PU" in reason
    assert calls == {"restart": 0, "s0": 0}


def test_console_dead_component_uses_monitor_restart(monkeypatch):
    calls = _patch(monkeypatch, console=True, listening=False, sessions=[], readers=["CASTLES EZ100PU 0"])
    ok, reason = sv.ensure_servisign()
    assert ok is True and "自癒" in reason
    assert calls["restart"] == 1 and calls["s0"] == 0


def test_console_restart_failure_is_actionable(monkeypatch):
    _patch(monkeypatch, console=True, listening=False, sessions=[], restart_ok=False)
    ok, reason = sv.ensure_servisign()
    assert ok is False and "TCGServiSignMonitor.exe" in reason


def test_console_no_reader_points_to_hardware_not_rdp(monkeypatch):
    _patch(monkeypatch, console=True, listening=True, sessions=[2], readers=[])
    ok, reason = sv.ensure_servisign()
    assert ok is False
    assert "HiCOS" in reason and "RDP" not in reason


def test_console_expected_reader_substring_must_match(monkeypatch):
    _patch(monkeypatch, console=True, listening=True, sessions=[2], readers=["Other Reader 0"])
    ok, reason = sv.ensure_servisign(expect_reader_substr="EZ100PU")
    assert ok is False and "EZ100PU" in reason


# ── 工具函式 ──────────────────────────────────────────────────────────────────

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
    monkeypatch.setattr(sv, "servisign_listening", lambda *a, **k: True)
    monkeypatch.setattr(sv.time, "sleep", lambda s: None)
    started = []
    monkeypatch.setattr(sv.subprocess, "Popen", lambda *a, **k: started.append(a))
    t = iter([0, 0, 10, 10, 10, 10])
    monkeypatch.setattr(sv.time, "time", lambda: next(t, 10))
    ok, _ = sv.restart_servisign()
    assert ok is False and started == []


def test_main_sessions_parses_tasklist_csv(monkeypatch):
    class _R:
        stdout = ('"TCGServiSign.exe","24068","Services","0","15,000 K"\n'
                  '"TCGServiSign.exe","19820","RDP-Tcp#30","2","28,000 K"\n')
    monkeypatch.setattr(sv.subprocess, "run", lambda *a, **k: _R())
    assert sv.servisign_main_sessions() == [0, 2]
    assert sv.servisign_in_session0() is True


def test_main_sessions_empty_when_not_running(monkeypatch):
    class _R:
        stdout = "INFO: No tasks are running which match the specified criteria.\n"
    monkeypatch.setattr(sv.subprocess, "run", lambda *a, **k: _R())
    assert sv.servisign_main_sessions() == []
    assert sv.servisign_in_session0() is False
