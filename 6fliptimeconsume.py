# optimized_flipkart_scraper_anchor_fallback.py

import json
import logging
import sys
import time
import random
import re
import atexit
from datetime import datetime
from typing import Dict, List, Optional, Any, Set
from pathlib import Path
from contextlib import contextmanager
from urllib.parse import quote_plus, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException
)
from webdriver_manager.chrome import ChromeDriverManager

# ==================== CONFIGURATION ====================

class ScraperConfig:
    """Professional configuration management"""
    def __init__(self):
        # NOTE: tuned defaults for speed; adjust upward if you hit blocks
        self.headless: bool = True
        self.max_pages: int = 5
        self.timeout: int = 12  # page load / request timeout
        self.min_delay: float = 0.15  # lowered for near-1s/page when safe
        self.max_delay: float = 0.4
        self.retry_attempts: int = 3
        self.retry_delay: float = 1.0
        self.save_interval: int = 100
        self.user_agents: List[str] = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
        ]

        # Multi-level fallback selectors for robustness (expanded)
        self.selectors = {
            # include Flipkart common grid/list containers
            'product_container': 'div[data-id], div._2kHMtA, div._13oc-S, div._1AtVbE[data-id], div._1fQZEK',
            'title': [
                'a.KrRmtj', 'a.wfMR5l', 'a.VJA3rP',
                'div.KzDlHZ', 'a[title]', 'div[class*="title"]', 'a._2rpwqI', 'div._4rR01T', 'a.s1Q9rs'
            ],
            'brand': [
                'div.Fo1I0b', 'div._1rcHFq', 'div._1W9f5C', 'div._2WkVRV',
                'div[class*="brand"]', 'span.brand', 'div.brand'
            ],
            'current_price': [
                'div.hZ3P6w', 'div.Nx9bqj', 'div._30jeq3',
                'div[class*="price"]', 'span[class*="price"]', 'div._25b18c'
            ],
            'original_price': [
                'div.kRYCnD', 'div._3I9_wc', 'div._3yAjsT',
                'div[class*="original"]', 'span[class*="original"]'
            ],
            'rating': [
                'div.XQDdHH', 'div._3LWZlK', 'span[class*="rating"]', 'div._3UAT2v'
            ],
            'rating_count': [
                'div.Wphh3N', 'div._2_R_DZ', 'span[class*="reviews"]'
            ],
            'out_of_stock': [
                'div.bgFu62', 'span.fRrrYo', 'div._2d4i2x',
                'div[class*="out-of-stock"]', 'span[class*="unavailable"]'
            ],
            'image': [
                'img.DByuf4', 'img._53J4C-', 'img._2r_T1I',
                'img[src*=".jpg"]', 'img[src*=".png"]', 'img._2r_T1I'
            ],
            # link selector left broad
            'link': 'a[href*="/p/"], a[href*="pid="], a._1fQZEK, a.s1Q9rs'
        }

        # Minimum expected per-page items; if below this, run anchor fallback
        self.min_products_threshold = 10

# ==================== DATA MODELS ====================

class FlipkartProduct:
    """Validated product data model"""
    def __init__(self, **kwargs):
        self.title: str = kwargs.get('title', '').strip()
        self.product_id: str = kwargs.get('product_id', '')
        self.price: int = kwargs.get('price', 0)
        self.original_price: int = kwargs.get('original_price', 0)
        self.discount: int = kwargs.get('discount', 0)
        self.rating: float = kwargs.get('rating', 0.0)
        self.rating_count: int = kwargs.get('rating_count', 0)
        self.brand: str = kwargs.get('brand', '').strip()
        self.product_url: str = kwargs.get('product_url', '')
        self.in_stock: bool = kwargs.get('in_stock', True)
        self.thumbnail: str = kwargs.get('thumbnail', '')
        self.page_number: int = kwargs.get('page_number', 0)
        self.timestamp: str = kwargs.get('timestamp', datetime.now().isoformat())

    def is_valid(self) -> bool:
        """Validate essential fields"""
        return bool(self.title and self.product_id and self.price > 0)

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__

# ==================== SOUP ELEMENT ADAPTER ====================

