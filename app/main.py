from fastapi import FastAPI
from app.api.routes import router

app = FastAPI(title="Arden Compliance API")

app.include_router(router)
