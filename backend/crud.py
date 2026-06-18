from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from models import Matter, Message, Document, RetrievedClause
import uuid

async def create_matter(db: AsyncSession, title: str = "New Dispute") -> Matter:
    matter = Matter(title=title)
    db.add(matter)
    await db.commit()
    await db.refresh(matter)
    return matter

async def get_matters(db: AsyncSession):
    result = await db.execute(select(Matter).order_by(Matter.updated_at.desc()))
    return result.scalars().all()

async def get_matter(db: AsyncSession, matter_id: uuid.UUID):
    result = await db.execute(select(Matter).where(Matter.id == matter_id))
    return result.scalars().first()

async def add_message(db: AsyncSession, matter_id: uuid.UUID, role: str, content: str):
    msg = Message(matter_id=matter_id, role=role, content=content)
    db.add(msg)
    # Update matter timestamp
    matter = await get_matter(db, matter_id)
    if matter:
        matter.updated_at = msg.created_at
    await db.commit()
    await db.refresh(msg)
    return msg

async def get_messages(db: AsyncSession, matter_id: uuid.UUID):
    result = await db.execute(select(Message).where(Message.matter_id == matter_id).order_by(Message.created_at.asc()))
    return result.scalars().all()

async def add_document(db: AsyncSession, matter_id: uuid.UUID, filename: str):
    doc = Document(matter_id=matter_id, filename=filename)
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc

async def get_documents(db: AsyncSession, matter_id: uuid.UUID):
    result = await db.execute(select(Document).where(Document.matter_id == matter_id))
    return result.scalars().all()

async def add_retrieved_clause(db: AsyncSession, matter_id: uuid.UUID, source: str, clause_number: str, title: str):
    clause = RetrievedClause(matter_id=matter_id, source_document=source, clause_number=clause_number, title=title)
    db.add(clause)
    await db.commit()
    await db.refresh(clause)
    return clause

async def get_retrieved_clauses(db: AsyncSession, matter_id: uuid.UUID):
    result = await db.execute(select(RetrievedClause).where(RetrievedClause.matter_id == matter_id))
    return result.scalars().all()
