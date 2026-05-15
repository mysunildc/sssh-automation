"""找出當前學校視窗 nav bar 中所有綠色群集位置，輸出到 login_pos.txt。"""
import ctypes, ctypes.wintypes
from PIL import ImageGrab, Image
import time

user32 = ctypes.windll.user32
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.POINTER(ctypes.c_int))

found = []
def cb(hwnd, _):
    if user32.IsWindowVisible(hwnd):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        t = buf.value
        if "Chrome" in t and any(k in t for k in ["sssh", "松山", "首頁"]):
            r = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            found.append((hwnd, r.left, r.top, r.right - r.left, r.bottom - r.top))
    return True

user32.EnumWindows(EnumWindowsProc(cb), None)
if not found:
    print("找不到學校視窗"); exit()

hwnd, wl, wt, ww, wh = found[0]
print(f"視窗: HWND={hwnd} size={ww}x{wh}")

# 最大化並截圖
SWP_NOMOVE = 0x0002; SWP_NOSIZE = 0x0001
user32.ShowWindow(hwnd, 3)
user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
user32.SetForegroundWindow(hwnd)
time.sleep(1.5)
user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)

r2 = ctypes.wintypes.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(r2))
wl, wt = r2.left, r2.top
ww = r2.right - r2.left
wh = r2.bottom - r2.top

img = ImageGrab.grab(bbox=(r2.left, r2.top, r2.right, r2.bottom))
nav_y0, nav_y1 = 90, min(210, int(wh * 0.25))
strip = img.crop((0, nav_y0, ww, nav_y1))
strip.save("nav_strip_now.png")
strip.resize((strip.width * 2, strip.height * 2), Image.NEAREST).save("nav_strip_now_2x.png")

# 分析綠色群集（每 20px 一個 bucket）
px = strip.load()
nw, nh = strip.size
buckets = {}
for y in range(nh):
    for x in range(nw):
        rv, gv, bv = px[x, y][:3]
        if gv > rv + 30 and gv > bv + 30 and 50 < gv < 200:
            b = x // 20
            buckets[b] = buckets.get(b, 0) + 1

lines = [f"視窗大小: {ww}x{wh}（最大化後）",
         f"Nav strip: y={nav_y0}~{nav_y1}，寬={nw}px",
         "綠色群集（strip_x = 視窗相對 x）："]
for b in sorted(buckets.keys()):
    x0 = b * 20
    lines.append(f"  strip_x={x0:5d}~{x0+19}  像素數={buckets[b]}")

with open("login_pos.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print("\n".join(lines))
print("\n已儲存 nav_strip_now.png 和 login_pos.txt")
