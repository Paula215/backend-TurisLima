from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from dotenv import load_dotenv
from fastapi import Depends
import os

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")

# Variables globales
client = None
db = None
users_collection = None
places_collection = None
events_collection = None
combined_collection = None

def connect_to_mongo():
    global client, db, users_collection, places_collection, events_collection, combined_collection
    
    try:
        print("🔄 Conectando a MongoDB...")
        client = MongoClient(
            MONGO_URI, 
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            socketTimeoutMS=5000
        )
        
        client.admin.command('ping')
        
        db = client[DB_NAME]
        
        users_collection = db["users"]
        places_collection = db["places"]
        events_collection = db["events"]
        combined_collection = db["combined"]   # <--- ahora sí global
        
        print(f"✅ Conectado a MongoDB Atlas")
        
        return True
        
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        return False

        
    except ConnectionFailure as e:
        print(f"❌ Error al conectar: {e}")
        return False
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        return False

def get_collections():
    """Retorna todas las colecciones"""
    return {
        "users": users_collection,
        "places": places_collection,
        "events": events_collection,
        "combined": combined_collection
    }

def get_collections_dependency():
    """Dependencia de FastAPI que retorna las colecciones de MongoDB."""
    collections = get_collections()
    
    # ... (Tu lógica de verificación de seguridad)
    if collections["users"] is None:
        raise ConnectionError("MongoDB collections are not initialized.")
        
    return collections

def close_mongo_connection():
    """Cierra la conexión a MongoDB"""
    global client
    if client:
        client.close()
        print("🔌 Conexión cerrada")

def get_database():
    """Retorna la instancia de la base de datos"""
    return db