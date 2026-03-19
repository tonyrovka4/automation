import json
import asyncio
from playwright.async_api import async_playwright, Page
from playwright_stealth import stealth
from backend.browser_utils import (
    get_random_user_agent,
    get_stealth_headers,
    get_random_proxy,
    human_delay,
    human_type,
    random_mouse_move
)
from backend.database import Account, async_session, AccountStatus
from backend.imap_reader import imap_reader
from backend.config import settings
from sqlalchemy import select


class ChatWorker:
    """Отправляет сообщения через браузер от имени аккаунтов."""
    
    async def _restore_session(self, context, account: Account) -> Page:
        """Восстанавливает сессию через cookies."""
        page = await context.new_page()
        await stealth(page)
        
        if account.cookies_json:
            cookies = json.loads(account.cookies_json)
            await context.add_cookies(cookies)
        
        await page.goto(settings.SERVICE_URL, wait_until="networkidle")
        await random_mouse_move(page)
        await human_delay(1500, 3000)
        
        return page
    
    async def _is_logged_in(self, page: Page) -> bool:
        """Проверяет, залогинены ли мы."""
        # Адаптируй: ищем элемент, который виден только залогиненным
        chat_area = page.locator("textarea, div[contenteditable], .chat-input")
        return await chat_area.count() > 0
    
    async def _relogin(self, page: Page, context, account: Account) -> bool:
        """Перелогинивается если сессия протухла."""
        from backend.registrar import AccountRegistrar
        reg = AccountRegistrar()
        
        try:
            await reg._login_flow(page, account.email, account.email_password)
            
            # Обновляем cookies
            cookies = await context.cookies()
            async with async_session() as session:
                result = await session.execute(
                    select(Account).where(Account.id == account.id)
                )
                acc = result.scalar_one()
                acc.cookies_json = json.dumps(cookies)
                await session.commit()
            
            return True
        except Exception as e:
            print(f"[WORKER] Реlogин не удался для {account.email}: {e}")
            return False
    
    async def send_message(
        self,
        account: Account,
        message: str,
        model: str = "default"
    ) -> str:
        """Отправляет сообщение в чат сервиса и возвращает ответ."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=settings.HEADLESS)
            
            context_options = {
                "user_agent": get_random_user_agent(),
                "viewport": {"width": 1280, "height": 720},
                "extra_http_headers": get_stealth_headers()
            }
            proxy = get_random_proxy()
            if proxy:
                context_options["proxy"] = proxy

            context = await browser.new_context(**context_options)
            
            try:
                page = await self._restore_session(context, account)
                
                # Проверяем авторизацию
                if not await self._is_logged_in(page):
                    print(f"[WORKER] Сессия протухла для {account.email}, перелогин...")
                    success = await self._relogin(page, context, account)
                    if not success:
                        raise Exception("Не удалось перелогиниться")
                
                # Выбираем модель (если нужно)
                if model != "default":
                    model_selector = page.locator(
                        f"[data-model='{model}'], "
                        f"option:has-text('{model}'), "
                        f"button:has-text('{model}')"
                    ).first
                    if await model_selector.count() > 0:
                        await model_selector.click()
                        await page.wait_for_timeout(1000)
                
                # Вводим сообщение
                input_area = page.locator(
                    "textarea, div[contenteditable='true']"
                ).first
                await human_type(page, input_area, message)
                await random_mouse_move(page)
                await human_delay(500, 1500)
                
                # Отправляем
                send_btn = page.locator(
                    "button[type='submit'], "
                    "button:has-text('Send'), "
                    "button[aria-label*='send' i], "
                    "button svg[data-icon='send']"
                ).first
                
                # Если кнопка не найдена — Enter
                if await send_btn.count() > 0:
                    await send_btn.click()
                else:
                    await input_area.press("Enter")
                
                # Ждём ответ
                response = await self._wait_for_response(page)
                
                # Сохраняем обновлённые cookies
                cookies = await context.cookies()
                async with async_session() as session:
                    result = await session.execute(
                        select(Account).where(Account.id == account.id)
                    )
                    acc = result.scalar_one()
                    acc.cookies_json = json.dumps(cookies)
                    await session.commit()
                
                return response
            
            finally:
                await browser.close()
    
    async def _wait_for_response(self, page: Page, timeout: int = 120) -> str:
        """
        Ожидает завершения генерации ответа.
        Следит за тем, что текст перестал обновляться.
        """
        # Адаптируй селектор — это последнее сообщение от бота
        response_selector = (
            ".message:last-child .content, "
            ".bot-message:last-child, "
            ".assistant-message:last-child, "
            "[data-role='assistant']:last-child"
        )
        
        await page.wait_for_selector(response_selector, timeout=30000)
        
        # Ждём пока текст перестанет обновляться (генерация закончилась)
        previous_text = ""
        stable_count = 0
        
        for _ in range(timeout * 2):  # Проверяем каждые 0.5 сек
            await page.wait_for_timeout(500)
            
            current_text = await page.locator(response_selector).last.inner_text()
            
            if current_text == previous_text and len(current_text) > 0:
                stable_count += 1
                if stable_count >= 4:  # 2 секунды без изменений
                    return current_text.strip()
            else:
                stable_count = 0
            
            previous_text = current_text
        
        # Таймаут — возвращаем что есть
        return previous_text.strip() if previous_text else "⚠️ Таймаут ожидания ответа"


chat_worker = ChatWorker()
