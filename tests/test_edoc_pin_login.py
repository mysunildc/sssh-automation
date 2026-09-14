"""edoc 站內二次憑證登入測試（2026-09-14）。

從 TAIPEION 點「公文(學校)」進 edoc 後，edoc 不吃 TAIPEION 的 session，會再要一次
自然人憑證 PinCode（index.jsp 的 #pinCode + #pinLogin）。原本沒處理這關，導致
process_document_system 在登入頁上空轉、誤判「無公文待處理」。

這裡用 fake driver 測 edoc_pin_login 的決策邏輯；實際 DOM 互動於實機驗證。
"""
import click_document as cd


class _FakeEl:
    def __init__(self, value="", displayed=True, on_click=None):
        self._value = value
        self._displayed = displayed
        self._on_click = on_click
        self.clicked = 0

    def is_displayed(self):
        return self._displayed

    def click(self):
        self.clicked += 1
        if self._on_click:
            self._on_click()

    def clear(self):
        self._value = ""

    def send_keys(self, s):
        self._value += s

    def get_attribute(self, name):
        return self._value if name == "value" else None


class _FakeDriver:
    """以 {xpath_substring: [elements]} 決定 find_elements 回傳什麼。"""

    def __init__(self, url, pin_el=None, login_el=None):
        self.current_url = url
        self.pin_el = pin_el
        self.login_el = login_el

    def find_elements(self, by, xpath):
        if "pinCode" in xpath or "PIN" in xpath:
            return [self.pin_el] if self.pin_el else []
        if "pinLogin" in xpath or "登入" in xpath:
            return [self.login_el] if self.login_el else []
        return []

    def execute_script(self, script, *args):
        return None


def test_not_on_login_page_is_noop(monkeypatch):
    """已在公文系統內（沒有 pinCode 欄位）→ 直接回 True，不讀 env.env。"""
    called = []
    monkeypatch.setattr("taipeion_login_selenium._read_pin",
                        lambda: called.append(1) or "630124")
    d = _FakeDriver("https://edoc.gov.taipei/tcqb/home/default.jsp")
    assert cd.edoc_pin_login(d, wait_form=0) is True
    assert called == [], "不在登入頁不該去讀 PIN"


def test_stuck_on_index_without_field_fails():
    """停在 index.jsp 卻找不到 pinCode 欄位 → False（不能當成功往下走）。"""
    d = _FakeDriver("https://edoc.gov.taipei/tcqb/index.jsp")
    assert cd.edoc_pin_login(d, wait_form=0) is False


def test_missing_pin_in_env_fails(monkeypatch):
    monkeypatch.setattr("taipeion_login_selenium._read_pin", lambda: None)
    pin_el = _FakeEl()
    d = _FakeDriver("https://edoc.gov.taipei/tcqb/index.jsp", pin_el, _FakeEl())
    assert cd.edoc_pin_login(d, wait_form=0) is False
    assert pin_el.get_attribute("value") == "", "讀不到 PIN 時不該碰欄位"


def test_autofill_tampering_aborts_before_submit(monkeypatch):
    """欄位值被 autofill 蓋掉 → 不送出（錯誤 PIN 連續送出會鎖卡）。"""
    monkeypatch.setattr("taipeion_login_selenium._read_pin", lambda: "630124")

    class _TamperedEl(_FakeEl):
        def send_keys(self, s):
            self._value = "已存密碼"  # 模擬 autofill 蓋掉

    login_el = _FakeEl()
    d = _FakeDriver("https://edoc.gov.taipei/tcqb/index.jsp", _TamperedEl(), login_el)
    assert cd.edoc_pin_login(d, wait_form=0) is False
    assert login_el.clicked == 0, "值不對就不可以按登入"


def test_successful_login(monkeypatch):
    monkeypatch.setattr("taipeion_login_selenium._read_pin", lambda: "630124")
    monkeypatch.setattr(cd.time, "sleep", lambda s: None)

    pin_el = _FakeEl()
    d = _FakeDriver("https://edoc.gov.taipei/tcqb/index.jsp", pin_el)
    # 按下登入後 URL 跳到 default.jsp
    d.login_el = _FakeEl(on_click=lambda: setattr(
        d, "current_url", "https://edoc.gov.taipei/tcqb/home/default.jsp"))

    assert cd.edoc_pin_login(d, wait_form=0, wait_nav=5) is True
    assert pin_el.get_attribute("value") == "630124"
    assert d.login_el.clicked == 1


def test_submit_without_navigation_fails(monkeypatch):
    """按了登入但一直沒離開 index.jsp → False。"""
    monkeypatch.setattr("taipeion_login_selenium._read_pin", lambda: "630124")
    monkeypatch.setattr(cd.time, "sleep", lambda s: None)

    d = _FakeDriver("https://edoc.gov.taipei/tcqb/index.jsp", _FakeEl(), _FakeEl())
    assert cd.edoc_pin_login(d, wait_form=0, wait_nav=2) is False
