from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, DateTime, Text, Enum as SAEnum
from datetime import datetime
import enum

from backend.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class AccountStatus(enum.Enum):
    PENDING = "pending"          # Ещё не зарегистрирован
    ACTIVE = "active"            # Рабочий
    EXHAUSTED = "exhausted"      # Лимит исчерпан навсегда
    BANNED = "banned"            # Забанен
    ERROR = "error"              # Ошибка при регистрации


class Account(Base):
    __tablename__ = "accounts"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email_password: Mapped[str] = mapped_column(String(255))
    status: Mapped[AccountStatus] = mapped_column(
        SAEnum(AccountStatus), default=AccountStatus.PENDING
    )
    requests_used: Mapped[int] = mapped_column(Integer, default=0)
    total_requests: Mapped[int] = mapped_column(Integer, default=0)
    last_used: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cookies_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # Куки в JSON
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RequestLog(Base):
    __tablename__ = "request_logs"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(Integer, index=True)
    user_message: Mapped[str] = mapped_column(Text)
    bot_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    duration_sec: Mapped[float | None] = mapped_column(nullable=True)
    success: Mapped[bool] = mapped_column(default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
