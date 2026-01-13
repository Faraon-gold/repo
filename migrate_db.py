#!/usr/bin/env python3
"""
Скрипт миграции базы данных для добавления недостающих столбцов
"""

import os
from sqlalchemy import create_engine, text

# Подключение к базе данных
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://attendance_user:attendance_pass@localhost:5432/attendance_db")

print(f"Подключение к базе данных: {DATABASE_URL}")
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    # Добавляем столбец is_headman, если он не существует
    print("Добавляем столбец is_headman...")
    result = conn.execute(text("""
        DO $$ 
        BEGIN
            IF NOT EXISTS (
                SELECT 1 
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                AND column_name = 'is_headman'
            ) THEN
                ALTER TABLE users ADD COLUMN is_headman BOOLEAN DEFAULT FALSE;
            END IF;
        END $$;
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
    
    # Добавляем новое ограничение без 'monitor'
    conn.execute(text("ALTER TABLE users ADD CONSTRAINT check_user_role CHECK (role IN ('student', 'teacher', 'dean', 'admin'));"))
    
    # Фиксируем изменения
    conn.commit()

print("Миграция завершена успешно!")