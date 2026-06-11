# 🤖 AI-Powered Document Intelligence Platform (Vectorless RAG)

An advanced AI-powered Document Intelligence Platform built using Python, FastAPI, LLMs, and a Vectorless RAG architecture. The system enables users to upload documents, ask questions, generate summaries, compare files, create knowledge maps, extract timelines, and interact using both text and voice.

---

## 🚀 Features

### 📄 Document Management
- Upload PDF and TXT documents
- Automatic document parsing and chunking
- Document indexing and retrieval
- Persistent document workspace

### 💬 Intelligent Chat
- Document-grounded Question Answering
- Strict Mode (Document Only)
- Optional Mode (Document + General Knowledge)
- General Mode (LLM Only)
- Conversation history support

### 📝 Notebook Module
- AI-generated notes
- Save and manage notes
- Export notes to PDF and DOCX

### 🔍 Compare Module
- Side-by-side document comparison
- Similarity and difference analysis
- Topic-based comparison

### 🧠 Knowledge Map
- Concept extraction
- Entity relationship visualization
- Interactive graph generation

### 📅 Timeline Generator
- Event extraction from documents
- Chronological timeline creation
- Date and milestone detection

### 🛠️ Tools Module
- Document summarization
- Keyword extraction
- Retrieval explanation
- Productivity utilities

### 🎙️ Voice AI Integration
- Speech-to-Text (Whisper)
- Text-to-Speech (SpeechT5)
- Voice-to-Voice interactions
- Audio preprocessing and format conversion

### 🖼️ AI Utilities
- Image generation support
- Document insights and analysis

---

## 🏗️ Architecture

```
User
 │
 ▼
Frontend (HTML, CSS, JavaScript)
 │
 ▼
FastAPI Backend
 │
 ├── Authentication
 ├── Document Upload
 ├── RAG Retrieval Engine
 ├── LLM Processing
 ├── Voice Processing
 ├── Knowledge Extraction
 └── Notes & Export Services
 │
 ▼
OpenRouter / Gemini Models
```

---

## 🧠 Vectorless RAG Workflow

Unlike traditional RAG systems that rely on vector databases, this project uses a PageIndex-style Vectorless Retrieval approach.

1. Upload Document
2. Parse Content
3. Build Hierarchical Page Tree
4. Navigate Through Relevant Sections
5. Retrieve Context
6. Generate Grounded Response

Benefits:
- No vector database required
- Lower infrastructure cost
- Explainable retrieval process
- Faster setup and maintenance

---

## 🛠️ Tech Stack

### Backend
- Python
- FastAPI
- LangChain
- LangGraph

### AI Models
- Google Gemini
- OpenRouter
- Whisper (STT)
- SpeechT5 (TTS)

### Frontend
- HTML
- CSS
- JavaScript

### Document Processing
- PyPDF
- python-docx
- FPDF

### Testing
- Pytest
- FastAPI TestClient

---

## 📂 Project Structure

```bash
Rag/
│
├── frontend/
│   ├── index.html
│   ├── css/
│   └── js/
│
├── src/rag/
│   ├── api.py
│   ├── answer.py
│   ├── auth.py
│   ├── ingest.py
│   ├── vectorless_retrieval.py
│   ├── page_tree.py
│   ├── document_compare.py
│   ├── knowledge_map.py
│   ├── timeline_extract.py
│   ├── notes_generator.py
│   ├── stt.py
│   ├── tts.py
│   └── server.py
│
├── tests/
├── sample_docs/
└── README.md
```

---

## ⚙️ Installation

### Clone Repository

```bash
git clone <repository-url>
cd Rag
```

### Create Virtual Environment

```bash
python -m venv .venv
```

### Activate Environment

Windows:

```bash
.venv\Scripts\activate
```

Linux/Mac:

```bash
source .venv/bin/activate
```

### Install Dependencies

```bash
pip install -e .
```

### Configure Environment Variables

Create a `.env` file:

```env
OPENROUTER_API_KEY=your_api_key
```

---

## ▶️ Run Application

### Ingest Documents

```bash
rag ingest sample_docs --user demo
```

### Start Server

```bash
rag serve
```

Open:

```text
http://127.0.0.1:8000
```

Demo Login:

```text
Username: demo
Password: demo123
```

---

## 🧪 Testing

Run all tests:

```bash
pytest
```

Tests cover:
- API functionality
- Retrieval pipeline
- Document comparison
- Knowledge maps
- Timeline extraction
- Voice modules
- Guardrails
- Summarization

---

## 🎯 Key Learning Outcomes

- Retrieval-Augmented Generation (RAG)
- LangChain & LangGraph
- FastAPI Development
- LLM Integration
- Voice AI (STT & TTS)
- Document Intelligence Systems
- Testing & Quality Assurance
- Performance Optimization
- Software Architecture Design

---

## 👨‍💻 Author

**Dirgha**
AI/ML Intern

Built as part of an AI Development Internship focused on Document Intelligence, Retrieval-Augmented Generation, Voice AI, and Machine Learning Systems.
