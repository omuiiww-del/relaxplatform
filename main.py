import sqlite3
import hashlib
import datetime
import threading
import time
import requests
import hmac
import random
import string
from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.core.window import Window

# =================== إعدادات CoinEx API (مفاتيح المنصة الثابتة) ===================
# ⚠️ استبدل هذه القيم بمفاتيح محفظة المنصة (المركزية)
PLATFORM_ACCESS_ID = "CA36FE11BEBD4257B531FA3FE57DA591"
PLATFORM_SECRET_KEY = "6C637CB07D9645FF906F5F89AF855FB2F159ADC3D7B9DE84"
COINEX_BASE_URL = "https://api.coinex.com/v1"

# دوال CoinEx API باستخدام مفاتيح المنصة
def coinex_request(endpoint, params=None, method='GET'):
    timestamp = int(time.time())
    if params is None:
        params = {}
    params['access_id'] = PLATFORM_ACCESS_ID
    params['timestamp'] = timestamp
    sorted_params = sorted(params.items())
    param_str = '&'.join([f"{k}={v}" for k, v in sorted_params])
    sign = hmac.new(PLATFORM_SECRET_KEY.encode(), param_str.encode(), hashlib.sha256).hexdigest()
    url = f"{COINEX_BASE_URL}/{endpoint}"
    if method == 'GET':
        resp = requests.get(url, params={**params, 'sign': sign})
    else:
        resp = requests.post(url, data={**params, 'sign': sign})
    return resp.json()

def withdraw_coin(currency, amount, address, memo=None):
    params = {'currency': currency, 'amount': amount, 'address': address}
    if memo:
        params['memo'] = memo
    result = coinex_request('account/withdraw', params=params, method='POST')
    return result.get('code') == 0

def get_platform_balance(currency='USDT'):
    result = coinex_request('account/balance')
    if result.get('code') == 0:
        for item in result['data']:
            if item['currency'] == currency:
                return float(item['available'])
    return 0.0
    # =================== الإعدادات العامة ===================
APP_NAME = "Relax Platform"
ESTABLISHED_YEAR = 2025
ESTABLISHED_MONTH = 3
ESTABLISHED_DAY = 31

INVEST_WINDOWS = [("15:00", "15:20"), ("17:00", "17:20"), ("19:00", "19:20")]
REFERRAL_BONUS_WINDOW = ("21:00", "21:20")
VIP_REFERRAL_WINDOW = ("22:00", "22:20")

PROFIT_PERCENT = 2.0
LOCK_DAYS = 45
WITHDRAW_COOLDOWN_HOURS = 12
MINIMUM_DEPOSIT = 500.0
REFERRAL_BONUS = {500: (30, 20), 1000: (60, 40), 2000: (120, 60), 3000: (180, 90)}

# عنوان إيداع المنصة (يظهر للمستخدمين)
PLATFORM_DEPOSIT_ADDRESS = "0xYourPlatformUSDTAddressHere"  # استبدله بعنوانك الحقيقي

# =================== دوال مساعدة ===================
def generate_referral_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def get_current_time_turkey():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=3)

def is_within_window(now, start_str, end_str):
    current_time = now.strftime("%H:%M")
    return start_str <= current_time <= end_str

def can_invest_normal(user_id):
    now = get_current_time_turkey()
    return any(is_within_window(now, s, e) for s, e in INVEST_WINDOWS)

def can_invest_referral_bonus(user_id):
    now = get_current_time_turkey()
    if not is_within_window(now, REFERRAL_BONUS_WINDOW[0], REFERRAL_BONUS_WINDOW[1]):
        return False
    conn = sqlite3.connect('relax_platform.db')
    c = conn.cursor()
    c.execute("SELECT id FROM temp_bonuses WHERE user_id=? AND expires_at > CURRENT_TIMESTAMP AND (last_used_date != date('now') OR last_used_date IS NULL)", (user_id,))
    row = c.fetchone()
    conn.close()
    return row is not None

