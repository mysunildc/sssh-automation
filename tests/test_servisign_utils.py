"""servisign_utils.ensure_servisign 決策邏輯測試(不碰真實進程/WinSCard/提權)。

實機(2026-09-16/23/24):TCGServiSign 主程式掉 → 56420 無人監聽 → 登入頁一直「重新檢測」;
RDP 語境下即使元件活著,只要它跑在使用者 session,winscard 就被重導、讀不到主機的卡;
以 SYSTEM 把主程式啟動到 session 0 後,同一 RDP 連線下登入頁就能偵測到卡。
這裡釘住兩條路徑的決策:RDP → session 0;console → Monitor 重啟 + WinSCard 實測。
"""
import servisign_utils as sv


def _patch(monkeypatch, *, console, listening, sessions, readers=(),
           restart_ok=True, s0_ok=True, port_owner="first", procs_fail=False):
    """sessions=[0, 2] → 主程式 pid 100→session 0, pid 101→session 2。
    port_owner="first" → 56420 由 sessions 第一個對應的 pid 持有;可給 pid 或 None。
    procs_fail=True → tasklist 探測失敗(servisign_main_procs 回 None)。"""
    calls = {"restart": 0, "s0": 0, "procs": 0}
    procs = {100 + i: s for i, s in enumerate(sessions)}
    owner = (next(iter(procs), None) if port_owner == "first" else port_owner)
    monkeypatch.setattr(sv, "_session_is_console", lambda: console)
    monkeypatch.setattr(sv, "servisign_listening", lambda *a, **k: listening)

    def _procs():
        calls["procs"] += 1
        return None if procs_fail else dict(procs)
    monkeypatch.setattr(sv, "servisign_main_procs", _procs)
    monkeypatch.setattr(sv, "servisign_port_owner_pid", lambda *a, **k: owner)
    monkeypatch.setattr(sv, "list_smartcard_readers", lambda: list(readers))

    def _restart(wait_listen=15.0):
        calls["restart"] += 1
        return restart_ok, 1.2
    monkeypatch.setattr(sv, "restart_servisign", _restart)

    def _s0(wait=45.0, grace=10.0):
        calls["s0"] += 1
        return (True, "3.5s") if s0_ok else (False, "UAC denied")
    monkeypatch.setattr(sv, "start_servisign_session0", _s0)
    return calls


# ── RDP 語境 ──────────────────────────────────────────────────────────────────

def test_rdp_component_in_session0_is_ok_without_touching_anything(monkeypatch):
    calls = _patch(monkeypatch, console=False, listening=True, sessions=[0])
    ok, reason = sv.ensure_servisign(expect_reader_substr="EZ100PU")
    assert ok is True and "session 0" in reason
    assert calls["restart"] == 0 and calls["s0"] == 0


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


def test_rdp_session0_failure_gives_real_alternatives(monkeypatch):
    """提權失敗的替代路必須是真的可行:再按 UAC / 手動以管理員跑腳本 / 到 console。
    舊訊息「中斷連線後等 30 秒重連」在新設計下無效(重跑仍是 RDP 語境、仍走提權)。"""
    _patch(monkeypatch, console=False, listening=True, sessions=[2], s0_ok=False)
    ok, reason = sv.ensure_servisign()
    assert ok is False
    assert "UAC" in reason and "servisign_session0.ps1" in reason and "console" in reason
    assert "中斷連線" not in reason


def test_rdp_session0_exists_but_user_session_owns_port_is_not_ok(monkeypatch):
    """session 0 有一份主程式,但 56420 被使用者 session 那份持有 → 登入頁對話的是被重導的那份,
    不能判 OK,必須重做 session 0(code review 2026-09-28)。"""
    calls = _patch(monkeypatch, console=False, listening=True, sessions=[0, 2], port_owner=101)
    ok, reason = sv.ensure_servisign()
    assert ok is True and calls["s0"] == 1


def test_rdp_probe_failure_while_alive_does_not_kill_anything(monkeypatch):
    """tasklist 暫時失敗(回 None)且元件活著 → 不能當成「不在 session 0」而 kill+提權重建。"""
    calls = _patch(monkeypatch, console=False, listening=True, sessions=[0], procs_fail=True)
    ok, reason = sv.ensure_servisign()
    assert ok is False and "tasklist" in reason
    assert calls["s0"] == 0 and calls["procs"] == 2  # 重試過一次


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
    assert calls["restart"] == 0 and calls["s0"] == 0
    assert calls["procs"] == 0  # console 路徑不需要查 session


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


_TASKLIST = ('"TCGServiSign.exe","24068","Services","0","15,000 K"\n'
             '"TCGServiSign.exe","19820","RDP-Tcp#30","2","28,000 K"\n')
