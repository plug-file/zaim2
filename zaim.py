import os
import time
import json
import requests
import ccxt
from datetime import datetime
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- 設定情報（GitHub Secretsから取得） ---
EMAIL = os.environ.get("ZAIM_EMAIL")
PASSWORD = os.environ.get("ZAIM_PASSWORD")
BITBANK_API_KEY = os.environ.get("BITBANK_API_KEY")
BITBANK_SECRET = os.environ.get("BITBANK_SECRET")

# --- 手動入力項目（万円単位） ---
MANUAL_ACCOUNTS = [
    {"name": "BITGET",   "value": 50,  "category": "暗号"},
    {"name": "ロボプロ",  "value": 10,  "category": "VT"},
    {"name": "SBI FX",   "value": 100, "category": "ドル"},
]

# --- 口座名 → カテゴリ のマッピング ---
ACCOUNT_CATEGORY = {
    "住信 SBI ネット銀行 代": "円",
    "住信 SBI ネット銀行 定": "円",
    "楽天銀行":               "円",
    "現金残高等":             "円",
    "モバイルSuica":          "円",
    "楽天証券":               "VT",
    "eMAXIS Slim 全世界":     "VT",
    "SBI岡三・US":            "ドル",
    "米ドル現金":             "ドル",
    "その他合計":             "ドル",
    "三菱 UFJ e スマート":    "債券",
    "マネックス証券":         "債券",
    "確定拠出年金":           "債券",
    "iシェアーズ コア 米国":  "債券",
    "楽天カード":             "-",
    "楽天":                   "日本",
    "225投信":                "日本",
    "SPDR ゴールド":          "GLD",
    "SBI-EXE-i":              "サウス",
    "iシェアーズ MSCI":       "サウス",
    "XYM":                    "暗号",
    "JPY (bitbank)":          "円",
    "CRYPTO (bitbank)":       "暗号",
    "ゴールド (田中貴金属)":  "GLD",
}

def categorize(name):
    for key, cat in ACCOUNT_CATEGORY.items():
        if key in name:
            return cat
    return "-"

# --- 金価格取得 ---
def get_gold_price():
    try:
        res = requests.get("https://gold.tanaka.co.jp/commodity/souba/d-gold.php", timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        cell = soup.find('td', class_='retail_tax')
        if cell:
            return int(cell.text.strip().split()[0].replace(',', ''))
    except Exception as e:
        print(f"金価格取得エラー: {e}")
    return 0

# --- bitbank残高取得 ---
def get_bitbank_balance():
    if not BITBANK_API_KEY or not BITBANK_SECRET:
        return 0, 0
    try:
        bb = ccxt.bitbank({'apiKey': BITBANK_API_KEY, 'secret': BITBANK_SECRET})
        markets = bb.load_markets()
        result = bb.fetch_balance()
        jpy = result['total'].get('JPY', 0)
        crypto_total = 0
        for sym, amt in result['total'].items():
            if sym == 'JPY' or not amt or amt <= 0:
                continue
            pair = f'{sym}/JPY'
            if pair in markets:
                try:
                    price = bb.fetch_ticker(pair)['last']
                    crypto_total += amt * price
                    print(f"  bitbank {sym}: {amt} × {price} = {round(amt * price)}円")
                except Exception as e:
                    print(f"  bitbank {sym} 価格取得失敗: {e}")
            else:
                print(f"  bitbank {sym}: JPYペアなしスキップ (残高 {amt})")
        return jpy, crypto_total
    except Exception as e:
        print(f"Bitbankエラー: {e}")
        return 0, 0

# --- ブラウザ設定 ---
def setup_browser():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    browser = webdriver.Chrome(options=options)
    browser.implicitly_wait(10)
    return browser

# --- くふう Zaim ログイン（id.zaim.net） ---
def login_zaim(browser):
    wait = WebDriverWait(browser, 20)

    # ログインページに直接アクセス
    browser.get('https://id.zaim.net')
    time.sleep(3)
    print(f"ログインページURL: {browser.current_url}")
    print(f"ページタイトル: {browser.title}")

    # メールアドレス入力
    email_field = wait.until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, "input[placeholder='登録したメールアドレス'], input[type='email'], input[name='email']")
    ))
    email_field.clear()
    email_field.send_keys(EMAIL)
    print("メールアドレス入力完了")

    # パスワード入力
    pw_field = wait.until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, "input[placeholder='登録したパスワード'], input[type='password']")
    ))
    pw_field.clear()
    pw_field.send_keys(PASSWORD)
    print("パスワード入力完了")

    # ログインボタンクリック（「ログイン」テキストのボタン）
    login_btn = wait.until(EC.element_to_be_clickable(
        (By.XPATH, "//button[contains(text(), 'ログイン')]")
    ))
    browser.execute_script("arguments[0].click();", login_btn)
    print("ログインボタンをクリックしました")

    # zaim.net/home へのリダイレクトを待機
    try:
        WebDriverWait(browser, 20).until(EC.url_contains("zaim.net/home"))
        print(f"ログイン成功: {browser.current_url}")
    except:
        print(f"リダイレクト待機タイムアウト。現在URL: {browser.current_url}")
        browser.save_screenshot("debug_after_login.png")
        # ログイン失敗チェック
        if "id.zaim.net" in browser.current_url:
            raise Exception("ログインに失敗しました。メールアドレス・パスワードを確認してください。")

    time.sleep(3)

