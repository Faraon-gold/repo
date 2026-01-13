from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import Response
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from datetime import datetime, date, timedelta
import enum
import jwt
from typing import Optional, List
from pydantic import BaseModel
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dateutil import parser
import os
from backend.app.models import Base, User, Group, Subject, Schedule, Attendance, TeacherGroup, UserRole
from backend.app.database import engine, SessionLocal

# Настройка приложения FastAPI
app = FastAPI(title="Система учёта посещаемости студентов", version="1.0.0")

# Подключение статических файлов и шаблонов
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Настройка безопасности
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = "your-secret-key-change-in-production"
ALGORITHM = "HS256"

# Определение перечислимого типа для статуса посещения
class AttendanceStatus(str, enum.Enum):
    present = "present"
    absent = "absent"
    late = "late"

# Pydantic-схемы для валидации данных
class UserCreate(BaseModel):
    full_name: str
    login: str
    password: str
    role: UserRole
    group_id: Optional[int] = None
    is_headman: Optional[bool] = False

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    login: Optional[str] = None
    password: Optional[str] = None
    role: Optional[UserRole] = None
    group_id: Optional[int] = None
    is_headman: Optional[bool] = None

class LoginRequest(BaseModel):
    login: str
    password: str

class AttendanceUpdate(BaseModel):
    status: AttendanceStatus

# Утилиты для работы с базой данных
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Функции для хэширования и проверки паролей
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    # Truncate password to 72 bytes to comply with bcrypt limitations
    truncated_password = password[:72] if len(password) > 72 else password
    return pwd_context.hash(truncated_password)

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

# Получение текущего пользователя из токена
async def get_current_user(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token:
        return None
    
    payload = decode_access_token(token)
    if not payload or "user_id" not in payload:
        return None
    
    user_id = payload["user_id"]
    user = db.query(User).filter(User.id == user_id).first()
    return user

# Проверка прав доступа
def check_permission(user: User, required_role: UserRole) -> bool:
    """Проверяет, имеет ли пользователь достаточные права"""
    role_hierarchy = {
        "student": 1,
        "teacher": 3,
        "dean": 4,
        "admin": 5
    }
    
    # Староста имеет права выше обычного студента
    if user.role.value == "student" and user.is_headman:
        return True  # Староста может выполнять действия студента
    
    return role_hierarchy.get(user.role.value, 0) >= role_hierarchy.get(required_role.value, 0)

# Синхронизация с Google Таблицами
def sync_google_sheet():
    """Синхронизирует расписание из Google Таблицы"""
    try:
        # Настройка доступа к Google Таблице
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_file = os.getenv('GOOGLE_SHEETS_CREDENTIALS_FILE', 'credentials.json')
        
        if not os.path.exists(creds_file):
            print("Файл учетных данных Google не найден. Пропускаем синхронизацию.")
            return
        
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)
        client = gspread.authorize(creds)
        
        # Открытие таблицы
        sheet_url = "https://docs.google.com/spreadsheets/d/1nJ7-eGB-gYJNgm5CTqodenKnUSQlhMeFs2gVLuyxEsM/edit?gid=1653075363#gid=1653075363"
        sheet = client.open_by_url(sheet_url).sheet1
        
        # Получение данных
        records = sheet.get_all_records()
        
        db = SessionLocal()
        try:
            # Очистка существующих записей (по желанию)
            # db.query(Schedule).delete()
            
            # Обработка данных из таблицы
            for record in records:
                # Преобразование даты
                class_date = parser.parse(record.get('date', '')).date()
                
                # Поиск или создание группы
                group_name = record.get('group', '')
                group = db.query(Group).filter(Group.name == group_name).first()
                if not group:
                    group = Group(name=group_name)
                    db.add(group)
                    db.commit()
                    db.refresh(group)
                
                # Поиск или создание предмета
                subject_name = record.get('subject', '')
                subject = db.query(Subject).filter(Subject.name == subject_name).first()
                if not subject:
                    subject = Subject(name=subject_name)
                    db.add(subject)
                    db.commit()
                    db.refresh(subject)
                
                # Поиск или создание преподавателя
                teacher_login = record.get('teacher_login', '')
                teacher = None
                if teacher_login:
                    teacher = db.query(User).filter(
                        User.login == teacher_login,
                        User.role == UserRole.teacher
                    ).first()
                
                # Создание записи расписания
                schedule_entry = Schedule(
                    date=class_date,
                    start_time=parser.parse(record.get('start_time', '00:00')).time(),
                    end_time=parser.parse(record.get('end_time', '00:00')).time(),
                    subject_id=subject.id,
                    group_id=group.id,
                    teacher_id=teacher.id if teacher else None
                )
                
                existing_schedule = db.query(Schedule).filter(
                    Schedule.date == schedule_entry.date,
                    Schedule.start_time == schedule_entry.start_time,
                    Schedule.subject_id == schedule_entry.subject_id,
                    Schedule.group_id == schedule_entry.group_id
                ).first()
                
                if not existing_schedule:
                    db.add(schedule_entry)
            
            db.commit()
            print("Синхронизация с Google Таблицей завершена успешно.")
        except Exception as e:
            print(f"Ошибка при синхронизации с Google Таблицей: {e}")
            db.rollback()
        finally:
            db.close()
    except Exception as e:
        print(f"Ошибка при доступе к Google Таблице: {e}")