_NETSTAT = ("  Proto  Local Address          Foreign Address        State           PID\n"
            "  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       1234\n"
            "  TCP    127.0.0.1:56420        0.0.0.0:0              LISTENING       {pid}\n"
            "  TCP    127.0.0.1:56420        127.0.0.1:50001        ESTABLISHED     {pid}\n")


def _fake_run(tasklist_out, netstat_out):
    class _R:
        def __init__(self, out): self.stdout = out
    def run(argv, *a, **k):
        return _R(tasklist_out if argv[0] == "tasklist" else netstat_out)
    return run


def test_main_procs_parses_tasklist_csv(monkeypatch):
    monkeypatch.setattr(sv.subprocess, "run", _fake_run(_TASKLIST, _NETSTAT.format(pid=24068)))
    assert sv.servisign_main_procs() == {24068: 0, 19820: 2}
    assert sv.servisign_main_sessions() == [0, 2]
    assert sv.servisign_port_owner_pid() == 24068
    assert sv.servisign_in_session0() is True


def test_in_session0_false_when_user_session_copy_owns_port(monkeypatch):
    """兩份都在,但 port 是 session 2 那份的 → 不算在 session 0。"""
    monkeypatch.setattr(sv.subprocess, "run", _fake_run(_TASKLIST, _NETSTAT.format(pid=19820)))
    assert sv.servisign_in_session0() is False


def test_main_procs_empty_when_not_running(monkeypatch):
    class _R:
        stdout = "INFO: No tasks are running which match the specified criteria.\n"
    monkeypatch.setattr(sv.subprocess, "run", lambda *a, **k: _R())
    assert sv.servisign_main_procs() == {}
    assert sv.servisign_main_sessions() == []
    assert sv.servisign_in_session0() is False


def test_main_procs_none_on_probe_failure(monkeypatch):
    def boom(*a, **k): raise sv.subprocess.TimeoutExpired("tasklist", 10)
    monkeypatch.setattr(sv.subprocess, "run", boom)
    assert sv.servisign_main_procs() is None
    assert sv.servisign_main_sessions() is None
    assert sv.servisign_in_session0() is False


# ── start_servisign_session0:不殺、逾時、exit code ─────────────────────────────

def _patch_s0(monkeypatch, *, run_effect, states):
    """run_effect: returncode 或 exception 類;states: 每次 _ok 檢查依序回的 bool。"""
    monkeypatch.setattr(sv.os.path, "isfile", lambda p: True)
    argvs = []
    def run(argv, *a, **k):
        argvs.append(argv)
        if isinstance(run_effect, type) and issubclass(run_effect, BaseException):
            raise run_effect("powershell", 45)
        class _P: returncode = run_effect
        return _P()
    monkeypatch.setattr(sv.subprocess, "run", run)
    it = iter(states)
    monkeypatch.setattr(sv, "servisign_listening", lambda *a, **k: True)
    monkeypatch.setattr(sv, "servisign_in_session0", lambda *a, **k: next(it, states[-1]))
    monkeypatch.setattr(sv, "servisign_main_sessions", lambda: [0])
    monkeypatch.setattr(sv.time, "sleep", lambda s: None)
    return argvs


def test_session0_does_not_taskkill_before_elevation(monkeypatch):
    """提權前不能殺進程:UAC 被拒時元件必須維持原狀(否則比呼叫前更糟)。"""
    argvs = _patch_s0(monkeypatch, run_effect=0, states=[True])
    ok, _ = sv.start_servisign_session0()
    assert ok is True
    assert all(a[0] != "taskkill" for a in argvs)
    assert any("-PassThru" in a[-1] and "exit $p.ExitCode" in a[-1] for a in argvs)


def test_session0_nonzero_exit_reports_log_without_waiting(monkeypatch):
    """UAC 按「否」→ exit 1:只確認一次現況就回報,指出 log 位置,不空等 45 秒。"""
    slept = []
    argvs = _patch_s0(monkeypatch, run_effect=1, states=[False])
    monkeypatch.setattr(sv.time, "sleep", lambda s: slept.append(s))
    ok, detail = sv.start_servisign_session0()
    assert ok is False and "servisign_session0.log" in detail and "回傳 1" in detail
    assert slept == []


def test_session0_timeout_still_checks_real_state(monkeypatch):
    """Start-Process -Wait 拖著 → TimeoutExpired 後仍要以實際狀態為準(舊版迴圈零次執行、直接 False)。"""
    _patch_s0(monkeypatch, run_effect=sv.subprocess.TimeoutExpired, states=[True])
    ok, _ = sv.start_servisign_session0(wait=1.0)
    assert ok is True
