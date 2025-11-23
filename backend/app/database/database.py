from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, AutoReconnect
from dotenv import load_dotenv
import os
import time
import logging

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Variables globales
client = None
db = None
users_collection = None
places_collection = None
events_collection = None
combined_collection = None

def connect_to_mongo(max_retries=3):
    global client, db, users_collection, places_collection, events_collection, combined_collection
    
    for attempt in range(max_retries):
        try:
            logger.info(f"🔄 Intento de conexión a MongoDB ({attempt + 1}/{max_retries})...")
            
            # ✅ CONFIGURACIÓN OPTIMIZADA PARA WSL + ATLAS
            client = MongoClient(
                MONGO_URI,
                # Timeouts más cortos para fallar rápido
                serverSelectionTimeoutMS=10000,
                connectTimeoutMS=10000,
                socketTimeoutMS=10000,
                
                # Configuración de pool más robusta
                maxPoolSize=10,
                minPoolSize=2,
                maxIdleTimeMS=45000,
                
                # Retry automático
                retryWrites=True,
                retryReads=True,
                
                # Write concern
                w='majority',
                wtimeoutMS=10000,
                
                # Compresión para reducir latencia
                compressors='snappy,zlib',
                
                # ⭐ NUEVO: Configuración para mejor manejo de DNS en WSL
                directConnection=False,
                appName='TurisLima-Backend',
            )
            
            # Test de conexión con timeout
            client.admin.command('ping', maxTimeMS=5000)
            
            db = client[DB_NAME]
            
            users_collection = db["users"]
            places_collection = db["places"]
            events_collection = db["events"]
            combined_collection = db["combined"]
            
            logger.info(f"✅ Conectado a MongoDB Atlas exitosamente")
            return True
            
        except ConnectionFailure as e:
            logger.error(f"❌ Error de conexión (intento {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2  # Backoff exponencial
                logger.info(f"⏳ Reintentando en {wait_time} segundos...")
                time.sleep(wait_time)
            else:
                logger.error("❌ No se pudo conectar después de varios intentos")
                logger.info("\n💡 Posibles soluciones:")
                logger.info("1. Verifica tu conexión a internet")
                logger.info("2. Verifica que tu IP esté permitida en MongoDB Atlas")
                logger.info("3. Revisa /etc/resolv.conf en WSL")
                logger.info("4. Intenta: sudo systemctl restart systemd-resolved")
                return False
            
        except Exception as e:
            logger.error(f"❌ Error inesperado: {e}")
            return False
    
    return False

def get_collections():
    """Retorna todas las colecciones con validación"""
    # Si las colecciones son None, intentar reconectar
    if users_collection is None:
        logger.warning("⚠️ Colecciones no inicializadas, intentando reconectar...")
        if not connect_to_mongo():
            raise ConnectionError("No se pudo establecer conexión con MongoDB")
    
    return {
        "users": users_collection,
        "places": places_collection,
        "events": events_collection,
        "combined": combined_collection
    }

def get_collections_dependency():
    """Dependencia de FastAPI que retorna las colecciones de MongoDB con manejo de errores."""
    try:
        collections = get_collections()
        
        if collections["users"] is None:
            raise ConnectionError("MongoDB collections are not initialized.")
            
        return collections
    except Exception as e:
        logger.error(f"❌ Error obteniendo colecciones: {e}")
        # Intentar reconectar
        connect_to_mongo()
        return get_collections()

def close_mongo_connection():
    """Cierra la conexión a MongoDB"""
    global client
    if client:
        try:
            client.close()
            logger.info("🔌 Conexión cerrada correctamente")
        except Exception as e:
            logger.error(f"Error cerrando conexión: {e}")

def get_database():
    """Retorna la instancia de la base de datos"""
    if db is None:
        logger.warning("⚠️ Base de datos no inicializada, reconectando...")
        connect_to_mongo()
    return db

def check_connection():
    """Verifica si la conexión está activa"""
    try:
        if client is not None:
            client.admin.command('ping', maxTimeMS=2000)
            return True
    except Exception:
        return False
    return False