from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from app.database.database import connect_to_mongo, close_mongo_connection, check_connection
from app.routes import user_routes, places_routes, events_routes, feed_routes

import logging
import time

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

# ⭐ NUEVO: Middleware para verificar conexión en cada request
@app.middleware("http")
async def check_db_connection(request: Request, call_next):
    # Solo verificar en rutas de API
    if request.url.path.startswith("/api/"):
        if not check_connection():
            logger.warning("⚠️ Conexión perdida, reintentando...")
            if not connect_to_mongo():
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Servicio temporalmente no disponible. Reintentando conexión..."}
                )
    
    response = await call_next(request)
    return response

# Servir archivos estáticos (avatars)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Iniciando aplicación...")
    max_attempts = 3
    
    for attempt in range(max_attempts):
        if connect_to_mongo():
            logger.info("✅ Aplicación lista")
            return
        
        if attempt < max_attempts - 1:
            wait_time = (attempt + 1) * 2
            logger.warning(f"⏳ Reintentando en {wait_time}s...")
            logger.info(f"🔄 Intento de conexión a MongoDB ({attempt + 2}/{max_attempts})...")
            time.sleep(wait_time)
    
    logger.error("❌ No se pudo conectar a MongoDB. La aplicación puede no funcionar correctamente.")

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
    logger.info("🔍 Verificando estado de salud de la aplicación...")
    connection_status = check_connection()
    
    return {
        "status": "ok" if connection_status else "degraded",
        "database": "connected" if connection_status else "disconnected",
        "timestamp": time.time()
    }

# Incluir routers
app.include_router(user_routes.router, prefix="/api/users", tags=["Users"])
app.include_router(places_routes.router, prefix="/api/places", tags=["Places"])
app.include_router(events_routes.router, prefix="/api/events", tags=["Events"])
app.include_router(feed_routes.router, prefix="/api/feed", tags=["Feed"])