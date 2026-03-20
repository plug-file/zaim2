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

# --- 口座名 → カテゴリ のマッピング ---
# Zaimの口座名の一部に合わせて編集してください
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
        result = bb.fetch_balance()
        jpy = result['total'].get('JPY', 0)
        crypto_total = 0
        for pair in ['BTC/JPY', 'XRP/JPY', 'ETH/JPY', 'XYM/JPY', 'GALA/JPY', 'SUI/JPY']:
            sym = pair.split('/')[0]
            amt = result['total'].get(sym, 0)
            if amt > 0:
                crypto_total += amt * bb.fetch_ticker(pair)['last']
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
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    browser = webdriver.Chrome(options=options)
    browser.implicitly_wait(10)
    return browser

# --- JSONビルド ---
def build_json(accounts, updated_at):
    cat_totals = {}
    for acc in accounts:
        cat = acc["category"]
        if cat != "-":
            cat_totals[cat] = cat_totals.get(cat, 0) + acc["value"]
    total = sum(cat_totals.values())
    return {
        "updated": updated_at,
        "total": round(total),
        "accounts": accounts,
        "categories": [
            {"name": k, "value": round(v)}
            for k, v in sorted(cat_totals.items(), key=lambda x: -x[1])
        ]
    }

# --- メイン処理 ---
def main():
    browser = setup_browser()
    accounts = []

    try:
        # 1. Zaimログイン
        print("Zaimにログイン中...")
        browser.get('https://zaim.net/home')
        browser.find_element(By.NAME, "email").send_keys(EMAIL)
        browser.find_element(By.NAME, "password").send_keys(PASSWORD)
        browser.find_element(By.ID, "submit").click()
        time.sleep(3)

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

        # 6. 金価格（保有量800gで固定 → 実際の保有量に変更してください）
        gold_price = get_gold_price()
        if gold_price > 0:
            GOLD_GRAMS = 800  # ← 保有グラム数を変更してください
            accounts.append({"name": "ゴールド (田中貴金属)", "value": round(gold_price * GOLD_GRAMS / 10000), "category": "GLD"})

        # 7. data.json出力
        now_str = datetime.now(ZoneInfo("Asia/Tokyo")).strftime('%Y/%m/%d %H:%M')
        output = build_json(accounts, now_str)
        os.makedirs("docs", exist_ok=True)
        with open("docs/data.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"完了: docs/data.json 出力（総資産 {output['total']}万円）")

    finally:
        browser.quit()

if __name__ == "__main__":
    main()
