"""
open_and_login.py
開啟臺北市單一帳號認證平台，點選「自然人憑證」分頁，再點選「登入」。

執行方式：
    C:\\Python314\\python.exe open_and_login.py
"""

import time

from browser_utils import (
    launch_chrome_and_wait,
    maximize_and_focus,
    grab_window,
    click_at,
    find_rightmost_cluster,
    find_color_pixels,
    center_of,
)

CHROME_PROFILE = "Profile 2"
URL            = "https://login.gov.taipei/login.php"
TITLE_KEYWORDS = ["單一帳號", "臺北", "登入"]


def find_tab_offset(hwnd, tab_index, total_tabs=4):
    """
    找出分頁列中第 tab_index 個分頁的點擊座標（1-based）。
    掃描頁面中段水平帶，依 x 方向分群後取第 tab_index 群的中心。
    """
    img, r = grab_window(hwnd)
    ww = r.right - r.left
    wh = r.bottom - r.top

    # 分頁列通常在頁面 20%~45% 高度範圍內
    y0 = int(wh * 0.20)
    y1 = int(wh * 0.45)
    strip = img.crop((0, y0, ww, y1))

    def is_tab_color(rv, gv, bv):
        # 排除純白背景和純黑文字，找有色區塊
        brightness = (rv + gv + bv) / 3
        saturation = max(rv, gv, bv) - min(rv, gv, bv)
        return saturation > 20 and 30 < brightness < 220

    pts = find_color_pixels(strip, is_tab_color)
    if not pts:
        return None

    # 按 x 分群（間距 > 50px 視為不同分頁）
    pts.sort(key=lambda p: p[0])
    clusters = []
    current = [pts[0]]
    for p in pts[1:]:
        if p[0] - current[-1][0] <= 50:
            current.append(p)
        else:
            if len(current) >= 30:
                clusters.append(current)
            current = [p]
    if len(current) >= 30:
        clusters.append(current)

    print(f"      分頁帶找到 {len(clusters)} 個色塊群集")
    if len(clusters) < tab_index:
        return None

    target = clusters[tab_index - 1]
    c = center_of(target)
    return c[0], y0 + c[1]


def find_button_offset(hwnd, y_start_ratio=0.45):
    """
    在頁面下半部找「登入」按鈕（最顯眼的有色按鈕群集）。
    """
    img, r = grab_window(hwnd)
    ww = r.right - r.left
    wh = r.bottom - r.top

    y0 = int(wh * y_start_ratio)
    strip = img.crop((0, y0, ww, wh))

    def is_button_color(rv, gv, bv):
        # 找藍色或綠色按鈕
        is_blue  = bv > rv + 20 and bv > gv + 10 and bv > 80
        is_green = gv > rv + 20 and gv > bv + 20 and gv > 80
        return is_blue or is_green

    c = find_rightmost_cluster(strip, is_button_color, min_pixels=50, gap=60)
    if c:
        return c[0], y0 + c[1]
    return None


def main():
    print("[1/4] 開啟臺北市單一帳號認證平台（Profile 2）...")
    win = launch_chrome_and_wait(CHROME_PROFILE, URL, TITLE_KEYWORDS)
    if not win:
        print("[ERROR] 無法找到登入頁面視窗。")
        return
    hwnd = win[0]
    print(f"      HWND={hwnd}，size={win[3]}x{win[4]}")

    time.sleep(2)
    maximize_and_focus(hwnd)
    time.sleep(1)

    # 儲存初始截圖供確認
    img, _ = grab_window(hwnd)
    img.save("step1_loaded.png")
    print("      初始截圖 → step1_loaded.png")

    print("[2/4] 點選「自然人憑證」分頁（第 3 個）...")
    offset = find_tab_offset(hwnd, tab_index=3)
    if offset:
        sx, sy = click_at(hwnd, offset[0], offset[1])
        print(f"      點擊分頁：螢幕座標 ({sx}, {sy})")
    else:
        print("[WARN] 找不到分頁，跳過")

    time.sleep(1.5)
    img, _ = grab_window(hwnd)
    img.save("step2_tab_clicked.png")
    print("      點擊後截圖 → step2_tab_clicked.png")

    print("[3/4] 點選「登入」按鈕...")
    btn = find_button_offset(hwnd)
    if btn:
        sx, sy = click_at(hwnd, btn[0], btn[1])
        print(f"      點擊登入：螢幕座標 ({sx}, {sy})")
    else:
        print("[WARN] 找不到登入按鈕")

    time.sleep(2.5)

    print("[4/4] 儲存結果截圖...")
    result_img, _ = grab_window(hwnd)
    result_img.save("result.png")
    print("[完成] result.png 已儲存")


if __name__ == "__main__":
    main()
