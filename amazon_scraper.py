"""
Amazon Laptop Scraper - Simple Version
"""

import asyncio
import random
import re
import os
from dataclasses import dataclass, asdict
from typing import List, Dict, Any

import pandas as pd
from playwright.async_api import async_playwright

try:
    from playwright_stealth import stealth_async
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False


@dataclass
class Laptop:
    rank: str = ""
    name: str = ""
    rating: str = ""
    reviews_count: str = ""
    price: str = ""
    url: str = ""
    asin: str = ""


class AmazonScraper:
    URL = "https://www.amazon.com/gp/bestsellers/amazon-renewed/21614632011"
    
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    ]

    def __init__(self):
        self.browser = None
        self.page = None

    async def run(self, max_results: int = 50) -> pd.DataFrame:
        """Main scraping function"""
        laptops = []
        
        async with async_playwright() as p:
            await self._setup_browser(p)
            
            print(f"🛒 Scraping Amazon Best Sellers Laptops...")
            print(f"🎯 Target: {max_results} laptops")
            
            # Scrape page 1
            laptops.extend(await self._scrape_page(self.URL, 1))
            
            # If page 1 doesn't have enough, don't save
            if len(laptops) < max_results:
                print(f"⚠️ Page 1 only has {len(laptops)} laptops, need {max_results}. Not saving.")
                await self.browser.close()
                return pd.DataFrame()
            
            await self.browser.close()
        
        # Remove duplicates by ASIN
        seen = set()
        unique_laptops = []
        for laptop in laptops:
            key = laptop.asin or laptop.name
            if key and key not in seen:
                seen.add(key)
                unique_laptops.append(laptop)
        
        # Convert to DataFrame
        if unique_laptops:
            df = pd.DataFrame([asdict(l) for l in unique_laptops[:max_results]])
            print(f"✅ Found {len(df)} laptops")
            return df
        
        print("❌ No laptops found")
        return pd.DataFrame()

    async def _setup_browser(self, playwright):
        """Setup browser with stealth"""
        self.browser = await playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
            ]
        )
        
        context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=random.choice(self.USER_AGENTS),
            locale="en-US",
        )
        
        await context.set_extra_http_headers({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
        })
        
        if STEALTH_AVAILABLE:
            await stealth_async(context)
        
        self.page = await context.new_page()
        
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

    async def _scrape_page(self, url: str, page_num: int) -> List[Laptop]:
        """Scrape a single page"""
        print(f"📄 Loading page {page_num}...")
        
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await self.page.wait_for_timeout(3000)
        except Exception as e:
            print(f"⚠️ Failed to load page {page_num}: {e}")
            return []
        
        # Handle popups
        await self._handle_popups()
        
        # Scroll to load content
        await self._scroll()
        
        # Extract laptops
        laptops = await self._extract_laptops()
        print(f"   Found {len(laptops)} laptops on page {page_num}")
        
        return laptops

    async def _handle_popups(self):
        """Close cookie/popup dialogs"""
        try:
            for selector in ['#sp-cc-accept', 'input[name="accept"]']:
                btn = self.page.locator(selector)
                if await btn.count() > 0:
                    await btn.first.click(timeout=2000)
                    await self.page.wait_for_timeout(1000)
                    break
        except:
            pass

    async def _scroll(self):
        """Scroll page to load lazy content"""
        for _ in range(10):
            await self.page.mouse.wheel(0, 500)
            await self.page.wait_for_timeout(300)
        await self.page.wait_for_timeout(2000)

    async def _extract_laptops(self) -> List[Laptop]:
        """Extract laptop data from page"""
        try:
            data = await self.page.evaluate('''() => {
                const products = [];
                const seen = new Set();
                
                document.querySelectorAll('a[href*="/dp/"]').forEach(link => {
                    try {
                        const asinMatch = link.href.match(/\\/dp\\/([A-Z0-9]{10})/);
                        if (!asinMatch) return;
                        
                        const asin = asinMatch[1];
                        if (seen.has(asin)) return;
                        seen.add(asin);
                        
                        const container = link.closest('[id^="p13n-asin-index-"]') || 
                                         link.closest('.zg-grid-general-faceout') ||
                                         link.closest('[data-asin]') ||
                                         link.closest('li');
                        
                        if (!container) return;
                        
                        // Get name
                        let name = '';
                        for (const sel of ['div[class*="line-clamp"]', 'div[class*="truncate"]', 'a span']) {
                            const el = container.querySelector(sel);
                            if (el && el.textContent.trim().length > 15) {
                                name = el.textContent.trim();
                                break;
                            }
                        }
                        if (!name) return;
                        
                        // Get rank
                        const rankEl = container.querySelector('.zg-bdg-text');
                        const rank = rankEl ? rankEl.textContent.replace('#', '').trim() : '';
                        
                        // Get rating
                        const ratingEl = container.querySelector('span.a-icon-alt');
                        let rating = '';
                        if (ratingEl) {
                            const match = ratingEl.textContent.match(/([\\d.]+)/);
                            rating = match ? match[1] : '';
                        }
                        
                        // Get reviews
                        let reviews = '';
                        container.querySelectorAll('span.a-size-small').forEach(el => {
                            const t = el.textContent.trim();
                            if (/^[\\d,]+$/.test(t)) reviews = t;
                        });
                        
                        // Get price
                        const priceEl = container.querySelector('.p13n-sc-price, .a-color-price');
                        const price = priceEl ? priceEl.textContent.trim() : '';
                        
                        products.push({
                            rank, name, rating, reviews, price, asin,
                            url: 'https://www.amazon.com/dp/' + asin
                        });
                    } catch(e) {}
                });
                
                return products;
            }''')
            
            laptops = []
            for idx, p in enumerate(data, 1):
                laptops.append(Laptop(
                    rank=p.get('rank') or str(idx),
                    name=p.get('name', ''),
                    rating=p.get('rating', ''),
                    reviews_count=p.get('reviews', ''),
                    price=p.get('price', ''),
                    url=p.get('url', ''),
                    asin=p.get('asin', '')
                ))
            
            return laptops
            
        except Exception as e:
            print(f"⚠️ Extraction error: {e}")
            return []


def main():
    """Main entry point"""
    scraper = AmazonScraper()
    df = asyncio.run(scraper.run(max_results=50))
    
    # Only save if we have data
    if len(df) > 0:
        os.makedirs("data", exist_ok=True)
        df.to_csv("data/data.csv", index=False)
        print(f"💾 Saved data/data.csv ({len(df)} rows)")
    else:
        print("⚠️ No data to save")


if __name__ == "__main__":
    main()
