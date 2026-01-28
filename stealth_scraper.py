import asyncio
import random
import os
import httpx
from dataclasses import dataclass, asdict
from datetime import datetime
import pandas as pd
from playwright.async_api import async_playwright
import nest_asyncio
nest_asyncio.apply()


@dataclass
class ProductComparison:
    model_name: str = ""
    amazon_method: str = ""
    amazon_ip_location: str = ""
    amazon_mrp: str = ""
    amazon_selling_price: str = ""
    ebazaar_mrp: str = ""
    ebazaar_selling_price: str = ""
    amazon_link: str = ""
    ebazaar_link: str = ""


class StealthScraper:
    def __init__(self, debug_mode: bool = False, us_only: bool = True):
        self.browser = None
        self.debug_mode = debug_mode
        self.us_only = us_only
        self.debug_dir = "debug_screenshots"
        self.local_ip_info = None
        self.local_country_code = None
        self.scraperapi_ip_cache = {}
        
        # Load API keys
        self.api_keys = []
        for i in range(1, 8):
            key = os.environ.get(f'SCRAPER_API_KEY_{i}', '')
            if key:
                self.api_keys.append(key)
        
        self.current_key_index = 0
        self.failed_keys = set()
        
        if self.debug_mode:
            os.makedirs(self.debug_dir, exist_ok=True)
        
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        ]
        
        self.viewports = [
            {"width": 1920, "height": 1080},
            {"width": 1366, "height": 768},
            {"width": 1536, "height": 864},
            {"width": 1440, "height": 900},
            {"width": 1280, "height": 720},
        ]

    def _get_stealth_scripts(self) -> list:
        """Return list of stealth JS patches to inject"""
        
        scripts = []
        
        # 1. Remove webdriver property
        scripts.append("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            delete navigator.__proto__.webdriver;
        """)
        
        # 2. Fix chrome object
        scripts.append("""
            window.chrome = {
                runtime: {
                    onConnect: null,
                    onMessage: null,
                    connect: function() {},
                    sendMessage: function() {},
                    onInstalled: { addListener: function() {} },
                    onStartup: { addListener: function() {} }
                },
                loadTimes: function() {
                    return {
                        requestTime: Date.now() * 0.001 - Math.random() * 100,
                        startLoadTime: Date.now() * 0.001 - Math.random() * 50,
                        commitLoadTime: Date.now() * 0.001 - Math.random() * 30,
                        finishDocumentLoadTime: Date.now() * 0.001 - Math.random() * 10,
                        finishLoadTime: Date.now() * 0.001,
                        firstPaintTime: Date.now() * 0.001 - Math.random() * 20,
                        firstPaintAfterLoadTime: 0,
                        navigationType: 'Other'
                    };
                },
                csi: function() {
                    return {
                        onloadT: Date.now(),
                        pageT: Date.now() * 0.001,
                        startE: Date.now(),
                        tran: 15
                    };
                },
                app: {
                    isInstalled: false,
                    InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
                    RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }
                }
            };
        """)
        
        # 3. Fix permissions API
        scripts.append("""
            if (navigator.permissions) {
                const originalQuery = navigator.permissions.query;
                navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            }
        """)
        
        # 4. Fix plugins array
        scripts.append("""
            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    const plugins = [
                        { name: 'Chrome PDF Plugin', description: 'Portable Document Format', filename: 'internal-pdf-viewer', length: 1 },
                        { name: 'Chrome PDF Viewer', description: '', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', length: 1 },
                        { name: 'Native Client', description: '', filename: 'internal-nacl-plugin', length: 2 }
                    ];
                    plugins.item = (index) => plugins[index] || null;
                    plugins.namedItem = (name) => plugins.find(p => p.name === name) || null;
                    plugins.refresh = () => {};
                    return plugins;
                }
            });
        """)
        
        # 5. Fix languages
        scripts.append("""
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
        """)
        
        # 6. Fix platform
        scripts.append("""
            Object.defineProperty(navigator, 'platform', {
                get: () => 'Win32'
            });
        """)
        
        # 7. Fix hardwareConcurrency
        scripts.append("""
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8
            });
        """)
        
        # 8. Fix deviceMemory
        scripts.append("""
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8
            });
        """)
        
        # 9. Fix WebGL vendor and renderer
        scripts.append("""
            const getParameterProxyHandler = {
                apply: function(target, ctx, args) {
                    const param = args[0];
                    if (param === 37445) return 'Google Inc. (NVIDIA)';
                    if (param === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1080 Direct3D11 vs_5_0 ps_5_0, D3D11)';
                    return Reflect.apply(target, ctx, args);
                }
            };
            
            try {
                const canvas = document.createElement('canvas');
                const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
                if (gl) {
                    const orig = gl.getParameter.bind(gl);
                    gl.__proto__.getParameter = new Proxy(orig, getParameterProxyHandler);
                }
            } catch(e) {}
        """)
        
        # 10. Fix connection info
        scripts.append("""
            Object.defineProperty(navigator, 'connection', {
                get: () => ({
                    effectiveType: '4g',
                    rtt: 50,
                    downlink: 10,
                    saveData: false
                })
            });
        """)
        
        # 11. Hide automation indicators
        scripts.append("""
            delete window.__playwright;
            delete window.__puppeteer_evaluation_script__;
            delete window.__selenium_evaluate;
            delete window.__webdriver_evaluate;
            delete window.__driver_evaluate;
            delete window.__webdriver_script_function;
            delete window.__fxdriver_evaluate;
            delete window._Selenium_IDE_Recorder;
            delete window._selenium;
            delete window.calledSelenium;
            delete document.__webdriver_script_fn;
            delete document.$cdc_asdjflasutopfhvcZLmcfl_;
        """)
        
        return scripts

    async def _human_delay(self, min_ms: int = 100, max_ms: int = 500):
        """Random delay with gaussian distribution"""
        mean = (min_ms + max_ms) / 2
        std = (max_ms - min_ms) / 4
        delay = max(min_ms, min(max_ms, random.gauss(mean, std)))
        await asyncio.sleep(delay / 1000)

    async def _human_mouse_move(self, page, x: int, y: int):
        """Move mouse in a human-like path"""
        try:
            steps = random.randint(10, 25)
            start_x, start_y = random.randint(0, 500), random.randint(0, 500)
            
            for i in range(steps + 1):
                t = i / steps
                curr_x = int(start_x + (x - start_x) * t + random.randint(-5, 5))
                curr_y = int(start_y + (y - start_y) * t + random.randint(-5, 5))
                await page.mouse.move(curr_x, curr_y)
                await asyncio.sleep(random.uniform(0.01, 0.03))
        except:
            pass

    async def _human_scroll(self, page):
        """Scroll page in a human-like manner"""
        try:
            for _ in range(random.randint(3, 8)):
                direction = random.choice([1, 1, 1, -1])
                amount = random.randint(100, 300) * direction
                await page.evaluate(f'window.scrollBy(0, {amount})')
                await asyncio.sleep(random.uniform(0.1, 0.3))
        except:
            pass

    async def _setup_browser(self, playwright):
        """Setup browser with stealth options"""
        self.browser = await playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-infobars',
                '--window-size=1920,1080',
                '--start-maximized',
                '--disable-extensions',
                '--no-first-run',
                '--no-default-browser-check',
            ]
        )
        print("  ✓ Stealth browser launched")

    async def _create_stealth_context(self):
        """Create a browser context with full stealth configuration"""
        
        viewport = random.choice(self.viewports)
        user_agent = random.choice(self.user_agents)
        
        context = await self.browser.new_context(
            viewport=viewport,
            user_agent=user_agent,
            locale='en-US',
            timezone_id='America/New_York',
            geolocation={'latitude': 40.7128, 'longitude': -74.0060},
            permissions=['geolocation'],
            color_scheme='light',
            device_scale_factor=1,
            is_mobile=False,
            has_touch=False,
            java_script_enabled=True,
            bypass_csp=True,
            ignore_https_errors=True,
            extra_http_headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Sec-Ch-Ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"Windows"',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Upgrade-Insecure-Requests': '1',
            }
        )
        
        return context

    async def _apply_stealth_to_page(self, page):
        """Apply all stealth patches to a page (NO EXTERNAL LIBRARY)"""
        
        # Apply custom stealth scripts
        stealth_scripts = self._get_stealth_scripts()
        
        for script in stealth_scripts:
            await page.add_init_script(script)
        
        print("  ✓ Stealth patches applied")
        return page

    async def _get_ip_location(self) -> str:
        """Get local IP and location info"""
        try:
            if self.local_ip_info:
                return self.local_ip_info
            
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get("http://ip-api.com/json/")
                if response.status_code == 200:
                    data = response.json()
                    ip = data.get('query', 'Unknown')
                    city = data.get('city', '')
                    region = data.get('regionName', '')
                    country = data.get('country', '')
                    self.local_country_code = data.get('countryCode', '')
                    
                    location = f"{city}, {region}, {country}" if region else f"{city}, {country}"
                    self.local_ip_info = f"{ip} ({location})"
                    return self.local_ip_info
        except Exception as e:
            print(f"  ⚠ IP lookup failed: {str(e)[:30]}")
        return "Unknown"

    async def _is_local_ip_us(self) -> bool:
        """Check if local IP is in the US"""
        await self._get_ip_location()
        return self.local_country_code == 'US'

    async def _get_scraperapi_ip(self, api_key: str, key_id: int) -> str:
        """Get ScraperAPI proxy location"""
        try:
            if key_id in self.scraperapi_ip_cache:
                return self.scraperapi_ip_cache[key_id]
            
            print(f"  → Fetching ScraperAPI proxy location...")
            api_url = f"http://api.scraperapi.com?api_key={api_key}&country_code=us&url=http://ip-api.com/json/"
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(api_url)
                if response.status_code == 200:
                    data = response.json()
                    ip = data.get('query', 'Unknown')
                    city = data.get('city', 'Unknown')
                    region = data.get('regionName', '')
                    country = data.get('country', 'Unknown')
                    
                    location = f"{city}, {region}, {country}" if region else f"{city}, {country}"
                    result = f"{ip} ({location})"
                    self.scraperapi_ip_cache[key_id] = result
                    print(f"  ✓ US Proxy location: {result}")
                    return result
        except Exception as e:
            print(f"  ⚠ Proxy IP lookup failed: {str(e)[:40]}")
        
        return "US Proxy (Unknown City)"

    def _get_next_api_key(self):
        """Round-robin through available API keys"""
        if not self.api_keys:
            return None
        
        attempts = 0
        while attempts < len(self.api_keys):
            key = self.api_keys[self.current_key_index]
            key_id = self.current_key_index + 1
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            
            if key_id in self.failed_keys:
                attempts += 1
                continue
            
            return key, key_id
        
        self.failed_keys.clear()
        key = self.api_keys[0]
        self.current_key_index = 1 % len(self.api_keys)
        return key, 1

    def _mark_key_failed(self, key_id: int):
        self.failed_keys.add(key_id)
        print(f"  ⚠ API Key #{key_id} marked as exhausted")

    def _is_valid_price(self, mrp: str, selling: str) -> bool:
        """Check if we got valid prices"""
        invalid = ['N/A', 'Error', 'CAPTCHA', 'Blocked', '', 'No API Key', None]
        return selling not in invalid and mrp not in invalid

    async def run(self, input_csv: str) -> pd.DataFrame:
        df_input = pd.read_csv(input_csv)
        products = []
        
        print(f"\n🔑 Loaded {len(self.api_keys)} API keys")
        print(f"🇺🇸 US-Only Mode: {'ENABLED' if self.us_only else 'DISABLED'}")
        print(f"🥷 Stealth Mode: ENABLED (custom implementation)")
        
        local_ip = await self._get_ip_location()
        is_us = await self._is_local_ip_us()
        print(f"🌐 Local IP: {local_ip}")
        print(f"   Local IP is US: {'Yes ✓' if is_us else 'No ✗'}")
        
        if self.us_only and not is_us:
            print(f"⚠ Local IP not in US - will use ScraperAPI for all Amazon requests")
        
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
                
                if pd.notna(row.get('amazon_link')) and str(row['amazon_link']).strip():
                    mrp, selling, method, ip_loc = await self._scrape_amazon(row['amazon_link'], idx)
                    product.amazon_mrp = mrp
                    product.amazon_selling_price = selling
                    product.amazon_method = method
                    product.amazon_ip_location = ip_loc
                
                await asyncio.sleep(random.uniform(1, 2))
                
                if pd.notna(row.get('ebazaar_link')) and str(row['ebazaar_link']).strip():
                    mrp, selling = await self._scrape_ebazaar(row['ebazaar_link'], idx)
                    product.ebazaar_mrp = mrp
                    product.ebazaar_selling_price = selling
                
                products.append(product)
                print(f"  ✓ Done: Method={product.amazon_method}, IP={product.amazon_ip_location}")
                print(f"         MRP(A)={product.amazon_mrp}, SP(A)={product.amazon_selling_price}, "
                      f"MRP(E)={product.ebazaar_mrp}, SP(E)={product.ebazaar_selling_price}")
                
                if idx < total - 1:
                    delay = random.uniform(5, 10)
                    print(f"  ⏳ Waiting {delay:.1f}s before next product...")
                    await asyncio.sleep(delay)
            
            await self.browser.close()
        
        return pd.DataFrame([asdict(p) for p in products])

    async def _scrape_amazon(self, url: str, idx: int) -> tuple:
        """Scrape Amazon with stealth Playwright"""
        
        is_local_us = await self._is_local_ip_us()
        
        if self.us_only and not is_local_us:
            print("  → Skipping local methods (non-US IP)")
            print("  → Method C: ScraperAPI (US proxy)...")
            mrp, selling, ip_loc = await self._scrape_amazon_api(url, idx)
            if self._is_valid_price(mrp, selling):
                return mrp, selling, "C", ip_loc
            return mrp, selling, "X", "N/A"
        
        print("  → Method B: Stealth Playwright...")
        mrp, selling = await self._scrape_amazon_stealth_playwright(url, idx)
        if self._is_valid_price(mrp, selling):
            ip_loc = await self._get_ip_location()
            print(f"  ✓ Stealth Playwright success!")
            return mrp, selling, "B", ip_loc
        
        print("  → Method C: ScraperAPI (fallback)...")
        mrp, selling, ip_loc = await self._scrape_amazon_api(url, idx)
        if self._is_valid_price(mrp, selling):
            return mrp, selling, "C", ip_loc
        
        return mrp, selling, "X", "N/A"

    async def _scrape_amazon_stealth_playwright(self, url: str, idx: int) -> tuple:
        """Scrape Amazon with full stealth measures"""
        context = None
        try:
            context = await self._create_stealth_context()
            page = await context.new_page()
            await self._apply_stealth_to_page(page)
            
            # Optional warm-up
            if random.random() < 0.3:
                print("  → Warming up session...")
                await page.goto('https://www.amazon.com', wait_until='domcontentloaded', timeout=30000)
                await self._human_delay(1000, 2000)
                await self._human_scroll(page)
            
            print(f"  → Navigating to product page...")
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            
            # Human-like behavior
            await self._human_delay(1500, 3000)
            await self._human_mouse_move(page, random.randint(400, 800), random.randint(200, 400))
            await self._human_scroll(page)
            await self._human_delay(500, 1500)
            
            html = await page.content()
            
            if self.debug_mode:
                await page.screenshot(path=f"{self.debug_dir}/amazon_stealth_{idx}.png", full_page=True)
            
            if 'captcha' in html.lower() or 'robot' in html.lower():
                print("  ⚠ Stealth Playwright: CAPTCHA detected")
                return "CAPTCHA", "CAPTCHA"
            
            return self._parse_amazon_prices(html)
            
        except Exception as e:
            print(f"  ⚠ Stealth Playwright failed: {str(e)[:50]}")
            return "N/A", "N/A"
        finally:
            if context:
                await context.close()

    async def _scrape_amazon_api(self, url: str, idx: int) -> tuple:
        """Scrape Amazon using ScraperAPI (fallback)"""
        
        if not self.api_keys:
            print("  ⚠ No API keys available")
            return "No API Key", "No API Key", "N/A"
        
        max_retries = min(3, len(self.api_keys))
        
        for attempt in range(max_retries):
            result = self._get_next_api_key()
            if result is None:
                return "No API Key", "No API Key", "N/A"
            
            api_key, key_id = result
            
            try:
                api_url = (
                    f"http://api.scraperapi.com?"
                    f"api_key={api_key}"
                    f"&country_code=us"
                    f"&url={url}"
                    f"&render=true"
                )
                print(f"  → Using API Key #{key_id} (US proxy)...")
                
                async with httpx.AsyncClient(timeout=90) as client:
                    response = await client.get(api_url)
                    
                    if response.status_code in [403, 429]:
                        print(f"  ⚠ API Key #{key_id} quota exceeded")
                        self._mark_key_failed(key_id)
                        continue
                    
                    if response.status_code != 200:
                        print(f"  ⚠ ScraperAPI returned {response.status_code}")
                        continue
                    
                    html = response.text
                    
                    if 'captcha' in html.lower():
                        print("  ⚠ CAPTCHA detected")
                        return "CAPTCHA", "CAPTCHA", "US Proxy (CAPTCHA)"
                    
                    mrp, selling = self._parse_amazon_prices(html)
                    ip_loc = await self._get_scraperapi_ip(api_key, key_id)
                    
                    print(f"  Amazon: MRP={mrp}, Selling={selling}")
                    return mrp, selling, ip_loc
                    
            except Exception as e:
                print(f"  ⚠ Attempt {attempt + 1} failed: {str(e)[:50]}")
                continue
        
        return "Error", "Error", "N/A"

    def _parse_amazon_prices(self, html: str) -> tuple:
        """Parse Amazon prices from HTML"""
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html, 'html.parser')
        
        selling_price = "N/A"
        mrp = "N/A"
        
        selling_selectors = [
            '.a-price:not([data-a-strike="true"]) .a-offscreen',
            '.priceToPay .a-offscreen',
            '#priceblock_ourprice',
            '#priceblock_dealprice',
            '.a-price .a-offscreen',
        ]
        
        for selector in selling_selectors:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(strip=True)
                if text and ('$' in text or '₹' in text):
                    parent = el.find_parent(attrs={'data-a-strike': 'true'})
                    if not parent:
                        parent = el.find_parent(class_='a-text-price')
                        if not parent:
                            selling_price = text
                            break
        
        mrp_selectors = [
            '.a-text-price .a-offscreen',
            '.basisPrice .a-offscreen',
            '[data-a-strike="true"] .a-offscreen',
            '#priceblock_listprice',
        ]
        
        for selector in mrp_selectors:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(strip=True)
                if text and ('$' in text or '₹' in text):
                    mrp = text
                    break
        
        if mrp == "N/A" and selling_price != "N/A":
            mrp = selling_price
        
        return mrp, selling_price

    async def _scrape_ebazaar(self, url: str, idx: int) -> tuple:
        """Scrape eBazaar using stealth Playwright"""
        context = None
        try:
            context = await self._create_stealth_context()
            page = await context.new_page()
            await self._apply_stealth_to_page(page)
            
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            await self._human_delay(2000, 4000)
            await self._human_scroll(page)
            
            data = await page.evaluate('''() => {
                let sellingPrice = '';
                let mrp = '';
                
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
                
                if (!sellingPrice || !mrp) {
                    const containers = document.querySelectorAll('.product-info-price, .price-box');
                    for (const container of containers) {
                        const prices = container.innerText.match(/\\$[\\d,]+\\.?\\d*/g);
                        if (prices && prices.length >= 2) {
                            const nums = prices.map(p => parseFloat(p.replace(/[$,]/g, '')));
                            if (!sellingPrice) sellingPrice = '$' + Math.min(...nums).toFixed(2);
                            if (!mrp) mrp = '$' + Math.max(...nums).toFixed(2);
                            break;
                        } else if (prices && prices.length === 1 && !sellingPrice) {
                            sellingPrice = prices[0];
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
            if context:
                await context.close()


async def test_stealth():
    """Test stealth effectiveness"""
    
    print("\n" + "=" * 60)
    print("🔬 STEALTH DETECTION TEST")
    print("=" * 60)
    
    scraper = StealthScraper(debug_mode=True)
    
    async with async_playwright() as p:
        await scraper._setup_browser(p)
        context = await scraper._create_stealth_context()
        page = await context.new_page()
        await scraper._apply_stealth_to_page(page)
        
        # Navigate to trigger init scripts
        await page.goto('about:blank')
        
        print("\n[Test 1] navigator.webdriver")
        webdriver = await page.evaluate('() => navigator.webdriver')
        print(f"  Result: {webdriver}")
        print(f"  {'✓ PASS' if webdriver in [None, False, 'undefined'] or webdriver is None else '✗ FAIL'}")
        
        print("\n[Test 2] window.chrome")
        chrome = await page.evaluate('() => !!window.chrome')
        print(f"  Result: {chrome}")
        print(f"  {'✓ PASS' if chrome else '✗ FAIL'}")
        
        print("\n[Test 3] navigator.plugins")
        plugins_len = await page.evaluate('() => navigator.plugins.length')
        print(f"  Result: {plugins_len} plugins")
        print(f"  {'✓ PASS' if plugins_len > 0 else '✗ FAIL'}")
        
        print("\n[Test 4] navigator.languages")
        languages = await page.evaluate('() => navigator.languages')
        print(f"  Result: {languages}")
        print(f"  {'✓ PASS' if languages and len(languages) > 0 else '✗ FAIL'}")
        
        print("\n[Test 5] Bot Detection Site")
        try:
            await page.goto('https://bot.sannysoft.com/', wait_until='networkidle', timeout=30000)
            await asyncio.sleep(3)
            await page.screenshot(path='debug_screenshots/bot_detection_test.png', full_page=True)
            print("  ✓ Screenshot saved: debug_screenshots/bot_detection_test.png")
        except Exception as e:
            print(f"  Error: {str(e)[:50]}")
        
        await context.close()
        await scraper.browser.close()
    
    print("\n" + "=" * 60)
    print("✓ Stealth test complete!")
    print("=" * 60)


def main():
    print("=" * 60)
    print("🥷 STEALTH Price Scraper Started")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    scraper = StealthScraper(debug_mode=True, us_only=True)
    
    try:
        df_output = asyncio.run(scraper.run('price/input_links.csv'))
        df_output.to_csv("price/data.csv", index=False)
        
        print("\n" + "=" * 60)
        print(f"✓ Saved {len(df_output)} products to price/data.csv")
        
        amazon_ok = len(df_output[~df_output['amazon_selling_price'].isin(['N/A', 'Error', 'CAPTCHA', 'Blocked', '', 'No API Key'])])
        ebazaar_ok = len(df_output[~df_output['ebazaar_selling_price'].isin(['N/A', 'Error', ''])])
        
        method_counts = df_output['amazon_method'].value_counts()
        print(f"\n  Method breakdown:")
        print(f"    B (Stealth PW): {method_counts.get('B', 0)}")
        print(f"    C (API/US):     {method_counts.get('C', 0)}")
        print(f"    X (Failed):     {method_counts.get('X', 0)}")
        
        print(f"\n  Amazon success:  {amazon_ok}/{len(df_output)}")
        print(f"  eBazaar success: {ebazaar_ok}/{len(df_output)}")
        print("=" * 60)
        
    except FileNotFoundError:
        print("✗ Error: 'price/input_links.csv' not found!")
    except Exception as e:
        print(f"✗ Error: {e}")
        raise


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        asyncio.run(test_stealth())
    else:
        main()
