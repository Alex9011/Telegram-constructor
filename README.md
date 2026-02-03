# Telegram Bot Constructor MVP

Простий MVP конструктора логіки Telegram-ботів на FastAPI.

## Що вміє

- Створення проєктів
- Редактор блоків: start, message, buttons, input, end
- Налаштування переходів між блоками
- Збереження схеми в SQLite (JSON)
- Симуляція сценарію в браузері
- Експорт JSON-схеми

## Вимоги

- Python 3.9+
- Windows PowerShell або CMD

## Встановлення та запуск

1. Перейди до папки проєкту:

   ```powershell
   cd C:\Users\1\OneDrive\Desktop\Telegram-constructor
   ```

2. Створи віртуальне оточення (якщо ще не створено):

   ```powershell
   python -m venv .venv
   ```

3. Активуй віртуальне оточення:

   ```powershell
   .venv\Scripts\activate
   ```

4. Встанови залежності:

   ```powershell
   pip install -r requirements.txt
   ```

5. Запусти сервер:

   ```powershell
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

6. Відкрий у браузері:

   http://127.0.0.1:8000

## Швидкий сценарій перевірки

1. На головній сторінці створи проєкт.
2. Перейди в редактор і додай блоки.
3. Натисни "Зберегти схему".
4. Відкрий "Симулятор" і пройди сценарій.
5. Перевір "Експорт JSON".

## Структура проєкту

- app/main.py — запуск FastAPI застосунку
- app/models.py — SQLAlchemy моделі Project та Block
- app/routers/projects.py — сторінки та API редактора
- app/routers/simulator.py — API симулятора
- app/services/flow_engine.py — логіка валідації та виконання схеми
- app/templates/ — HTML шаблони
- app/static/ — CSS та JavaScript

## Примітка

Команда npm start для цього проєкту не використовується, бо це не Node.js застосунок. Запуск виконується через uvicorn.
