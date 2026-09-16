"""密碼自動填入防護測試（2026-07-14 公告失敗根因修正）。

三層防護中可純函式測試的部分：
  1. _build_chrome_options 的 prefs 必須關閉密碼管理員
  2. _purge_saved_passwords 啟動前清除 profile 內已存密碼、保留使用者「永不儲存」黑名單
     （2026-09-16：從整檔刪除改成 sqlite3 選擇性刪除，見下方 blacklist 測試）
  3. _force_field_value 送出前驗證欄位最終值、被蓋掉時 JS 改回
登入頁實際 autofill 行為為 live Selenium，於實機驗證。
"""
import os
import sqlite3

import taipeion_login_selenium as tls
from document_closure.document_closure_post_web import _force_field_value


# ── 1. prefs 關閉密碼管理員 ─────────────────────────────────────────────────

def test_chrome_options_disable_password_manager():
    prefs = tls._build_chrome_options().experimental_options["prefs"]
    assert prefs["credentials_enable_service"] is False
    assert prefs["credentials_enable_autosignin"] is False
    assert prefs["profile.password_manager_enabled"] is False
    assert prefs["profile.password_manager_leak_detection"] is False
    # 原有的剪貼簿允許設定不可被弄丟
    assert prefs["profile.default_content_setting_values.clipboard"] == 1


# ── 2. _purge_saved_passwords ───────────────────────────────────────────────

_LOGIN_DB_FILES = ("Login Data", "Login Data-journal",
                   "Login Data For Account", "Login Data For Account-journal")


def test_purge_deletes_login_databases(tmp_path, monkeypatch):
    """假內容 b"x" 不是有效的 SQLite 檔，sqlite3.connect 後第一次查詢就會丟例外，
    因此這裡實際測的是「開檔/操作失敗 → fallback 整檔刪除」那條路徑，行為與舊版
    整檔刪除一致（4 個檔仍應全部被刪），所以本測試不需因新行為而調整斷言。"""
    profile = tmp_path / "User Data" / "Default"
    profile.mkdir(parents=True)
    for name in _LOGIN_DB_FILES:
        (profile / name).write_bytes(b"x")
    (profile / "Preferences").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(tls, "USER_DATA_DIR", str(tmp_path / "User Data"))
    monkeypatch.setattr(tls, "PROFILE_DIR", "Default")
    tls._purge_saved_passwords()

    for name in _LOGIN_DB_FILES:
        assert not (profile / name).exists(), f"{name} 應被刪除"
    assert (profile / "Preferences").exists(), "不相干檔案不可被刪"


def _make_logins_db(path, with_blacklist_column=True):
    """在指定路徑建立最小可用的假 Login Data SQLite 檔：
    1 筆黑名單列（signon_realm='https://edoc.gov.taipei/'，無密碼，只是封鎖標記）
    + 1 筆有密碼的一般登入列。"""
    conn = sqlite3.connect(str(path))
    try:
        cur = conn.cursor()
        columns = "origin_url TEXT, signon_realm TEXT, username_value TEXT, password_value BLOB"
        if with_blacklist_column:
            columns += ", blacklisted_by_user INTEGER"
        cur.execute(f"CREATE TABLE logins ({columns})")
        if with_blacklist_column:
            cur.execute(
                "INSERT INTO logins (origin_url, signon_realm, username_value, "
                "password_value, blacklisted_by_user) VALUES (?, ?, ?, ?, 1)",
                ("https://edoc.gov.taipei/", "https://edoc.gov.taipei/", "", b""),
            )
            cur.execute(
                "INSERT INTO logins (origin_url, signon_realm, username_value, "
                "password_value, blacklisted_by_user) VALUES (?, ?, ?, ?, 0)",
                ("https://login.gov.taipei/", "https://login.gov.taipei/", "user1", b"secret"),
            )
        else:
            cur.execute(
                "INSERT INTO logins (origin_url, signon_realm, username_value, "
                "password_value) VALUES (?, ?, ?, ?)",
                ("https://login.gov.taipei/", "https://login.gov.taipei/", "user1", b"secret"),
            )
        conn.commit()
    finally:
        conn.close()


def test_purge_keeps_blacklist_deletes_passwords(tmp_path, monkeypatch):
    """核心行為：sqlite3 只刪一般密碼列，「永不儲存」黑名單列要保留，
    這樣使用者按過的黑名單下次跑程式不會被洗掉、密碼泡泡不會再跳出來。"""
    profile = tmp_path / "User Data" / "Default"
    profile.mkdir(parents=True)
    db_path = profile / "Login Data"
    _make_logins_db(db_path)

    monkeypatch.setattr(tls, "USER_DATA_DIR", str(tmp_path / "User Data"))
    monkeypatch.setattr(tls, "PROFILE_DIR", "Default")
    tls._purge_saved_passwords()

    assert db_path.exists(), "DB 檔本身應保留（只清內容，不刪檔）"
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT signon_realm, blacklisted_by_user, password_value FROM logins"
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 1, "應只剩黑名單那一列"
    realm, blacklisted, password_value = rows[0]
    assert realm == "https://edoc.gov.taipei/"
    assert blacklisted == 1
    assert bytes(password_value) == b"", "黑名單列本來就沒有密碼"


def test_purge_falls_back_when_blacklist_column_missing(tmp_path, monkeypatch):
    """schema 沒有 blacklisted_by_user 欄位（舊版 Chrome）時，
    無法區分黑名單列，必須 fallback 整檔刪除（安全性優先，寧可刪檔）。"""
    profile = tmp_path / "User Data" / "Default"
    profile.mkdir(parents=True)
    db_path = profile / "Login Data"
    _make_logins_db(db_path, with_blacklist_column=False)

    monkeypatch.setattr(tls, "USER_DATA_DIR", str(tmp_path / "User Data"))
    monkeypatch.setattr(tls, "PROFILE_DIR", "Default")
    tls._purge_saved_passwords()

    assert not db_path.exists(), "欄位不存在時應 fallback 整檔刪除"


def test_purge_tolerates_missing_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(tls, "USER_DATA_DIR", str(tmp_path / "不存在" / "User Data"))
    monkeypatch.setattr(tls, "PROFILE_DIR", "Default")
    tls._purge_saved_passwords()  # 不應丟例外


# ── 3. _force_field_value ───────────────────────────────────────────────────

class _FakeFieldDriver:
    """模擬單一欄位的 driver：read JS 回目前值、write JS 設值。

    frozen=True 模擬「怎麼改都被 autofill 蓋回去」的極端情況（寫入無效）。
    """

    def __init__(self, initial, frozen=False):
        self.value = initial
        self.frozen = frozen
        self.writes = 0

    def execute_script(self, script, *args):
        if "return el ? el.value" in script:
            return self.value
        self.writes += 1
        if not self.frozen:
            self.value = args[1]


def test_force_field_value_already_correct():
    d = _FakeFieldDriver("acc123")
    assert _force_field_value(d, "login-user-name", "acc123", settle=0) is True
    assert d.writes == 0  # 值已正確就不動欄位


def test_force_field_value_overwritten_by_autofill_gets_fixed():
    d = _FakeFieldDriver("robot")  # 被 autofill 填成別組帳號
    assert _force_field_value(d, "login-user-name", "acc123", settle=0) is True
    assert d.value == "acc123"
    assert d.writes == 1


def test_force_field_value_gives_up_when_field_stuck():
    d = _FakeFieldDriver("robot", frozen=True)
    assert _force_field_value(d, "login-user-name", "acc123",
                              attempts=3, settle=0) is False
    assert d.writes == 3
