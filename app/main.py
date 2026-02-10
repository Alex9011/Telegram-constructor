from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .database import Base, engine
from .routers import projects, simulator, telegram_admin
from .services.telegram_polling_manager import stop_polling


def create_app() -> FastAPI:
    app = FastAPI(title="Telegram Bot Constructor MVP")

    Base.metadata.create_all(bind=engine)

    templates = Jinja2Templates(directory="app/templates")
    app.state.templates = templates

    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.include_router(projects.router)
    app.include_router(simulator.router)
    app.include_router(telegram_admin.router)

    @app.on_event("shutdown")
    def on_shutdown() -> None:
        stop_polling()

    return app


app = create_app()