def create_admin_user_if_not_exists(db: Session):
    """Создает администратора, если он не существует"""
    admin_user = db.query(User).filter(User.login == "admin").first()
    if not admin_user:
        admin_user = User(
            full_name="Администратор системы",
            login="admin",
            password_hash=get_password_hash("admin123"),
            role=UserRole.admin
        )
        db.add(admin_user)
        db.commit()
        print("Создан пользователь-администратор: login='admin', password='admin123'")
    else:
        print("Пользователь-администратор уже существует")

# Инициализация базы данных при запуске
@app.on_event("startup")
def startup_event():
    Base.metadata.create_all(bind=engine)
    sync_google_sheet()
    
    # Создание администратора при запуске
    db = SessionLocal()
    try:
        create_admin_user_if_not_exists(db)
    finally:
        db.close()

# Маршрут главной страницы (форма входа)
@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

# Маршрут аутентификации
@app.post("/login")
async def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.login == login_data.login).first()
    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    
    token = create_access_token(data={"user_id": user.id})
    response = RedirectResponse(url=f"/dashboard/{user.role.value}", status_code=302)
    response.set_cookie(key="access_token", value=token, httponly=True)
    return response

# Маршрут выхода
@app.post("/logout")
async def logout(response: Response):
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("access_token")
    return response

# Маршруты для администратора
@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user or current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    users = db.query(User).all()
    groups = db.query(Group).all()
    return templates.TemplateResponse("admin_users.html", {
        "request": request,
        "current_user": current_user,
        "users": users,
        "groups": groups
    })

