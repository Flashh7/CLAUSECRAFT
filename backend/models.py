import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime, timedelta

class Matter(Base):
    __tablename__ = "matters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, default="New Dispute")
    matter_type = Column(String, default="Pending")
    risk_level = Column(String, default="Unknown")
    confidence = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = Column(DateTime, default=lambda: datetime.utcnow() + timedelta(hours=24))
    session_id = Column(String, index=True, nullable=True)

    messages = relationship("Message", back_populates="matter", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="matter", cascade="all, delete-orphan")
    retrieved_clauses = relationship("RetrievedClause", back_populates="matter", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    matter_id = Column(UUID(as_uuid=True), ForeignKey("matters.id"), nullable=False)
    role = Column(String, nullable=False) # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    matter = relationship("Matter", back_populates="messages")

class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    matter_id = Column(UUID(as_uuid=True), ForeignKey("matters.id"), nullable=False)
    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=True)
    metadata_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    matter = relationship("Matter", back_populates="documents")

class RetrievedClause(Base):
    __tablename__ = "retrieved_clauses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    matter_id = Column(UUID(as_uuid=True), ForeignKey("matters.id"), nullable=False)
    source_document = Column(String)
    clause_number = Column(String)
    title = Column(String)
    retrieved_at = Column(DateTime, default=datetime.utcnow)

    matter = relationship("Matter", back_populates="retrieved_clauses")
