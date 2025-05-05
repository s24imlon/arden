# Arden

**Arden** is an intelligent, LLM-powered compliance assistant that helps professionals review legal contracts for alignment with regulations.

## 🔍 Overview

Unlike traditional rule-based compliance checkers, Arden uses modern Large Language Models (LLMs) and Retrieval-Augmented Generation (RAG) to understand the **intent** behind regulatory standards. This enables more nuanced, context-aware compliance checking that goes beyond simple keyword matching.


## 📋 Installation

```bash
# Clone the repository
git clone https://github.com/s24imlon/arden.git
cd arden

```

## 🚀 Getting Started

### Prerequisites

- Python 3.8+
- API key for your preferred LLM provider
- Docker

### Configuration

Set the following in your `.env` file:

```
GROQ_API_KEY=your_api_key_here
```

### Running Locally (Streamlit Demo)

1. Ensure your compliance document is in data/compliance/

2. Run the following
```bash
docker-compose build
docker-compose up -d

```
3. Go to http://localhost:8501/ and upload your contract.


## Project Structure

```
arden/
├── app/
│   ├── main.py                 # FastAPI entrypoint
│   ├── api/                    # API routes
│   │   └── routes.py
│   ├── frontend/               # Streamlit
│   │   ├── streamlit_app.py
│   │   ├── streamlit_Dockerfile
│   │   └── streamlit_requirements.txt
│   ├── models/                 # Pydantic
│   │   └── schemas.py
│   ├── services/               # Core logic
│   │   └── rag_services.py     # Vector search + retrieval logic
│   ├── vectorstore/
│   │   └── index.py
│   └── utils/
│      └── helpers.py          # Text splitting, cleaning, parsing, etc.
│
├── data/
│   ├── contracts/
│   ├── compliance/
│   └── uploads/
│
├── scripts/
│   └── ingest_docs.py          # CLI script to embed and index docs
│
├── .env                        # Environment variables
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Docker container for backend
├── docker-compose.yml          # Vector DB + Backend services
├── README.md
└── .gitignore
```