from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
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
    booking_requests = relationship(
        "BookingRequest",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    broadcast_campaigns = relationship(
        "BroadcastCampaign",
        back_populates="project",
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
    chats = relationship(
        "Chat",
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


class Chat(Base):
    __tablename__ = "chats"
    __table_args__ = (
        UniqueConstraint("telegram_bot_id", "chat_id", name="uq_bot_telegram_chat"),
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
    username = Column(String(255), nullable=True)
    full_name = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False, default="open")
    is_human_mode = Column(Boolean, nullable=False, default=False)
    unread_count = Column(Integer, nullable=False, default=0)
    last_message_text = Column(Text, nullable=True)
    last_message_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    telegram_bot = relationship("TelegramBot", back_populates="chats")
    messages = relationship(
        "Message",
        back_populates="chat",
        cascade="all, delete-orphan",
        order_by="Message.created_at.asc()",
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(
        Integer,
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    direction = Column(String(8), nullable=False)
    text = Column(Text, nullable=False)
    telegram_message_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    chat = relationship("Chat", back_populates="messages")


class BookingRequest(Base):
    __tablename__ = "booking_requests"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    telegram_user_id = Column(String(32), nullable=False, index=True)
    client_name = Column(String(255), nullable=False)
    client_phone = Column(String(64), nullable=False)
    selected_service = Column(String(255), nullable=False)
    selected_barber = Column(String(255), nullable=False)
    booking_date = Column(String(64), nullable=False)
    booking_time = Column(String(64), nullable=False)
    comment = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="new")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    project = relationship("Project", back_populates="booking_requests")


class BroadcastCampaign(Base):
    __tablename__ = "broadcast_campaigns"
    __table_args__ = (
        Index("ix_broadcast_campaigns_project_active", "project_id", "is_active"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(150), nullable=False)
    message_text = Column(Text, nullable=False)
    schedule_type = Column(String(20), nullable=False, default="daily")
    day_of_week = Column(Integer, nullable=True)
    day_of_month = Column(Integer, nullable=True)
    hour = Column(Integer, nullable=False, default=10)
    minute = Column(Integer, nullable=False, default=0)
    interval_days = Column(Integer, nullable=True)
    timezone = Column(String(64), nullable=False, default="Europe/Kiev")
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    last_run_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    project = relationship("Project", back_populates="broadcast_campaigns")
