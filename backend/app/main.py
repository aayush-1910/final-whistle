"""
Final Whistle — FastAPI application entry point.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Final Whistle",
    description="Football analytics and season-forecasting API.",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# CORS — allow the local Vite dev server during development.
# Tighten this for production.
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite default
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------
@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "service": "final-whistle"}

