import asyncio
import json
from playwright.async_api import async_playwright, Page, BrowserContext
from playwright_stealth import stealth
from backend.browser_utils import (
    get_random_user_agent,
    get_stealth_headers,
    get_random_proxy,
    human_delay,
    human_type,
    random_mouse_move
)
from backend.database import Account, AccountStatus, async_session
from backend.imap_reader import imap_reader
from backend.config import settings
from sqlalchemy import select


class AccountRegistrar:
    """Массовая регистрация аккаунтов через Playwright + IMAP."""
    
    async def _login_flow(self, page: Page, email_addr: str, email_pass: str) -> dict:
        """
        Выполняет полный флоу логина/регистрации.
        Возвращает cookies при успехе.
        """
        # 1. Открываем сервис
        await page.goto(settings.SERVICE_URL, wait_until="networkidle")
        await random_mouse_move(page)
        await human_delay(1500, 3000)
        
        # 2. Нажимаем "Start for free"
        start_btn = page.get_by_text("Start for free", exact=False)
        await random_mouse_move(page)
        await start_btn.click()
        await page.wait_for_load_state("networkidle")
        await human_delay(1000, 2000)
        
        # 3. Нажимаем "Login"
        login_btn = page.get_by_text("Login", exact=False)
        await random_mouse_move(page)
        await login_btn.click()
        await human_delay(1500, 2500)
        
        # 4. Вводим email
        # Адаптируй селектор под реальную форму
        email_input = page.locator("input[type='email'], input[placeholder*='email' i], input[name='email']").first
        await human_type(page, email_input, email_addr)
        
        # 5. Нажимаем кнопку отправки (Send code / Continue / Submit)
        submit_btn = page.locator(
            "button:has-text('Send'), button:has-text('Continue'), "
            "button:has-text('Submit'), button:has-text('Get code'), "
            "button[type='submit']"
        ).first
        await random_mouse_move(page)
        await submit_btn.click()
        
        print(f"[REG] Код отправлен на {email_addr}, ожидаю письмо...")
        
        # 6. Параллельно ждём код из IMAP
        code = await imap_reader.fetch_code_async(
            email_addr=email_addr,
            email_pass=email_pass,
            sender_filter="",  # Укажи домен отправителя для надёжности
            timeout=90
        )
        
        if not code:
            raise TimeoutError(f"Не получен код верификации для {email_addr}")
        
        print(f"[REG] Получен код: {code} для {email_addr}")
        
        # 7. Вводим код
        code_input = page.locator(
            "input[placeholder*='code' i], input[placeholder*='verif' i], "
            "input[type='text'], input[name='code']"
        ).first
        await human_type(page, code_input, code)
        
        # Если код вводится по цифрам (6 отдельных инпутов)
        code_inputs = page.locator("input.code-input, input[data-index]")
        count = await code_inputs.count()
        if count == 6:
            for i, digit in enumerate(code):
                await human_type(page, code_inputs.nth(i), digit)
        
        # 8. Нажимаем Verify / Confirm
        verify_btn = page.locator(
            "button:has-text('Verify'), button:has-text('Confirm'), "
            "button:has-text('Login'), button[type='submit']"
        ).first
        
        if await verify_btn.count() > 0:
            await random_mouse_move(page)
            await verify_btn.click()
        
        # 9. Ждём загрузки интерфейса чата
        await human_delay(4000, 6000)
        await page.wait_for_load_state("networkidle")
        
        print(f"[REG] ✅ Успешный вход для {email_addr}")
        
        return True
    
    async def register_single(self, email_addr: str, email_pass: str) -> bool:
        """Регистрирует/логинит один аккаунт и сохраняет сессию."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=settings.HEADLESS,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu'
                ]
            )
            
            context_options = {
                "user_agent": get_random_user_agent(),
                "viewport": {"width": 1280, "height": 720},
                "locale": "en-US",
                "extra_http_headers": get_stealth_headers()
            }
            proxy = get_random_proxy()
            if proxy:
                context_options["proxy"] = proxy
                
            context = await browser.new_context(**context_options)
            
            page = await context.new_page()
            await stealth(page)
            
            try:
                await self._login_flow(page, email_addr, email_pass)
                
                # Сохраняем cookies
                cookies = await context.cookies()
                cookies_json = json.dumps(cookies)
                
                # Обновляем в БД
                async with async_session() as session:
                    result = await session.execute(
                        select(Account).where(Account.email == email_addr)
                    )
                    account = result.scalar_one()
                    account.status = AccountStatus.ACTIVE
                    account.cookies_json = cookies_json
                    account.error_message = None
                    await session.commit()
                
                return True
            
            except Exception as e:
                print(f"[REG] ❌ Ошибка для {email_addr}: {e}")
                
                # Делаем скриншот для отладки
                try:
                    await page.screenshot(path=f"debug_error.png", full_page=True)
                    print(f"[REG] Скриншот ошибки сохранен как debug_error.png")
                except Exception as screenshot_error:
                    print(f"[REG] Не удалось сделать скриншот: {screenshot_error}")

                async with async_session() as session:
                    result = await session.execute(
                        select(Account).where(Account.email == email_addr)
                    )
                    account = result.scalar_one_or_none()
                    if account:
                        account.status = AccountStatus.ERROR
                        account.error_message = str(e)
                        await session.commit()
                
                return False
            
            finally:
                await browser.close()
    
    async def register_batch(
        self, 
        accounts: list[dict],   # [{"email": "...", "password": "..."}]
        concurrency: int = 2,   # Сколько браузеров одновременно
        delay: float = 5.0      # Пауза между стартами
    ):
        """Массовая регистрация с контролем параллельности."""
        semaphore = asyncio.Semaphore(concurrency)
        results = {"success": 0, "failed": 0, "total": len(accounts)}
        
        async def process_one(acc: dict, index: int):
            async with semaphore:
                # Задержка чтобы не спамить
                await asyncio.sleep(delay * index / concurrency)
                
                print(f"[BATCH] ({index+1}/{len(accounts)}) Регистрирую {acc['email']}...")
                success = await self.register_single(acc["email"], acc["password"])
                
                if success:
                    results["success"] += 1
                else:
                    results["failed"] += 1
                
                print(
                    f"[BATCH] Прогресс: ✅{results['success']} "
                    f"❌{results['failed']} / {results['total']}"
                )
        
        tasks = [process_one(acc, i) for i, acc in enumerate(accounts)]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        return results


registrar = AccountRegistrar()
