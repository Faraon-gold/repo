from pydantic import BaseModel
from typing import Optional
from .models import UserRole, AttendanceStatus

class UserCreate(BaseModel):
    full_name: str
    login: str
    password: str
    role: UserRole
    group_id: Optional[int] = None

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    login: Optional[str] = None
    password: Optional[str] = None
    role: Optional[UserRole] = None
    group_id: Optional[int] = None

class LoginRequest(BaseModel):
    login: str
    password: str

class AttendanceUpdate(BaseModel):
    status: AttendanceStatus