"""servisign_utils.py
本機簽章元件 TCGServiSign(Changingtec ServiSign,監聽 https://127.0.0.1:56420/56520/56620)
的健康檢查與自癒,供 main.py 起手式呼叫。

── 為何需要(2026-09-16 / 09-23 / 09-24 實機) ──────────────────────────────────────
1. TCGServiSign.exe 主程式會自己掉(實測都在 RDP 重連後),只剩 Monitor/Worker、56420 沒人聽;
   登入頁偵測不到元件,一直「重新檢測」、PIN 欄位不出現,看起來像卡片壞了。
2. **RDP 的陷阱(微軟官方行為,見 README「遠端桌面(RDP)與讀卡機」)**:winscard.dll 在「被載入
   那一刻」決定 —— 在 RDP session 內載入 → 所有讀卡呼叫重導到 RDP 用戶端那台電腦,永遠看不到
   主機上的讀卡機;在 console / session 0 載入 → 本機處理。所以主程式若是在 RDP 連線中被
   (Monitor)重新拉起,新 context 走重導 → 讀不到主機的卡。
   2026-09-24 實驗:同一個 RDP 連線下,元件跑在使用者 session → 登入頁 RECHECK_STUCK;
   改成以 SYSTEM 把主程式(TCGServiSign.exe 0)啟動到 **session 0** → 登入頁 OK_LOGIN_VISIBLE。
   (Monitor 在 session 0 沒有桌面會立刻退出,所以只啟動主程式。)

── 策略 ──────────────────────────────────────────────────────────────────────────
- 本程序在 RDP session:元件必須跑在 session 0。不在 → 停掉使用者 session 的那組、以 RunAs 提權
  執行 scripts/servisign_session0.ps1(排程工作,SYSTEM)。此機 UAC 設為提權不提示,無人介入;
  其他機器會跳 UAC 對話框,需使用者按「是」。
- 本程序在 console:維持原本 Monitor 方式重啟,並用 WinSCard 實測讀卡機可見。
- **WinSCard 檢查只在 console 有意義**:RDP 語境下本程序自己的 winscard 也被重導,list 必為空,
  不能拿來判定元件能不能讀卡(2026-09-24 踩到,原本會誤 STOP)。

此模組自包含(ctypes + subprocess + socket),不依賴專案其他模組。
"""
import ctypes
import os
import socket
import subprocess
import time

SERVISIGN_PORT = 56420
SERVISIGN_DIR = r"C:\Program Files (x86)\TCG\TCGServiSign"
SERVISIGN_MONITOR = os.path.join(SERVISIGN_DIR, "TCGServiSignMonitor.exe")
SERVISIGN_MAIN_IMAGE = "TCGServiSign.exe"
# 元件全家的 image name。taskkill /IM 的萬用字元(TCGServiSign*.exe)實測**殺不到任何東西**
# (2026-09-23:回 True 卻一個進程都沒死,還多啟動一份 Monitor),必須逐一列名。
SERVISIGN_IMAGES = (SERVISIGN_MAIN_IMAGE, "TCGServiSignMonitor.exe", "TCGServiSignWorker.exe")
SESSION0_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "scripts", "servisign_session0.ps1")

_SCARD_SCOPE_USER = 0
_SM_REMOTESESSION = 0x1000


# ── 基本探測 ─────────────────────────────────────────────────────────────────────

def servisign_listening(port=SERVISIGN_PORT, timeout=1.0):
    """TCP 連得上 127.0.0.1:port 就視為元件主程式活著(不做 TLS 握手,只確認有人監聽)。"""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def servisign_main_sessions():
    """回傳所有 TCGServiSign.exe 主程式所在的 session id(list,可能為空)。

    用 tasklist /FO CSV 解析(欄位:Image Name, PID, Session Name, Session#, Mem Usage)。
    SYSTEM 在 session 0 的進程一般使用者也看得到,足以判定「有沒有跑在 session 0」。
    """
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {SERVISIGN_MAIN_IMAGE}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, errors="replace", timeout=10).stdout
    except Exception:
        return []
    sessions = []
    for line in out.splitlines():
        parts = [p.strip().strip('"') for p in line.split('","')]
        if len(parts) >= 4 and parts[0].lower() == SERVISIGN_MAIN_IMAGE.lower():
            try:
                sessions.append(int(parts[3]))
            except ValueError:
                continue
    return sessions


def servisign_in_session0():
    """主程式是否有一份跑在 session 0(本機讀卡語境)。"""
    return 0 in servisign_main_sessions()


