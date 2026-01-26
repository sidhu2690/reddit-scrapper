import asyncio
import random
import os
from dataclasses import dataclass, asdict
from datetime import datetime
import pandas as pd
from playwright.async_api import async_playwright
import nest_asyncio
nest_asyncio.apply()


@dataclass
class ProductComparison:
    model_name: str = ""
    amazon_mrp: str = ""
    amazon_selling_price: str = ""
    ebazaar_mrp: str = ""
    ebazaar_selling_price: str = ""
    amazon_link: str = ""
    ebazaar_link: str = ""


class UnifiedScraper:
    def __init__(self, debug_mode: bool = False):
        self.browser = None
        self.context = None
        self.debug_mode = debug_mode
        self.debug_dir = "debug_screenshots"
        
        if self.debug_mode:
            os.makedirs(self.debug_dir, exist_ok=True)
        
        # Rotate user agents
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0"
        ]

    async def run(self, input_csv: str) -> pd.DataFrame:
        df_input = pd.read_csv(input_csv)
        products = []
        
        async with async_playwright() as p:
            await self._setup_browser(p)
            
            total = len(df_input)
            for idx, row in df_input.iterrows():
                print(f"\n[{idx + 1}/{total}] Processing: {row['model_name']}")
                
                product = ProductComparison(
                    model_name=row['model_name'],
                    amazon_link=row.get('amazon_link', ''),
                    ebazaar_link=row.get('ebazaar_link', '')
                )
                
                # Scrape Amazon with fresh page
                if pd.notna(row.get('amazon_link')) and str(row['amazon_link']).strip():
                    mrp, selling = await self._scrape_amazon_with_new_page(row['amazon_link'], idx)
                    product.amazon_mrp = mrp
                    product.amazon_selling_price = selling
                
                await asyncio.sleep(random.uniform(2, 4))
                
                # Scrape eBazaar
                if pd.notna(row.get('ebazaar_link')) and str(row['ebazaar_link']).strip():
                    mrp, selling = await self._scrape_ebazaar_with_new_page(row['ebazaar_link'], idx)
                    product.ebazaar_mrp = mrp
                    product.ebazaar_selling_price = selling
                
                products.append(product)
                print(f"  ✓ Done: MRP(A)={product.amazon_mrp}, SP(A)={product.amazon_selling_price}, "
                      f"MRP(E)={product.ebazaar_mrp}, SP(E)={product.ebazaar_selling_price}")
                
                if idx < total - 1:
                    await asyncio.sleep(random.uniform(3, 6))
            
            await self.browser.close()
        
        return pd.DataFrame([asdict(p) for p in products])

    async def _setup_browser(self, playwright):
        self.browser = await playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--disable-infobars',
                '--disable-extensions',
                '--disable-gpu',
                '--no-first-run',
                '--no-default-browser-check',
                '--ignore-certificate-errors',
            ]
        )

    async def _create_stealth_context(self):
        """Create a new context with stealth settings"""
        context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=random.choice(self.user_agents),
            locale='en-US',
            timezone_id='America/New_York',
            color_scheme='light',
            device_scale_factor=1,
            has_touch=False,
            is_mobile=False,
            java_script_enabled=True,
            permissions=['geolocation'],
            geolocation={'latitude': 40.7128, 'longitude': -74.0060},
            extra_http_headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0',
            }
        )
        
        # Comprehensive stealth script
        await context.add_init_script('''
            // Webdriver
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            delete navigator.__proto__.webdriver;
            
            // Plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    const plugins = [
                        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                        { name: 'Native Client', filename: 'internal-nacl-plugin' }
                    ];
                    plugins.item = (index) => plugins[index];
                    plugins.namedItem = (name) => plugins.find(p => p.name === name);
                    plugins.refresh = () => {};
                    return plugins;
                }
            });
            
            // Languages
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'language', { get: () => 'en-US' });
            
            // Platform
            Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
            
            // Hardware concurrency
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
            
            // Device memory
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
            
            // Chrome
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
            
            // Permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            // WebGL Vendor
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Intel Inc.';
                if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                return getParameter.call(this, parameter);
            };
            
            // Console
            const originalConsole = window.console;
            window.console = {
                ...originalConsole,
                debug: () => {},
            };
        ''')
        
        return context

    async def _scrape_amazon_with_new_page(self, url: str, idx: int) -> tuple:
        """Scrape Amazon with a fresh context for each request"""
        context = await self._create_stealth_context()
        page = await context.new_page()
        
        try:
            # First visit Amazon homepage to get cookies
            print("  → Visiting Amazon homepage first...")
            await page.goto('https://www.amazon.com', wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(random.uniform(2, 4))
            
            # Now visit the product page
            print(f"  → Loading product page...")
            response = await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            
            # Check for blocks
            if response and response.status >= 400:
                print(f"  ⚠ Amazon returned status {response.status}")
                if self.debug_mode:
                    await self._save_debug(page, idx, "amazon")
                return "Blocked", "Blocked"
            
            await asyncio.sleep(random.uniform(3, 5))
            
            # Check for CAPTCHA
            page_content = await page.content()
            if 'captcha' in page_content.lower() or 'robot' in page_content.lower():
                print("  ⚠ CAPTCHA detected!")
                if self.debug_mode:
                    await self._save_debug(page, idx, "amazon_captcha")
                return "CAPTCHA", "CAPTCHA"
            
            # Human-like scrolling
            await page.evaluate('window.scrollBy(0, 300)')
            await asyncio.sleep(random.uniform(0.5, 1))
            await page.evaluate('window.scrollBy(0, 200)')
            await asyncio.sleep(random.uniform(0.5, 1))
            
            # Wait for price elements
            try:
                await page.wait_for_selector(
                    '#corePrice_feature_div, #priceblock_ourprice, .a-price, #apex_desktop',
                    timeout=10000
                )
            except:
                print("  ⚠ Price element not found in DOM")
            
            await asyncio.sleep(1)
            
            # Extract prices
            data = await page.evaluate('''() => {
                let sellingPrice = '';
                let mrp = '';
                
                // SELLING PRICE - Try multiple methods
                const sellingSelectors = [
                    '#corePrice_feature_div .a-price:not([data-a-strike="true"]) .a-offscreen',
                    '.priceToPay .a-offscreen',
                    '.a-price.aok-align-center .a-offscreen',
                    '#apex_offerDisplay_desktop .a-offscreen',
                    '.a-price.reinventPricePriceToPayMargin .a-offscreen',
                    '#priceblock_ourprice',
                    '#priceblock_dealprice',
                    '#priceblock_saleprice',
                    '.a-price .a-offscreen',
                    'span.a-price-whole'
                ];
                
                for (const selector of sellingSelectors) {
                    const els = document.querySelectorAll(selector);
                    for (const el of els) {
                        const text = el?.textContent?.trim();
                        if (text && /[$₹£€]/.test(text)) {
                            const parent = el.closest('[data-a-strike="true"], .a-text-price');
                            if (!parent) {
                                sellingPrice = text;
                                break;
                            }
                        }
                    }
                    if (sellingPrice) break;
                }
                
                // Build price from parts if needed
                if (!sellingPrice) {
                    const whole = document.querySelector('.a-price-whole');
                    const fraction = document.querySelector('.a-price-fraction');
                    if (whole) {
                        sellingPrice = '$' + whole.textContent.replace(/[^0-9]/g, '');
                        if (fraction) {
                            sellingPrice += '.' + fraction.textContent.trim();
                        }
                    }
                }
                
                // MRP PRICE
                const mrpSelectors = [
                    '.a-text-price .a-offscreen',
                    '.basisPrice .a-offscreen',
                    '[data-a-strike="true"] .a-offscreen',
                    '#priceblock_listprice',
                    '#listPrice',
                    '.a-text-strike'
                ];
                
                for (const selector of mrpSelectors) {
                    const el = document.querySelector(selector);
                    const text = el?.textContent?.trim();
                    if (text && /[$₹£€]/.test(text)) {
                        mrp = text;
                        break;
                    }
                }
                
                if (!mrp && sellingPrice) mrp = sellingPrice;
                
                return { mrp, sellingPrice };
            }''')
            
            mrp = data.get('mrp', '').strip() or "N/A"
            selling = data.get('sellingPrice', '').strip() or "N/A"
            
            if selling == "N/A" and self.debug_mode:
                await self._save_debug(page, idx, "amazon")
            
            print(f"  Amazon: MRP={mrp}, Selling={selling}")
            return mrp, selling
            
        except Exception as e:
            print(f"  ✗ Amazon error: {str(e)[:80]}")
            if self.debug_mode:
                try:
                    await self._save_debug(page, idx, "amazon_error")
                except:
                    pass
            return "Error", "Error"
        finally:
            await context.close()

    async def _scrape_ebazaar_with_new_page(self, url: str, idx: int) -> tuple:
        """Scrape eBazaar with a fresh context"""
        context = await self._create_stealth_context()
        page = await context.new_page()
        
        try:
            response = await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            
            if response and response.status >= 400:
                print(f"  ⚠ eBazaar returned status {response.status}")
                return "Blocked", "Blocked"
            
            await asyncio.sleep(random.uniform(2, 4))
            
            try:
                await page.wait_for_selector(
                    '.product-info-price, .price-box, .price',
                    timeout=10000
                )
            except:
                pass
            
            await asyncio.sleep(1)
            
            data = await page.evaluate('''() => {
                let sellingPrice = '';
                let mrp = '';
                
                // Try data attributes first
                const finalPriceEl = document.querySelector('[data-price-type="finalPrice"]');
                if (finalPriceEl) {
                    const amount = finalPriceEl.getAttribute('data-price-amount');
                    if (amount) sellingPrice = '$' + parseFloat(amount).toFixed(2);
                }
                
                const oldPriceEl = document.querySelector('[data-price-type="oldPrice"]');
                if (oldPriceEl) {
                    const amount = oldPriceEl.getAttribute('data-price-amount');
                    if (amount) mrp = '$' + parseFloat(amount).toFixed(2);
                }
                
                // Fallback: parse text
                if (!sellingPrice || !mrp) {
                    const containers = document.querySelectorAll('.product-info-price, .price-box, .product-info-main');
                    for (const container of containers) {
                        const text = container.innerText;
                        const prices = text.match(/\\$[\\d,]+\\.?\\d*/g);
                        if (prices && prices.length >= 2) {
                            const nums = prices.map(p => parseFloat(p.replace(/[$,]/g, '')));
                            if (!sellingPrice) sellingPrice = '$' + Math.min(...nums).toFixed(2);
                            if (!mrp) mrp = '$' + Math.max(...nums).toFixed(2);
                            break;
                        } else if (prices && prices.length === 1) {
                            if (!sellingPrice) sellingPrice = prices[0];
                        }
                    }
                }
                
                if (!mrp && sellingPrice) mrp = sellingPrice;
                
                return { mrp, sellingPrice };
            }''')
            
            mrp = data.get('mrp', '').strip() or "N/A"
            selling = data.get('sellingPrice', '').strip() or "N/A"
            
            print(f"  eBazaar: MRP={mrp}, Selling={selling}")
            return mrp, selling
            
        except Exception as e:
            print(f"  ✗ eBazaar error: {str(e)[:80]}")
            return "Error", "Error"
        finally:
            await context.close()

    async def _save_debug(self, page, idx: int, source: str):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            await page.screenshot(path=f"{self.debug_dir}/{source}_{idx}_{timestamp}.png", full_page=True)
            html = await page.content()
            with open(f"{self.debug_dir}/{source}_{idx}_{timestamp}.html", "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  📸 Debug saved: {source}_{idx}_{timestamp}")
        except Exception as e:
            print(f"  Failed to save debug: {e}")


def main():
    print("=" * 60)
    print("Price Scraper Started")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Enable debug_mode=True to save screenshots when Amazon fails
    scraper = UnifiedScraper(debug_mode=True)
    
    try:
        df_output = asyncio.run(scraper.run('price/input_links.csv'))
        df_output.to_csv("price/data.csv", index=False)
        
        print("\n" + "=" * 60)
        print(f"✓ Done! Saved {len(df_output)} products to price/data.csv")
        
        # Stats
        amazon_ok = len(df_output[(df_output['amazon_selling_price'] != 'N/A') & 
                                   (df_output['amazon_selling_price'] != 'Error') &
                                   (df_output['amazon_selling_price'] != 'CAPTCHA') &
                                   (df_output['amazon_selling_price'] != 'Blocked')])
        ebazaar_ok = len(df_output[(df_output['ebazaar_selling_price'] != 'N/A') & 
                                    (df_output['ebazaar_selling_price'] != 'Error')])
        
        print(f"  Amazon success:  {amazon_ok}/{len(df_output)}")
        print(f"  eBazaar success: {ebazaar_ok}/{len(df_output)}")
        print("=" * 60)
        
    except FileNotFoundError:
        print("✗ Error: 'price/input_links.csv' not found!")
    except Exception as e:
        print(f"✗ Error: {e}")
        raise


if __name__ == "__main__":
    main()
