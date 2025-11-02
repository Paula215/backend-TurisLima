from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.user_routes import router as user_router
from app.database.database import connect_to_mongo, close_mongo_connection

app = FastAPI(
    title="TurisLima Backend",
    description="API para gestión de turismo en Lima",
    version="1.0.0"
)

# CORS - Configurar según tus necesidades
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especifica los dominios permitidos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_db_client():
    """Evento que se ejecuta al iniciar la aplicación"""
    connect_to_mongo()

@app.on_event("shutdown")
def shutdown_db_client():
    """Evento que se ejecuta al cerrar la aplicación"""
    close_mongo_connection()

# Incluir routers
app.include_router(user_router, prefix="/api/users", tags=["Users"])

@app.get("/", tags=["Root"])
def root():
    return {
        "message": "Backend TurisLima funcionando 🚀",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/health", tags=["Health"])
def health_check():
    """Endpoint para verificar el estado del servicio"""
    return {
        "status": "healthy",
        "service": "TurisLima Backend"
    }