@app.post("/admin/users/create")
async def create_user(user_data: UserCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user or current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    # Проверяем, существует ли пользователь с таким логином
    existing_user = db.query(User).filter(User.login == user_data.login).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Пользователь с таким логином уже существует")
    
    # Создаем нового пользователя
    new_user = User(
        full_name=user_data.full_name,
        login=user_data.login,
        password_hash=get_password_hash(user_data.password),
        role=user_data.role,
        group_id=user_data.group_id,
        is_headman=user_data.is_headman
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {"success": True, "message": "Пользователь успешно создан"}

@app.put("/admin/users/{user_id}")
async def update_user(user_id: int, user_data: UserUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user or current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Обновляем данные пользователя
    if user_data.full_name is not None:
        user.full_name = user_data.full_name
    if user_data.login is not None:
        # Проверяем, не занят ли новый логин другим пользователем
        existing_user = db.query(User).filter(
            User.login == user_data.login,
            User.id != user_id
        ).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Пользователь с таким логином уже существует")
        user.login = user_data.login
    if user_data.password is not None:
        user.password_hash = get_password_hash(user_data.password)
    if user_data.role is not None:
        user.role = user_data.role
    if user_data.group_id is not None:
        user.group_id = user_data.group_id
    if user_data.is_headman is not None:
        user.is_headman = user_data.is_headman
    
    db.commit()
    return {"success": True, "message": "Пользователь успешно обновлён"}

@app.get("/admin/users/{user_id}")
async def get_user(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user or current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    return {
        "id": user.id,
        "full_name": user.full_name,
        "login": user.login,
        "role": user.role.value,
        "group_id": user.group_id,
        "is_headman": user.is_headman
    }

@app.delete("/admin/users/{user_id}")
async def delete_user(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user or current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Не позволяем удалить самого себя
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить собственный аккаунт")
    
    db.delete(user)
    db.commit()
    return {"success": True, "message": "Пользователь успешно удалён"}

# Маршрут для обновления расписания (доступно только администратору)
@app.post("/admin/sync-schedule")
async def sync_schedule(current_user: User = Depends(get_current_user)):
    if not current_user or current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    sync_google_sheet()
    return {"success": True, "message": "Расписание успешно обновлено из Google Таблицы"}

# Маршрут для добавления новой группы (доступно только администратору)
@app.post("/admin/groups/create")
async def create_group(group_data: dict, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user or current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    # Проверяем, существует ли группа с таким названием
    existing_group = db.query(Group).filter(Group.name == group_data.get("name")).first()
    if existing_group:
        raise HTTPException(status_code=400, detail="Группа с таким названием уже существует")
    
    # Создаем новую группу
    new_group = Group(
        name=group_data.get("name")
    )
    
    db.add(new_group)
    db.commit()
    db.refresh(new_group)
    
    return {"success": True, "message": "Группа успешно создана", "group_id": new_group.id}

# Маршрут для получения списка групп
@app.get("/api/groups")
async def get_groups(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    groups = db.query(Group).all()
    return [{"id": group.id, "name": group.name} for group in groups]

# Маршруты для студентов
@app.get("/dashboard/student", response_class=HTMLResponse)
async def student_dashboard(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user or current_user.role != UserRole.student:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    # Получаем расписание для группы студента
    schedule = db.query(Schedule).filter(Schedule.group_id == current_user.group_id).all()
    
    # Получаем посещаемость студента
    attendances = db.query(Attendance).filter(Attendance.user_id == current_user.id).all()
    
    return templates.TemplateResponse("student_dashboard.html", {
        "request": request,
        "current_user": current_user,
        "schedule": schedule,
        "attendances": attendances
    })

# Маршруты для старост (как специальный случай студента)
@app.get("/dashboard/headman", response_class=HTMLResponse)
async def headman_dashboard(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user or current_user.role != UserRole.student or not current_user.is_headman:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    # Получаем студентов своей группы
    students = db.query(User).filter(User.group_id == current_user.group_id).all()
    
    # Получаем сегодняшние занятия для своей группы
    today = date.today()
    today_schedule = db.query(Schedule).filter(
        Schedule.group_id == current_user.group_id,
        Schedule.date == today
    ).all()
    
    return templates.TemplateResponse("monitor_dashboard.html", {
        "request": request,
        "current_user": current_user,
        "students": students,
        "today_schedule": today_schedule
    })

# Маршруты для преподавателей
@app.get("/dashboard/teacher", response_class=HTMLResponse)
async def teacher_dashboard(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user or current_user.role != UserRole.teacher:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    # Получаем группы, которые ведёт преподаватель
    teacher_groups = db.query(TeacherGroup).filter(TeacherGroup.teacher_id == current_user.id).all()
    group_ids = [tg.group_id for tg in teacher_groups]
    
    # Получаем расписание для этих групп
    schedule = db.query(Schedule).filter(Schedule.group_id.in_(group_ids)).all()
    
    return templates.TemplateResponse("teacher_dashboard.html", {
        "request": request,
        "current_user": current_user,
        "schedule": schedule,
        "group_ids": group_ids
    })

# Маршруты для деканата
@app.get("/dashboard/dean", response_class=HTMLResponse)
async def dean_dashboard(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user or current_user.role != UserRole.dean:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    # Деканат видит всех студентов и все занятия
    students = db.query(User).filter(User.role == UserRole.student).all()
    schedule = db.query(Schedule).all()
    
    return templates.TemplateResponse("dean_dashboard.html", {
        "request": request,
        "current_user": current_user,
        "students": students,
        "schedule": schedule
    })

# Маршруты для администратора
@app.get("/dashboard/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, current_user: User = Depends(get_current_user)):
    if not current_user or current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request,
        "current_user": current_user
    })

# Маршрут для получения посещаемости студента
@app.get("/attendance/{user_id}/{schedule_id}")
async def get_attendance(user_id: int, schedule_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Проверяем права доступа к этой информации
    if current_user.role == UserRole.student and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    if current_user.role == UserRole.student and current_user.is_headman:
        # Староста может видеть только студентов своей группы
        student = db.query(User).filter(User.id == user_id).first()
        if not student or student.group_id != current_user.group_id:
            raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    attendance = db.query(Attendance).filter(
        Attendance.user_id == user_id,
        Attendance.schedule_id == schedule_id
    ).first()
    
    if not attendance:
        return {"status": None}
    
    return {"status": attendance.status}

# Маршрут для обновления посещаемости
@app.put("/attendance/{user_id}/{schedule_id}")
async def update_attendance(
    user_id: int, 
    schedule_id: int, 
    attendance_data: AttendanceUpdate, 
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    # Проверяем права доступа к изменению посещаемости
    if current_user.role == UserRole.student and not current_user.is_headman:
        raise HTTPException(status_code=403, detail="Студенты не могут изменять посещаемость")
    
    # Получаем информацию о занятии
    schedule_item = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not schedule_item:
        raise HTTPException(status_code=404, detail="Занятие не найдено")
    
    if current_user.role == UserRole.student and current_user.is_headman:
        # Староста может отмечать только студентов своей группы
        student = db.query(User).filter(User.id == user_id).first()
        if not student or student.group_id != current_user.group_id:
            raise HTTPException(status_code=403, detail="Доступ запрещён")
        
        # Староста может отмечать только на сегодняшние занятия
        if schedule_item.date != date.today():
            raise HTTPException(status_code=403, detail="Староста может отмечать посещаемость только на сегодняшние занятия")
    
    elif current_user.role == UserRole.teacher:
        # Преподаватель может отмечать только студентов своих групп
        teacher_group = db.query(TeacherGroup).filter(
            TeacherGroup.teacher_id == current_user.id,
            TeacherGroup.group_id == schedule_item.group_id
        ).first()
        
        if not teacher_group:
            raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    # Обновляем или создаём запись о посещении
    attendance = db.query(Attendance).filter(
        Attendance.user_id == user_id,
        Attendance.schedule_id == schedule_id
    ).first()
    
    if attendance:
        attendance.status = attendance_data.status
        attendance.updated_at = datetime.utcnow()
        attendance.updated_by = current_user.id
    else:
        attendance = Attendance(
            user_id=user_id,
            schedule_id=schedule_id,
            status=attendance_data.status,
            updated_at=datetime.utcnow(),
            updated_by=current_user.id
        )
        db.add(attendance)
    
    db.commit()
    return {"success": True, "message": "Посещаемость успешно обновлена"}

# Маршрут для получения профиля текущего пользователя
@app.get("/api/users/me")
async def get_current_user_profile(current_user: User = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    
    return {
        "id": current_user.id,
        "full_name": current_user.full_name,
        "login": current_user.login,
        "role": current_user.role.value,
        "group_id": current_user.group_id,
        "is_headman": current_user.is_headman
    }

# Маршрут для изменения пароля пользователя
@app.put("/api/users/change-password")
async def change_password(password_data: dict, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    
    # Проверяем, совпадает ли старый пароль
    old_password = password_data.get("old_password")
    if not verify_password(old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Неверный старый пароль")
    
    new_password = password_data.get("new_password")
    if not new_password:
        raise HTTPException(status_code=400, detail="Новый пароль не указан")
    
    # Обновляем пароль
    current_user.password_hash = get_password_hash(new_password)
    db.commit()
    
    return {"success": True, "message": "Пароль успешно изменён"}

# Маршрут для обновления профиля пользователя
@app.put("/api/users/update-profile")
async def update_user_profile(profile_data: dict, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    
    # Обновляем данные профиля
    if "full_name" in profile_data:
        current_user.full_name = profile_data["full_name"]
    if "login" in profile_data:
        # Проверяем, не занят ли новый логин другим пользователем
        existing_user = db.query(User).filter(
            User.login == profile_data["login"],
            User.id != current_user.id
        ).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Пользователь с таким логином уже существует")
        current_user.login = profile_data["login"]
    
    db.commit()
    
    return {"success": True, "message": "Профиль успешно обновлён"}