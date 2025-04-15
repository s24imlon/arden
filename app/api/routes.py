from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse

router = APIRouter()


@router.post("/upload-regulation")
async def upload_regulation(file: UploadFile = File(...)):
    return JSONResponse(content={"message": "Regulation uploaded (stub)"})


@router.post("/upload-contract")
async def upload_contract(file: UploadFile = File(...)):
    return JSONResponse(content={"message": "Contract uploaded (stub)"})


@router.post("/analyze")
async def analyze():
    return JSONResponse(content={"message": "Analysis started (stub)"})


@router.get("/clauses")
async def get_clauses():
    return JSONResponse(content={"clauses": []})
