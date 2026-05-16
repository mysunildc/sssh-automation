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
    find_color_pixels,
    center_of,
)

CHROME_PROFILE = "Profile 2"
URL            = "https://login.gov.taipei/login.php"
TITLE_KEYWORDS = ["單一帳號", "臺北", "登入"]


def is_teal(rv, gv, bv):
    """判斷像素是否為頁面的青綠色（登入按鈕和分頁底線的顏色）。"""
    return gv > 150 and bv > 150 and rv < 80 and abs(gv - bv) < 60


def cluster_by_x(pts, gap=15, min_pixels=5):
    """將像素點按 x 方向分群，回傳所有群集的清單。"""
    if not pts:
        return []
    pts.sort(key=lambda p: p[0])
    clusters = []
    current = [pts[0]]
    for p in pts[1:]:
        if p[0] - current[-1][0] <= gap:
            current.append(p)
        else:
            if len(current) >= min_pixels:
                clusters.append(current)
            current = [p]
    if len(current) >= min_pixels:
        clusters.append(current)
    return clusters


def find_cert_tab_offset(hwnd):
    """
    偵測「自然人憑證」分頁的青綠色底線，回傳其上方的點擊座標。
    找不到底線時使用比例座標備用（57.6% x, 51% y）。
    """
    img, r = grab_window(hwnd)
    ww = r.right - r.left
    wh = r.bottom - r.top

    # 分頁底線位於視窗高度約 48%~56% 的水平帶
    y0 = int(wh * 0.48)
    y1 = int(wh * 0.56)
    strip = img.crop((0, y0, ww, y1))

    pts = find_color_pixels(strip, is_teal)
    clusters = cluster_by_x(pts, gap=10, min_pixels=3)
    print(f"      分頁底線青綠群集數：{len(clusters)}")

    if clusters:
        # 選取次右側的群集（最右是「行動自然人憑證」，次右是「自然人憑證」）
        clusters.sort(key=lambda c: max(p[0] for p in c))
        target = clusters[-2] if len(clusters) >= 2 else clusters[-1]
        c = center_of(target)
        # 點底線上方（tab 文字區域）
        return c[0], y0 + c[1] - 12

    print("      [備用] 使用比例座標定位分頁")
    return int(ww * 0.576), int(wh * 0.508)


def find_login_button_offset(hwnd):
    """找出頁面中最大的青綠色區塊（「登入」按鈕）的中心座標。"""
    img, r = grab_window(hwnd)
    ww = r.right - r.left
    wh = r.bottom - r.top

    # 登入按鈕位於視窗高度約 60%~82%
    y0 = int(wh * 0.60)
    y1 = int(wh * 0.82)
    strip = img.crop((0, y0, ww, y1))

    pts = find_color_pixels(strip, is_teal)
    clusters = cluster_by_x(pts, gap=20, min_pixels=20)
    print(f"      登入按鈕青綠群集數：{len(clusters)}")

    if not clusters:
        return None

    # 最大群集 = 登入按鈕（按鈕面積最大）
    largest = max(clusters, key=len)
    c = center_of(largest)
    return c[0], y0 + c[1]


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

    print("[2/4] 點選「自然人憑證」分頁...")
    tab = find_cert_tab_offset(hwnd)
    sx, sy = click_at(hwnd, tab[0], tab[1])
    print(f"      點擊分頁：螢幕座標 ({sx}, {sy})")

    time.sleep(1.5)
    img, _ = grab_window(hwnd)
    img.save("step2_tab_clicked.png")
    print("      點擊後截圖 → step2_tab_clicked.png")

    print("[3/4] 點選「登入」按鈕...")
    btn = find_login_button_offset(hwnd)
    if btn:
        sx, sy = click_at(hwnd, btn[0], btn[1])
        print(f"      點擊登入：螢幕座標 ({sx}, {sy})")
    else:
        print("[WARN] 找不到登入按鈕（請確認自然人憑證卡片已插入讀卡機）")

    time.sleep(2.5)

    print("[4/4] 儲存結果截圖...")
    result_img, _ = grab_window(hwnd)
    result_img.save("result.png")
    print("[完成] result.png 已儲存")


if __name__ == "__main__":
    main()
