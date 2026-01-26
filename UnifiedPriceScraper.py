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
        self.page = None
        self.debug_mode = debug_mode
        self.debug_dir = "debug_screenshots"
        
        if self.debug_mode:
            os.makedirs(self.debug_dir, exist_ok=True)

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
                
                # Scrape Amazon
                if pd.notna(row.get('amazon_link')) and str(row['amazon_link']).strip():
                    mrp, selling = await self._scrape_with_retry(
                        self._scrape_amazon, 
                        row['amazon_link'],
                        idx,
                        "amazon"
                    )
                    product.amazon_mrp = mrp
                    product.amazon_selling_price = selling
                
                await self._random_delay(2000, 3000)
                
                # Scrape eBazaar
                if pd.notna(row.get('ebazaar_link')) and str(row['ebazaar_link']).strip():
                    mrp, selling = await self._scrape_with_retry(
                        self._scrape_ebazaar, 
                        row['ebazaar_link'],
                        idx,
                        "ebazaar"
                    )
                    product.ebazaar_mrp = mrp
                    product.ebazaar_selling_price = selling
                
                products.append(product)
                print(f"  ✓ Done: MRP(A)={product.amazon_mrp}, SP(A)={product.amazon_selling_price}, "
                      f"MRP(E)={product.ebazaar_mrp}, SP(E)={product.ebazaar_selling_price}")
                
                if idx < total - 1:
                    await self._random_delay(3000, 5000)
            
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
                '--window-size=1920,1080',
                '--disable-extensions',
                '--disable-gpu'
            ]
        )
        
        context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale='en-US',
            timezone_id='America/New_York',
            java_script_enabled=True
        )
        
        # Remove automation detection
        await context.add_init_script('''
            // Remove webdriver flag
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            
            // Mock plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            // Mock languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            
            // Remove chrome automation flags
            window.chrome = { runtime: {} };
        ''')
        
        self.page = await context.new_page()
        
        # Block unnecessary resources to speed up loading
        await self.page.route("**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2}", lambda route: route.abort())

    async def _random_delay(self, min_ms: int, max_ms: int):
        await self.page.wait_for_timeout(random.randint(min_ms, max_ms))

    async def _scrape_with_retry(self, scrape_func, url: str, idx: int, source: str, retries: int = 3) -> tuple:
        for attempt in range(retries):
            try:
                result = await scrape_func(url)
                
                # Check if we got valid data
                if result[1] != "N/A" and result[1] != "Error":
                    return result
                
                if attempt < retries - 1:
                    print(f"  ⟳ {source.capitalize()} retry {attempt + 2}/{retries}...")
                    await self._random_delay(3000, 5000)
                    
                    # Refresh page on retry
                    await self.page.reload(wait_until="networkidle", timeout=30000)
                    await self._random_delay(2000, 3000)
                    
            except Exception as e:
                print(f"  ✗ {source.capitalize()} attempt {attempt + 1} failed: {str(e)[:50]}")
                if attempt < retries - 1:
                    await self._random_delay(3000, 5000)
        
        # Save debug info on final failure
        if self.debug_mode and (result[0] == "Error" or result[1] == "N/A"):
            await self._save_debug(idx, source)
        
        return result

    async def _save_debug(self, idx: int, source: str):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            await self.page.screenshot(path=f"{self.debug_dir}/{source}_{idx}_{timestamp}.png", full_page=True)
            html = await self.page.content()
            with open(f"{self.debug_dir}/{source}_{idx}_{timestamp}.html", "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  📸 Debug saved for {source} #{idx}")
        except Exception as e:
            print(f"  Failed to save debug: {e}")

    async def _scrape_amazon(self, url: str) -> tuple:
        try:
            # Navigate with longer timeout
            response = await self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Check for blocked/captcha
            if response and response.status >= 400:
                print(f"  ⚠ Amazon returned status {response.status}")
                return "Blocked", "Blocked"
            
            # Wait for page to stabilize
            await self._random_delay(2000, 3000)
            
            # Try to wait for price elements
            try:
                await self.page.wait_for_selector(
                    '.a-price, #priceblock_ourprice, #priceblock_dealprice, '
                    '#corePrice_feature_div, .a-price-whole, #apex_desktop',
                    timeout=10000
                )
            except:
                print("  ⚠ Price selector timeout, continuing anyway...")
            
            await self._random_delay(1000, 2000)
            
            # Scroll to trigger lazy loading
            await self.page.evaluate('window.scrollBy(0, 500)')
            await self._random_delay(500, 1000)
            
            data = await self.page.evaluate('''() => {
                let sellingPrice = '';
                let mrp = '';
                
                // ============ SELLING PRICE SELECTORS ============
                const sellingSelectors = [
                    // Core price display (most common)
                    '#corePrice_feature_div .a-price:not([data-a-strike="true"]) .a-offscreen',
                    '.priceToPay .a-offscreen',
                    '#apex_offerDisplay_desktop .a-offscreen',
                    
                    // Standard price selectors
                    '.a-price:not(.a-text-price) .a-offscreen',
                    '#priceblock_ourprice',
                    '#priceblock_dealprice',
                    '#priceblock_saleprice',
                    
                    // Deal prices
                    '.apexPriceToPay .a-offscreen',
                    '#corePrice_desktop .a-offscreen',
                    '.reinventPricePriceToPayMargin .a-offscreen',
                    
                    // Fallback selectors
                    '.a-price-whole',
                    'span[data-a-color="price"] .a-offscreen',
                    '.a-color-price'
                ];
                
                for (const selector of sellingSelectors) {
                    const elements = document.querySelectorAll(selector);
                    for (const el of elements) {
                        const text = el.textContent?.trim();
                        if (text && (text.includes('$') || text.includes('₹') || text.includes('£') || text.includes('€'))) {
                            // Avoid MRP values (usually crossed out)
                            const parent = el.closest('.a-text-price, [data-a-strike="true"]');
                            if (!parent) {
                                sellingPrice = text;
                                break;
                            }
                        }
                    }
                    if (sellingPrice) break;
                }
                
                // ============ MRP SELECTORS ============
                const mrpSelectors = [
                    // Crossed out prices
                    '.a-text-price:not(.apexPriceToPay) .a-offscreen',
                    '.basisPrice .a-offscreen',
                    '[data-a-strike="true"] .a-offscreen',
                    
                    // List price
                    '#priceblock_listprice',
                    '#listPrice',
                    '.a-text-strike',
                    
                    // Other MRP indicators
                    '.priceBlockStrikePriceString',
                    'span[data-a-strike="true"]',
                    '.a-price[data-a-strike="true"] .a-offscreen'
                ];
                
                for (const selector of mrpSelectors) {
                    const elements = document.querySelectorAll(selector);
                    for (const el of elements) {
                        const text = el.textContent?.trim();
                        if (text && (text.includes('$') || text.includes('₹') || text.includes('£') || text.includes('€'))) {
                            mrp = text;
                            break;
                        }
                    }
                    if (mrp) break;
                }
                
                // If no MRP found, it might be same as selling price (no discount)
                if (!mrp && sellingPrice) {
                    mrp = sellingPrice;
                }
                
                return { mrp, sellingPrice };
            }''')
            
            mrp = data.get('mrp', '').strip() or "N/A"
            selling = data.get('sellingPrice', '').strip() or "N/A"
            
            print(f"  Amazon: MRP={mrp}, Selling={selling}")
            return mrp, selling
            
        except Exception as e:
            print(f"  ✗ Amazon error: {str(e)[:80]}")
            return "Error", "Error"

    async def _scrape_ebazaar(self, url: str) -> tuple:
        try:
            response = await self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            if response and response.status >= 400:
                print(f"  ⚠ eBazaar returned status {response.status}")
                return "Blocked", "Blocked"
            
            await self._random_delay(2000, 3000)
            
            # Wait for price container
            try:
                await self.page.wait_for_selector(
                    '.product-info-price, .price-box, .product-info-main, .price',
                    timeout=10000
                )
            except:
                print("  ⚠ eBazaar price selector timeout...")
            
            await self._random_delay(1000, 2000)
            
            data = await self.page.evaluate('''() => {
                let sellingPrice = '';
                let mrp = '';
                
                // ============ TRY DATA ATTRIBUTES FIRST ============
                const finalPriceEl = document.querySelector('[data-price-type="finalPrice"]');
                if (finalPriceEl) {
                    const amount = finalPriceEl.getAttribute('data-price-amount');
                    if (amount) {
                        sellingPrice = '$' + parseFloat(amount).toFixed(2);
                    }
                }
                
                const oldPriceEl = document.querySelector('[data-price-type="oldPrice"]');
                if (oldPriceEl) {
                    const amount = oldPriceEl.getAttribute('data-price-amount');
                    if (amount) {
                        mrp = '$' + parseFloat(amount).toFixed(2);
                    }
                }
                
                // ============ FALLBACK: TEXT PARSING ============
                if (!sellingPrice || !mrp) {
                    const priceContainers = document.querySelectorAll(
                        '.product-info-price, .price-box, .product-info-main, .price-wrapper'
                    );
                    
                    for (const container of priceContainers) {
                        const text = container.innerText;
                        const priceMatches = text.match(/\\$[\\d,]+\\.?\\d*/g);
                        
                        if (priceMatches && priceMatches.length >= 2) {
                            // Usually: first is selling, second is MRP (crossed out)
                            const prices = priceMatches.map(p => parseFloat(p.replace(/[$,]/g, '')));
                            const minPrice = Math.min(...prices);
                            const maxPrice = Math.max(...prices);
                            
                            if (!sellingPrice) sellingPrice = '$' + minPrice.toFixed(2);
                            if (!mrp) mrp = '$' + maxPrice.toFixed(2);
                            break;
                        } else if (priceMatches && priceMatches.length === 1) {
                            if (!sellingPrice) sellingPrice = priceMatches[0];
                        }
                    }
                }
                
                // ============ MORE SPECIFIC SELECTORS ============
                if (!sellingPrice) {
                    const selectors = [
                        '.price-wrapper .price',
                        '.special-price .price',
                        '.final-price .price',
                        '.price'
                    ];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.textContent.includes('$')) {
                            sellingPrice = el.textContent.trim();
                            break;
                        }
                    }
                }
                
                if (!mrp) {
                    const selectors = [
                        '.old-price .price',
                        '.regular-price .price',
                        'del .price',
                        '.was-price'
                    ];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.textContent.includes('$')) {
                            mrp = el.textContent.trim();
                            break;
                        }
                    }
                }
                
                // If no MRP, assume same as selling (no discount)
                if (!mrp && sellingPrice) {
                    mrp = sellingPrice;
                }
                
                return { mrp, sellingPrice };
            }''')
            
            mrp = data.get('mrp', '').strip() or "N/A"
            selling = data.get('sellingPrice', '').strip() or "N/A"
            
            print(f"  eBazaar: MRP={mrp}, Selling={selling}")
            return mrp, selling
            
        except Exception as e:
            print(f"  ✗ eBazaar error: {str(e)[:80]}")
            return "Error", "Error"