class SoupElementWrapper:
    """
    Minimal adapter so BeautifulSoup elements behave like Selenium elements for parsing.
    Provides: find_elements(By.CSS_SELECTOR, selector), get_attribute(name), .text
    """
    def __init__(self, soup_elem):
        self.e = soup_elem

    @staticmethod
    def _css_select(elem, selector):
        # many selectors may be comma-separated; just delegate to soup.select
        try:
            return elem.select(selector)
        except Exception:
            return []

    def find_elements(self, by, selector):
        if by == By.CSS_SELECTOR:
            nodes = self._css_select(self.e, selector)
            return [SoupElementWrapper(n) for n in nodes]
        return []

    def get_attribute(self, name):
        if name == "href":
            return self.e.get("href") or ""
        if name == "src":
            return self.e.get("src") or self.e.get("data-src") or ""
        # data-id or other attributes
        return self.e.get(name, "")

    @property
    def text(self):
        return self.e.get_text(separator=" ", strip=True) if self.e else ""

# ==================== CORE SCRAPER ====================

class RobustFlipkartScraper:
    """Production-ready Flipkart scraper with anchor fallback"""

    def __init__(self, config: Optional[ScraperConfig] = None):
        self.config = config or ScraperConfig()
        self.driver: Optional[webdriver.Chrome] = None
        self.wait: Optional[WebDriverWait] = None
        self.seen_ids: Set[str] = set()
        self.stats = {
            'pages_scraped': 0,
            'products_found': 0,
            'products_valid': 0,
            'errors': 0
        }

        # Prepare a requests session for fast-path HTTP fetches
        self.session = requests.Session()
        self.session.headers.update({
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        })

        # Initialize driver lazily — only if fallback to Selenium is needed
        self._driver_initialized = False
        logger.info(" Scraper instance created (driver lazy-init)")
        logger.info(" Will try fast HTTP fetch first, fallback to browser when needed")

    def _initialize_driver(self):
        """Initialize stealth browser only when required"""
        if self._driver_initialized:
            return

        try:
            options = Options()

            if self.config.headless:
                options.add_argument('--headless=new')

            # Stealth & speed settings
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--window-size=1920,1080')
            options.add_argument(f'--user-agent={random.choice(self.config.user_agents)}')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-plugins')
            # still turn off images in browser to save time (we do image urls via requests)
            options.add_argument('--disable-images')

            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            options.add_experimental_option("prefs", {
                "profile.default_content_setting_values.notifications": 2,
                "profile.managed_default_content_settings.images": 2
            })

            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            self.wait = WebDriverWait(self.driver, self.config.timeout)

            # Stealth scripts
            try:
                self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                self.driver.execute_script("""
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                """)
            except Exception:
                # Not critical
                pass

            self._driver_initialized = True
            logger.info(" Stealth browser initialized (lazy)")
        except Exception as e:
            logger.error(f" Driver init failed: {e}")
            raise

    def _random_delay(self):
        """Random delay for anti-detection"""
        time.sleep(random.uniform(self.config.min_delay, self.config.max_delay))

    @contextmanager
    def _page_timeout(self):
        """Context manager for page timeouts"""
        if not self.driver:
            yield
            return
        old_timeout = None
        try:
            old_timeout = self.driver.timeouts.page_load
            self.driver.set_page_load_timeout(self.config.timeout)
            yield
        finally:
            if self.driver and old_timeout is not None:
                try:
                    self.driver.set_page_load_timeout(old_timeout)
                except Exception:
                    pass

    def search(self, query: str, max_pages: Optional[int] = None) -> List[Dict[str, Any]]:
        """Main search function with comprehensive error handling"""
        max_pages = max_pages or self.config.max_pages
        logger.info(f"🔍 Searching '{query}' (max {max_pages} pages)")

        base_url = f"https://www.flipkart.com/search?q={quote_plus(query)}&otracker=search&otracker1=search"
        all_products = []

        try:
            for page in range(1, max_pages + 1):
                logger.info(f"\n📄 Page {page}/{max_pages}")

                try:
                    # 1) Fast path: try HTTP fetch and parse
                    page_products = self._scrape_page_requests(base_url, page)
                    logger.debug(f"Fast-path found {len(page_products)} items")
                    if len(page_products) >= self.config.min_products_threshold:
                        all_products.extend(page_products)
                    else:
                        logger.info("⚠️ Fast-path returned few items; running anchor fallback or browser fallback")
                        # Try anchor fallback in requests first
                        alt_products = self._scrape_page_requests_anchor_fallback(base_url, page)
                        if len(alt_products) >= self.config.min_products_threshold:
                            logger.info(f"⚡ Anchor-fallback (requests) returned {len(alt_products)} items")
                            all_products.extend(alt_products)
                        else:
                            # 2) Fallback: use Selenium for pages where JS rendering required
                            logger.info(" Falling back to browser rendering for this page")
                            page_products = self._scrape_page(base_url, page)
                            # if selenium returns few, try selenium anchor fallback
                            if len(page_products) < self.config.min_products_threshold:
                                alt_products = self._scrape_page_selenium_anchor_fallback(page)
                                logger.info(f"Selenium anchor-fallback returned {len(alt_products)}")
                                page_products.extend([p for p in alt_products if p['product_id'] not in self.seen_ids])
                            all_products.extend(page_products)

                    # Progress checkpoint
                    if len(all_products) % self.config.save_interval == 0 and len(all_products) > 0:
                        self._save_checkpoint(all_products, query, page)

                    # Early exit detection
                    if len(all_products) < 1 and page > 2:
                        logger.info("⚠️ No products found on multiple pages, ending early")
                        break

                    # Aim for low delays — but sleep a small amount
                    self._random_delay()

                except Exception as e:
                    logger.error(f"❌ Page {page} failed: {e}")
                    self.stats['errors'] += 1
                    continue

            self.stats['products_valid'] = len(all_products)
            logger.info(f"✅ Found {len(all_products)} unique products")
            return all_products

        except KeyboardInterrupt:
            logger.warning("⚠️ User interrupted")
        finally:
            self._save_checkpoint(all_products, query, "final")

        return all_products

    # ------------------ REQUESTS PATHS ------------------

    def _scrape_page_requests(self, base_url: str, page: int) -> List[Dict[str, Any]]:
        """
        Fast-path: fetch page HTML with requests and parse with BeautifulSoup.
        Wrap soup elements in SoupElementWrapper so existing parsing code works unchanged.
        """
        url = f"{base_url}&page={page}" if page > 1 else base_url
        headers = {
            "User-Agent": random.choice(self.config.user_agents)
        }
        try:
            resp = self.session.get(url, headers=headers, timeout=self.config.timeout)
            if resp.status_code != 200:
                logger.debug(f"HTTP fast-path status != 200: {resp.status_code}")
                return []

            soup = BeautifulSoup(resp.text, "lxml")

            # Find product nodes using the combined container selector
            raw_nodes = []
            try:
                raw_nodes = soup.select(self.config.selectors['product_container'])
            except Exception:
                raw_nodes = []

            products = []
            for n in raw_nodes:
                try:
                    wrapped = SoupElementWrapper(n)
                    product = self._parse_product(wrapped, page)
                    if product and product.is_valid():
                        if product.product_id not in self.seen_ids:
                            self.seen_ids.add(product.product_id)
                            products.append(product.to_dict())
                except Exception:
                    continue

            # set stats
            if products:
                self.stats['pages_scraped'] += 1
                logger.debug(f"Fast-path parsed {len(products)} products (page {page})")
            return products

        except Exception as e:
            logger.debug(f"Fast-path request failed: {e}")
            return []

    def _scrape_page_requests_anchor_fallback(self, base_url: str, page: int) -> List[Dict[str, Any]]:
        """
        Anchor-based fallback for requests/soup:
        Find product anchor links and climb ancestors to locate the product card.
        This helps capture electronics / mobiles / appliances which use different containers.
        """
        url = f"{base_url}&page={page}" if page > 1 else base_url
        headers = {"User-Agent": random.choice(self.config.user_agents)}
        try:
            resp = self.session.get(url, headers=headers, timeout=self.config.timeout)
            if resp.status_code != 200:
                return []

            soup = BeautifulSoup(resp.text, "lxml")
            anchors = soup.select('a[href*="/p/"], a[href*="pid="], a._1fQZEK, a.s1Q9rs')
            products = []

            seen_hrefs = set()
            for a in anchors:
                try:
                    href = a.get('href') or ""
                    # normalize absolute
                    if href.startswith('/'):
                        href_norm = f"https://www.flipkart.com{href}"
                    else:
                        href_norm = href
                    if not href_norm:
                        continue
                    # dedupe by href
                    if href_norm in seen_hrefs:
                        continue
                    seen_hrefs.add(href_norm)

                    # climb ancestors up to depth 4 to find a node that has price or image
                    candidate = None
                    node = a
                    for _ in range(5):
                        # node may be the anchor or parent
                        if node is None:
                            break
                        # check for price / image / title inside this ancestor
                        if node.select_one(self.config.selectors['current_price']) or node.select_one(self.config.selectors['image']) or node.select_one(self.config.selectors['title']):
                            candidate = node
                            break
                        node = node.parent

                    # fallback: use anchor's parent chain even if no price found
                    if candidate is None:
                        candidate = a.parent or a

                    wrapped = SoupElementWrapper(candidate)
                    # ensure product_url is visible by adding href attribute to candidate if missing
                    if not wrapped.get_attribute('href'):
                        # attach href on the wrapper's element (not modifying actual DOM but provide via a helper)
                        # workaround: the SoupElementWrapper will consult the element for href; set a temporary attr
                        try:
                            candidate['href'] = href_norm
                        except Exception:
                            pass

                    product = self._parse_product(wrapped, page)
                    # ensure product_url if empty, set it from anchor
                    if product:
                        if not product.product_url and href_norm:
                            product.product_url = href_norm
                        if product.is_valid() and product.product_id not in self.seen_ids:
                            self.seen_ids.add(product.product_id)
                            products.append(product.to_dict())
                except Exception:
                    continue

            if products:
                self.stats['pages_scraped'] += 1
            return products

        except Exception as e:
            logger.debug(f"Anchor fallback (requests) failed: {e}")
            return []

    # ------------------ SELENIUM PATHS ------------------

    def _scrape_page(self, base_url: str, page: int) -> List[Dict[str, Any]]:
        """Original Selenium page scraping preserved (lazy driver init)."""
        url = f"{base_url}&page={page}" if page > 1 else base_url

        try:
            self._initialize_driver()

            with self._page_timeout():
                self.driver.get(url)

            # Wait for products to load (original behavior)
            self.wait.until(
                EC.presence_of_all_elements_located(
                    (By.CSS_SELECTOR, self.config.selectors['product_container'])
                )
            )

            # Smart scroll to load all products
            self._smart_scroll()
            logger.info(f"page scrapping: {page}")
            # Extract products
            products = self._extract_products(page)

            self.stats['pages_scraped'] += 1
            logger.info(f"📦 Extracted {len(products)} products (browser)")
            return products

        except TimeoutException:
            logger.warning(f"⏰ Timeout on page {page}")
            return []
        except Exception as e:
            logger.error(f"❌ Page {page} error: {e}")
            return []

    def _scrape_page_selenium_anchor_fallback(self, page: int) -> List[Dict[str, Any]]:
        """
        Selenium anchor-based fallback: find anchors and climb DOM ancestors to find product cards.
        This is more robust for mobiles / laptops / TVs / appliances.
        """
        try:
            if not self._driver_initialized:
                return []

            anchors = self.driver.find_elements(By.CSS_SELECTOR, 'a[href*="/p/"], a[href*="pid="], a._1fQZEK, a.s1Q9rs')
            products = []
            href_seen = set()

            for a in anchors:
                try:
                    href = a.get_attribute('href') or ""
                    if not href:
                        continue
                    if href in href_seen:
                        continue
                    href_seen.add(href)

                    # Climb ancestors (selenium): try up to 5 ancestor divs
                    candidate = None
                    try:
                        # get ancestor nodes using XPath axis
                        ancestors = a.find_elements(By.XPATH, './ancestor::div')
                        # iterate shallow-first
                        for anc in ancestors[:5]:
                            try:
                                # check if this ancestor has a price/img/title inside
                                if anc.find_elements(By.CSS_SELECTOR, self.config.selectors['current_price']) or anc.find_elements(By.CSS_SELECTOR, self.config.selectors['image']) or anc.find_elements(By.CSS_SELECTOR, self.config.selectors['title']):
                                    candidate = anc
                                    break
                            except Exception:
                                continue
                    except Exception:
                        candidate = None

                    if candidate is None:
                        # fallback to parent
                        try:
                            candidate = a.find_element(By.XPATH, './parent::*')
                        except Exception:
                            candidate = a

                    product = self._parse_product(candidate, page)
                    # ensure product_url if empty, set it from anchor
                    if product:
                        if not product.product_url and href:
                            product.product_url = href
                        if product.is_valid() and product.product_id not in self.seen_ids:
                            self.seen_ids.add(product.product_id)
                            products.append(product.to_dict())

                except StaleElementReferenceException:
                    continue
                except Exception:
                    continue

            return products

        except Exception as e:
            logger.debug(f"Selenium anchor fallback failed: {e}")
            return []

    def _smart_scroll(self):
        """Dynamic scroll detection (preserved)."""
        if not self.driver:
            return
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        scroll_attempts = 0

        while scroll_attempts < 4:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)

            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                # Check if loading indicator exists
                if not self.driver.find_elements(By.CSS_SELECTOR, "div._2bnFzA"):
                    break

            last_height = new_height
            scroll_attempts += 1

    def _extract_products(self, page_num: int) -> List[Dict[str, Any]]:
        """Extract with deduplication (preserved logic)."""
        products = []
        elements = self.driver.find_elements(
            By.CSS_SELECTOR, self.config.selectors['product_container']
        )

        for element in elements:
            try:
                product = self._parse_product(element, page_num)
                if product and product.is_valid():
                    if product.product_id not in self.seen_ids:
                        self.seen_ids.add(product.product_id)
                        products.append(product.to_dict())
            except StaleElementReferenceException:
                continue  # Skip stale elements
            except Exception as e:
                logger.debug(f"Parse error: {e}")
                continue

        return products

    def _parse_product(self, element, page_num: int) -> Optional[FlipkartProduct]:
        """Parse product with intelligent fallbacks (kept original logic + small enhancements)."""
        try:
            # Product ID
            product_id = element.get_attribute("data-id") or element.get_attribute("data-pid") or element.get_attribute("data-product-id")
            if not product_id:
                # try to extract from product href if present
                href = ""
                try:
                    # some wrappers might have anchor inside
                    link_elems = element.find_elements(By.CSS_SELECTOR, 'a[href*="/p/"], a[href*="pid="]')
                    if link_elems:
                        href = link_elems[0].get_attribute('href') or ""
                except Exception:
                    href = ""
                if href:
                    # try parse pid from query like ?pid=XXXX
                    parsed = urlparse(href)
                    qs = parse_qs(parsed.query)
                    pid = qs.get('pid') or qs.get('product_id') or qs.get('p')
                    if pid:
                        product_id = pid[0]
                    else:
                        # fallback: hash of href
                        product_id = f"href_{abs(hash(href)) % 1000000}"

            if not product_id:
                # Fallback: generate from title hash
                title_elem = element.find_elements(By.CSS_SELECTOR, "a")
                if title_elem:
                    product_id = f"pid_{abs(hash(title_elem[0].text)) % 100000}"
                else:
                    return None

            # Title (critical field)
            title = self._get_text_with_fallbacks(element, self.config.selectors['title'])
            if not title:
                # fallback: look for generic anchor text
                try:
                    a_elems = element.find_elements(By.CSS_SELECTOR, 'a')
                    if a_elems:
                        title = a_elems[0].text.strip()
                except Exception:
                    title = ""
            if not title:
                return None

            # Brand
            brand = self._get_text_with_fallbacks(element, self.config.selectors['brand'])

            # Prices
            current_price = self._get_price_with_fallbacks(element, self.config.selectors['current_price'])
            original_price = self._get_price_with_fallbacks(element, self.config.selectors['original_price']) or current_price

            # Stock status
            try:
                out_sel = ','.join(self.config.selectors['out_of_stock'])
                in_stock = len(element.find_elements(By.CSS_SELECTOR, out_sel)) == 0
            except Exception:
                in_stock = True

            # URL
            product_url = self._get_product_url(element)

            # Rating
            rating = self._extract_rating(element)
            rating_count = self._extract_rating_count(element)

            # Image
            thumbnail = self._get_image_url(element)

            # Calculate discount
            discount = self._calculate_discount(current_price, original_price)

            return FlipkartProduct(
                title=title,
                product_id=product_id,
                brand=brand,
                price=current_price,
                original_price=original_price,
                discount=discount,
                rating=rating,
                rating_count=rating_count,
                product_url=product_url,
                in_stock=in_stock,
                thumbnail=thumbnail,
                page_number=page_num,
                timestamp=datetime.now().isoformat()
            )

        except Exception as e:
            logger.debug(f"Product parse failed: {e}")
            return None

    def _get_text_with_fallbacks(self, element, selectors: List[str]) -> str:
        """Try multiple selectors intelligently (preserved)."""
        if isinstance(selectors, str):
            selectors = [selectors]
        for selector in selectors:
            try:
                elems = element.find_elements(By.CSS_SELECTOR, selector)
                if elems:
                    attr_text = elems[0].get_attribute("title")
                    if attr_text:
                        return attr_text.strip()

                    text = elems[0].text.strip()
                    if text:
                        return text
            except Exception:
                continue
        return ""

    def _get_price_with_fallbacks(self, element, selectors: List[str]) -> int:
        """Extract price with sanitization (preserved)."""
        if isinstance(selectors, str):
            selectors = [selectors]
        for selector in selectors:
            text = self._get_text_with_fallbacks(element, [selector])
            if text:
                nums = re.sub(r'[^\d]', '', text)
                if nums:
                    try:
                        return int(nums)
                    except Exception:
                        continue
        return 0

    def _get_product_url(self, element) -> str:
        """Extract canonical product URL (preserved)."""
        try:
            link_elems = element.find_elements(
                By.CSS_SELECTOR, self.config.selectors['link']
            )
            if link_elems:
                href = link_elems[0].get_attribute("href")
                if href:
                    if href.startswith('/'):
                        return f"https://www.flipkart.com{href}"
                    return href
            # If element itself is anchor wrapper (soup fallback), try href attr
            href_attr = element.get_attribute("href")
            if href_attr:
                return href_attr if href_attr.startswith("http") else f"https://www.flipkart.com{href_attr}"
        except Exception:
            pass
        return ""

    def _get_image_url(self, element) -> str:
        """Extract high-quality image URL (preserved with small heuristic)."""
        for selector in self.config.selectors['image']:
            try:
                img_elems = element.find_elements(By.CSS_SELECTOR, selector)
                if img_elems:
                    src = img_elems[0].get_attribute("src")
                    if not src:
                        src = img_elems[0].get_attribute("data-src")
                    if src:
                        return src.replace("200/200", "400/400")
            except Exception:
                continue
        return ""

    def _extract_rating(self, element) -> float:
        """Extract rating value (preserved)."""
        text = self._get_text_with_fallbacks(element, self.config.selectors['rating'])
        try:
            if text:
                return float(text.split()[0])
        except Exception:
            pass
        return 0.0

    def _extract_rating_count(self, element) -> int:
        """Extract number of ratings (preserved)."""
        text = self._get_text_with_fallbacks(element, self.config.selectors['rating_count'])
        nums = re.sub(r'[^\d]', '', text)
        return int(nums) if nums else 0

    def _calculate_discount(self, price: int, original: int) -> int:
        """Calculate discount percentage safely (preserved)."""
        if original > 0 and price > 0 and price < original:
            return int(((original - price) / original) * 100)
        return 0

    def _save_checkpoint(self, products: List[Dict], query: str, page: Any):
        """Save progress (preserved)."""
        try:
            safe_query = re.sub(r'[^\w]', '_', query)
            filename = f"checkpoint_{safe_query}_p{page}_{int(time.time())}.json"

            data = {
                "query": query,
                "page": page,
                "timestamp": datetime.now().isoformat(),
                "stats": self.stats,
                "products": products[-self.config.save_interval:]  # Last N
            }

            Path(filename).write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
            logger.debug(f"Checkpoint saved: {filename}")
        except Exception as e:
            logger.warning(f"Checkpoint failed: {e}")

    def save_results(self, products: List[Dict], query: str,
                     filename: Optional[str] = None) -> str:
        """Save final results (preserved)."""
        try:
            if not filename:
                safe_query = re.sub(r'[^\w]', '_', query)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"flipkart_{safe_query}_{timestamp}.json"

            # Enrich with metadata
            data = {
                "metadata": {
                    "query": query,
                    "total": len(products),
                    "unique": len(self.seen_ids),
                    "stats": self.stats,
                    "timestamp": datetime.now().isoformat(),
                    "scraper_version": "2.0.0-anchor"
                },
                "products": products
            }

            Path(filename).write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )

            logger.info(f" Results saved: {filename}")
            return filename

        except Exception as e:
            logger.error(f"Save failed: {e}")
            raise

    def display_summary(self, products: List[Dict]):
        """Display professional summary (preserved)."""
        if not products:
            print("\n No products found")
            return

        # Statistics
        in_stock = sum(1 for p in products if p.get('in_stock'))
        avg_price = sum(p.get('price', 0) for p in products) / len(products) if products else 0
        avg_discount = sum(p.get('discount', 0) for p in products) / len(products) if products else 0
        unique_brands = len(set(p.get('brand', '') for p in products if p.get('brand')))

        print("\n" + "="*120)
        print(" FLIPKART SEARCH SUMMARY".center(120))
        print("="*120)
        print(f"Total Products: {len(products):,}")
        print(f"In Stock: {in_stock:,} ({in_stock/len(products)*100:>5.1f}%)")
        print(f"Average Price: ₹{avg_price:>10,.0f}")
        print(f"Average Discount: {avg_discount:>10.1f}%")
        print(f"Unique Brands: {unique_brands:,}")
        print(f"Pages Scraped: {self.stats['pages_scraped']}")
        print("="*120)

        # Top deals
        print("\n🏆 TOP 10 DEALS:")
        print("-"*120)
        top_deals = sorted(products, key=lambda x: x.get('discount', 0), reverse=True)[:10]

        for idx, p in enumerate(top_deals, 1):
            title = p['title'][:55]
            print(f"{idx:2d}. {title:55s} | "
                  f"₹{p['price']:>7,} | "
                  f"Discount: {p['discount']:>2d}% | "
                  f"{'✅' if p['in_stock'] else '❌'}")

        print("\n" + "✅"*30)
        print(f" Search completed! Data saved to JSON file.")
        print("✅"*30)

    def close(self):
        """Graceful shutdown (preserved)."""
        try:
            if self.driver:
                self.driver.quit()
                logger.info("🚪 Browser closed")
        except Exception as e:
            logger.warning(f"Close error: {e}")

