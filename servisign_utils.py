"""servisign_utils.py
本機簽章元件 TCGServiSign(Changingtec ServiSign,監聽 https://127.0.0.1:56420/56520/56620)
的健康檢查與自癒,供 main.py 起手式呼叫。

為何需要(2026-09-16 與 2026-09-23 各發生一次):
  TCGServiSign.exe 主程式會自己掉(只剩 Monitor/Worker,56420 沒人監聽),此時
  login.gov.taipei 的自然人憑證頁偵測不到元件,一直顯示「重新檢測」、PIN 欄位不出現,
  流程在「重試 2 輪後仍未看到『登入』按鈕」失敗,看起來像卡片壞了,其實跟卡片無關。
  兩次都是手動 kill 三個進程、重啟 Monitor 後立刻恢復。這裡把這件事自動化。

RDP 的陷阱(微軟官方行為,見 README「遠端桌面」一節):
  winscard.dll 在「被載入那一刻」決定 —— 在 RDP session 內載入 → 所有讀卡呼叫重導到
  RDP 用戶端那台電腦,永遠看不到主機上的讀卡機;在 console 載入 → 本機處理。
  因此元件若是在「RDP 連線中」被重啟,新 context 會走重導 → 讀不到主機的卡。
  重啟後一律用 WinSCard 實測讀卡機是否可見,看不到就依 session 類型給正確指引。

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
# 元件全家的 image name。taskkill /IM 的萬用字元(TCGServiSign*.exe)實測**殺不到任何東西**
# (2026-09-23:回 True 卻一個進程都沒死,還多啟動一份 Monitor),必須逐一列名。
SERVISIGN_IMAGES = ("TCGServiSign.exe", "TCGServiSignMonitor.exe", "TCGServiSignWorker.exe")

_SCARD_SCOPE_USER = 0
_SCARD_E_NO_READERS_AVAILABLE = 0x8010002E


def servisign_listening(port=SERVISIGN_PORT, timeout=1.0):
    """TCP 連得上 127.0.0.1:port 就視為元件主程式活著(不做 TLS 握手,只確認有人監聽)。"""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def list_smartcard_readers():
    """用 WinSCard 列出「本程序此刻」看得到的讀卡機名稱;回 list(可能為空)。

    注意:結果反映的是「呼叫者所在 session 的 winscard 走向」—— 在 RDP session 內的
    新程序看到的是 RDP 用戶端那邊的讀卡機(通常沒有),不是主機上的。查失敗回 []。
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


def restart_servisign(wait_listen=15.0):
    """殺掉 TCGServiSign 全家(主程式/Monitor/Worker)→ 啟動 Monitor(它會拉起主程式與 Worker)
    → 等 56420 恢復監聽。回 (ok, elapsed_seconds)。

    為何殺全家:實機看到的故障型態是「Monitor/Worker 活著、主程式死了」,Monitor 不會
    自己把主程式拉回來,只重啟主程式也試過不穩;整組重啟 1~2 秒內就恢復(2026-09-16/23)。
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


def taskkill_argv():
    """組 taskkill 參數:每個 image name 各一組 /IM(taskkill 支援多個 /IM)。"""
    argv = ["taskkill", "/F"]
    for img in SERVISIGN_IMAGES:
        argv += ["/IM", img]
    return argv


def _session_is_console():
    """本程序是否跑在 console session(而非 RDP)。用 SESSIONNAME 環境變數判斷,查不到回 None。"""
    name = os.environ.get("SESSIONNAME")
    if not name:
        return None
    return name.lower() == "console"


def ensure_servisign(auto_restart=True, expect_reader_substr=None):
    """起手式:確認簽章元件活著且讀得到讀卡機;必要時自癒。回 (ok, reason)。

    流程:
      1. 56420 有人監聽 → 元件活著;沒有 → auto_restart 時重啟,重啟失敗 → (False, ...)
      2. 用 WinSCard 列讀卡機:有(且含 expect_reader_substr,若有給)→ (True, ...)
         沒有 → (False, 依 session 類型的指引):
           - RDP session:元件很可能是在 RDP 語境被(重新)拉起,讀卡呼叫被重導到用戶端;
             請「中斷連線(不是登出)」後等元件重啟,或到主機 console 操作。
           - console:讀卡機/卡片本身的問題(拔插、驗 HiCOS)。
    """
    alive = servisign_listening()
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
        return True, f"簽章元件正常{tag},讀卡機:{readers}"

    console = _session_is_console()
    where = ("(讀卡機清單為空)" if not readers
             else f"(看得到 {readers},但沒有 {expect_reader_substr!r})")
    if console is False:
        return False, (f"WinSCard 看不到主機讀卡機{where}。本程序跑在 RDP session 內:"
                       f"Windows 會把 RDP session 內的讀卡呼叫全部重導到你連進來的那台電腦,"
                       f"主機上的讀卡機永遠看不到;若簽章元件是在 RDP 連線中被(重新)拉起,"
                       f"它也一樣讀不到。解法:把遠端桌面「中斷連線」(不是登出)後等 30 秒,"
                       f"在斷線狀態重啟元件(可再跑一次本程式,它會自動重啟並改在本機語境載入),"
                       f"或直接到主機 console 操作。")
    return False, (f"WinSCard 看不到讀卡機{where}(session={'console' if console else '未知'})。"
                   f"請確認讀卡機接妥、卡片插好,並用 HiCOS 卡片管理工具檢測。")