# --- JSONビルド ---
def build_json(accounts, updated_at, prev_data=None):
    cat_totals = {}
    for acc in accounts:
        cat = acc["category"]
        if cat != "-":
            cat_totals[cat] = cat_totals.get(cat, 0) + acc["value"]
    total = sum(cat_totals.values())

    prev_cats = {}
    prev_total = None
    if prev_data:
        for c in prev_data.get("categories", []):
            prev_cats[c["name"]] = c["value"]
        prev_total = prev_data.get("total")

    categories = []
    for k, v in sorted(cat_totals.items(), key=lambda x: -x[1]):
        v_rounded = round(v)
        entry = {"name": k, "value": v_rounded}
        if k in prev_cats:
            entry["diff"] = v_rounded - prev_cats[k]
        categories.append(entry)

    for prev_name, prev_val in prev_cats.items():
        if prev_name not in cat_totals:
            categories.append({
                "name": prev_name,
                "value": 0,
                "diff": 0 - prev_val
            })

    result = {
        "updated": updated_at,
        "total": round(total),
        "accounts": accounts,
        "categories": categories,
    }
    if prev_total is not None:
        result["total_diff"] = round(total) - prev_total
    return result

# --- メイン処理 ---
def main():
    browser = setup_browser()
    accounts = []

    try:
        # 1. Zaimログイン
        print("Zaimにログイン中...")
        login_zaim(browser)

        # 2. 更新ボタン押下
        try:
            browser.find_element(By.CLASS_NAME, "reload-btn").click()
            WebDriverWait(browser, 10).until(EC.alert_is_present()).accept()
            print("更新中... 30秒待機")
            time.sleep(30)
        except:
            print("更新ボタンなし、スキップ")

        # 3. ホーム画面から口座残高取得
        browser.get('https://zaim.net/home')
        names  = [e.text for e in browser.find_elements(By.XPATH, "//div[@class='name']")]
        values = [e.text.replace('¥', '').replace(',', '') for e in browser.find_elements(By.XPATH, "//div[contains(@class, 'value')]")]
        for name, val in zip(names, values):
            try:
                val_man = round(int(val) / 10000)
            except:
                continue
            accounts.append({"name": name, "value": val_man, "category": categorize(name)})

        # 4. 証券ページ詳細取得
        browser.get('https://zaim.net/securities/7547235')
        for table in browser.find_elements(By.CLASS_NAME, "table"):
            for row in table.find_elements(By.TAG_NAME, "tr")[1:]:
                cols = row.find_elements(By.TAG_NAME, "td")
                if len(cols) >= 5:
                    name, raw = cols[0].text, cols[-2].text.replace("¥", "").replace(",", "")
                elif len(cols) >= 2:
                    name, raw = cols[0].text, cols[-1].text.replace("¥", "").replace(",", "")
                else:
                    continue
                try:
                    val_man = round(int(raw) / 10000)
                except:
                    continue
                accounts.append({"name": name, "value": val_man, "category": categorize(name)})

        # 5. bitbank残高
        jpy, crypto = get_bitbank_balance()
        if jpy > 0:
            accounts.append({"name": "JPY (bitbank)", "value": round(jpy / 10000), "category": "円"})
        if crypto > 0:
            accounts.append({"name": "CRYPTO (bitbank)", "value": round(crypto / 10000), "category": "暗号"})

        # 6. 金価格（保有量800gで固定）
        gold_price = get_gold_price()
        if gold_price > 0:
            GOLD_GRAMS = 800
            accounts.append({"name": "ゴールド (田中貴金属)", "value": round(gold_price * GOLD_GRAMS / 10000), "category": "GLD"})

        # 7. 手動入力項目を追加
        for m in MANUAL_ACCOUNTS:
            accounts.append({"name": m["name"], "value": m["value"], "category": m["category"]})
            print(f"  手動追加: {m['name']} {m['value']}万円 [{m['category']}]")

        # 8. data.json出力
        now_str = datetime.now(ZoneInfo("Asia/Tokyo")).strftime('%Y/%m/%d %H:%M')

        prev_data = None
        prev_path = "docs/data.json"
        if os.path.exists(prev_path):
            try:
                with open(prev_path, "r", encoding="utf-8") as f:
                    prev_data = json.load(f)
                print(f"前回データを読み込みました（total={prev_data.get('total')}万円）")
            except Exception as e:
                print(f"前回データ読み込みエラー: {e}")

        output = build_json(accounts, now_str, prev_data)
        os.makedirs("docs", exist_ok=True)
        with open(prev_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"完了: docs/data.json 出力（総資産 {output['total']}万円）")

    finally:
        browser.quit()

if __name__ == "__main__":
    main()
