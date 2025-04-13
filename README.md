arden/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI entrypoint
│   ├── api/                    # API routes
│   │   ├── __init__.py
│   │   └── routes.py
│   ├── services/               # Core logic
│   │   ├── __init__.py
│   │   ├── rag.py              # Vector search + retrieval logic
│   │   ├── llm.py              # Call to LLM (e.g., HuggingFace)
│   │   ├── compliance.py       # Analysis functions, scoring, etc.
│   ├── models/                 # Pydantic models for request/response
│   │   ├── __init__.py
│   │   └── schemas.py
│   ├── vectorstore/            # Vector DB setup (FAISS / Chroma)
│   │   └── index.py
│   └── utils/                  # Text splitting, cleaning, parsing, etc.
│       └── helpers.py
│
├── data/
│   ├── contracts/              # Uploaded contract examples
│   ├── compliance/             # Uploaded or referenced regulations
│
├── scripts/
│   ├── ingest_docs.py          # CLI script to embed and index docs
│
├── .env                        # Environment variables
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Docker container for backend
├── docker-compose.yml          # Vector DB + Backend services
├── README.md
└── .gitignore
