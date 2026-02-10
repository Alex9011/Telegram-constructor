import argparse
import asyncio
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from .database import SessionLocal
from .models import TelegramBot
from .services.telegram_renderer import send_flow_events
from .services.telegram_runtime import (
    continue_with_button,
    continue_with_text,
    get_active_telegram_bot,
    start_for_user,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Telegram bot polling for Telegram-constructor")
    parser.add_argument(
        "--project-id",
        type=int,
        default=None,
        help="Run active bot for a specific project",
    )
    return parser.parse_args()


def load_active_bot(project_id: Optional[int]) -> TelegramBot:
    db = SessionLocal()
    try:
        bot_config = get_active_telegram_bot(db, project_id=project_id)
        if not bot_config:
            if project_id is None:
                raise RuntimeError("Не знайдено активного Telegram-бота")
            raise RuntimeError(f"Для project_id={project_id} не знайдено активного Telegram-бота")
        db.expunge(bot_config)
        return bot_config
    finally:
        db.close()


def build_dispatcher(telegram_bot_id: int) -> Dispatcher:
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def on_start(message: Message, bot: Bot):
        if not message.from_user:
            return

        db = SessionLocal()
        try:
            events, _ = start_for_user(
                db=db,
                telegram_bot_id=telegram_bot_id,
                telegram_user_id=message.from_user.id,
                chat_id=message.chat.id,
            )
        except Exception as exc:
            await bot.send_message(message.chat.id, f"Помилка запуску: {exc}")
            return
        finally:
            db.close()

        await send_flow_events(bot=bot, chat_id=message.chat.id, events=events)

    @dp.callback_query(F.data.startswith("choose:"))
    async def on_choose(callback: CallbackQuery, bot: Bot):
        if not callback.from_user or not callback.message:
            return

        try:
            _, raw_index = callback.data.split(":", 1)
            button_index = int(raw_index)
        except Exception:
            await callback.answer("Некоректна кнопка", show_alert=False)
            return

        db = SessionLocal()
        try:
            events, _ = continue_with_button(
                db=db,
                telegram_bot_id=telegram_bot_id,
                telegram_user_id=callback.from_user.id,
                chat_id=callback.message.chat.id,
                button_index=button_index,
            )
        except Exception as exc:
            await callback.answer("Помилка", show_alert=False)
            await bot.send_message(callback.message.chat.id, f"Помилка: {exc}")
            return
        finally:
            db.close()

        await callback.answer()
        await send_flow_events(bot=bot, chat_id=callback.message.chat.id, events=events)

    @dp.message(F.text)
    async def on_text(message: Message, bot: Bot):
        if not message.from_user:
            return

        db = SessionLocal()
        try:
            events, _ = continue_with_text(
                db=db,
                telegram_bot_id=telegram_bot_id,
                telegram_user_id=message.from_user.id,
                chat_id=message.chat.id,
                text=message.text or "",
            )
        except Exception as exc:
            await bot.send_message(message.chat.id, f"Помилка: {exc}")
            return
        finally:
            db.close()

        await send_flow_events(bot=bot, chat_id=message.chat.id, events=events)

    return dp


async def run_polling(project_id: Optional[int]) -> None:
    bot_config = load_active_bot(project_id=project_id)
    token = bot_config.token
    telegram_bot_id = bot_config.id

    bot = Bot(token=token)
    dp = build_dispatcher(telegram_bot_id=telegram_bot_id)

    try:
        me = await bot.get_me()
        print(f"Polling started: @{me.username or 'unknown'} (project_id={bot_config.project_id})")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


def main() -> None:
    args = parse_args()
    asyncio.run(run_polling(project_id=args.project_id))


if __name__ == "__main__":
    main()
