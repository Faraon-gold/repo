from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, datetime
import os

from ..models import User, Group, Subject, Schedule, Attendance, TeacherGroup, UserRole, AttendanceStatus
from ..schemas import LoginRequest, UserCreate, UserUpdate, AttendanceUpdate
from ..utils import get_db, verify_password, get_password_hash, create_access_token, decode_access_token, check_permission
from ..init_db import sync_google_sheet
from .auth import get_current_user

router = APIRouter()

# Маршруты для администратора
@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user or current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    users = db.query(User).all()
    groups = db.query(Group).all()
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="../../templates")
    return templates.TemplateResponse("admin_users.html", {
        "request": request,
        "current_user": current_user,
        "users": users,
        "groups": groups
    })

@router.post("/admin/users/create")
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
        group_id=user_data.group_id
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {"success": True, "message": "Пользователь успешно создан"}

@router.put("/admin/users/{user_id}")
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
    
    db.commit()
    return {"success": True, "message": "Пользователь успешно обновлён"}

@router.get("/admin/users/{user_id}")
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
        "group_id": user.group_id
    }

@router.delete("/admin/users/{user_id}")
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

# Маршруты для студентов
@router.get("/dashboard/student", response_class=HTMLResponse)
async def student_dashboard(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user or current_user.role != UserRole.student:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    # Получаем расписание для группы студента
    schedule = db.query(Schedule).filter(Schedule.group_id == current_user.group_id).all()
    
    # Получаем посещаемость студента
    attendances = db.query(Attendance).filter(Attendance.user_id == current_user.id).all()
    
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="../../templates")
    return templates.TemplateResponse("student_dashboard.html", {
        "request": request,
        "current_user": current_user,
        "schedule": schedule,
        "attendances": attendances
    })

# Маршруты для старост
@router.get("/dashboard/monitor", response_class=HTMLResponse)
async def monitor_dashboard(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user or current_user.role != UserRole.monitor:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    # Получаем студентов своей группы
    students = db.query(User).filter(User.group_id == current_user.group_id).all()
    
    # Получаем сегодняшние занятия для своей группы
    today = date.today()
    today_schedule = db.query(Schedule).filter(
        Schedule.group_id == current_user.group_id,
        Schedule.date == today
    ).all()
    
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="../../templates")
    return templates.TemplateResponse("monitor_dashboard.html", {
        "request": request,
        "current_user": current_user,
        "students": students,
        "today_schedule": today_schedule
    })

# Маршруты для преподавателей
@router.get("/dashboard/teacher", response_class=HTMLResponse)
async def teacher_dashboard(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user or current_user.role != UserRole.teacher:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    # Получаем группы, которые ведёт преподаватель
    teacher_groups = db.query(TeacherGroup).filter(TeacherGroup.teacher_id == current_user.id).all()
    group_ids = [tg.group_id for tg in teacher_groups]
    
    # Получаем расписание для этих групп
    schedule = db.query(Schedule).filter(Schedule.group_id.in_(group_ids)).all()
    
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="../../templates")
    return templates.TemplateResponse("teacher_dashboard.html", {
        "request": request,
        "current_user": current_user,
        "schedule": schedule,
        "group_ids": group_ids
    })

# Маршруты для деканата
@router.get("/dashboard/dean", response_class=HTMLResponse)
async def dean_dashboard(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user or current_user.role != UserRole.dean:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    # Деканат видит всех студентов и все занятия
    students = db.query(User).filter(User.role == UserRole.student).all()
    schedule = db.query(Schedule).all()
    
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="../../templates")
    return templates.TemplateResponse("dean_dashboard.html", {
        "request": request,
        "current_user": current_user,
        "students": students,
        "schedule": schedule
    })

# Маршруты для администратора
@router.get("/dashboard/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, current_user: User = Depends(get_current_user)):
    if not current_user or current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="../../templates")
    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request,
        "current_user": current_user
    })

# Маршрут для обновления расписания (доступно только администратору)
@router.post("/admin/sync-schedule")
async def sync_schedule(current_user: User = Depends(get_current_user)):
    if not current_user or current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    sync_google_sheet()
    return {"success": True, "message": "Расписание успешно обновлено из Google Таблицы"}