from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Depends
from fastapi.responses import JSONResponse
from app.vectorstore.index import VectorStore
from app.utils.helpers import (
    read_document,
    chunk_text,
    clean_text,
    validate_file_extension
)
from app.services.rag_service import RAGService
from app.models.schemas import AnalysisRequest
from pathlib import Path
import shutil
import uuid
import os
from typing import Optional
import logging
from fastapi.security import HTTPBearer
from fastapi import Form
from pydantic import BaseModel

router = APIRouter()
security = HTTPBearer()
logger = logging.getLogger(__name__)

# Configuration
UPLOAD_DIR = Path("data/uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED_EXTENSIONS = {'.pdf', '.docx'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

async def get_vector_store():
    """Dependency for VectorStore with error handling"""
    try:
        return VectorStore()
    except Exception as e:
        logger.error(f"VectorStore initialization failed: {str(e)}")
        raise HTTPException(status_code=500, detail="VectorStore unavailable")

@router.post("/upload-regulation")
async def upload_regulation(
    file: UploadFile = File(...),
    vs: VectorStore = Depends(get_vector_store),
    #token: str = Depends(security)
):
    """Upload compliance document (GDPR, CCPA, etc.)"""
    return await _process_upload(file, vs, "compliance")

class TextUploadRequest(BaseModel):
    text: str

@router.post("/upload-contract")
async def upload_contract(
    file: UploadFile = File(None),
    text: str = Form(None),
    vs: VectorStore = Depends(get_vector_store)
):
    """Handle both file and text uploads"""
    try:
        if file:
            # Process file upload
            return await _process_upload(file, vs, "contract")
        elif text:
            # Process direct text
            file_id = str(uuid.uuid4())
            chunks = chunk_text(text, "contract")

            batch_objects = [{
                "text": chunk,
                "doc_type": "contract",
                "section": f"upload_{file_id[:8]}_{i}",
                **metadata
            } for i, (chunk, metadata) in enumerate(chunks)]

            vs.batch_store(batch_objects, class_name="ContractClause")

            return JSONResponse(
                content={
                    "status": "success",
                    "chunks_ingested": len(batch_objects),
                    "document_id": file_id
                },
                status_code=201
            )
        else:
            raise HTTPException(status_code=422, detail="Either file or text must be provided")
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Document processing failed")


async def _process_upload(file: UploadFile, vs: VectorStore, doc_type: str):
    """Shared upload processing with enhanced validation"""
    try:
        # Validate file
        file_ext = Path(file.filename).suffix.lower()
        validate_file_extension(file_ext, ALLOWED_EXTENSIONS)

        # Check file size
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail=f"File too large. Max size: {MAX_FILE_SIZE/1024/1024}MB")

        # Secure save with unique filename
        file_id = str(uuid.uuid4())
        file_path = UPLOAD_DIR / f"{file_id}{file_ext}"
        logger.info(f"Saving uploaded file to: {file_path.absolute()}")

        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Process and store
        text = clean_text(read_document(file_path))
        chunks = chunk_text(text, doc_type)
        logging.info(f"Generated {len(chunks)} chunks for {doc_type}")
        for i, (chunk, meta) in enumerate(chunks[:3]):  # Print first 3 chunks
            logging.info(f"Chunk {i}: {chunk[:50]}... | Meta: {meta}")

        assert all(isinstance(c, tuple) and isinstance(c[0], str) and isinstance(c[1], dict) for c in chunks), \
            f"Malformed chunks: {chunks[:1]}"

        batch_objects = [{
            "text": chunk,
            "doc_type": doc_type,
            "section": f"upload_{file_id[:8]}_{i}",
            **metadata
        } for i, (chunk, metadata) in enumerate(chunks)]

        # Assign the correct class based on doc_type
        class_name = "ContractClause" if doc_type == "contract" else "ComplianceClause"
        vs.batch_store(batch_objects, class_name=class_name)

        return JSONResponse(
            content={
                "status": "success",
                "chunks_ingested": len(batch_objects),
                "document_type": doc_type,
                "document_id": file_id
            },
            status_code=201
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}")
        if 'file_path' in locals():
            try: os.unlink(file_path)
            except: pass
        raise HTTPException(status_code=500, detail="Document processing failed")