# ==================== CLI INTERFACE ====================

def interactive_mode() -> tuple[str, ScraperConfig, Optional[str]]:
    """Professional CLI (preserved)."""
    print("\n" + "🛒"*40)
    print(" Flipkart Professional Scraper v2.0 ".center(80))
    print("🛒"*40)

    config = ScraperConfig()

    query = input("\n Enter search keyword: ").strip()
    if not query:
        logger.error("Search query cannot be empty")
        sys.exit(1)

    try:
        pages = input(f" Pages (1-10, default={config.max_pages}): ").strip()
        if pages:
            config.max_pages = max(1, min(int(pages), 10))
    except:
        pass

    headless = input("🖥️  Headless mode? (Y/n): ").strip().lower()
    config.headless = headless != 'n'

    filename = input("💾 Custom filename (optional): ").strip()

    return query, config, filename or None

def main():
    """Entry point (preserved)."""
    scraper = None

    try:
        query, config, filename = interactive_mode()

        scraper = RobustFlipkartScraper(config)
        products = scraper.search(query, config.max_pages)

        scraper.display_summary(products)

        saved_file = scraper.save_results(products, query, filename)
        print(f"\n💾 Saved to: {saved_file}")

    except KeyboardInterrupt:
        logger.warning("\n Cancelled by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f" Fatal error: {e}", exc_info=True)
        print(f"\n Error: {e}")
        sys.exit(1)
    finally:
        if scraper:
            scraper.close()

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('flipkart_scraper.log', encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    logger = logging.getLogger(__name__)

    main()