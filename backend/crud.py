from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from models import Matter, Message, Document, RetrievedClause
from datetime import datetime, timedelta
import uuid

async def create_matter(db: AsyncSession, session_id: str, title: str = "New Dispute") -> Matter:
    matter = Matter(title=title, session_id=session_id)
    matter.expires_at = datetime.utcnow() + timedelta(hours=24)
    db.add(matter)
    await db.commit()
    await db.refresh(matter)
    return matter

async def touch_matter(db: AsyncSession, matter: Matter):
    now = datetime.utcnow()
    matter.updated_at = now
    matter.expires_at = now + timedelta(hours=24)
    await db.commit()
    await db.refresh(matter)

async def get_matters(db: AsyncSession, session_id: str):
    now = datetime.utcnow()
    result = await db.execute(
        select(Matter)
        .where(Matter.session_id == session_id)
        .where(Matter.expires_at > now)
        .order_by(Matter.updated_at.desc())
    )
    return result.scalars().all()

async def get_matter(db: AsyncSession, matter_id: uuid.UUID, session_id: str = None):
    query = select(Matter).where(Matter.id == matter_id)
    if session_id:
        query = query.where(Matter.session_id == session_id)
    
    result = await db.execute(query)
    matter = result.scalars().first()
    
    if matter and matter.expires_at > datetime.utcnow():
        await touch_matter(db, matter)
        return matter
    return None

async def add_message(db: AsyncSession, matter_id: uuid.UUID, role: str, content: str, session_id: str = None):
    matter = await get_matter(db, matter_id, session_id)
    if not matter:
        raise ValueError("Matter not found or expired")
        
    msg = Message(matter_id=matter_id, role=role, content=content)
    db.add(msg)
    await db.commit()
    await touch_matter(db, matter)
    await db.refresh(msg)
    return msg

async def get_messages(db: AsyncSession, matter_id: uuid.UUID, session_id: str = None):
    matter = await get_matter(db, matter_id, session_id)
    if not matter:
        return []
    result = await db.execute(select(Message).where(Message.matter_id == matter_id).order_by(Message.created_at.asc()))
    return result.scalars().all()

async def add_document(db: AsyncSession, matter_id: uuid.UUID, filename: str, metadata_json: dict = None, session_id: str = None):
    matter = await get_matter(db, matter_id, session_id)
    if not matter:
        raise ValueError("Matter not found or expired")
        
    doc = Document(matter_id=matter_id, filename=filename, metadata_json=metadata_json)
    db.add(doc)
    await db.commit()
    await touch_matter(db, matter)
    await db.refresh(doc)
    return doc

async def get_documents(db: AsyncSession, matter_id: uuid.UUID, session_id: str = None):
    matter = await get_matter(db, matter_id, session_id)
    if not matter:
        return []
    result = await db.execute(select(Document).where(Document.matter_id == matter_id))
    return result.scalars().all()

async def add_retrieved_clause(db: AsyncSession, matter_id: uuid.UUID, source: str, clause_number: str, title: str, session_id: str = None):
    matter = await get_matter(db, matter_id, session_id)
    if not matter:
        raise ValueError("Matter not found or expired")
        
    clause = RetrievedClause(matter_id=matter_id, source_document=source, clause_number=clause_number, title=title)
    db.add(clause)
    await db.commit()
    await touch_matter(db, matter)
    await db.refresh(clause)
    return clause

async def get_retrieved_clauses(db: AsyncSession, matter_id: uuid.UUID, session_id: str = None):
    matter = await get_matter(db, matter_id, session_id)
    if not matter:
        return []
    result = await db.execute(select(RetrievedClause).where(RetrievedClause.matter_id == matter_id))
    return result.scalars().all()

async def cleanup_expired_matters(db: AsyncSession):
    now = datetime.utcnow()
    result = await db.execute(select(Matter).where(Matter.expires_at <= now))
    expired_matters = result.scalars().all()
    for matter in expired_matters:
        await db.delete(matter)
    await db.commit()
    return len(expired_matters)
