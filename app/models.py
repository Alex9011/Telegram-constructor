from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    flow_json = Column(Text, nullable=False, default='{"blocks": []}')
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    blocks = relationship(
        "Block",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    telegram_bot = relationship(
        "TelegramBot",
        back_populates="project",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Block(Base):
    __tablename__ = "blocks"
    __table_args__ = (
        UniqueConstraint("project_id", "uid", name="uq_project_block_uid"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uid = Column(String(50), nullable=False)
    block_type = Column(String(20), nullable=False)
    data_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    project = relationship("Project", back_populates="blocks")


class TelegramBot(Base):
    __tablename__ = "telegram_bots"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    token = Column(Text, nullable=False)
    bot_username = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    project = relationship("Project", back_populates="telegram_bot")
    sessions = relationship(
        "BotSession",
        back_populates="telegram_bot",
        cascade="all, delete-orphan",
    )


class BotSession(Base):
    __tablename__ = "bot_sessions"
    __table_args__ = (
        UniqueConstraint(
            "telegram_bot_id",
            "telegram_user_id",
            "chat_id",
            name="uq_bot_session_user_chat",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    telegram_bot_id = Column(
        Integer,
        ForeignKey("telegram_bots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    telegram_user_id = Column(String(32), nullable=False, index=True)
    chat_id = Column(String(32), nullable=False, index=True)
    current_block_id = Column(String(50), nullable=True)
    waiting = Column(String(20), nullable=True)
    variables_json = Column(Text, nullable=False, default="{}")
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    telegram_bot = relationship("TelegramBot", back_populates="sessions")
