"""ime_utils.py
強制把輸入法切回英文(美式鍵盤),供所有 GUI/鍵盤自動化腳本共用。

為何需要:本機只裝了 zh-Hant-TW(注音 TSF IME)一種輸入法。若執行自動化時 IME 停在
中文模式,透過 SendInput(pending_doc_handler 打 JFileChooser 路徑)或 pyautogui
(browser_utils.type_text)模擬的按鍵會被 IME 攔截組字,導致路徑被打成中文/亂碼。
實測 2026-05-20:「匯出公文資料」對話框路徑被填錯。

做法:
  1. 載入並啟用美式鍵盤佈局(KLID 00000409) → 該佈局沒有 IME,按鍵直接是字面 ASCII。
  2. 對目標視窗送 WM_INPUTLANGCHANGEREQUEST,把它的輸入語言切到剛載入的英文佈局。
     (Windows 預設每個視窗各自記輸入法,故必須針對「正要打字的那個視窗」切,
      JFileChooser 那種他行程的視窗才吃得到。)
  3. 雙保險:找該視窗的 IME 視窗,送 IMC_SETOPENSTATUS=0 關閉組字(切英數模式)。

此模組自包含(自帶 user32/imm32 handle),不依賴專案其他模組,避免耦合。
"""
import ctypes

# ── Win32 常數 ────────────────────────────────────────────────────────────────
_ENGLISH_KLID = "00000409"          # English (United States)
_KLF_ACTIVATE = 0x00000001          # LoadKeyboardLayout:載入後立即啟用
_WM_INPUTLANGCHANGEREQUEST = 0x0050  # 要求視窗切換輸入語言
_WM_IME_CONTROL = 0x0283            # 操作 IME
_IMC_SETOPENSTATUS = 0x0006         # WM_IME_CONTROL 子命令:設定開/關(0=關=英數)

# ── Win32 handle 與型別宣告(64-bit 安全:HKL/HWND 是指標寬度) ──────────────────
_user32 = ctypes.windll.user32
_imm32 = ctypes.windll.imm32

_user32.GetForegroundWindow.restype = ctypes.c_void_p
_user32.LoadKeyboardLayoutW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint]
_user32.LoadKeyboardLayoutW.restype = ctypes.c_void_p
_user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
_user32.PostMessageW.restype = ctypes.c_int
_user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
_user32.SendMessageW.restype = ctypes.c_void_p
_imm32.ImmGetDefaultIMEWnd.argtypes = [ctypes.c_void_p]
_imm32.ImmGetDefaultIMEWnd.restype = ctypes.c_void_p


# ── 互動桌面狀態(WTS) ──────────────────────────────────────────────────────
# SendInput / pyautogui 這類「實體輸入注入」只在「連線中的互動桌面」才有效。RDP 斷線
# (session 進入 Disconnected)或工作站鎖定後,SendInput 一律回 0、GetLastError=5
# (ERROR_ACCESS_DENIED);Selenium/CDP 走 DevTools 不受影響,所以流程會一路成功到
# 「把路徑打進 KdApp 的 Java 對話框」那一步才莫名失敗(2026-09-23 實機:RDP 斷線後
# MWAA1156009472 下載對話框卡 10s、誤報「路徑可能無效」)。這裡用 WTS API 讀本 session
# 的連線狀態,讓主流程在**啟動前**就擋下並講清楚原因。
_WTS_CURRENT_SERVER_HANDLE = None
_WTS_CURRENT_SESSION = 0xFFFFFFFF
_WTS_CONNECT_STATE = 8               # WTS_INFO_CLASS.WTSConnectState
_WTS_ACTIVE = 0                      # WTS_CONNECTSTATE_CLASS.WTSActive
_WTS_STATE_NAMES = {0: "Active", 1: "Connected", 2: "ConnectQuery", 3: "Shadow",
                    4: "Disconnected", 5: "Idle", 6: "Listen", 7: "Reset",
                    8: "Down", 9: "Init"}


def _query_wts_connect_state():
    """讀本 session 的 WTS_CONNECTSTATE_CLASS 整數;API 失敗或例外回 None(交給呼叫端不誤擋)。"""
    try:
        wtsapi32 = ctypes.WinDLL("wtsapi32", use_last_error=True)
        buf = ctypes.c_void_p()
        size = ctypes.c_uint(0)
        wtsapi32.WTSQuerySessionInformationW.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_int,
            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint)]
        if not wtsapi32.WTSQuerySessionInformationW(
                _WTS_CURRENT_SERVER_HANDLE, _WTS_CURRENT_SESSION, _WTS_CONNECT_STATE,
                ctypes.byref(buf), ctypes.byref(size)):
            return None
        try:
            return ctypes.cast(buf, ctypes.POINTER(ctypes.c_int)).contents.value
        finally:
            wtsapi32.WTSFreeMemory(buf)
    except Exception:
        return None


def interactive_desktop_state():
    """回 (ok, reason):本 session 的桌面目前能不能接受 SendInput/pyautogui 實體輸入。

    ok=True  → 狀態 Active(RDP 連線中或本機 console 登入中)。
    ok=False → 例如 RDP 已斷線(Disconnected):此時 SendInput 必定被拒(error 5),
               reason 會說明狀態與解法。
    查不到(非 Windows / API 失敗)→ 視為 ok=True,不誤擋;reason 註明「無法判定」。
    """
    state = _query_wts_connect_state()
    if state is None:
        return True, "無法判定桌面狀態(WTS 查詢失敗),不擋"

    name = _WTS_STATE_NAMES.get(state, str(state))
    if state == _WTS_ACTIVE:
        return True, f"桌面狀態 {name}"
    return False, (f"目前 session 桌面狀態 = {name}(非 Active)。RDP 已斷線或工作站鎖定時,"
                   f"SendInput/pyautogui 的實體輸入一律被拒(ERROR_ACCESS_DENIED),"
                   f"KdApp「匯出公文資料」對話框的路徑會打不進去。請把遠端桌面連回來、"
                   f"保持連線且不鎖屏,再重跑。")


def ensure_english_ime(hwnd=None):
    """把指定視窗(預設為目前前景視窗)的輸入法強制切成英文(美式鍵盤)。

    在任何 SendInput / pyautogui 打字「之前」呼叫,確保打出的是字面 ASCII,
    不被中文 IME 攔截組字。

    參數:
        hwnd  目標視窗 handle;None 時用 GetForegroundWindow()。

    回傳:
        bool  成功 True,失敗 False。失敗一律靜默(只印 WARN),絕不丟例外中斷主流程。
    """
    try:
        if hwnd is None:
            hwnd = _user32.GetForegroundWindow()

        hkl = _user32.LoadKeyboardLayoutW(_ENGLISH_KLID, _KLF_ACTIVATE)
        _user32.PostMessageW(hwnd, _WM_INPUTLANGCHANGEREQUEST, 0, hkl)

        ime_hwnd = _imm32.ImmGetDefaultIMEWnd(hwnd)
        if ime_hwnd:
            _user32.SendMessageW(ime_hwnd, _WM_IME_CONTROL, _IMC_SETOPENSTATUS, 0)
        return True
    except Exception as e:
        print(f"      [WARN] 切換英文輸入法失敗:{type(e).__name__}: {e}")
        return False