def list_smartcard_readers():
    """用 WinSCard 列出「本程序此刻」看得到的讀卡機名稱;回 list(可能為空)。

    只在 console 語境有意義:RDP session 內的新程序看到的是 RDP 用戶端那邊的讀卡機(通常沒有),
    不是主機上的。查失敗回 []。
    """
    try:
        winscard = ctypes.WinDLL("winscard", use_last_error=True)
        ctx = ctypes.c_void_p()
        rc = winscard.SCardEstablishContext(_SCARD_SCOPE_USER, None, None, ctypes.byref(ctx))
        if rc != 0:
            return []
        try:
            size = ctypes.c_uint(0)
            winscard.SCardListReadersW.argtypes = [
                ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
            rc = winscard.SCardListReadersW(ctx, None, None, ctypes.byref(size))
            if rc != 0 or size.value == 0:
                return []
            buf = ctypes.create_unicode_buffer(size.value)
            rc = winscard.SCardListReadersW(ctx, None, buf, ctypes.byref(size))
            if rc != 0:
                return []
            raw = buf[:size.value]
            return [s for s in raw.split("\0") if s]
        finally:
            winscard.SCardReleaseContext(ctx)
    except Exception:
        return []


def _session_is_console():
    """本程序是否跑在 console(非 RDP)。查不到回 None。

    不能用 SESSIONNAME 環境變數:session 從 console 登入後被 RDP 接管,環境變數仍是
    "Console"(2026-09-24 實測:rdp-tcp#30 Active 但 SESSIONNAME=Console)。
    GetSystemMetrics(SM_REMOTESESSION) 反映的是「此刻」是否遠端 session,才是對的。
    """
    try:
        return ctypes.windll.user32.GetSystemMetrics(_SM_REMOTESESSION) == 0
    except Exception:
        return None


# ── 重啟:console 語境(Monitor 方式) ─────────────────────────────────────────────

def taskkill_argv():
    """組 taskkill 參數:每個 image name 各一組 /IM(taskkill 支援多個 /IM)。
    只殺得到同一使用者的進程;SYSTEM 在 session 0 的那份殺不到 —— 這正好是我們要的。"""
    argv = ["taskkill", "/F"]
    for img in SERVISIGN_IMAGES:
        argv += ["/IM", img]
    return argv


def restart_servisign(wait_listen=15.0):
    """(console 語境用)殺掉使用者 session 的 TCGServiSign 全家 → 啟動 Monitor(它會拉起主程式與
    Worker)→ 等 56420 恢復監聽。回 (ok, elapsed_seconds)。

    為何殺全家:實機看到的故障型態是「Monitor/Worker 活著、主程式死了」;整組重啟 1~2 秒內恢復。
    """
    if not os.path.isfile(SERVISIGN_MONITOR):
        return False, 0.0
    t0 = time.time()
    subprocess.run(taskkill_argv(), capture_output=True, text=True, errors="replace")
    # 一定要等舊主程式真的釋放 56420 再啟動新的,否則「還在監聽」會被誤判成重啟成功
    # (且會多出一份 Monitor 互搶)。
    while servisign_listening() and time.time() - t0 < 5.0:
        time.sleep(0.3)
    if servisign_listening():
        return False, round(time.time() - t0, 1)  # 殺不掉舊的,不要再疊一份上去
    time.sleep(0.5)
    # DETACHED + 新 process group:元件是常駐程式,不能跟著本腳本結束而死
    creation = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([SERVISIGN_MONITOR], cwd=SERVISIGN_DIR, creationflags=creation,
                     close_fds=True)
    while time.time() - t0 < wait_listen:
        if servisign_listening():
            return True, round(time.time() - t0, 1)
        time.sleep(0.5)
    return False, round(time.time() - t0, 1)


# ── 重啟:RDP 語境(session 0 方式,需提權) ──────────────────────────────────────────

def start_servisign_session0(wait=45.0):
    """以 RunAs 提權執行 scripts/servisign_session0.ps1:停掉使用者 session 的元件、用排程工作把
    主程式以 SYSTEM 啟動到 session 0。回 (ok, detail)。

    此機 UAC 為「提權不提示」→ 全自動;其他機器會跳 UAC,使用者需按「是」。
    成功判準不是 exit code,而是回到本程序後實測:56420 有人聽 且 主程式在 session 0。
    """
    if not os.path.isfile(SESSION0_SCRIPT):
        return False, f"找不到 {SESSION0_SCRIPT}"
    # 先殺使用者 session 的那組(SYSTEM 的殺不到、也不需要殺)
    subprocess.run(taskkill_argv(), capture_output=True, text=True, errors="replace")
    ps = (f"Start-Process powershell -Verb RunAs -Wait -ArgumentList "
          f"'-NoProfile -ExecutionPolicy Bypass -File \"{SESSION0_SCRIPT}\"'")
    t0 = time.time()
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, text=True, errors="replace", timeout=wait)
    except subprocess.TimeoutExpired:
        pass  # 有時 -Wait 會拖著;下面以實際狀態為準
    except Exception as e:
        return False, f"提權啟動失敗:{type(e).__name__}: {e}"
    while time.time() - t0 < wait:
        if servisign_listening() and servisign_in_session0():
            return True, f"{round(time.time() - t0, 1)}s"
        time.sleep(0.5)
    return False, (f"{int(wait)}s 內 56420 未由 session 0 的主程式監聽"
                   f"(sessions={servisign_main_sessions()}, listening={servisign_listening()})")


