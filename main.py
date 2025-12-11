from __future__ import annotations
from apify import Actor
import asyncio
import json
import time
import random
import re
import requests
from datetime import datetime
from typing import Dict, List, Optional, Any, Set
from urllib.parse import quote_plus, urlparse, parse_qs
from bs4 import BeautifulSoup

# Selenium Imports
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager

# =============================
# Configuration
# =============================
BASE_URL = "https://www.flipkart.com/search"

# Tuned defaults
TIMEOUT = 12
MAX_RETRIES = 3
MIN_PRODUCTS_THRESHOLD = 10

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
]

SELECTORS = {
    'product_container': 'div[data-id], div._2kHMtA, div._13oc-S, div._1AtVbE[data-id], div._1fQZEK',
    'title': ['a.KrRmtj', 'a.wfMR5l', 'a.VJA3rP', 'div.KzDlHZ', 'a[title]', 'div._4rR01T', 'a.s1Q9rs'],
    'brand': ['div.Fo1I0b', 'div._1rcHFq', 'div._2WkVRV', 'span.brand', 'div.brand'],
    'current_price': ['div.hZ3P6w', 'div.Nx9bqj', 'div._30jeq3', 'div._25b18c'],
    'original_price': ['div.kRYCnD', 'div._3I9_wc', 'div._3yAjsT', 'span[class*="original"]'],
    'rating': ['div.XQDdHH', 'div._3LWZlK', 'span[class*="rating"]'],
    'rating_count': ['div.Wphh3N', 'div._2_R_DZ', 'span[class*="reviews"]'],
    'out_of_stock': ['div.bgFu62', 'span.fRrrYo', 'div._2d4i2x'],
    'image': ['img.DByuf4', 'img._53J4C-', 'img._2r_T1I', 'img[src*=".jpg"]'],
    'link': 'a[href*="/p/"], a[href*="pid="], a._1fQZEK, a.s1Q9rs'
}

# =============================
# Helper: Soup Adapter & Parsing
# =============================
class SoupElementWrapper:
    """Adapter to make BS4 elements behave like Selenium elements for unified parsing"""
    def __init__(self, soup_elem):
        self.e = soup_elem

    def find_elements(self, by, selector):
        # We assume 'by' is always CSS_SELECTOR for this adapter
        try:
            nodes = self.e.select(selector)
            return [SoupElementWrapper(n) for n in nodes]
        except:
            return []

    def get_attribute(self, name):
        if name == "href": return self.e.get("href") or ""
        if name == "src": return self.e.get("src") or self.e.get("data-src") or ""
        return self.e.get(name, "")

    @property
    def text(self):
        return self.e.get_text(separator=" ", strip=True) if self.e else ""

def get_text_fallback(element, selectors):
    for sel in selectors:
        try:
            elems = element.find_elements(By.CSS_SELECTOR, sel)
            if elems:
                return elems[0].get_attribute("title") or elems[0].text.strip()
        except: continue
    return ""

def parse_product(element, page: int, keyword: str) -> dict:
    """Unified parser that works with both Selenium elements and SoupElementWrapper"""
    try:
        # 1. Product ID
        product_id = element.get_attribute("data-id") or element.get_attribute("data-pid")
        
        # ID Fallback strategy
        if not product_id:
            try:
                link_elems = element.find_elements(By.CSS_SELECTOR, 'a[href*="/p/"]')
                if link_elems:
                    href = link_elems[0].get_attribute('href')
                    parsed = urlparse(href)
                    qs = parse_qs(parsed.query)
                    pid = qs.get('pid') or qs.get('p')
                    if pid: product_id = pid[0]
            except: pass

        if not product_id: return None

        # 2. Title
        title = get_text_fallback(element, SELECTORS['title'])
        if not title: return None

        # 3. Prices
        price_txt = get_text_fallback(element, SELECTORS['current_price'])
        price = int(re.sub(r'[^\d]', '', price_txt)) if price_txt else 0
        
        orig_txt = get_text_fallback(element, SELECTORS['original_price'])
        orig_price = int(re.sub(r'[^\d]', '', orig_txt)) if orig_txt else price

        # 4. Meta
        brand = get_text_fallback(element, SELECTORS['brand'])
        rating_txt = get_text_fallback(element, SELECTORS['rating'])
        rating = float(rating_txt.split()[0]) if rating_txt else 0.0

        # 5. Image & Link
        image = ""
        for sel in SELECTORS['image']:
            imgs = element.find_elements(By.CSS_SELECTOR, sel)
            if imgs:
                image = imgs[0].get_attribute("src")
                break
        
        item_url = ""
        links = element.find_elements(By.CSS_SELECTOR, SELECTORS['link'])
        if links:
            raw_link = links[0].get_attribute("href")
            if raw_link:
                item_url = "https://www.flipkart.com" + raw_link if raw_link.startswith("/") else raw_link

        return {
            "itemId": product_id,
            "name": title,
            "brand": brand,
            "price": price,
            "originalPrice": orig_price,
            "ratingScore": rating,
            "image": image,
            "itemUrl": item_url,
            "page": page,
            "keyword": keyword,
            "scrapedAt": datetime.now().isoformat()
        }
    except Exception as e:
        return None