def main():
    print("=" * 50)
    print("Price Scraper Started")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    # Set debug_mode=True to save screenshots on failures
    scraper = UnifiedScraper(debug_mode=False)
    
    try:
        df_output = asyncio.run(scraper.run('price/input_links.csv'))
        
        # Save output
        df_output.to_csv("price/data.csv", index=False)
        
        print("\n" + "=" * 50)
        print(f"✓ Done! Saved {len(df_output)} products to price/data.csv")
        
        # Summary statistics
        amazon_success = len(df_output[df_output['amazon_selling_price'].notna() & 
                                        (df_output['amazon_selling_price'] != 'N/A') & 
                                        (df_output['amazon_selling_price'] != 'Error')])
        ebazaar_success = len(df_output[df_output['ebazaar_selling_price'].notna() & 
                                         (df_output['ebazaar_selling_price'] != 'N/A') & 
                                         (df_output['ebazaar_selling_price'] != 'Error')])
        
        print(f"  Amazon success: {amazon_success}/{len(df_output)}")
        print(f"  eBazaar success: {ebazaar_success}/{len(df_output)}")
        print("=" * 50)
        
    except FileNotFoundError:
        print("✗ Error: Input file 'price/input_links.csv' not found!")
    except Exception as e:
        print(f"✗ Error: {e}")
        raise


if __name__ == "__main__":
    main()
