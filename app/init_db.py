from sqlalchemy.orm import Session
from .models import Group, Subject, User, UserRole
from .utils import get_password_hash
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dateutil import parser
import os

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
        
        from .utils import SessionLocal
        db = SessionLocal()
        try:
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
                from .models import Schedule
                schedule_entry = Schedule(
                    date=class_date,
                    start_time=parser.parse(record.get('start_time', '00:00')).time(),
                    end_time=parser.parse(record.get('end_time', '00:00')).time(),
                    subject_id=subject.id,
                    group_id=group.id,
                    teacher_id=teacher.id if teacher else None
                )
                
                from sqlalchemy import and_
                existing_schedule = db.query(Schedule).filter(
                    and_(
                        Schedule.date == schedule_entry.date,
                        Schedule.start_time == schedule_entry.start_time,
                        Schedule.subject_id == schedule_entry.subject_id,
                        Schedule.group_id == schedule_entry.group_id
                    )
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

def init_sample_data(db: Session):
    """Инициализация начальными данными"""
    try:
        # Создание групп
        if not db.query(Group).count():
            group1 = Group(name="ИС-201")
            group2 = Group(name="ИС-202")
            db.add(group1)
            db.add(group2)
            db.commit()
            db.refresh(group1)
            db.refresh(group2)
            print("Созданы группы: ИС-201, ИС-202")
        
        # Создание предметов
        if not db.query(Subject).count():
            subject1 = Subject(name="Математический анализ")
            subject2 = Subject(name="Программирование")
            subject3 = Subject(name="Физика")
            db.add(subject1)
            db.add(subject2)
            db.add(subject3)
            db.commit()
            db.refresh(subject1)
            db.refresh(subject2)
            db.refresh(subject3)
            print("Созданы предметы: Математический анализ, Программирование, Физика")
        
        # Создание пользователей
        if not db.query(User).count():
            # Получаем ID групп
            group1 = db.query(Group).filter(Group.name == "ИС-201").first()
            group2 = db.query(Group).filter(Group.name == "ИС-202").first()
            
            # Администратор
            admin_user = User(
                full_name="Админ Администратов",
                login="admin",
                password_hash=get_password_hash("admin123"),
                role=UserRole.admin
            )
            
            # Преподаватель
            teacher_user = User(
                full_name="Петр Петров",
                login="teacher",
                password_hash=get_password_hash("teacher123"),
                role=UserRole.teacher
            )
            
            # Староста
            monitor_user = User(
                full_name="Иван Иванов",
                login="monitor",
                password_hash=get_password_hash("monitor123"),
                role=UserRole.monitor,
                group_id=group1.id
            )
            
            # Студент
            student_user = User(
                full_name="Сидор Сидоров",
                login="student",
                password_hash=get_password_hash("student123"),
                role=UserRole.student,
                group_id=group1.id
            )
            
            # Деканат
            dean_user = User(
                full_name="Елена Дмитриева",
                login="dean",
                password_hash=get_password_hash("dean123"),
                role=UserRole.dean
            )
            
            db.add(admin_user)
            db.add(teacher_user)
            db.add(monitor_user)
            db.add(student_user)
            db.add(dean_user)
            db.commit()
            db.refresh(admin_user)
            db.refresh(teacher_user)
            db.refresh(monitor_user)
            db.refresh(student_user)
            db.refresh(dean_user)
            print("Созданы пользователи: админ, преподаватель, староста, студент, деканат")

    except Exception as e:
        print(f"Ошибка при инициализации начальных данных: {e}")
        db.rollback()