# =============================
# Core: Fetch One Page (Hybrid)
# =============================
def get_selenium_driver(headless=True):
    """Lazy init for Selenium Driver"""
    options = Options()
    if headless: options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument(f'--user-agent={random.choice(USER_AGENTS)}')
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def fetch_page_hybrid(
    session: requests.Session, 
    driver_ref: dict, # Pass dict to hold shared driver instance {'driver': None}
    page: int, 
    keyword: str
) -> list:
    
    url = f"{BASE_URL}?q={quote_plus(keyword)}&page={page}"
    Actor.log.info(f"Page {page} → Fetching...")
    
    products = []
    
    # --- METHOD 1: Fast HTTP Requests ---
    try:
        resp = session.get(url, headers={"User-Agent": random.choice(USER_AGENTS)}, timeout=TIMEOUT)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "lxml")
            
            # Standard Container Parsing
            nodes = soup.select(SELECTORS['product_container'])
            
            # Fallback: Anchor Parsing (Your optimized logic)
            if len(nodes) < MIN_PRODUCTS_THRESHOLD:
                Actor.log.info(f"Page {page} → Low HTTP count, trying Anchor Fallback...")
                anchors = soup.select('a[href*="/p/"], a[href*="pid="]')
                seen_hrefs = set()
                for a in anchors:
                    href = a.get('href')
                    if href and href not in seen_hrefs:
                        seen_hrefs.add(href)
                        # Climb up to find a container-like parent
                        parent = a.parent
                        for _ in range(4):
                            if parent: parent = parent.parent
                        if parent: nodes.append(parent)

            # Extract
            for n in nodes:
                wrapped = SoupElementWrapper(n)
                p = parse_product(wrapped, page, keyword)
                if p: products.append(p)
                
            if len(products) >= MIN_PRODUCTS_THRESHOLD:
                Actor.log.info(f"Page {page} → HTTP Success: {len(products)} items")
                return products
    except Exception as e:
        Actor.log.warning(f"Page {page} → HTTP Failed: {e}")

    # --- METHOD 2: Selenium Fallback ---
    Actor.log.info(f"Page {page} → Falling back to Selenium")
    
    if driver_ref['driver'] is None:
        driver_ref['driver'] = get_selenium_driver(headless=True)
    
    driver = driver_ref['driver']
    
    try:
        driver.get(url)
        WebDriverWait(driver, TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'body'))
        )
        
        # Smart Scroll
        last_height = driver.execute_script("return document.body.scrollHeight")
        for _ in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height: break
            last_height = new_height
            
        elements = driver.find_elements(By.CSS_SELECTOR, SELECTORS['product_container'])
        
        # Selenium Anchor Fallback
        if len(elements) < MIN_PRODUCTS_THRESHOLD:
            anchors = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/p/"]')
            for a in anchors:
                try:
                    # XPath to get ancestor
                    ancestor = a.find_element(By.XPATH, "./ancestor::div[4]")
                    elements.append(ancestor)
                except: pass

        seen_ids = set()
        for el in elements:
            try:
                p = parse_product(el, page, keyword)
                if p and p['itemId'] not in seen_ids:
                    seen_ids.add(p['itemId'])
                    products.append(p)
            except: continue
            
        Actor.log.info(f"Page {page} → Selenium Success: {len(products)} items")
        return products

    except Exception as e:
        Actor.log.error(f"Page {page} → Selenium Failed: {e}")
        return []

# =============================
# Main Actor
# =============================
async def main() -> None:
    async with Actor:
        input_data = await Actor.get_input() or {}
        
        # === INPUT VALIDATION ===
        keyword = (input_data.get("search_keyword") or "").strip()
        if not keyword:
            await Actor.fail("search_keyword is required")
            return

        max_pages = int(input_data.get("max_pages", 5))
        
        Actor.log.info(f"Starting Flipkart Scraper: '{keyword}' | Max Pages: {max_pages}")

        # Shared Resources
        session = requests.Session()
        driver_ref = {'driver': None} # Mutable container for lazy driver
        
        total_products = 0
        all_products = []

        try:
            for page in range(1, max_pages + 1):
                # We run the synchronous hybrid fetcher
                products = fetch_page_hybrid(session, driver_ref, page, keyword)
                
                if products:
                    await Actor.push_data(products)
                    total_products += len(products)
                    all_products.extend(products)
                else:
                    Actor.log.warning(f"Page {page} returned 0 items. Stopping.")
                    break
                    
                # Rate Limiting
                time.sleep(random.uniform(1, 2))
                
        finally:
            # Cleanup
            session.close()
            if driver_ref['driver']:
                driver_ref['driver'].quit()
                Actor.log.info("Driver closed.")

        # === FINAL OUTPUT ===
        await Actor.set_value("OUTPUT", {
            "status": "success" if total_products > 0 else "no_results",
            "totalProducts": total_products,
            "keyword": keyword,
            "pagesScraped": page
        })
        
        Actor.log.info(f"DONE. Scraped {total_products} products.")

# =============================
# Run
# =============================
if __name__ == "__main__":
    asyncio.run(main())