def can_invest_vip_bonus(user_id):
    now = get_current_time_turkey()
    if not is_within_window(now, VIP_REFERRAL_WINDOW[0], VIP_REFERRAL_WINDOW[1]):
        return False
    conn = sqlite3.connect('relax_platform.db')
    c = conn.cursor()
    c.execute("SELECT permanent_bonus FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row and row[0] == 1

def mark_temp_bonus_used(user_id):
    conn = sqlite3.connect('relax_platform.db')
    c = conn.cursor()
    c.execute("UPDATE temp_bonuses SET used_today=1, last_used_date=date('now') WHERE user_id=? AND expires_at > CURRENT_TIMESTAMP", (user_id,))
    conn.commit()
    conn.close()

# =================== قاعدة البيانات ===================
def init_db():
    conn = sqlite3.connect('relax_platform.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email_or_phone TEXT UNIQUE,
        password TEXT,
        display_name TEXT,
        referral_code TEXT UNIQUE,
        referrer_code TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        total_deposit REAL DEFAULT 0,
        current_balance REAL DEFAULT 0,
        locked_balance REAL DEFAULT 0,
        last_withdraw TIMESTAMP,
        has_deposited BOOLEAN DEFAULT 0,
        referral_count INTEGER DEFAULT 0,
        permanent_bonus BOOLEAN DEFAULT 0,
        withdraw_address TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS investments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        profit REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        executed_at TIMESTAMP,
        status TEXT DEFAULT 'pending',
        bonus_type TEXT DEFAULT 'normal'
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        is_profit BOOLEAN,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id INTEGER,
        referred_id INTEGER,
        deposit_amount REAL,
        bonus_to_referrer REAL,
        bonus_to_referred REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS temp_bonuses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        expires_at TIMESTAMP,
        used_today BOOLEAN DEFAULT 0,
        last_used_date DATE
    )''')
    conn.commit()
    conn.close()

init_db()
# =================== إدارة المستخدمين ===================
class UserManager:
    @staticmethod
    def create_user(email_or_phone, password, display_name, referrer_code=None):
        conn = sqlite3.connect('relax_platform.db')
        c = conn.cursor()
        hashed = hashlib.sha256(password.encode()).hexdigest()
        referrer_id = None
        if referrer_code:
            c.execute("SELECT id FROM users WHERE referral_code=?", (referrer_code,))
            row = c.fetchone()
            if row:
                referrer_id = row[0]
        new_referral_code = generate_referral_code()
        try:
            c.execute("INSERT INTO users (email_or_phone, password, display_name, referral_code, referrer_code) VALUES (?,?,?,?,?)",
                      (email_or_phone, hashed, display_name, new_referral_code, referrer_code))
            user_id = c.lastrowid
            conn.commit()
            if referrer_id:
                expires = (datetime.datetime.now() + datetime.timedelta(days=10)).isoformat()
                c.execute("INSERT INTO temp_bonuses (user_id, expires_at) VALUES (?,?)", (referrer_id, expires))
                c.execute("INSERT INTO temp_bonuses (user_id, expires_at) VALUES (?,?)", (user_id, expires))
                conn.commit()
            return user_id
        except sqlite3.IntegrityError:
            return None
        finally:
            conn.close()

    @staticmethod
    def authenticate(email_or_phone, password):
        conn = sqlite3.connect('relax_platform.db')
        c = conn.cursor()
        hashed = hashlib.sha256(password.encode()).hexdigest()
        c.execute("SELECT id, display_name, referral_code FROM users WHERE email_or_phone=? AND password=?", (email_or_phone, hashed))
        row = c.fetchone()
        conn.close()
        return row

    @staticmethod
    def get_user_balance(user_id):
        conn = sqlite3.connect('relax_platform.db')
        c = conn.cursor()
        c.execute("SELECT current_balance, locked_balance, has_deposited FROM users WHERE id=?", (user_id,))
        row = c.fetchone()
        conn.close()
        return row if row else (0, 0, False)

    @staticmethod
    def update_balance(user_id, amount, lock=False):
        conn = sqlite3.connect('relax_platform.db')
        c = conn.cursor()
        if lock:
            c.execute("UPDATE users SET locked_balance = locked_balance + ? WHERE id=?", (amount, user_id))
        else:
            c.execute("UPDATE users SET current_balance = current_balance + ? WHERE id=?", (amount, user_id))
        conn.commit()
        conn.close()

    @staticmethod
    def process_deposit(user_id, amount):
        if amount < MINIMUM_DEPOSIT:
            return False, f"الحد الأدنى للإيداع هو ${MINIMUM_DEPOSIT:,.0f}"
        conn = sqlite3.connect('relax_platform.db')
        c = conn.cursor()
        c.execute("SELECT total_deposit, has_deposited, referrer_code, referral_count FROM users WHERE id=?", (user_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return False, "المستخدم غير موجود"
        total_deposit_before, has_deposited, referrer_code, referral_count = row
        new_total = total_deposit_before + amount
        c.execute("UPDATE users SET total_deposit = ? WHERE id=?", (new_total, user_id))
        if not has_deposited and amount >= MINIMUM_DEPOSIT:
            c.execute("UPDATE users SET has_deposited = 1 WHERE id=?", (user_id,))
            bonus_referred = 0
            bonus_referrer = 0
            for threshold, (ref_bonus, new_bonus) in REFERRAL_BONUS.items():
                if amount >= threshold:
                    bonus_referrer = ref_bonus
                    bonus_referred = new_bonus
            c.execute("UPDATE users SET current_balance = current_balance + ? WHERE id=?", (amount + bonus_referred, user_id))
            if referrer_code:
                c.execute("SELECT id FROM users WHERE referral_code=?", (referrer_code,))
                referrer_row = c.fetchone()
                if referrer_row and bonus_referrer > 0:
                    referrer_id = referrer_row[0]
                    c.execute("UPDATE users SET current_balance = current_balance + ? WHERE id=?", (bonus_referrer, referrer_id))
                    c.execute("INSERT INTO referrals (referrer_id, referred_id, deposit_amount, bonus_to_referrer, bonus_to_referred) VALUES (?,?,?,?,?)",
                              (referrer_id, user_id, amount, bonus_referrer, bonus_referred))
                    c.execute("UPDATE users SET referral_count = referral_count + 1 WHERE id=?", (referrer_id,))
                    c.execute("SELECT referral_count FROM users WHERE id=?", (referrer_id,))
                    new_count = c.fetchone()[0]
                    if new_count >= 5:
                        c.execute("UPDATE users SET permanent_bonus = 1 WHERE id=?", (referrer_id,))
            conn.commit()
            conn.close()
            return True, f"تم إيداع ${amount:,.2f} بنجاح. حصلت على مكافأة ${bonus_referred:,.2f}."
        else:
            c.execute("UPDATE users SET current_balance = current_balance + ? WHERE id=?", (amount, user_id))
            conn.commit()
            conn.close()
            return True, f"تم إيداع ${amount:,.2f} بنجاح."

    @staticmethod
    def can_withdraw(user_id):
        conn = sqlite3.connect('relax_platform.db')
        c = conn.cursor()
        c.execute("SELECT last_withdraw FROM users WHERE id=?", (user_id,))
        row = c.fetchone()
        conn.close()
        if row and row[0]:
            last = datetime.datetime.fromisoformat(row[0])
            now = datetime.datetime.now()
            return (now - last).total_seconds() >= WITHDRAW_COOLDOWN_HOURS * 3600
        return True

    @staticmethod
    def record_withdraw(user_id, amount, is_profit=True):
        conn = sqlite3.connect('relax_platform.db')
        c = conn.cursor()
        c.execute("INSERT INTO withdrawals (user_id, amount, is_profit) VALUES (?,?,?)", (user_id, amount, is_profit))
        c.execute("UPDATE users SET last_withdraw = CURRENT_TIMESTAMP WHERE id=?", (user_id,))
        if is_profit:
            c.execute("UPDATE users SET current_balance = current_balance - ? WHERE id=?", (amount, user_id))
        else:
            c.execute("UPDATE users SET locked_balance = locked_balance - ? WHERE id=?", (amount, user_id))
        conn.commit()
        conn.close()

    @staticmethod
    def can_invest(user_id):
        conn = sqlite3.connect('relax_platform.db')
        c = conn.cursor()
        c.execute("SELECT has_deposited, current_balance FROM users WHERE id=?", (user_id,))
        row = c.fetchone()
        conn.close()
        return row and row[0] and row[1] > 0

    @staticmethod
    def get_user_stats(user_id):
        conn = sqlite3.connect('relax_platform.db')
        c = conn.cursor()
        c.execute("SELECT referral_count, permanent_bonus FROM users WHERE id=?", (user_id,))
        row = c.fetchone()
        conn.close()
        return row if row else (0, 0)

    @staticmethod
    def get_withdraw_address(user_id):
        conn = sqlite3.connect('relax_platform.db')
        c = conn.cursor()
        c.execute("SELECT withdraw_address FROM users WHERE id=?", (user_id,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else None

    @staticmethod
    def set_withdraw_address(user_id, address):
        conn = sqlite3.connect('relax_platform.db')
        c = conn.cursor()
        c.execute("UPDATE users SET withdraw_address = ? WHERE id=?", (address, user_id))
        conn.commit()
        conn.close()

    @staticmethod
    def get_referral_code(user_id):
        conn = sqlite3.connect('relax_platform.db')
        c = conn.cursor()
        c.execute("SELECT referral_code FROM users WHERE id=?", (user_id,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else None
        # =================== نظام الاستثمار ===================
class InvestmentManager:
    @staticmethod
    def schedule_investment(user_id, amount, bonus_type='normal'):
        conn = sqlite3.connect('relax_platform.db')
        c = conn.cursor()
        c.execute("INSERT INTO investments (user_id, amount, status, bonus_type) VALUES (?,?,?,?)", (user_id, amount, 'scheduled', bonus_type))
        inv_id = c.lastrowid
        conn.commit()
        conn.close()
        threading.Thread(target=lambda: Clock.schedule_once(lambda dt: InvestmentManager.execute_investment(inv_id), 15*60)).start()
        return inv_id

    @staticmethod
    def execute_investment(investment_id):
        conn = sqlite3.connect('relax_platform.db')
        c = conn.cursor()
        c.execute("SELECT user_id, amount, bonus_type FROM investments WHERE id=? AND status='scheduled'", (investment_id,))
        row = c.fetchone()
        if row:
            user_id, amount, bonus_type = row
            profit = amount * PROFIT_PERCENT / 100
            UserManager.update_balance(user_id, -amount, lock=True)
            UserManager.update_balance(user_id, amount + profit, lock=False)
            c.execute("UPDATE investments SET status='completed', profit=?, executed_at=CURRENT_TIMESTAMP WHERE id=?", (profit, investment_id))
            conn.commit()
            if bonus_type == 'temp':
                mark_temp_bonus_used(user_id)
            Clock.schedule_once(lambda dt: InvestmentManager.show_notification(user_id, amount, profit, bonus_type), 0)
        conn.close()

    @staticmethod
    def show_notification(user_id, amount, profit, bonus_type):
        msg = f'تم تنفيذ استثمارك بقيمة ${amount:,.2f} وحققت ربح ${profit:,.2f}'
        if bonus_type == 'temp':
            msg += ' (مكافأة إحالة)'
        elif bonus_type == 'vip':
            msg += ' (مكافأة VIP)'
        popup = Popup(title='استثمار', content=Label(text=msg), size_hint=(0.8,0.4))
        popup.open()
        # =================== شاشات Kivy ===================
class LoginScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=50, spacing=20)
        layout.add_widget(Label(text=APP_NAME, font_size='30sp'))
        self.email_or_phone = TextInput(hint_text='البريد الإلكتروني أو رقم الهاتف', multiline=False)
        self.password = TextInput(hint_text='كلمة المرور', password=True, multiline=False)
        btn_login = Button(text='دخول')
        btn_login.bind(on_press=self.login)
        btn_register = Button(text='تسجيل جديد')
        btn_register.bind(on_press=self.go_to_register)
        layout.add_widget(self.email_or_phone)
        layout.add_widget(self.password)
        layout.add_widget(btn_login)
        layout.add_widget(btn_register)
        self.add_widget(layout)

    def login(self, instance):
        user = UserManager.authenticate(self.email_or_phone.text, self.password.text)
        if user:
            self.manager.current = 'home'
            self.manager.get_screen('home').set_user(user[0], user[1], user[2])
        else:
            popup = Popup(title='خطأ', content=Label(text='بيانات الدخول غير صحيحة'), size_hint=(0.8,0.4))
            popup.open()

    def go_to_register(self, instance):
        self.manager.current = 'register'

class RegisterScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=50, spacing=20)
        layout.add_widget(Label(text='إنشاء حساب', font_size='24sp'))
        self.email_or_phone = TextInput(hint_text='البريد الإلكتروني أو رقم الهاتف', multiline=False)
        self.display_name = TextInput(hint_text='الاسم الظاهر (اختياري)', multiline=False)
        self.password = TextInput(hint_text='كلمة المرور', password=True, multiline=False)
        self.confirm = TextInput(hint_text='تأكيد كلمة المرور', password=True, multiline=False)
        self.referral_code = TextInput(hint_text='رمز الدعوة (اختياري)', multiline=False)
        btn_register = Button(text='تسجيل')
        btn_register.bind(on_press=self.register)
        btn_back = Button(text='رجوع')
        btn_back.bind(on_press=self.go_back)
        layout.add_widget(self.email_or_phone)
        layout.add_widget(self.display_name)
        layout.add_widget(self.password)
        layout.add_widget(self.confirm)
        layout.add_widget(self.referral_code)
        layout.add_widget(btn_register)
        layout.add_widget(btn_back)
        self.add_widget(layout)

    def register(self, instance):
        if self.password.text != self.confirm.text:
            popup = Popup(title='خطأ', content=Label(text='كلمة المرور غير متطابقة'), size_hint=(0.8,0.4))
            popup.open()
            return
        display = self.display_name.text.strip()
        if not display:
            display = self.email_or_phone.text.split('@')[0]
        user_id = UserManager.create_user(self.email_or_phone.text, self.password.text, display, self.referral_code.text)
        if user_id:
            popup = Popup(title='تم', content=Label(text='تم التسجيل بنجاح! قم بإيداع 500$ أو أكثر لبدء الاستثمار.'), size_hint=(0.8,0.4))
            popup.open()
            self.manager.current = 'login'
        else:
            popup = Popup(title='خطأ', content=Label(text='البريد/الهاتف مستخدم بالفعل'), size_hint=(0.8,0.4))
            popup.open()

    def go_back(self, instance):
        self.manager.current = 'login'

class HomeScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = BoxLayout(orientation='vertical', padding=20, spacing=10)
        self.balance_label = Label(text='', size_hint_y=0.3, halign='center')
        self.layout.add_widget(self.balance_label)

        self.deposit_btn = Button(text='💰 إيداع', size_hint_y=0.08)
        self.deposit_btn.bind(on_press=self.go_to_deposit)

        self.invest_btn = Button(text='📈 استثمار عادي', size_hint_y=0.08, background_color=(0.2,0.7,0.2,1))
        self.invest_btn.bind(on_press=self.invest_normal)

        self.bonus_btn = Button(text='🎁 استثمار مكافأة إحالة', size_hint_y=0.08, background_color=(1,0.6,0,1))
        self.bonus_btn.bind(on_press=self.invest_referral_bonus)

        self.vip_btn = Button(text='👑 استثمار VIP', size_hint_y=0.08, background_color=(0.6,0.2,0.8,1))
        self.vip_btn.bind(on_press=self.invest_vip_bonus)

        self.withdraw_btn = Button(text='💸 سحب الأرباح', size_hint_y=0.08)
        self.withdraw_btn.bind(on_press=self.withdraw)

        self.team_btn = Button(text='👥 فريقي', size_hint_y=0.08)
        self.team_btn.bind(on_press=self.go_to_team)

        self.news_btn = Button(text='📰 الأخبار', size_hint_y=0.08)
        self.news_btn.bind(on_press=self.go_to_news)

        self.contest_btn = Button(text='🏆 المسابقات', size_hint_y=0.08)
        self.contest_btn.bind(on_press=self.go_to_contest)

        self.settings_btn = Button(text='⚙️ الإعدادات', size_hint_y=0.08)
        self.settings_btn.bind(on_press=self.go_to_settings)

        self.layout.add_widget(self.deposit_btn)
        self.layout.add_widget(self.invest_btn)
        self.layout.add_widget(self.bonus_btn)
        self.layout.add_widget(self.vip_btn)
        self.layout.add_widget(self.withdraw_btn)
        self.layout.add_widget(self.team_btn)
        self.layout.add_widget(self.news_btn)
        self.layout.add_widget(self.contest_btn)
        self.layout.add_widget(self.settings_btn)
        self.add_widget(self.layout)
        self.user_id = None
        self.display_name = None
        self.referral_code = None

    def set_user(self, user_id, display_name, referral_code):
        self.user_id = user_id
        self.display_name = display_name
        self.referral_code = referral_code
        self.update_balance_display()
        Clock.schedule_interval(lambda dt: self.update_balance_display(), 30)

    def update_balance_display(self):
        if self.user_id:
            current, locked, has_deposited = UserManager.get_user_balance(self.user_id)
            referral_count, permanent_bonus = UserManager.get_user_stats(self.user_id)
            status = "✅ مؤهل للاستثمار" if has_deposited else "❌ غير مؤهل (أقل من 500$ إيداع)"
            bonus_status = f"🎁 مكافأة إحالة: {'متاحة' if can_invest_referral_bonus(self.user_id) else 'غير متاحة'}"
            vip_status = f"👑 VIP: {'متاحة' if permanent_bonus and can_invest_vip_bonus(self.user_id) else 'غير متاحة'}"
            self.balance_label.text = f"مرحباً {self.display_name}\n💰 الرصيد المتاح: ${current:,.2f}\n🔒 رأس المال المستثمر: ${locked:,.2f}\n📊 الحالة: {status}\n👥 إحالات: {referral_count}\n{bonus_status}\n{vip_status}\n🔑 رمز دعوتك: {self.referral_code}"

    def invest_normal(self, instance):
        if not UserManager.can_invest(self.user_id):
            popup = Popup(title='تنبيه', content=Label(text=f'لا يمكنك الاستثمار. يجب إيداع {MINIMUM_DEPOSIT}$ أولاً.'), size_hint=(0.8,0.4))
            popup.open()
            return
        if not can_invest_normal(self.user_id):
            windows = ", ".join([f"{s}-{e}" for s,e in INVEST_WINDOWS])
            popup = Popup(title='تنبيه', content=Label(text=f'أوقات الاستثمار العادي: {windows}'), size_hint=(0.8,0.4))
            popup.open()
            return
        current, _, _ = UserManager.get_user_balance(self.user_id)
        if current <= 0:
            popup = Popup(title='تنبيه', content=Label(text='لا يوجد رصيد متاح للاستثمار'), size_hint=(0.8,0.4))
            popup.open()
            return
        amount = current
        InvestmentManager.schedule_investment(self.user_id, amount, 'normal')
        UserManager.update_balance(self.user_id, -amount, lock=False)
        UserManager.update_balance(self.user_id, amount, lock=True)
        popup = Popup(title='تم', content=Label(text=f'تم استثمار ${amount:,.2f}. سيظهر الربح بعد 15 دقيقة.'), size_hint=(0.8,0.4))
        popup.open()
        self.update_balance_display()

    def invest_referral_bonus(self, instance):
        if not UserManager.can_invest(self.user_id):
            popup = Popup(title='تنبيه', content=Label(text=f'لا يمكنك الاستثمار. يجب إيداع {MINIMUM_DEPOSIT}$ أولاً.'), size_hint=(0.8,0.4))
            popup.open()
            return
        if not can_invest_referral_bonus(self.user_id):
            popup = Popup(title='تنبيه', content=Label(text=f'مكافأة الإحالة متاحة فقط من {REFERRAL_BONUS_WINDOW[0]} إلى {REFERRAL_BONUS_WINDOW[1]} ولمدة 10 أيام بعد التسجيل'), size_hint=(0.8,0.4))
            popup.open()
            return
        current, _, _ = UserManager.get_user_balance(self.user_id)
        if current <= 0:
            popup = Popup(title='تنبيه', content=Label(text='لا يوجد رصيد متاح للاستثمار'), size_hint=(0.8,0.4))
            popup.open()
            return
        amount = current
        InvestmentManager.schedule_investment(self.user_id, amount, 'temp')
        UserManager.update_balance(self.user_id, -amount, lock=False)
        UserManager.update_balance(self.user_id, amount, lock=True)
        mark_temp_bonus_used(self.user_id)
        popup = Popup(title='تم', content=Label(text=f'تم استثمار ${amount:,.2f} (مكافأة إحالة). سيظهر الربح بعد 15 دقيقة.'), size_hint=(0.8,0.4))
        popup.open()
        self.update_balance_display()

    def invest_vip_bonus(self, instance):
        if not UserManager.can_invest(self.user_id):
            popup = Popup(title='تنبيه', content=Label(text=f'لا يمكنك الاستثمار. يجب إيداع {MINIMUM_DEPOSIT}$ أولاً.'), size_hint=(0.8,0.4))
            popup.open()
            return
        if not can_invest_vip_bonus(self.user_id):
            popup = Popup(title='تنبيه', content=Label(text=f'مكافأة VIP متاحة فقط من {VIP_REFERRAL_WINDOW[0]} إلى {VIP_REFERRAL_WINDOW[1]} وللمستخدمين الذين لديهم 5 إحالات على الأقل'), size_hint=(0.8,0.4))
            popup.open()
            return
        current, _, _ = UserManager.get_user_balance(self.user_id)
        if current <= 0:
            popup = Popup(title='تنبيه', content=Label(text='لا يوجد رصيد متاح للاستثمار'), size_hint=(0.8,0.4))
            popup.open()
            return
        amount = current
        InvestmentManager.schedule_investment(self.user_id, amount, 'vip')
        UserManager.update_balance(self.user_id, -amount, lock=False)
        UserManager.update_balance(self.user_id, amount, lock=True)
        popup = Popup(title='تم', content=Label(text=f'تم استثمار ${amount:,.2f} (VIP). سيظهر الربح بعد 15 دقيقة.'), size_hint=(0.8,0.4))
        popup.open()
        self.update_balance_display()

    def withdraw(self, instance):
        if not UserManager.can_withdraw(self.user_id):
            popup = Popup(title='تنبيه', content=Label(text='يمكنك السحب مرة كل 12 ساعة'), size_hint=(0.8,0.4))
            popup.open()
            return
        current, _, _ = UserManager.get_user_balance(self.user_id)
        if current <= 0:
            popup = Popup(title='تنبيه', content=Label(text='لا توجد أرباح قابلة للسحب'), size_hint=(0.8,0.4))
            popup.open()
            return
        amount = current
        address = UserManager.get_withdraw_address(self.user_id)
        if not address:
            popup = Popup(title='تنبيه', content=Label(text='يرجى إدخال عنوان سحب في الإعدادات أولاً'), size_hint=(0.8,0.4))
            popup.open()
            return
        if withdraw_coin('USDT', amount, address):
            UserManager.record_withdraw(self.user_id, amount, is_profit=True)
            popup = Popup(title='تم', content=Label(text=f'تم سحب ${amount:,.2f} بنجاح'), size_hint=(0.8,0.4))
        else:
            popup = Popup(title='خطأ', content=Label(text='فشل السحب، حاول مرة أخرى'), size_hint=(0.8,0.4))
        popup.open()
        self.update_balance_display()

    def go_to_deposit(self, instance):
        self.manager.current = 'deposit'
    def go_to_team(self, instance):
        self.manager.current = 'team'
    def go_to_news(self, instance):
        self.manager.current = 'news'

    def go_to_contest(self, instance):
        self.manager.current = 'contest'

    def go_to_settings(self, instance):
        self.manager.current = 'settings'


class DepositScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=20, spacing=10)
        layout.add_widget(Label(text='إيداع', font_size='20sp'))
        layout.add_widget(Label(text=f'عنوان إيداع المنصة (USDT):\n{PLATFORM_DEPOSIT_ADDRESS}', size_hint_y=0.2))
        self.amount_input = TextInput(hint_text=f'المبلغ (الحد الأدنى {MINIMUM_DEPOSIT}$)', multiline=False, input_filter='float')
        layout.add_widget(self.amount_input)
        btn_deposit = Button(text='أؤكد إيداعي')
        btn_deposit.bind(on_press=self.deposit)
        layout.add_widget(btn_deposit)
        self.result_label = Label(text='', size_hint_y=0.3)
        layout.add_widget(self.result_label)
        btn_back = Button(text='رجوع', size_hint_y=0.1)
        btn_back.bind(on_press=self.go_back)
        layout.add_widget(btn_back)
        self.add_widget(layout)

    def on_enter(self):
        self.result_label.text = ''

    def deposit(self, instance):
        try:
            amount = float(self.amount_input.text)
        except:
            self.result_label.text = '❌ أدخل مبلغاً صحيحاً'
            return
        home = self.manager.get_screen('home')
        if not home.user_id:
            self.result_label.text = '❌ خطأ في المستخدم'
            return
        # هنا يجب التحقق من وصول الإيداع الفعلي إلى محفظة المنصة.
        # للتبسيط نفترض أن المستخدم أكد الإيداع.
        success, msg = UserManager.process_deposit(home.user_id, amount)
        self.result_label.text = msg
        if success:
            self.amount_input.text = ''
            home.update_balance_display()

    def go_back(self, instance):
        self.manager.current = 'home'

class TeamScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=20, spacing=10)
        layout.add_widget(Label(text='فريق الإحالات', font_size='20sp'))
        self.team_info = Label(text='', size_hint_y=0.7, halign='left', valign='top')
        self.team_info.bind(size=self.team_info.setter('text_size'))
        layout.add_widget(self.team_info)
        btn_back = Button(text='رجوع', size_hint_y=0.1)
        btn_back.bind(on_press=self.go_back)
        layout.add_widget(btn_back)
        self.add_widget(layout)

    def on_enter(self):
        home = self.manager.get_screen('home')
        if home.user_id:
            conn = sqlite3.connect('relax_platform.db')
            c = conn.cursor()
            c.execute("SELECT referred_id, deposit_amount, bonus_to_referrer, bonus_to_referred FROM referrals WHERE referrer_id=?", (home.user_id,))
            rows = c.fetchall()
            conn.close()
            if rows:
                text = "الأشخاص الذين دعوتهم:\n\n"
                for r in rows:
                    referred_id, dep, ref_bonus, new_bonus = r
                    text += f"المستخدم ID: {referred_id} | إيداع: ${dep:,.2f} | حصلت على: ${ref_bonus:,.2f}\n"
                self.team_info.text = text
            else:
                self.team_info.text = "لم تقم بدعوة أحد حتى الآن."

    def go_back(self, instance):
        self.manager.current = 'home'

class NewsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=20, spacing=10)
        layout.add_widget(Label(text='آخر الأخبار', font_size='20sp'))
        news_text = f"""📢 منصة {APP_NAME} تأسست في {ESTABLISHED_YEAR}/{ESTABLISHED_MONTH}/{ESTABLISHED_DAY}
🚀 نعمل بجدية وشفافية.
💰 الحد الأدنى للإيداع: {MINIMUM_DEPOSIT}$.
🎁 مكافآت الإحالات:
   • عند دعوة صديق يودع 500$ فما فوق، تحصل أنت وصديقك على مكافآت فورية.
   • أيضاً تحصلان على استثمار إضافي يومي لمدة 10 أيام (الساعة 9:00 – 9:20).
👑 عندما تصل إحالاتك إلى 5، تحصل على استثمار VIP دائم (الساعة 10:00 – 10:20).
📈 أوقات الاستثمار العادي: 3:00-3:20 ، 5:00-5:20 ، 7:00-7:20 (بتوقيت تركيا)."""
        self.news_label = Label(text=news_text, size_hint_y=0.7, halign='left', valign='top')
        self.news_label.bind(size=self.news_label.setter('text_size'))
        layout.add_widget(self.news_label)
        btn_back = Button(text='رجوع', size_hint_y=0.1)
        btn_back.bind(on_press=self.go_back)
        layout.add_widget(btn_back)
        self.add_widget(layout)

    def go_back(self, instance):
        self.manager.current = 'home'

class ContestScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=20, spacing=10)
        layout.add_widget(Label(text='المسابقات', font_size='20sp'))
        contest_text = "🏆 مسابقة أفضل مستثمر لهذا الشهر\nالجائزة: 1000 USDT\n\n🎲 مسابقة يومية: كل إيداع 500$ يمنحك فرصة للفوز بجوائز فورية.\n\n📅 سيتم الإعلان عن الفائزين يومياً."
        self.contest_label = Label(text=contest_text, size_hint_y=0.7, halign='left', valign='top')
        self.contest_label.bind(size=self.contest_label.setter('text_size'))
        layout.add_widget(self.contest_label)
        btn_back = Button(text='رجوع', size_hint_y=0.1)
        btn_back.bind(on_press=self.go_back)
        layout.add_widget(btn_back)
        self.add_widget(layout)

    def go_back(self, instance):
        self.manager.current = 'home'

class SettingsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=20, spacing=10)
        layout.add_widget(Label(text='الإعدادات', font_size='20sp'))
        self.address_input = TextInput(hint_text='عنوان محفظة USDT للسحب', multiline=False)
        layout.add_widget(self.address_input)
        btn_save = Button(text='حفظ العنوان')
        btn_save.bind(on_press=self.save_address)
        layout.add_widget(btn_save)
        self.status_label = Label(text='')
        layout.add_widget(self.status_label)
        btn_back = Button(text='رجوع', size_hint_y=0.1)
        btn_back.bind(on_press=self.go_back)
        layout.add_widget(btn_back)
        self.add_widget(layout)

    def on_enter(self):
        home = self.manager.get_screen('home')
        if home.user_id:
            addr = UserManager.get_withdraw_address(home.user_id)
            if addr:
                self.address_input.text = addr

    def save_address(self, instance):
        home = self.manager.get_screen('home')
        if home.user_id:
            addr = self.address_input.text.strip()
            if addr:
                UserManager.set_withdraw_address(home.user_id, addr)
                self.status_label.text = '✓ تم حفظ العنوان'
            else:
                self.status_label.text = '❌ الرجاء إدخال عنوان صالح'

    def go_back(self, instance):
        self.manager.current = 'home'

# =================== تطبيق Kivy الرئيسي ===================
class RelaxPlatformApp(App):
    def build(self):
        sm = ScreenManager()
        sm.add_widget(LoginScreen(name='login'))
        sm.add_widget(RegisterScreen(name='register'))
        sm.add_widget(HomeScreen(name='home'))
        sm.add_widget(DepositScreen(name='deposit'))
        sm.add_widget(TeamScreen(name='team'))
        sm.add_widget(NewsScreen(name='news'))
        sm.add_widget(ContestScreen(name='contest'))
        sm.add_widget(SettingsScreen(name='settings'))
        return sm

if __name__ == '__main__':
    RelaxPlatformApp().run()