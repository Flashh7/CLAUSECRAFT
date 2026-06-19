import os
import json
import asyncio
import uuid
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from openai import OpenAI
from dotenv import load_dotenv

from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings
from langchain_community.vectorstores import Chroma
from sqlalchemy.ext.asyncio import AsyncSession

from prompts import CLAUSECRAFT_SYSTEM_PROMPT
from database import get_db, Base, engine, AsyncSessionLocal
import crud

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Load environment variables
load_dotenv()

# Initialize Rate Limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="ClauseCraft Counsel API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://10.97.201.50:3000",
        "https://clausecraft.ai",
        "https://www.clausecraft.ai"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(
  base_url="https://integrate.api.nvidia.com/v1",
  api_key=os.getenv("NVIDIA_API_KEY")
)

embeddings = NVIDIAEmbeddings(
    model="nvidia/llama-nemotron-embed-1b-v2",
    api_key=os.getenv("NVIDIA_API_KEY"),
    truncate="END"
)

CHROMA_DIR = "./chroma_db"
if os.path.exists(CHROMA_DIR):
    vectorstore = Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
else:
    retriever = None

# Background Task for Hourly Cleanup
async def cleanup_task():
    while True:
        await asyncio.sleep(3600)  # Every hour
        async with AsyncSessionLocal() as db:
            deleted = await crud.cleanup_expired_matters(db)
            if deleted > 0:
                print(f"Cleaned up {deleted} expired matters.")

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_task())

# Middleware for Anonymous Sessions
@app.middleware("http")
async def session_middleware(request: Request, call_next):
    session_id = request.cookies.get("clausecraft_session_id")
    # We will generate a new session_id if missing, but we can't easily set cookies on StreamingResponse from middleware 
    # if it yields. Instead, we'll set it here and let the response object handle it.
    is_new_session = False
    if not session_id:
        session_id = str(uuid.uuid4())
        is_new_session = True
        
    request.state.session_id = session_id
    response = await call_next(request)
    
    if is_new_session:
        response.set_cookie(
            key="clausecraft_session_id", 
            value=session_id, 
            httponly=True, 
            secure=True, 
            samesite="lax",
            max_age=86400  # 24 hours
        )
    return response

class ContractRouter:
    @staticmethod
    def route(query: str, history: List['ChatMessage']) -> dict:
        query_lower = query.lower()
        context_str = " ".join([m.content.lower() for m in history[-3:]]) + " " + query_lower
        
        source = "Unknown"
        if "cpwd" in context_str:
            source = "CPWD"
        elif "railway" in context_str or "railways" in context_str or "iricen" in context_str:
            source = "Railways"
        elif "uploaded" in context_str or "custom" in context_str or "epc" in context_str or "fidic" in context_str:
            source = "Custom"
            
        requires_retrieval = True
        greetings = ["hello", "hi", "hey", "good morning", "good afternoon"]
        if query_lower.strip() in greetings or len(query_lower.split()) < 4:
            requires_retrieval = False
            
        matter_type = "General Query"
        if "delay" in context_str or "eot" in context_str or "extension" in context_str:
            matter_type = "Delay/EOT"
        elif "payment" in context_str or "bill" in context_str:
            matter_type = "Payment"
        elif "arbitration" in context_str or "dispute" in context_str:
            matter_type = "Arbitration"
        elif "terminate" in context_str or "termination" in context_str:
            matter_type = "Termination"
        elif "variation" in context_str or "extra item" in context_str:
            matter_type = "Variation"
            
        return {"source": source, "requires_retrieval": requires_retrieval, "matter_type": matter_type}

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    matter_id: Optional[str] = None
    messages: List[ChatMessage]

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "ClauseCraft Counsel Engine"}

@app.get("/api/matters")
async def get_recent_matters(request: Request, db: AsyncSession = Depends(get_db)):
    session_id = request.state.session_id
    matters = await crud.get_matters(db, session_id=session_id)
    return [{"id": str(m.id), "title": m.title, "date": m.updated_at.isoformat()} for m in matters]