@router.get("/clauses")
async def get_clauses(
    query: str = Query("", min_length=1, max_length=100),
    doc_type: Optional[str] = Query(None, regex="^(contracts|compliance)$"),
    limit: int = Query(10, gt=0, le=100),
    vs: VectorStore = Depends(get_vector_store)
):
    """Search stored clauses with semantic search"""
    try:
        # Vector search
        search_params = {
            "limit": limit,
            "certainty": 0.55  # Tuned threshold
        }

        if query:
            search_params["vector"] = vs.encoder.encode(query).tolist()

        if doc_type:
            search_params["where"] = {
                "path": ["doc_type"],
                "operator": "Equal",
                "valueString": doc_type
            }

        results = vs.client.query\
            .get("ComplianceClause", ["text", "doc_type", "section"])\
            .with_additional(["certainty"])\
            .with_limit(limit)

        if "vector" in search_params:
            results = results.with_near_vector({
                "vector": search_params["vector"],
                "certainty": search_params["certainty"]
            })
        if "where" in search_params:
            results = results.with_where(search_params["where"])

        clauses = results.do()["data"]["Get"]["ComplianceClause"]
        return {"clauses": clauses}

    except Exception as e:
        logger.error(f"Search failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Search operation failed")

def get_rag_service():
    return RAGService()

@router.post("/analyze")
async def analyze_contract(
    request: AnalysisRequest,
    rag: RAGService = Depends(get_rag_service)
):
    """Endpoint for RAG analysis"""
    return rag.analyze_compliance(request.contract_text)
# async def analyze(
#     contract_id: str = Query(..., min_length=8, max_length=36),
#     regulation_id: Optional[str] = Query(None, min_length=8, max_length=36),
#     vs: VectorStore = Depends(get_vector_store)
# ):
#     """Compare contract against regulations with enhanced matching"""
#     try:
#         # Get contract clauses
#         contract_clauses = vs.client.query\
#             .get("ComplianceClause", ["text", "section"]).with_additional(["id"])\
#             .with_where({
#                 "path": ["section"],
#                 "operator": "Like",
#                 "valueString": f"upload_{contract_id[:8]}%"
#             })\
#             .do()

#         # Get relevant regulations
#         regulation_filter = {
#             "path": ["section"],
#             "operator": "Like",
#             "valueString": f"upload_{regulation_id[:8]}%"
#         } if regulation_id else {
#             "path": ["doc_type"],
#             "operator": "Equal",
#             "valueString": "compliance"
#         }

#         regulations = vs.client.query\
#             .get("ComplianceClause", ["text", "doc_type"]).with_additional(["id"])\
#             .with_where(regulation_filter)\
#             .do()

#         # Enhanced analysis - add your compliance logic here
#         analysis = {
#             "contract_id": contract_id,
#             "regulation_id": regulation_id,
#             "contract_clauses_count": len(contract_clauses["data"]["Get"]["ComplianceClause"]),
#             "relevant_regulations_count": len(regulations["data"]["Get"]["ComplianceClause"]),
#             "potential_issues": []  # Add your compliance check results
#         }

#         return analysis

#     except Exception as e:
#         logger.error(f"Analysis failed: {str(e)}")
#         raise HTTPException(status_code=500, detail="Analysis failed")


@router.post("/analyze-contract")
async def analyze_full_contract(
    document_id: str = Query(..., min_length=8, max_length=36),
    vs: VectorStore = Depends(get_vector_store),
    rag: RAGService = Depends(get_rag_service)
):
    try:
        # 1. Get clauses with proper error handling
        result = vs.client.query.get(
            "ContractClause",
            ["text", "section"]
        ).with_where({
            "path": ["section"],
            "operator": "Like",
            "valueString": f"upload_{document_id[:8]}%"
        }).do()

        # Debug: Print raw Weaviate response
        logging.info("Weaviate response:", result)

        # Validate response structure
        if not result.get("data", {}).get("Get", {}).get("ContractClause"):
            raise HTTPException(
                status_code=404,
                detail=f"No clauses found for document {document_id}"
            )

        clauses = result["data"]["Get"]["ContractClause"]

        # 2. Analyze each clause
        results = []
        for clause in clauses:
            analysis = rag.analyze_compliance(clause["text"])
            results.append({
                "clause_text": clause["text"],
                "section": clause.get("section", ""),
                "analysis": analysis
            })

        return {
            "document_id": document_id,
            "clauses_analyzed": len(results),
            "results": results
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analysis failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))