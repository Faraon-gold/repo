-- Простой SQL-скрипт для добавления недостающих элементов в базу данных

-- Добавляем столбец is_headman в таблицу users, если он не существует
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_headman BOOLEAN DEFAULT FALSE;

-- Удаляем старое ограничение и добавляем новое (без 'monitor')
DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    SELECT conname INTO constraint_name
    FROM pg_constraint
    WHERE conrelid = 'users'::regclass
    AND contype = 'c'
    AND conname LIKE '%role%';

    IF constraint_name IS NOT NULL THEN
        EXECUTE 'ALTER TABLE users DROP CONSTRAINT ' || constraint_name;
    END IF;

    -- Добавляем новое ограничение без 'monitor'
    ALTER TABLE users ADD CONSTRAINT check_user_role CHECK (role IN ('student', 'teacher', 'dean', 'admin'));
END $$;