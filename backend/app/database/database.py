from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from dotenv import load_dotenv
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

def connect_to_mongo():
    """Conecta a MongoDB y configura las colecciones"""
    global client, db, users_collection, places_collection, events_collection
    
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
        
        print(f"✅ Conectado a MongoDB Atlas")
        print(f"📊 users: {users_collection.count_documents({})}, "
              f"places: {places_collection.count_documents({})}, "
              f"events: {events_collection.count_documents({})}")
        
        return True
        
    except ConnectionFailure as e:
        print(f"❌ Error al conectar: {e}")
        return False
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        return False

def close_mongo_connection():
    """Cierra la conexión a MongoDB"""
    global client
    if client:
        client.close()
        print("🔌 Conexión cerrada")

def get_database():
    """Retorna la instancia de la base de datos"""
    return db