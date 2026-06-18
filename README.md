# ClauseCraft Counsel

ClauseCraft Counsel is an AI-powered Construction Contract Intelligence Assistant specifically tailored for analyzing Indian construction contracts, including the **CPWD GCC** and **Railways GCC 2022**. It uses Retrieval-Augmented Generation (RAG) to provide real-time, precision legal analysis for delay claims, extensions of time (EOT), payment disputes, and more.

## Architecture

ClauseCraft is built with a modern, high-performance tech stack:

- **Frontend**: Next.js 15, React 19, Tailwind CSS, shadcn/ui
- **Backend API**: FastAPI (Python), Async SQLAlchemy
- **Database**: PostgreSQL (for transactional Matter/Message persistence)
- **Vector Store**: ChromaDB (for semantic search of contract clauses)
- **Embeddings**: `nvidia/llama-nemotron-embed-1b-v2` (Nvidia NIM)
- **Reasoning Engine**: `meta/llama-3.3-70b-instruct` (Nvidia NIM)

### Key Features
1. **Intelligent Contract Routing**: The backend employs a lightweight Rule-Based Router to instantly detect whether a dispute falls under CPWD or Railways based on conversational context.
2. **Isolated RAG Pipelines**: ClauseCraft never mixes clauses from different contract families. If you are discussing a CPWD dispute, it explicitly searches only the CPWD GCC.
3. **Structured Legal Analysis**: Responses are strictly formatted into Issue Summaries, Applicable Clauses, Contractor/Employer Positions, Risk Assessments, and Recommended Actions.
4. **Persistent Matter Storage**: All conversations, retrieved clauses, and uploaded documents are saved to a PostgreSQL database and instantly retrievable from the frontend sidebar.

## Prerequisites

- **Node.js** (v18+)
- **Python** (3.10+)
- **Docker** & **Docker Compose** (for PostgreSQL)
- **Nvidia API Key** (for NIM embeddings and inference)

## Setup & Installation

### 1. Environment Variables
In the `backend` directory, create a `.env` file and add your Nvidia API Key:
```env
NVIDIA_API_KEY=nvapi-your-key-here
```

### 2. Start PostgreSQL Database
ClauseCraft requires a PostgreSQL database to store "Matters" and "Messages".
```bash
cd backend
docker-compose up -d
```
*(This will spin up `clausecraft_db` on port 5432 and `pgAdmin` on port 5050).*

### 3. Initialize the Backend
Set up your Python virtual environment, install dependencies, and run database migrations.
```bash
cd backend
python -m venv venv
venv\Scripts\activate  # On Windows
pip install -r requirements.txt

# Run Alembic migrations to build the DB schema
alembic upgrade head
```

### 4. Ingest Contract Data (ChromaDB)
ClauseCraft needs to embed the standard GCC documents into the vector database before it can answer questions.
```bash
cd backend
python ingest.py
```
*(Ensure `CPWD GCC.pdf` and `RAILWAYS GCC-2022.pdf` are located in `backend/data/` before running this).*

### 5. Start the FastAPI Server
```bash
cd backend
uvicorn main:app --reload
```
The API will run on `http://localhost:8000`.

### 6. Start the Next.js Frontend
In a new terminal window, initialize the frontend:
```bash
cd clausecraft
npm install
npm run dev
```
The application will be accessible at `http://localhost:3000/counsel`.

## Usage

1. Open `http://localhost:3000/counsel`.
2. Begin a new conversation by describing your dispute. For example: 
   *"I am a contractor facing a delay claim due to rain. How does this apply under CPWD?"*
3. The **Contract Router** will automatically detect "CPWD", filter the vector search, and generate a structured legal assessment.
4. Your matter is automatically saved to the PostgreSQL database and will appear in the left sidebar for future reference.
