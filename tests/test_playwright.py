import asyncio
from playwright.async_api import async_playwright

async def test_browser():
    print("[BOOT] Booting up Playwright Engine...")
    
    # Start the Playwright context manager
    async with async_playwright() as p:
        # Launch a Chromium browser. 
        # headless=False means we will actually see the browser pop up!
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        print("[NAVIGATE] Navigating to a test store...")
        # We will use a standard demo store for our first test
        await page.goto("https://www.saucedemo.com/")
        
        # Wait for 3 seconds so you can see it with your own eyes
        await asyncio.sleep(3)
        
        # Take a screenshot to prove we were there
        await page.screenshot(path="tests/proof_of_life.png")
        print("[SUCCESS] Screenshot saved to tests/proof_of_life.png!")
        
        await browser.close()
        print("[DONE] Test complete. Browser closed.")

if __name__ == "__main__":
    asyncio.run(test_browser())
