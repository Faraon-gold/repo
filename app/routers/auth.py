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
from ..init_db import init_sample_data, sync_google_sheet

router = APIRouter()

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

# Маршрут главной страницы (форма входа)
@router.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="../../templates")
    return templates.TemplateResponse("login.html", {"request": request})

# Маршрут аутентификации
@router.post("/login")
async def login(login_data: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.login == login_data.login).first()
    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    
    token = create_access_token(data={"user_id": user.id})
    # Set the cookie with the token
    response.set_cookie(key="access_token", value=token, httponly=True)
    # Return success response with redirect URL
    return {"success": True, "redirect_url": f"/dashboard/{user.role.value}"}

# Маршрут выхода
@router.post("/logout")
async def logout(response: Response):
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("access_token")
    return response

# Маршрут для получения посещаемости студента
@router.get("/attendance/{user_id}/{schedule_id}")
async def get_attendance(user_id: int, schedule_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Проверяем права доступа к этой информации
    if current_user.role == UserRole.student and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    if current_user.role == UserRole.monitor:
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
@router.put("/attendance/{user_id}/{schedule_id}")
async def update_attendance(
    user_id: int, 
    schedule_id: int, 
    attendance_data: AttendanceUpdate, 
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    # Проверяем права доступа к изменению посещаемости
    if current_user.role == UserRole.student:
        raise HTTPException(status_code=403, detail="Студенты не могут изменять посещаемость")
    
    # Получаем информацию о занятии
    schedule_item = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not schedule_item:
        raise HTTPException(status_code=404, detail="Занятие не найдено")
    
    if current_user.role == UserRole.monitor:
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