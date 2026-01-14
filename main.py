from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.models import Base
from app.utils import engine, SessionLocal
from app.routers import auth, dashboard
from app.init_db import init_sample_data, sync_google_sheet

# Настройка приложения FastAPI
app = FastAPI(title="Система учёта посещаемости студентов", version="1.0.0")

# Подключение статических файлов и шаблонов
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Подключаем маршруты
app.include_router(auth.router)
app.include_router(dashboard.router)

# Инициализация базы данных при запуске
@app.on_event("startup")
def startup_event():
    Base.metadata.create_all(bind=engine)
    sync_google_sheet()
    # Создаем сессию и вызываем инициализацию начальных данных
    db = SessionLocal()
    try:
        init_sample_data(db)
    finally:
        db.close()