# ── 起手式決策 ────────────────────────────────────────────────────────────────────

def ensure_servisign(auto_restart=True, expect_reader_substr=None):
    """起手式:確認簽章元件處於「能讀到主機讀卡機」的狀態;必要時自癒。回 (ok, reason)。

    RDP 語境(本程序在遠端 session):
      - 主程式在 session 0 且 56420 監聯 → OK。
      - 否則(沒跑 / 跑在使用者 session = 讀卡會被重導)→ auto_restart 時切到 session 0;
        失敗 → (False, 指引:UAC/提權、或中斷連線後重跑、或到 console)。
    console 語境:
      - 56420 沒人聽 → auto_restart 時以 Monitor 方式重啟。
      - 用 WinSCard 實測讀卡機(含 expect_reader_substr)→ 看不到 → (False, 查硬體/HiCOS)。
    """
    console = _session_is_console()
    alive = servisign_listening()
    in_s0 = servisign_in_session0()

    if console is False:  # ── RDP ──
        if alive and in_s0:
            return True, "RDP 語境:簽章元件跑在 session 0(本機讀卡語境),讀卡機不受 RDP 重導影響"
        where = ("未監聽 :%d" % SERVISIGN_PORT) if not alive else \
                f"跑在使用者 session {servisign_main_sessions()}(RDP 語境,讀卡會被重導到用戶端)"
        if not auto_restart:
            return False, f"RDP 語境:簽章元件{where};需切到 session 0 才能讀主機的卡"
        print(f"      [WARN] RDP 語境:簽章元件{where},改以 SYSTEM 啟動到 session 0(提權)...")
        ok, detail = start_servisign_session0()
        if ok:
            return True, f"RDP 語境:已把簽章元件切到 session 0({detail}),可讀主機讀卡機"
        return False, (f"RDP 語境下無法把簽章元件切到 session 0:{detail}。可能是提權(UAC)被拒。"
                       f"替代做法:把遠端桌面「中斷連線」(不是登出)後等 30 秒再重連重跑,或到主機 console 操作。")

    # ── console(或判定不出) ──
    restarted = False
    if not alive:
        if not auto_restart:
            return False, f"簽章元件 TCGServiSign 未監聽 127.0.0.1:{SERVISIGN_PORT}(主程式已掉)"
        print(f"      [WARN] 簽章元件 TCGServiSign 未監聽 :{SERVISIGN_PORT}(主程式已掉),自動重啟...")
        ok, secs = restart_servisign()
        if not ok:
            return False, (f"TCGServiSign 重啟後 {secs}s 內 :{SERVISIGN_PORT} 仍未監聽。"
                           f"請手動執行 {SERVISIGN_MONITOR} 或檢查元件安裝。")
        print(f"      OK：TCGServiSign 已重啟,{secs}s 後 :{SERVISIGN_PORT} 恢復監聽")
        restarted = True

    readers = list_smartcard_readers()
    if readers and (not expect_reader_substr
                    or any(expect_reader_substr.lower() in r.lower() for r in readers)):
        tag = "(剛自癒重啟)" if restarted else ""
        s0 = "(元件在 session 0)" if in_s0 else ""
        return True, f"簽章元件正常{tag}{s0},讀卡機:{readers}"
    where = ("(讀卡機清單為空)" if not readers
             else f"(看得到 {readers},但沒有 {expect_reader_substr!r})")
    return False, (f"WinSCard 看不到讀卡機{where}(session={'console' if console else '未知'})。"
                   f"請確認讀卡機接妥、卡片插好,並用 HiCOS 卡片管理工具檢測。")
