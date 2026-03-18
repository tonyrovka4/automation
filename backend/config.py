from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # PostgreSQL
    DATABASE_URL: str = "postgresql+asyncpg://chatpool:chatpool_secret@localhost:5432/chatpool"
    
    # IMAP (для чтения кодов)
    IMAP_SERVER: str = "imap.example.com"
    IMAP_PORT: int = 993
    IMAP_USE_TLS: bool = True
    
    # Сервис
    SERVICE_URL: str = "https://the-service.com"
    REQUESTS_PER_ACCOUNT: int = 3
    
    # Playwright
    HEADLESS: bool = True
    MAX_CONCURRENT_BROWSERS: int = 3
    BROWSER_TIMEOUT: int = 60000
    
    # Пути
    SESSIONS_DIR: str = "./sessions"
    
    class Config:
        env_file = ".env"

settings = Settings()
