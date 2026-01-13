#!/usr/bin/env python3
"""
Скрипт для миграции и инициализации базы данных
"""

import os
from sqlalchemy import create_engine, text

# Подключение к базе данных
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://attendance_user:attendance_pass@localhost:5432/attendance_db")

print(f"Подключение к базе данных: {DATABASE_URL}")
engine = create_engine(DATABASE_URL)

try:
    with engine.connect() as conn:
        # Добавляем столбец is_headman, если он не существует
        print("Добавляем столбец is_headman...")
        conn.execute(text("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS is_headman BOOLEAN DEFAULT FALSE;
        """))
        
        # Обновляем ограничение для роли, убираем 'monitor'
        print("Обновляем ограничение для роли...")
        # Сначала получим имя текущего ограничения
        result = conn.execute(text("""
            SELECT conname 
            FROM pg_constraint
            WHERE conrelid = 'users'::regclass
            AND contype = 'c';
        """))
        
        constraint_names = []
        for row in result:
            constraint_names.append(row[0])
        
        # Удаляем все проверочные ограничения, связанные с ролью
        for constraint_name in constraint_names:
            if 'role' in constraint_name.lower():
                print(f"Удаляем ограничение {constraint_name}...")
                conn.execute(text(f'ALTER TABLE users DROP CONSTRAINT {constraint_name};'))
        
        # Сначала обновляем все недопустимые роли на 'student' как значение по умолчанию
        print("Обновляем недопустимые роли...")
        conn.execute(text("""
            UPDATE users 
            SET role = 'student' 
            WHERE role NOT IN ('student', 'teacher', 'dean', 'admin');
        """))
        
        # Добавляем новое ограничение без 'monitor'
        conn.execute(text("ALTER TABLE users ADD CONSTRAINT check_user_role CHECK (role IN ('student', 'teacher', 'dean', 'admin'));"))
        
        # Фиксируем изменения
        conn.commit()
        
    print("Миграция завершена успешно!")
    
    # Теперь запускаем обновленный init_db
    import subprocess
    import sys
    
    print("Запуск инициализации базы данных...")
    result = subprocess.run([sys.executable, '/app/init_db.py'], capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Ошибка при выполнении init_db.py:")
        print(result.stdout)
        print(result.stderr)
        exit(result.returncode)
    else:
        print("Инициализация базы данных завершена успешно!")
        print(result.stdout)

except Exception as e:
    print(f"Ошибка при миграции: {e}")
    import traceback
    traceback.print_exc()
    exit(1)