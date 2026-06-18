import os
import json
import asyncio
import uuid
import re
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
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
from database import get_db, Base, engine
import crud

# Load environment variables
load_dotenv()

app = FastAPI(title="ClauseCraft Counsel API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
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

class ContractRouter:
    @staticmethod
    def route(query: str, history: List['ChatMessage']) -> dict:
        query_lower = query.lower()
        # Also check last few messages in history for context if needed
        context_str = " ".join([m.content.lower() for m in history[-3:]]) + " " + query_lower
        
        # 1. Detect Contract Source
        source = "Unknown"
        if "cpwd" in context_str:
            source = "CPWD"
        elif "railway" in context_str or "railways" in context_str or "iricen" in context_str:
            source = "Railways"
        elif "uploaded" in context_str or "custom" in context_str or "epc" in context_str or "fidic" in context_str:
            source = "Custom"
            
        # 2. Detect Retrieval Necessity
        requires_retrieval = True
        greetings = ["hello", "hi", "hey", "good morning", "good afternoon"]
        if query_lower.strip() in greetings or len(query_lower.split()) < 4:
            requires_retrieval = False
            
        # 3. Detect Matter Type
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
            
        return {
            "source": source,
            "requires_retrieval": requires_retrieval,
            "matter_type": matter_type
        }

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    matter_id: Optional[str] = None
    messages: List[ChatMessage]
    conversation_history: Optional[List[Dict[str, Any]]] = []
    uploaded_documents: Optional[List[Dict[str, Any]]] = []

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "ClauseCraft Counsel Engine"}

@app.get("/api/matters")
async def get_recent_matters(db: AsyncSession = Depends(get_db)):
    matters = await crud.get_matters(db)
    return [{"id": str(m.id), "title": m.title, "date": m.updated_at.isoformat()} for m in matters]

@app.get("/api/matters/{matter_id}")
async def get_matter_details(matter_id: str, db: AsyncSession = Depends(get_db)):
    try:
        m_id = uuid.UUID(matter_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid matter_id format")
    
    matter = await crud.get_matter(db, m_id)
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")
        
    messages = await crud.get_messages(db, m_id)
    clauses = await crud.get_retrieved_clauses(db, m_id)
    docs = await crud.get_documents(db, m_id)
    
    return {
        "id": str(matter.id),
        "title": matter.title,
        "metadata": {
            "matterType": matter.matter_type,
            "riskLevel": matter.risk_level,
            "confidence": matter.confidence,
            "clauses": [{"source": c.source_document, "clause_number": c.clause_number, "title": c.title} for c in clauses],
            "timeline": [],
            "documents": [{"name": d.filename} for d in docs]
        },
        "messages": [{"id": str(msg.id), "role": msg.role, "content": msg.content} for msg in messages]
    }

async def generate_chat_stream(request: ChatRequest, db: AsyncSession):
    def format_sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    last_user_msg = next((m.content for m in reversed(request.messages) if m.role == "user"), "")
    
    # Run the Lightweight Router
    router_decision = ContractRouter.route(last_user_msg, request.messages)
    is_greeting = not router_decision["requires_retrieval"]

    # 1. Matter Management
    matter_id = None
    try:
        if request.matter_id and request.matter_id != "m-1234" and request.matter_id != "":
            matter_id = uuid.UUID(request.matter_id)
            matter = await crud.get_matter(db, matter_id)
            if not matter:
                matter = await crud.create_matter(db, title=last_user_msg[:30] + "...")
                matter_id = matter.id
            else:
                # Update matter type based on router if it's currently Pending
                if matter.matter_type == "Pending" and router_decision["matter_type"] != "General Query":
                    matter.matter_type = router_decision["matter_type"]
                    await db.commit()
        else:
            matter = await crud.create_matter(db, title=last_user_msg[:30] + "...")
            matter_id = matter.id
    except ValueError:
        matter = await crud.create_matter(db, title=last_user_msg[:30] + "...")
        matter_id = matter.id

    # 2. Store User Message
    await crud.add_message(db, matter_id, "user", last_user_msg)

    retrieved_docs = []
    actual_clauses = []
    
    if not is_greeting:
        yield format_sse("status", {"stage": f"Classifying Dispute: {router_decision['matter_type']}"})
        await asyncio.sleep(0.5)
        
        if router_decision["source"] == "Unknown":
            # Bypass retrieval, ask user
            yield format_sse("status", {"stage": "Clarification Required"})
            # No retrieval docs
        else:
            yield format_sse("status", {"stage": f"Searching {router_decision['source']} Clauses..."})
            if retriever:
                search_kwargs = {"k": 5}
                if router_decision["source"] == "CPWD":
                    search_kwargs["filter"] = {"source_document": "CPWD GCC.pdf"}
                elif router_decision["source"] == "Railways":
                    search_kwargs["filter"] = {"source_document": "RAILWAYS GCC-2022.pdf"}
                # If Custom, we would ideally filter by uploaded docs. For now, empty filter.
                
                retriever.search_kwargs = search_kwargs
                retrieved_docs = retriever.invoke(last_user_msg)
                
                # Store retrieved clauses
                for doc in retrieved_docs:
                    await crud.add_retrieved_clause(
                        db, 
                        matter_id, 
                        doc.metadata.get("source_document", "Unknown"),
                        doc.metadata.get("clause_number", "Unknown"),
                        doc.metadata.get("clause_title", "Unknown")
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
            "timeline": [],
            "documents": request.uploaded_documents or []
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

    # Add historical messages from DB to context
    db_messages = await crud.get_messages(db, matter_id)
    for msg in db_messages:
        api_messages.append({"role": msg.role, "content": msg.content})

    full_response = ""
    try:
        completion = client.chat.completions.create(
            model="meta/llama-3.3-70b-instruct", # Switched back to LLaMA for speed and capability
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
    await crud.add_message(db, matter_id, "assistant", full_response)

    yield format_sse("done", {})

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    return StreamingResponse(generate_chat_stream(request, db), media_type="text/event-stream")

@app.post("/api/upload")
async def upload_document(matter_id: str, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    try:
        m_id = uuid.UUID(matter_id)
        await crud.add_document(db, m_id, file.filename)
    except ValueError:
        pass
    return {
        "matter_id": matter_id, 
        "filename": file.filename, 
        "status": "processed"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
