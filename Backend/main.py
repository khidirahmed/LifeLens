"""
LifeLens FastAPI Backend
------------------------
iPhone ↔ MongoDB ↔ FastAPI ↔ Hex

Run:
    cp .env.example .env        # fill in your values
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import connect_db, close_db
from routes.auth_routes  import router as auth_router
from routes.video_routes import router as video_router

load_dotenv()   # reads .env file


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    yield
    await close_db()


app = FastAPI(
    title="LifeLens API",
    version="0.2.0",
    description="Elderly safety monitoring — video upload + analysis",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(video_router)


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "service": "LifeLens API", "version": "0.2.0"}
