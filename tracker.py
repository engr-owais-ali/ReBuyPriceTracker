import os
import json
import sqlite3
from datetime import datetime
from bs4 import BeautifulSoup
from curl_cffi import requests

GRADE_MAP = {
    "A1": "Eccellente",
    "A2": "Molto buono",
    "A3": "Buono",
    "A4": "Accettabile",
}

def init_db(db_path="data/rebuy_prices.db"):
    """Creates the data directory and SQLite database if they don't exist."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS price_history (
                timestamp TEXT,
                model TEXT,
                color TEXT,
                memory TEXT,
                condition TEXT,
                price_eur REAL,
                in_stock INTEGER,
                quantity INTEGER
            )
        ''')

def extract_full_matrix(base_url: str):
    """Navigates through memory variants to extract all color/condition combinations."""
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    session = requests.Session(impersonate="chrome120")
    
    try:
        # 1. Fetch initial product page
        res = session.get(base_url, headers=headers, timeout=15)
        if res.status_code != 200:
            print(f"Failed to fetch initial page: {res.status_code}")
            return []
            
        soup = BeautifulSoup(res.text, "html.parser")
        script_tag = soup.find("script", id="ry-inject")
        if not script_tag:
            return []
            
        data = json.loads(script_tag.string)
        p_view = data.get("productViewResponseDto", {})

        # 2. Collect URLs for all memory sizes
        memory_items = p_view.get("relations", {}).get("memory", [])
        memory_urls = [
            f"https://www.rebuy.it/i,{m['id']}/{m['product_slug']}"
            for m in memory_items if "id" in m and "product_slug" in m
        ]
        
        # Fallback if no memory variants exist
        if not memory_urls:
            memory_urls = [base_url]

        all_records = []
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        visited_ids = set()

        # 3. Visit each memory page to collect all colors for that size
        for url in memory_urls:
            r = session.get(url, headers=headers, timeout=15)
            s = BeautifulSoup(r.text, "html.parser")
            tag = s.find("script", id="ry-inject")
            if not tag:
                continue
                
            d = json.loads(tag.string)
            pv = d.get("productViewResponseDto", {})

            # Combine main product with its color variants
            items = [pv.get("product", {})]
            items.extend(pv.get("relations", {}).get("color", []))

            for item in items:
                p_id = item.get("id")
                if not p_id or p_id in visited_ids:
                    continue
                visited_ids.add(p_id)

                model = item.get("basic_name", item.get("name", "Unknown"))
                color = item.get("originalColor", "Unknown")
                memory = item.get("memory_size", "Unknown")

                # Extract the price condition matrix
                for variant in item.get("variants", []):
                    grade_code = variant.get("label", "Unknown")
                    condition = GRADE_MAP.get(grade_code, grade_code)
                    raw_price = variant.get("price")
                    price_eur = raw_price / 100 if raw_price else None
                    qty = variant.get("quantity", 0)

                    all_records.append((
                        now_str, model, color, memory, condition,
                        price_eur, 1 if qty > 0 else 0, qty
                    ))

        return all_records
    except Exception as e:
        print(f"Error during extraction: {e}")
        return []

def save_records(records, db_path="data/rebuy_prices.db"):
    """Saves records to SQLite."""
    if not records:
        print("No records to save.")
        return
    with sqlite3.connect(db_path) as conn:
        conn.executemany('''
            INSERT INTO price_history 
            (timestamp, model, color, memory, condition, price_eur, in_stock, quantity)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', records)
    print(f"[{records[0][0]}] Successfully stored {len(records)} price rows.")

if __name__ == "__main__":
    DB_PATH = "data/rebuy_prices.db"
    
    # You can swap this URL out for any other phone model on Rebuy
    TARGET_URL = "https://www.rebuy.it/i,15362306/smartphone-e-cellulari/samsung-galaxy-s24-plus-dual-sim-256gb-onyx-black"
    
    init_db(DB_PATH)
    records = extract_full_matrix(TARGET_URL)
    save_records(records, DB_PATH)