from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import time

from backend.database import init_db, RequestLog, async_session
from backend.account_manager import account_manager
from backend.browser_worker import chat_worker
from backend.registrar import registrar
from backend.config import settings

app = FastAPI(title="Chat Pool Proxy")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

request_semaphore = asyncio.Semaphore(2)


# ─── Модели запросов ───

class ChatRequest(BaseModel):
    message: str
    model: str = "default"

class ImportRequest(BaseModel):
    accounts: list[dict]  # [{"email": "...", "password": "..."}]

class RegisterRequest(BaseModel):
    concurrency: int = 2
    delay: float = 5.0


# ─── Эндпоинты ───

@app.on_event("startup")
async def startup():
    await init_db()


@app.post("/chat")
async def chat(req: ChatRequest):
    """Отправить сообщение через пул аккаунтов."""
    account = await account_manager.get_available_account()
    
    if not account:
        raise HTTPException(
            429, 
            "Все аккаунты исчерпали лимит запросов. "
            "Добавьте и зарегистрируйте новые аккаунты."
        )
    
    async with request_semaphore:
        start = time.time()
        log = RequestLog(account_id=account.id, user_message=req.message)
        
        try:
            response = await chat_worker.send_message(
                account=account,
                message=req.message,
                model=req.model
            )
            
            await account_manager.mark_used(account.id)
            
            log.bot_response = response
            log.success = True
            log.duration_sec = time.time() - start
            
            async with async_session() as session:
                session.add(log)
                await session.commit()
            
            return {
                "reply": response,
                "duration": round(time.time() - start, 2),
                "account": account.email[:3] + "***"
            }
        
        except Exception as e:
            log.error_message = str(e)
            log.success = False
            
            async with async_session() as session:
                session.add(log)
                await session.commit()
            
            raise HTTPException(500, f"Ошибка: {str(e)}")


@app.get("/status")
async def status():
    """Статус пула аккаунтов."""
    return await account_manager.get_stats()


@app.post("/accounts/import")
async def import_accounts(req: ImportRequest):
    """Импортировать аккаунты из списка email:password."""
    result = await account_manager.import_accounts(req.accounts)
    return result


@app.post("/accounts/register-all")
async def register_all(req: RegisterRequest):
    """Зарегистрировать все PENDING аккаунты."""
    from backend.database import Account, AccountStatus
    from sqlalchemy import select
    
    async with async_session() as session:
        result = await session.execute(
            select(Account).where(Account.status == AccountStatus.PENDING)
        )
        pending = result.scalars().all()
    
    if not pending:
        return {"message": "Нет аккаунтов для регистрации"}
    
    accounts_data = [{"email": a.email, "password": a.email_password} for a in pending]
    
    # Запускаем в фоне
    asyncio.create_task(
        registrar.register_batch(accounts_data, req.concurrency, req.delay)
    )
    
    return {"message": f"Запущена регистрация {len(accounts_data)} аккаунтов"}


@app.get("/accounts")
async def list_accounts():
    """Список всех аккаунтов."""
    from backend.database import Account
    from sqlalchemy import select
    
    async with async_session() as session:
        result = await session.execute(select(Account))
        accounts = result.scalars().all()
    
    return [
        {
            "id": a.id,
            "email": a.email[:3] + "***" + a.email[a.email.index("@"):],
            "status": a.status.value,
            "requests_used": a.requests_used,
            "requests_remaining": settings.REQUESTS_PER_ACCOUNT - a.requests_used,
            "total_requests": a.total_requests,
            "error": a.error_message
        }
        for a in accounts
    ]


# Статика для фронтенда
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
