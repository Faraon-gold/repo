from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from passlib.context import CryptContext
import jwt
from datetime import datetime, timedelta
import os
from .models import Base

# Настройка безопасности
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = "your-secret-key-change-in-production"
ALGORITHM = "HS256"

# Конфигурация базы данных
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./attendance.db")
if DATABASE_URL.startswith("postgres"):
    engine = create_engine(DATABASE_URL)
else:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Утилиты для работы с базой данных
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Функции для хэширования и проверки паролей
def verify_password(plain_password, hashed_password):
    # Обрезаем пароль до 72 байт, если он длиннее
    if len(plain_password.encode('utf-8')) > 72:
        plain_password = plain_password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except ValueError:
        # Обрабатываем ошибку bcrypt, если пароль все равно слишком длинный
        return False

def get_password_hash(password):
    # Обрезаем пароль до 72 байт, если он длиннее
    if len(password.encode('utf-8')) > 72:
        password = password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
    return pwd_context.hash(password)

# Создание и получение токенов JWT
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=30)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.JWTError:
        return None

# Проверка прав доступа
def check_permission(user, required_role) -> bool:
    """Проверяет, имеет ли пользователь достаточные права"""
    role_hierarchy = {
        "student": 1,
        "monitor": 2,
        "teacher": 3,
        "dean": 4,
        "admin": 5
    }
    
    return role_hierarchy.get(user.role.value, 0) >= role_hierarchy.get(required_role.value, 0)