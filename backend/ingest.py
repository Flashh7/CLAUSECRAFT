import os
import re
from pathlib import Path
from dotenv import load_dotenv

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

load_dotenv()

# Initialize Nvidia Embeddings natively
embeddings = NVIDIAEmbeddings(
    model="nvidia/llama-nemotron-embed-1b-v2",
    api_key=os.getenv("NVIDIA_API_KEY"),
    truncate="END"
)

CHROMA_DIR = "./chroma_db"
DATA_DIR = Path("./data")

def extract_clause_metadata(text: str):
    """
    Attempts to extract clause number and title from text.
    Example: 'CLAUSE 17 Extension of Time' or '17.2 Liquidated Damages'
    """
    clause_number = "Unknown"
    clause_title = "Unknown"
    
    # Matches 'CLAUSE 17' or 'Clause 17.2'
    match = re.search(r'(?i)(?:clause)\s*([0-9\.]+)', text)
    if not match:
        # Matches standalone '17.2' at start of text block
        match = re.match(r'^\s*([0-9]+\.[0-9]+)', text)
    
    if match:
        clause_number = match.group(1)
        # Attempt to grab the next few words as title
        title_match = re.search(re.escape(match.group(0)) + r'\s+([^\n\.]+)', text)
        if title_match:
            clause_title = title_match.group(1).strip()[:50] # Keep it short
            
    return clause_number, clause_title

def parse_and_chunk_pdf(pdf_path: Path):
    print(f"Loading {pdf_path.name}...")
    loader = PyPDFLoader(str(pdf_path))
    pages = loader.load()
    
    full_text = "\n".join([p.page_content for p in pages])
    
    # 1. Clause-Aware Splitting
    # We look for "CLAUSE <number>" or specific header patterns to split.
    # This regex looks for 'CLAUSE X' or 'Clause X' as a boundary.
    clause_pattern = re.compile(r'(?i)(?=\n\s*clause\s+[0-9]+)')
    
    raw_chunks = clause_pattern.split(full_text)
    
    # If the document didn't have explicit "CLAUSE X" markers, the split length will be very small
    # and we fallback to recursive text splitting.
    fallback_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=200,
        separators=["\n\n", "\n", ".", " ", ""]
    )
    
    documents = []
    chunk_counter = 1
    
    for chunk_text in raw_chunks:
        if len(chunk_text.strip()) < 50:
            continue
            
        # Extract metadata from this specific chunk
        c_num, c_title = extract_clause_metadata(chunk_text)
        
        # If the chunk is still massively huge (e.g., regex failed to find enough clauses), 
        # apply recursive splitting to this chunk.
        if len(chunk_text) > 4000:
            sub_chunks = fallback_splitter.split_text(chunk_text)
            for sub_text in sub_chunks:
                doc = Document(
                    page_content=sub_text,
                    metadata={
                        "source_document": pdf_path.name,
                        "clause_number": c_num,
                        "clause_title": c_title,
                        "page_number": "N/A", # Complex to map page exact after string join
                        "chunk_id": f"{pdf_path.name}-chunk-{chunk_counter}"
                    }
                )
                documents.append(doc)
                chunk_counter += 1
        else:
            doc = Document(
                page_content=chunk_text,
                metadata={
                    "source_document": pdf_path.name,
                    "clause_number": c_num,
                    "clause_title": c_title,
                    "page_number": "N/A",
                    "chunk_id": f"{pdf_path.name}-chunk-{chunk_counter}"
                }
            )
            documents.append(doc)
            chunk_counter += 1
            
    return documents

def build_vector_store():
    all_docs = []
    for pdf_file in DATA_DIR.glob("*.pdf"):
        docs = parse_and_chunk_pdf(pdf_file)
        all_docs.extend(docs)
        print(f"Extracted {len(docs)} chunks from {pdf_file.name}")
        
    print(f"Total chunks to embed: {len(all_docs)}")
    print("Initializing ChromaDB and creating embeddings. This may take a moment...")
    
    # Initialize ChromaDB
    vectorstore = Chroma.from_documents(
        documents=all_docs,
        embedding=embeddings,
        persist_directory=CHROMA_DIR
    )
    print("Vector store created successfully at ./chroma_db !")

if __name__ == "__main__":
    build_vector_store()
