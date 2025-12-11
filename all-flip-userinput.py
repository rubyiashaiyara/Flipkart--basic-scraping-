# flipkart_scraper.py
import requests
import json
import os
import logging
import sys
import time
import argparse
from typing import Dict, Optional, Any, List
from dataclasses import dataclass
from urllib.parse import urljoin

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('flipkart_scraper.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class FlipkartConfig:
    """Configuration for Flipkart API"""
    base_url: str = "https://1.rome.api.flipkart.com"
    api_endpoint: str = "/api/4/product/swatch"
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    fk_user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 FKUA/website/42/website/Desktop"
    timeout: int = 30
    max_retries: int = 3
    retry_delay: int = 2

class FlipkartAPIError(Exception):
    """Custom exception for Flipkart API errors"""
    pass

class FlipkartScraper:
    """Professional Flipkart Product API Scraper"""
    
    def __init__(self, config: Optional[FlipkartConfig] = None, cookie: Optional[str] = None):
        """
        Initialize the scraper
        
        Args:
            config: FlipkartConfig object (uses defaults if None)
            cookie: Authentication cookie (reads from FLIPKART_COOKIE env var if None)
        """
        self.config = config or FlipkartConfig()
        
        # Try multiple ways to get cookie
        self.cookie = cookie or os.getenv('FLIPKART_COOKIE')
        
        # If still no cookie, prompt user interactively
        if not self.cookie:
            print("\n" + "!"*50)
            print("⚠️  COOKIE NOT FOUND!")
            print("!"*50)
            print("\nTo fix this, you have 3 options:")
            print("1. Set environment variable: export FLIPKART_COOKIE='your_cookie'")
            print("2. Create a .env file with FLIPKART_COOKIE='your_cookie'")
            print("3. Paste it directly below (will not be saved)\n")
            
            self.cookie = input("Please paste your Flipkart cookie here: ").strip()
            
            if not self.cookie:
                raise ValueError("Cookie cannot be empty. Please provide a valid cookie.")
            
            print("✅ Cookie accepted. To avoid this prompt in the future, set the environment variable.\n")
        
        # Initialize session with connection pooling
        self.session = requests.Session()
        self.session.headers.update(self._build_headers())
        
        # Test cookie validity
        self._test_cookie()
        logger.info("FlipkartScraper initialized successfully")
    
    def _build_headers(self) -> Dict[str, str]:
        """Build request headers dynamically"""
        return {
            "Accept": "*/*",
            "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "Origin": "https://www.flipkart.com",
            "Referer": "https://www.flipkart.com/",
            "User-Agent": self.config.user_agent,
            "X-User-Agent": self.config.fk_user_agent,
            "Cookie": self.cookie
        }
    
    def _test_cookie(self):
        """Test if the cookie is valid by making a small request"""
        logger.info("Testing cookie validity...")
        test_payload = {
            "pidLidMap": {"TEST": "TEST"},
            "pincode": "",
            "snippetContext": {
                "facetMap": {},
                "layout": "grid",
                "query": "",
                "queryType": "null",
                "storePath": "clo/ash/axc/mmk/bk1",
                "viewType": "QUICK_VIEW"
            },
            "showSuperTitle": True
        }
        
        try:
            # This will fail with 401 if cookie is invalid
            self._make_request(test_payload)
        except FlipkartAPIError as e:
            if "401" in str(e):
                raise ValueError(
                    "Cookie is INVALID or EXPIRED!\n\n"
                    "To get a fresh cookie:\n"
                    "1. Open Chrome/Firefox and go to flipkart.com\n"
                    "2. Login to your account\n"
                    "3. Press F12 > Network tab\n"
                    "4. Refresh the page\n"
                    "5. Click any request to '1.rome.api.flipkart.com'\n"
                    "6. Right-click > Copy > Copy as cURL\n"
                    "7. Extract the 'Cookie' header value\n"
                    "8. Set it as: export FLIPKART_COOKIE='paste_here'\n"
                )
            raise
    
    def _build_payload(
        self, 
        pid_lid_map: Dict[str, str],
        pincode: str = "",
        query: str = "",
        store_path: str = "clo/ash/axc/mmk/bk1",
        view_type: str = "QUICK_VIEW",
        show_super_title: bool = True,
        layout: str = "grid"
    ) -> Dict[str, Any]:
        """Build API payload dynamically"""
        return {
            "pidLidMap": pid_lid_map,
            "pincode": pincode,
            "snippetContext": {
                "facetMap": {},
                "layout": layout,
                "query": query,
                "queryType": "null",
                "storePath": store_path,
                "viewType": view_type
            },
            "showSuperTitle": show_super_title
        }
    
    def _make_request(self, payload: Dict[str, Any], retries: int = 0) -> requests.Response:
        """Make POST request with error handling and retry logic"""
        url = urljoin(self.config.base_url, self.config.api_endpoint)
        
        try:
            response = self.session.post(url, json=payload, timeout=self.config.timeout)
            response.raise_for_status()
            return response
            
        except requests.exceptions.HTTPError as e:
            if response.status_code == 401 and retries < self.config.max_retries:
                logger.warning(f"Authentication failed. Retry {retries + 1}/{self.config.max_retries}")
                time.sleep(self.config.retry_delay)
                return self._make_request(payload, retries + 1)
            logger.error(f"HTTP {response.status_code}: {response.text}")
            raise FlipkartAPIError(f"HTTP Error {response.status_code}: {response.text}")
                
        except requests.exceptions.RequestException as e:
            if retries < self.config.max_retries:
                logger.warning(f"Request failed. Retry {retries + 1}/{self.config.max_retries}")
                time.sleep(self.config.retry_delay)
                return self._make_request(payload, retries + 1)
            logger.error(f"Request error: {e}")
            raise FlipkartAPIError(f"Request Error: {e}")
    
    def fetch_product_data(
        self, 
        products: List[Dict[str, str]],
        pincode: str = "",
        query: str = "",
        store_path: str = "clo/ash/axc/mmk/bk1",
        view_type: str = "QUICK_VIEW",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Fetch product data from Flipkart API
        
        Args:
            products: List of {"product_id": "...", "listing_id": "..."}
            pincode: Delivery pincode
            query: Search query
            store_path: Store path
            view_type: View type
            **kwargs: Additional payload parameters
        
        Returns:
            API response as dictionary
        """
        if not products:
            raise ValueError("Products list cannot be empty")
        
        pid_lid_map = {p['product_id']: p['listing_id'] for p in products}
        payload = self._build_payload(
            pid_lid_map=pid_lid_map,
            pincode=pincode,
            query=query,
            store_path=store_path,
            view_type=view_type,
            **kwargs
        )
        
        logger.info(f"Fetching data for {len(products)} product(s)")
        response = self._make_request(payload)
        
        try:
            return response.json()
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response: {e}")
            raise FlipkartAPIError(f"JSON Parse Error: {e}")
    
    def save_to_file(self, data: Dict[str, Any], filename: str = "flipkart_response.json"):
        """Save data to JSON file"""
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            logger.info(f"Saved to {filename}")
        except Exception as e:
            logger.error(f"File save error: {e}")
            raise FlipkartAPIError(f"File Error: {e}")
    
    def close(self):
        """Close the session"""
        self.session.close()
        logger.info("Session closed")

def get_user_input() -> Dict[str, Any]:
    """Interactive user input with validation"""
    print("\n" + "="*40)
    print("Flipkart Product Data Scraper")
    print("="*40 + "\n")
    
    products = []
    while True:
        print("Enter product details (or 'done' to finish):")
        product_id = input("  Product ID: ").strip()
        
        if product_id.lower() == 'done':
            break
        
        listing_id = input("  Listing ID: ").strip()
        
        if not product_id or not listing_id:
            print("  ❌ Both fields required. Try again.\n")
            continue
        
        products.append({"product_id": product_id, "listing_id": listing_id})
        
        add_more = input("\nAdd another product? (y/n): ").strip().lower()
        if add_more != 'y':
            break
    
    if not products:
        raise ValueError("At least one product required")
    
    # Optional parameters
    pincode = input("\nPincode (optional): ").strip()
    query = input("Search query (optional): ").strip()
    store_path = input("Store path (optional, Enter=default): ").strip()
    
    return {
        "products": products,
        "pincode": pincode,
        "query": query,
        "store_path": store_path or "clo/ash/axc/mmk/bk1"
    }

def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(description="Scrape Flipkart product data")
    parser.add_argument("--cookie", help="Flipkart cookie string")
    parser.add_argument("--env-file", help="Path to .env file", default=".env")
    parser.add_argument("--test", action="store_true", help="Test cookie validity and exit")
    args = parser.parse_args()
    
    try:
        # Load .env file if it exists
        if os.path.exists(args.env_file):
            from dotenv import load_dotenv
            load_dotenv(args.env_file)
            logger.info(f"Loaded environment from {args.env_file}")
        
        # Initialize scraper
        scraper = FlipkartScraper(cookie=args.cookie)
        
        if args.test:
            print("Cookie is valid!")
            scraper.close()
            sys.exit(0)
        
        # Get input
        user_inputs = get_user_input()
        
        # Fetch
        data = scraper.fetch_product_data(**user_inputs)
        
        # Save
        filename = input("\nOutput filename (default: flipkart_response.json): ").strip()
        scraper.save_to_file(data, filename or "flipkart_response.json")
        
        print(f"\n✅ Success! Processed {len(user_inputs['products'])} product(s)")

    except KeyboardInterrupt:
        print("\n\n❌ Cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}")
        print(f"\n❌ Error: {e}")
        sys.exit(1)
    finally:
        if 'scraper' in locals():
             scraper.close()
if __name__ == "__main__":
    main()