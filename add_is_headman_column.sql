-- Добавляем столбец is_headman в таблицу users, если он не существует
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

-- Обновляем ограничение для роли, убираем 'monitor'
DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    SELECT conname INTO constraint_name
    FROM pg_constraint
    WHERE conrelid = 'users'::regclass
    AND contype = 'c';

    IF constraint_name LIKE '%role%' THEN
        EXECUTE 'ALTER TABLE users DROP CONSTRAINT ' || constraint_name;
    END IF;

    -- Добавляем новое ограничение без 'monitor'
    ALTER TABLE users ADD CONSTRAINT check_user_role CHECK (role IN ('student', 'teacher', 'dean', 'admin'));
END $$;