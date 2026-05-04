from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from .database import Base, engine
from .routers import admin_chats, broadcasts, projects, simulator, telegram_admin
from .services.broadcast_scheduler import start_broadcast_scheduler, stop_broadcast_scheduler
from .services.telegram_polling_manager import stop_polling


def ensure_telegram_bot_columns() -> None:
    with engine.begin() as connection:
        rows = connection.execute(text("PRAGMA table_info(telegram_bots)")).fetchall()
        columns = {row[1] for row in rows}
        if "web_app_url" not in columns:
            connection.execute(text("ALTER TABLE telegram_bots ADD COLUMN web_app_url TEXT"))
        if "web_app_button_text" not in columns:
            connection.execute(
                text("ALTER TABLE telegram_bots ADD COLUMN web_app_button_text VARCHAR(255)")
            )


def create_app() -> FastAPI:
    app = FastAPI(title="Telegram Bot Constructor MVP")

    Base.metadata.create_all(bind=engine)
    ensure_telegram_bot_columns()

    templates = Jinja2Templates(directory="app/templates")
    app.state.templates = templates

    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.include_router(projects.router)
    app.include_router(simulator.router)
    app.include_router(telegram_admin.router)
    app.include_router(admin_chats.router)
    app.include_router(broadcasts.router)

    @app.on_event("startup")
    def on_startup() -> None:
        start_broadcast_scheduler()

    @app.on_event("shutdown")
    def on_shutdown() -> None:
        stop_broadcast_scheduler()
        stop_polling()

    return app


app = create_app()
