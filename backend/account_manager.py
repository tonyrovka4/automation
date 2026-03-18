from sqlalchemy import select, func
from backend.database import Account, AccountStatus, async_session
from datetime import datetime
from backend.config import settings

class AccountManager:
    
    async def get_available_account(self) -> Account | None:
        """Выбирает аккаунт с наименьшим числом использованных запросов."""
        async with async_session() as session:
            # Просто выбираем активный аккаунт с оставшимися запросами
            result = await session.execute(
                select(Account)
                .where(Account.status == AccountStatus.ACTIVE)
                .where(Account.requests_used < settings.REQUESTS_PER_ACCOUNT)
                .order_by(Account.requests_used.asc(), Account.last_used.asc())
                .limit(1)
            )
            return result.scalar_one_or_none()
    
    async def mark_used(self, account_id: int):
        async with async_session() as session:
            result = await session.execute(
                select(Account).where(Account.id == account_id)
            )
            acc = result.scalar_one()
            acc.requests_used += 1
            acc.total_requests += 1
            acc.last_used = datetime.utcnow()
            
            if acc.requests_used >= settings.REQUESTS_PER_ACCOUNT:
                acc.status = AccountStatus.EXHAUSTED
            
            await session.commit()
    
    async def get_stats(self) -> dict:
        async with async_session() as session:
            result = await session.execute(select(Account))
            accounts = result.scalars().all()
            
            active = [a for a in accounts if a.status == AccountStatus.ACTIVE]
            remaining = sum(settings.REQUESTS_PER_ACCOUNT - a.requests_used for a in active)
            
            return {
                "total_accounts": len(accounts),
                "active": len(active),
                "exhausted": sum(1 for a in accounts if a.status == AccountStatus.EXHAUSTED),
                "banned": sum(1 for a in accounts if a.status == AccountStatus.BANNED),
                "errors": sum(1 for a in accounts if a.status == AccountStatus.ERROR),
                "remaining_requests": remaining,
                "total_requests_made": sum(a.total_requests for a in accounts),
                "requests_per_account_limit": settings.REQUESTS_PER_ACCOUNT,
            }
    
    async def import_accounts(self, accounts_data: list[dict]):
        """Импортирует список {'email': '...', 'password': '...'} в БД."""
        async with async_session() as session:
            added = 0
            skipped = 0
            
            for data in accounts_data:
                existing = await session.execute(
                    select(Account).where(Account.email == data["email"])
                )
                if existing.scalar_one_or_none():
                    skipped += 1
                    continue
                
                account = Account(
                    email=data["email"],
                    email_password=data["password"],
                    status=AccountStatus.PENDING
                )
                session.add(account)
                added += 1
            
            await session.commit()
            return {"added": added, "skipped": skipped}


account_manager = AccountManager()
