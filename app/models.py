from sqlalchemy import Column, Integer, String, Text, DateTime, Date, Time, ForeignKey, Enum, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum
from datetime import datetime

Base = declarative_base()

# Определение перечислимого типа для ролей пользователей
class UserRole(str, enum.Enum):
    student = "student"
    monitor = "monitor"
    teacher = "teacher"
    dean = "dean"
    admin = "admin"

# Определение перечислимого типа для статуса посещения
class AttendanceStatus(str, enum.Enum):
    present = "present"
    absent = "absent"
    late = "late"

# Модель пользователя
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)  # ФИО пользователя
    login = Column(String, unique=True, nullable=False)  # Логин для входа
    password_hash = Column(String, nullable=False)  # Хэш пароля
    role = Column(Enum(UserRole), nullable=False)  # Роль пользователя
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)  # Идентификатор группы
    
    # Связи
    group = relationship("Group", back_populates="students")
    attendances = relationship("Attendance", primaryjoin="User.id==Attendance.user_id", back_populates="user")
    scheduled_classes = relationship("Schedule", back_populates="teacher")

# Модель группы
class Group(Base):
    __tablename__ = "groups"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)  # Название группы (например, "ИС-201")
    
    # Связи
    students = relationship("User", back_populates="group")
    schedules = relationship("Schedule", back_populates="group")
    teachers = relationship("TeacherGroup", back_populates="group")

# Модель предмета
class Subject(Base):
    __tablename__ = "subjects"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)  # Название предмета
    
    # Связи
    schedules = relationship("Schedule", back_populates="subject")

# Модель расписания
class Schedule(Base):
    __tablename__ = "schedule"
    
    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False)  # Дата занятия
    start_time = Column(Time, nullable=False)  # Время начала
    end_time = Column(Time, nullable=False)  # Время окончания
    subject_id = Column(Integer, ForeignKey("subjects.id"))  # ID предмета
    group_id = Column(Integer, ForeignKey("groups.id"))  # ID группы
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # ID преподавателя (опционально)
    
    # Связи
    subject = relationship("Subject", back_populates="schedules")
    group = relationship("Group", back_populates="schedules")
    teacher = relationship("User", back_populates="scheduled_classes")
    attendances = relationship("Attendance", back_populates="schedule")

# Модель посещаемости
class Attendance(Base):
    __tablename__ = "attendance"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))  # ID пользователя
    schedule_id = Column(Integer, ForeignKey("schedule.id"))  # ID расписания
    status = Column(Enum(AttendanceStatus), nullable=False)  # Статус посещения
    updated_at = Column(DateTime, default=datetime.utcnow)  # Время последнего обновления
    updated_by = Column(Integer, ForeignKey("users.id"))  # Кто обновил статус
    
    # Связи
    user = relationship("User", foreign_keys=[user_id], back_populates="attendances")
    schedule = relationship("Schedule", back_populates="attendances")
    updater = relationship("User", foreign_keys=[updated_by])

# Модель связи преподавателей и групп
class TeacherGroup(Base):
    __tablename__ = "teacher_groups"
    
    teacher_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"), primary_key=True)
    
    # Связи
    teacher = relationship("User")
    group = relationship("Group", back_populates="teachers")