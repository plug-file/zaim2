import os
import time
import json
import requests
import gspread
import ccxt
from datetime import datetime
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from oauth2client.service_account import ServiceAccountCredentials

# --- 設定情報（GitHub Secretsから取得） ---
EMAIL = os.environ.get("ZAIM_EMAIL")
PASSWORD = os.environ.get("ZAIM_PASSWORD")
GCP_JSON_DATA = os.environ.get("GCP_JSON_KEY")
SPREADSHEET_URL = os.environ.get("SPREADSHEET_URL")
BITBANK_API_KEY = os.environ.get("BITBANK_API_KEY")
BITBANK_SECRET = os.environ.get("BITBANK_SECRET")

# --- カテゴリ定義（口座名 → カテゴリ） ---
# スプレッドシートのD列の値をもとに分類
CATEGORY_MAP = {
    "円":       ["円"],
    "VT":       ["VT"],
    "ドル":     ["ドル"],
    "債券":     ["債券"],
    "日本":     ["日本"],
    "GLD":      ["GLD"],
    "サウス":   ["サウス"],
    "暗号":     ["暗号"],
}

# --- 金価格取得ロジック ---
def get_gold_price():
    url = "https://gold.tanaka.co.jp/commodity/souba/d-gold.php"
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        price_table = soup.find('table')
        if price_table:
            price_cell = price_table.find('td', class_='retail_tax')
            if price_cell:
                return price_cell.text.strip().split()[0].replace(',', '')
        return "0"
    except Exception:
        return "0"

# --- bitbank残高取得ロジック ---
def get_bitbank_balance():
    try:
        bitbank = ccxt.bitbank({'apiKey': BITBANK_API_KEY, 'secret': BITBANK_SECRET})
        result = bitbank.fetch_balance()
        jpy = result['total'].get('JPY', 0)
        pairs = ['BTC/JPY', 'XRP/JPY', 'ETH/JPY', 'XYM/JPY', 'GALA/JPY', 'SUI/JPY']
        crypto_total = 0
        for pair in pairs:
            symbol = pair.split('/')[0]
            amount = result['total'].get(symbol, 0)
            if amount > 0:
                last_price = bitbank.fetch_ticker(pair)['last']
                crypto_total += amount * last_price
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

# --- データをJSONに変換する関数 ---
def build_json(raw_data, updated_at):
    """
    raw_data: [["口座名", 万円値, "カテゴリ"], ...] の形式
    スプレッドシートのA列=名前, C列=万円, D列=カテゴリに対応
    """
    accounts = []
    for row in raw_data:
        if len(row) >= 2:
            name = str(row[0]).strip()
            try:
                val_man = float(str(row[1]).replace(',', '').replace('¥', ''))
            except:
                val_man = 0
            category = str(row[2]).strip() if len(row) >= 3 else "-"
            if name and val_man != 0:
                accounts.append({
                    "name": name,
                    "value": round(val_man),
                    "category": category
                })

    # カテゴリ別集計
    cat_totals = {}
    for acc in accounts:
        cat = acc["category"]
        if cat not in ("-", ""):
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
    raw_data = []  # [name, 万円, カテゴリ]

    try:
        # 1. Zaimログイン
        browser.get('https://zaim.net/home')
        browser.find_element(By.NAME, "email").send_keys(EMAIL)
        browser.find_element(By.NAME, "password").send_keys(PASSWORD)
        browser.find_element(By.ID, "submit").click()
        time.sleep(3)

        # 2. 更新ボタン押下
        print("更新中...")
        try:
            reload_btn = browser.find_element(By.CLASS_NAME, "reload-btn")
            reload_btn.click()
            WebDriverWait(browser, 10).until(EC.alert_is_present()).accept()
            print("30秒待機...")
            time.sleep(30)
        except:
            print("更新ボタンなし")

        # 3. データ取得
        browser.get('https://zaim.net/home')
        names = [e.text for e in browser.find_elements(By.XPATH, "//div[@class='name']")]
        values = [e.text.replace('¥', '').replace(',', '') for e in browser.find_elements(By.XPATH, "//div[contains(@class, 'value')]")]
        for n, v in zip(names, values):
            raw_data.append([n, v, ""])  # カテゴリはスプレッドシート側で付与されるため空

        # 証券ページ詳細
        browser.get('https://zaim.net/securities/7547235')
        tables = browser.find_elements(By.CLASS_NAME, "table")
        for table in tables:
            rows = table.find_elements(By.TAG_NAME, "tr")[1:]
            for row in rows:
                cols = row.find_elements(By.TAG_NAME, "td")
                if len(cols) >= 5:
                    name = cols[0].text
                    val = cols[-2].text.replace("¥", "").replace(",", "")
                    raw_data.append([name, val, ""])
                elif len(cols) >= 2:
                    name = cols[0].text
                    val = cols[-1].text.replace("¥", "").replace(",", "")
                    raw_data.append([name, val, ""])

        # 4. 外部データ統合
        jpy, crypto = get_bitbank_balance()
        raw_data.append(["JPY (bitbank)", jpy / 10000, "円"])
        raw_data.append(["CRYPTO (bitbank)", crypto / 10000, "暗号"])

        gold_price = get_gold_price()
        gold_val = int(gold_price) * 800 / 10000
        raw_data.append(["SPDR ゴールド", gold_val, "GLD"])

        now_str = datetime.now(ZoneInfo("Asia/Tokyo")).strftime('%Y/%m/%d %H:%M')

        # 5. スプレッドシート更新（従来通り）
        print("スプレッドシート更新中...")
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(GCP_JSON_DATA), scope)
        client = gspread.authorize(creds)
        worksheet = client.open_by_url(SPREADSHEET_URL).sheet1

        # スプレッドシートからカテゴリ付きデータを再取得してJSONを作成
        # (スプレッドシートのzaimタブが整理されたデータを持っている場合)
        zaim_sheet = client.open_by_url(SPREADSHEET_URL).worksheet("zaim")
        all_values = zaim_sheet.get_all_values()

        # A=名前, B=残高(円), C=万円換算, D=カテゴリ の形式を想定
        structured = []
        for row in all_values[1:]:  # ヘッダー行をスキップ
            if len(row) >= 4 and row[0]:
                try:
                    val_man = float(row[2].replace(',', '')) if row[2] else 0
                except:
                    val_man = 0
                structured.append([row[0], val_man, row[3] if len(row) > 3 else ""])

        output = build_json(structured, now_str)

        # JSONファイルを docs/ ディレクトリに出力（GitHub Pages用）
        os.makedirs("docs", exist_ok=True)
        with open("docs/data.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"docs/data.json を出力しました (total: {output['total']}万円)")

        # 従来のスプレッドシート更新も継続
        worksheet.clear()
        data_to_write = [[r[0], r[1]] for r in raw_data]
        worksheet.insert_rows(data_to_write, 1)
        worksheet.update('E1', [[now_str]])

        print("すべて完了しました。")

    finally:
        browser.quit()

if __name__ == "__main__":
    main()
