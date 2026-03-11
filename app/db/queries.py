from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MessageLog, Session, User, UserProfile


async def get_or_create_user(db: AsyncSession, tg_id: str) -> User:
    result = await db.execute(select(User).where(User.tg_id == tg_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(tg_id=tg_id)
        db.add(user)
        await db.flush()
    return user


async def get_active_session(db: AsyncSession, user_id: int) -> Session | None:
    result = await db.execute(
        select(Session)
        .where(Session.user_id == user_id)
        .order_by(Session.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_session(db: AsyncSession, user_id: int, state: str = "WELCOME") -> Session:
    session = Session(
        user_id=user_id,
        state=state,
        last_user_message_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.flush()
    return session


async def update_session_state(
    db: AsyncSession,
    session: Session,
    new_state: str,
    payload: dict | None = None,
) -> None:
    session.state = new_state
    if payload is not None:
        session.state_payload_json = payload
    session.last_user_message_at = datetime.now(timezone.utc)
    await db.flush()


async def get_or_create_profile(db: AsyncSession, user_id: int) -> UserProfile:
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
        await db.flush()
    return profile


async def save_message(
    db: AsyncSession,
    user_id: int,
    direction: str,
    message_type: str,
    body: str | None = None,
    tg_message_id: str | None = None,
    media_url: str | None = None,
) -> MessageLog:
    msg = MessageLog(
        user_id=user_id,
        direction=direction,
        message_type=message_type,
        body=body,
        tg_message_id=tg_message_id,
        media_url=media_url,
    )
    db.add(msg)
    await db.flush()
    return msg


async def message_already_processed(db: AsyncSession, tg_message_id: str) -> bool:
    result = await db.execute(
        select(MessageLog.id).where(MessageLog.tg_message_id == tg_message_id).limit(1)
    )
    return result.scalar_one_or_none() is not None
