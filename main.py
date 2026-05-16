"""
main.py
自動化主程式 — 統一呼叫各功能模組的入口。

執行方式：
    C:\\Python314\\python.exe main.py
"""

from taipeion_login import login_taipeion

# ── 功能清單 ──────────────────────────────────────────────────────────────────
# 每新增一個功能，在此加入一列：(顯示名稱, 呼叫函式)

FEATURES = [
    ("臺北市單一帳號認證平台 — 自然人憑證登入", login_taipeion),
]


# ── 主選單 ────────────────────────────────────────────────────────────────────

def show_menu():
    print("\n===== 自動化功能選單 =====")
    for i, (name, _) in enumerate(FEATURES, start=1):
        print(f"  {i}. {name}")
    print("  0. 離開")
    print("==========================")


def main():
    while True:
        show_menu()
        choice = input("請選擇功能編號：").strip()

        if choice == "0":
            print("再見！")
            break

        if not choice.isdigit() or not (1 <= int(choice) <= len(FEATURES)):
            print(f"[錯誤] 請輸入 0~{len(FEATURES)} 之間的數字")
            continue

        name, func = FEATURES[int(choice) - 1]
        print(f"\n▶ 執行：{name}")
        print("-" * 40)
        func()
        print("-" * 40)
        input("按 Enter 返回選單...")


if __name__ == "__main__":
    main()
