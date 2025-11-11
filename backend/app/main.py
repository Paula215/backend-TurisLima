from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.database.database import connect_to_mongo, close_mongo_connection
from app.routes import user_routes, places_routes, events_routes
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="TurisLima API",
    description="API para turismo en Lima",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir archivos estáticos (avatars)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Iniciando aplicación...")
    connect_to_mongo()

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("👋 Cerrando aplicación...")
    close_mongo_connection()

@app.get("/")
def root():
    return {
        "message": "TurisLima API",
        "status": "running",
        "docs": "/docs"
    }

@app.get("/health")
def health():
    from app.database.database import db
    if db is not None:
        return {"status": "ok", "database": "connected"}
    return {"status": "error", "database": "disconnected"}

# Incluir routers
app.include_router(user_routes.router, prefix="/api/users", tags=["Users"])
app.include_router(places_routes.router, prefix="/api/places", tags=["Places"])
app.include_router(events_routes.router, prefix="/api/events", tags=["Events"])