@app.get("/api/matters/{matter_id}")
async def get_matter_details(request: Request, matter_id: str, db: AsyncSession = Depends(get_db)):
    session_id = request.state.session_id
    try:
        m_id = uuid.UUID(matter_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid matter_id format")
    
    matter = await crud.get_matter(db, m_id, session_id=session_id)
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found or expired")
        
    messages = await crud.get_messages(db, m_id, session_id=session_id)
    clauses = await crud.get_retrieved_clauses(db, m_id, session_id=session_id)
    docs = await crud.get_documents(db, m_id, session_id=session_id)
    
    return {
        "id": str(matter.id),
        "title": matter.title,
        "metadata": {
            "matterType": matter.matter_type,
            "riskLevel": matter.risk_level,
            "confidence": matter.confidence,
            "clauses": [{"source": c.source_document, "clause_number": c.clause_number, "title": c.title} for c in clauses],
            "timeline": [],
            "documents": [{"name": d.filename, "metadata_json": d.metadata_json} for d in docs]
        },
        "messages": [{"id": str(msg.id), "role": msg.role, "content": msg.content} for msg in messages]
    }

async def generate_chat_stream(request_data: ChatRequest, db: AsyncSession, session_id: str):
    def format_sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    last_user_msg = next((m.content for m in reversed(request_data.messages) if m.role == "user"), "")
    
    router_decision = ContractRouter.route(last_user_msg, request_data.messages)
    is_greeting = not router_decision["requires_retrieval"]

    # 1. Matter Management
    matter_id = None
    try:
        if request_data.matter_id and request_data.matter_id != "m-1234" and request_data.matter_id != "":
            matter_id = uuid.UUID(request_data.matter_id)
            matter = await crud.get_matter(db, matter_id, session_id=session_id)
            if not matter:
                matter = await crud.create_matter(db, session_id=session_id, title=last_user_msg[:30] + "...")
                matter_id = matter.id
            else:
                if matter.matter_type == "Pending" and router_decision["matter_type"] != "General Query":
                    matter.matter_type = router_decision["matter_type"]
                    await db.commit()
        else:
            matter = await crud.create_matter(db, session_id=session_id, title=last_user_msg[:30] + "...")
            matter_id = matter.id
    except ValueError:
        matter = await crud.create_matter(db, session_id=session_id, title=last_user_msg[:30] + "...")
        matter_id = matter.id

    # 2. Store User Message
    await crud.add_message(db, matter_id, "user", last_user_msg, session_id=session_id)

    retrieved_docs = []
    actual_clauses = []
    
    if not is_greeting:
        yield format_sse("status", {"stage": f"Classifying Dispute: {router_decision['matter_type']}"})
        await asyncio.sleep(0.5)
        
        if router_decision["source"] == "Unknown":
            yield format_sse("status", {"stage": "Clarification Required"})
        else:
            yield format_sse("status", {"stage": f"Searching {router_decision['source']} Clauses..."})
            if retriever:
                search_kwargs = {"k": 5}
                if router_decision["source"] == "CPWD":
                    search_kwargs["filter"] = {"source_document": "CPWD GCC.pdf"}
                elif router_decision["source"] == "Railways":
                    search_kwargs["filter"] = {"source_document": "RAILWAYS GCC-2022.pdf"}
                
                retriever.search_kwargs = search_kwargs
                retrieved_docs = retriever.invoke(last_user_msg)
                
                for doc in retrieved_docs:
                    await crud.add_retrieved_clause(
                        db, 
                        matter_id, 
                        doc.metadata.get("source_document", "Unknown"),
                        doc.metadata.get("clause_number", "Unknown"),
                        doc.metadata.get("clause_title", "Unknown"),
                        session_id=session_id
                    )
            else:
                yield format_sse("status", {"stage": "Vector DB not found. Run ingest.py first!"})
                await asyncio.sleep(1.0)
                
            yield format_sse("status", {"stage": "Reviewing Evidence..."})
            await asyncio.sleep(0.5)
            
            yield format_sse("status", {"stage": "Assessing Risk..."})
            await asyncio.sleep(0.5)

    if not is_greeting:
        for doc in retrieved_docs:
            actual_clauses.append({
                "source": doc.metadata.get("source_document", "Unknown"),
                "clause_number": doc.metadata.get("clause_number", "Unknown"),
                "title": doc.metadata.get("clause_title", "Unknown"),
                "text": doc.page_content
            })
            
        metadata = {
            "matter_id": str(matter_id),
            "matterType": router_decision["matter_type"],
            "riskLevel": "Medium" if actual_clauses else "Unknown",
            "confidence": 85 if len(actual_clauses) > 0 else 20,
            "clauses": actual_clauses,
            "timeline": []
        }
        yield format_sse("metadata", metadata)

        for clause in actual_clauses:
            yield format_sse("citation", {
                "source": clause["source"],
                "clause_number": clause["clause_number"],
                "title": clause["title"]
            })
            await asyncio.sleep(0.1)
    else:
        yield format_sse("metadata", {"matter_id": str(matter_id)})

    if not is_greeting:
        yield format_sse("status", {"stage": "Drafting Legal Analysis..."})
    else:
        yield format_sse("status", {"stage": "Thinking..."})
    
    api_messages = [{"role": "system", "content": CLAUSECRAFT_SYSTEM_PROMPT}]
    
    if router_decision["source"] == "Unknown" and not is_greeting:
        context_injection = "The user has not specified a contract framework. Ask them if their dispute is governed by the CPWD GCC, Railways GCC, or a Custom Contract before providing legal analysis. DO NOT retrieve or analyze yet."
        api_messages.append({"role": "system", "content": context_injection})
    elif not is_greeting and len(retrieved_docs) > 0:
        context_str = "\n\n---\n\n".join([f"Source: {c['source']}\nClause: {c['clause_number']}\nTitle: {c['title']}\nText: {c['text']}" for c in actual_clauses])
        context_injection = f"RETRIEVED {router_decision['source']} CONTRACT CLAUSES:\n\n{context_str}\n\nUse these clauses strictly to formulate your Case Assessment. Do not mix clauses from other sources."
        api_messages.append({"role": "system", "content": context_injection})

    # Add historical messages
    db_messages = await crud.get_messages(db, matter_id, session_id)
    for msg in db_messages:
        api_messages.append({"role": msg.role, "content": msg.content})

    full_response = ""
    try:
        completion = client.chat.completions.create(
            model="meta/llama-3.3-70b-instruct",
            messages=api_messages,
            temperature=0.2,
            top_p=0.7,
            max_tokens=4096,
            stream=True
        )

        for chunk in completion:
            if not chunk.choices:
                continue
            
            content = chunk.choices[0].delta.content
            if content is not None:
                full_response += content
                yield format_sse("content", {"text": content})
                
    except Exception as e:
        error_msg = f"\n\n[Error generating response: {str(e)}]"
        full_response += error_msg
        yield format_sse("content", {"text": error_msg})

    # Save Assistant Response
    await crud.add_message(db, matter_id, "assistant", full_response, session_id)

    yield format_sse("done", {})

def get_session_id(request: Request) -> str:
    return getattr(request.state, "session_id", get_remote_address(request))

@app.post("/api/chat")
@limiter.limit("100/hour", key_func=get_remote_address)
@limiter.limit("20/minute", key_func=get_session_id)
async def chat_endpoint(request: Request, body: ChatRequest, db: AsyncSession = Depends(get_db)):
    session_id = request.state.session_id
    return StreamingResponse(generate_chat_stream(body, db, session_id), media_type="text/event-stream")

from pypdf import PdfReader
import io

@app.post("/api/upload")
@limiter.limit("50/hour", key_func=get_remote_address)
async def upload_document(request: Request, matter_id: str, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    session_id = request.state.session_id
    try:
        m_id = uuid.UUID(matter_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid matter id")

    content = await file.read()
    text_content = ""
    
    # Simple PDF text extraction
    if file.filename.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(content))
        for page in reader.pages[:10]: # Extract first 10 pages for speed/cost
            text_content += page.extract_text() + "\n"
    else:
        try:
            text_content = content.decode("utf-8")[:10000]
        except:
            text_content = ""

    # Run LLM Extraction (Phase 4)
    extracted_data = {}
    if text_content.strip():
        extraction_prompt = """
        You are a Legal AI Assistant. Extract the following information from the provided contract or evidence document.
        Return ONLY valid JSON matching this schema exactly, nothing else:
        {
          "Employer": "Name or null",
          "Contractor": "Name or null",
          "Project Name": "Name or null",
          "Contract Number": "String or null",
          "Contract Value": "String or null",
          "Key Dates": "String or null",
          "Completion Dates": "String or null",
          "Delay Events": "Brief summary or null",
          "Notices": "List of notices or null",
          "Liquidated Damages references": "String or null",
          "Variation references": "String or null"
        }
        
        DOCUMENT TEXT:
        """ + text_content[:15000]

        try:
            completion = client.chat.completions.create(
                model="meta/llama-3.3-70b-instruct",
                messages=[{"role": "user", "content": extraction_prompt}],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            extracted_data = json.loads(completion.choices[0].message.content)
        except Exception as e:
            print("Extraction error:", e)
            extracted_data = {"error": "Extraction failed"}

    doc = await crud.add_document(db, m_id, file.filename, metadata_json=extracted_data, session_id=session_id)
    
    return {
        "matter_id": matter_id, 
        "filename": file.filename, 
        "metadata": extracted_data,
        "status": "processed"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
