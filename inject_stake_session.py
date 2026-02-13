import asyncio
import json
from playwright.async_api import async_playwright

COOKIE_STRING = """locale=en; fiat_number_format=en; sidebarView=hidden; quick_bet_popup=false; oddsFormat=decimal; level_up_vip_flag=; sportMarketGroupMap={}; cookie_last_vip_tab=progress; _ga=GA1.1.19512616.1770933193; g_state={"i_l":0,"i_ll":1770933193447,"i_b":"UB2N4yxZF0i2/eFxK4DT3sT4RUgl3Nswbl/9GioD0Tw","i_e":{"enable_itp_optimization":0}}; intercom-id-cx1ywgf2=bbe26e30-437c-4946-b422-a166cd42fe18; intercom-device-id-cx1ywgf2=ada56350-c21d-4508-959c-6ef8d731d6d5; session_info={"id":"ba384f42-7f90-4980-a52a-018ea5de75c7","sessionName":"Chrome (Linux PC)","ip":"185.67.177.112","country":"XK","city":"Pristina","active":true,"updatedAt":"Thu, 12 Feb 2026 21:53:45 GMT","__typename":"UserSession"}; currency_currency=usdt; cookie_consent=true; currency_currencyView=eur; currency_hideZeroBalances=false; leftSidebarView_v2=minimized; __cf_bm=hAKyUNY4R038krScB2QnsNJsIvmEiPajAI.zZ4A13fQ-1770973033-1.0.1.1-lwhdlnOQX.4QPaJdQGX3THau44LhWHBlO8UqtxY1QDqlmHwK2ULGk6Wt6uVu_SaiooS.92lTLO.6p9YHJNDpwLw_HUm2QghkFoYDJjY4034; _cfuvid=284ChbYMRfULid48YHo3unu8imjiTY8vH5Y9VLhAsNE-1770973033190-0.0.1.1-604800000; cf_clearance=xZO7_3K41N7D3xB7TPli4MYiEn9fD5VPKYypFVZqK2M-1770973033-1.2.1.1-z7cIcRaIfAwTipsH0bMcAiK1beRAI4Kat3f4xI32c43RakCj_DhUSw7FrN6mC8Laz9KqUNiBNcep9pMgXSAjuSJkt1LO4rCcBiEl1fdLGSqR8KyyV4Ekxk6m3fAJILTMbe9auGmiXMCTwwrp3RGlq1xi9YttpRbRFvdxVVIuYnfYbzcQfkIw7saRFbGTd7OAzvTvtc_OngQO9AOEIOfTwpCooLOtBbMTBdNmHbTiIyo; mp_e29e8d653fb046aa5a7d7b151ecf6f99_mixpanel=%7B%22distinct_id%22%3A%222fc68474-f22d-4ca9-9076-efdd888c98b4%22%2C%22%24device_id%22%3A%2215e13548-cba1-414d-8775-110c824ec1e9%22%2C%22%24initial_referrer%22%3A%22%24direct%22%2C%22%24initial_referring_domain%22%3A%22%24direct%22%2C%22__mps%22%3A%7B%7D%2C%22__mpso%22%3A%7B%7D%2C%22__mpus%22%3A%7B%7D%2C%22__mpa%22%3A%7B%7D%2C%22__mpu%22%3A%7B%7D%2C%22__mpr%22%3A%5B%5D%2C%22__mpap%22%3A%5B%5D%2C%22%24user_id%22%3A%222fc68474-f22d-4ca9-9076-efdd888c98b4%22%7D; intercom-session-cx1ywgf2=OThyb3N2SklDejFSbWNta3dNT0UzNVlZaFl2WkhSK3RiQVpQNHV2VCtzV3ozUWlSa2NYeENRbStPWHB3bE5BRFJwYzZONUlibjNXd1NQcXFmU1Y5N0ErdGgrT1dCb3NPTDNWa1VYNXo1STJ2SENIL1Jwa2x6R1p6bFkzWEtmV3ozZjVVOUNkR3FVTW4yNVB5NzBUR0x4SWdWVmo3MXV2Q1E4KzRWOTdEZWViUEJlRUh0RUF0K0pKSk90SjAzZlJrLS00aHQyNHBoamp2NmVLUktmTmxuV1JnPT0=--fe2601b2d1bb8b73f5b049df5c9f29763ee88086; _dd_s=rum=0&expire=1770973934443&logs=1&id=9761aabb-7807-4f84-b439-570c7a373c9d&created=1770973034443; _ga_TWGX3QNXGG=GS2.1.s1770968914$o2$g1$t1770973049$j45$l0$h1350914247; session=f40f51be0e7c945925afee2dcec32c06b93f98e529091d5bdd924669f5825b459532b32df5a3e9dac4705e6eea3047b2"""

async def inject():
    # Parse cookies
    cookies = []
    for item in COOKIE_STRING.split('; '):
        if '=' in item:
            name, value = item.split('=', 1)
            cookies.append({
                "name": name,
                "value": value,
                "domain": ".stake.com",
                "path": "/"
            })

    async with async_playwright() as p:
        try:
            print("Connecting to background Chrome...")
            browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            context = browser.contexts[0]
            
            print(f"Injecting {len(cookies)} cookies...")
            await context.add_cookies(cookies)
            
            # Also inject x-access-token into local storage just in case
            token = "f40f51be0e7c945925afee2dcec32c06b93f98e529091d5bdd924669f5825b459532b32df5a3e9dac4705e6eea3047b2"
            
            page = context.pages[0] if context.pages else await context.new_page()
            
            print("Navigating to Stake to apply changes...")
            await page.goto("https://stake.com", wait_until="domcontentloaded")
            
            # Inject token into local storage
            await page.evaluate(f"window.localStorage.setItem('x-access-token', '{token}')")
            
            print("Taking verification screenshot...")
            await asyncio.sleep(5)
            await page.goto("https://stake.com/settings/offers", wait_until="networkidle")
            await asyncio.sleep(2)
            await page.screenshot(path="stake_injected_verify.png")
            
            print("Done! Check stake_injected_verify.png")
            
        except Exception as e:
            print(f"Error during injection: {e}")

if __name__ == "__main__":
    asyncio.run(inject())
