import imaplib
import email
import re
import time
import asyncio
from email.header import decode_header
from backend.config import settings


class IMAPCodeReader:
    """Читает коды верификации из почтовых ящиков через IMAP."""
    
    def _connect(self, email_addr: str, email_pass: str) -> imaplib.IMAP4_SSL:
        """Создаёт IMAP соединение."""
        if settings.IMAP_USE_TLS:
            mail = imaplib.IMAP4_SSL(settings.IMAP_SERVER, settings.IMAP_PORT)
        else:
            mail = imaplib.IMAP4(settings.IMAP_SERVER, settings.IMAP_PORT)
        
        mail.login(email_addr, email_pass)
        return mail
    
    def _extract_code(self, msg) -> str | None:
        """Извлекает 6-значный код из письма."""
        # Проверяем тему
        subject = decode_header(msg["Subject"])[0]
        subject_text = subject[0]
        if isinstance(subject_text, bytes):
            subject_text = subject_text.decode(subject[1] or "utf-8")
        
        # Ищем код в теме: "Your verification code is 784028"
        code_match = re.search(r"verification code is (\d{6})", subject_text)
        if code_match:
            return code_match.group(1)
        
        # Если в теме нет — ищем в теле письма
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    break
        else:
            body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
        
        code_match = re.search(r"verification code is (\d{6})", body)
        if code_match:
            return code_match.group(1)
        
        return None
    
    def fetch_verification_code(
        self, 
        email_addr: str, 
        email_pass: str,
        sender_filter: str = "",  # Фильтр по отправителю
        timeout: int = 60,
        poll_interval: int = 3
    ) -> str | None:
        """
        Ждёт письмо с кодом верификации.
        Полит почту каждые poll_interval секунд, максимум timeout секунд.
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                mail = self._connect(email_addr, email_pass)
                mail.select("INBOX")
                
                # Ищем непрочитанные письма
                search_criteria = '(UNSEEN)'
                if sender_filter:
                    search_criteria = f'(UNSEEN FROM "{sender_filter}")'
                
                status, message_ids = mail.search(None, search_criteria)
                
                if status == "OK" and message_ids[0]:
                    ids = message_ids[0].split()
                    
                    # Берём последнее письмо (самое свежее)
                    for msg_id in reversed(ids):
                        status, msg_data = mail.fetch(msg_id, "(RFC822)")
                        if status != "OK":
                            continue
                        
                        msg = email.message_from_bytes(msg_data[0][1])
                        code = self._extract_code(msg)
                        
                        if code:
                            # Помечаем как прочитанное
                            mail.store(msg_id, "+FLAGS", "\\Seen")
                            mail.logout()
                            return code
                
                mail.logout()
                
            except Exception as e:
                print(f"[IMAP] Ошибка при чтении {email_addr}: {e}")
            
            time.sleep(poll_interval)
        
        return None  # Таймаут
    
    async def fetch_code_async(
        self,
        email_addr: str,
        email_pass: str,
        sender_filter: str = "",
        timeout: int = 60
    ) -> str | None:
        """Асинхронная обёртка (IMAP — синхронная библиотека)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.fetch_verification_code,
            email_addr, email_pass, sender_filter, timeout
        )


# Синглтон
imap_reader = IMAPCodeReader()
