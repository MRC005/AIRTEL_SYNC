"""Capture prototype screens for the deck. Needs the app running on http://localhost:8000.

python3 deck/capture.py            # guided mode, or Gemini mode if the key is set
"""
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path(__file__).parent / "shots"
OUT.mkdir(exist_ok=True)
URL = "http://localhost:8000"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome")
        phone = await browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        page = await phone.new_page()
        await page.goto(URL)
        await page.wait_for_selector(".bubble.bot")
        gemini = "Gemini" in (await page.inner_text("#mode") or "")
        answers = (["नमस्ते, मेरा डेंटल क्लिनिक है पुणे में", "12 लोग काम करते हैं, एक ही क्लिनिक है",
                    "हाँ, GST है", "इंटरनेट, स्टाफ के लिए ईमेल, और इंटरनेट बंद हो तो बैकअप चाहिए"]
                   if gemini else ["Dental clinic", "11-25", "1", "Pune", "Yes",
                                   "Internet, Business email, Backup if internet fails, Staff phone lines"])
        for a in answers:
            if await page.is_visible("#quote"):
                break
            await page.fill("#msg", a)
            await page.press("#msg", "Enter")
            await page.wait_for_function("!document.querySelector('.bubble.typing')", timeout=60000)
            await page.wait_for_timeout(400)
        await page.screenshot(path=OUT / "1_advisor.png")
        await page.wait_for_selector("#quote:not([hidden])", timeout=60000)
        await page.wait_for_timeout(1200)
        await page.screenshot(path=OUT / "2_quote.png")
        await page.click("#toKyc")
        await page.wait_for_selector("#notice dt")
        await page.screenshot(path=OUT / "3_consent.png")
        await page.check("#agree")
        await page.click("#giveConsent")
        await page.select_option("#sample", "K07")
        await page.click("#verify")
        await page.wait_for_selector(".decision", timeout=60000)
        await page.evaluate("document.querySelector('#kycResult').scrollIntoView()")
        await page.screenshot(path=OUT / "4_kyc.png")
        await page.click("#placeOrder")
        await page.wait_for_selector("#track:not([hidden])")
        await page.click("#advance")
        await page.wait_for_timeout(400)
        await page.click("#advance")
        await page.wait_for_timeout(600)
        await page.screenshot(path=OUT / "5_tracker.png")

        desk = await browser.new_context(viewport={"width": 1180, "height": 760}, device_scale_factor=2)
        bo = await desk.new_page()
        await bo.goto(URL)
        await bo.click("#toBackoffice")
        await bo.wait_for_selector("#callList tbody tr")
        await bo.screenshot(path=OUT / "6_backoffice.png")
        await browser.close()
        print("captured", "gemini" if gemini else "guided", sorted(x.name for x in OUT.glob("*.png")))


asyncio.run(main())
