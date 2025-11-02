from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from dotenv import load_dotenv
import os

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")

# Variables globales - inicialmente None
client = None
db = None
users_collection = None
places_collection = None
events_collection = None

def connect_to_mongo():
    """Conecta a MongoDB y configura las colecciones"""
    global client, db, users_collection, places_collection, events_collection
    
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        
        db = client[DB_NAME]
        
        users_collection = db["users"]
        places_collection = db["places"]
        events_collection = db["events"]
        
        try:
            users_collection.create_index("email", unique=True)
            users_collection.create_index("username", unique=True)
            places_collection.create_index("place_id", unique=True)
            events_collection.create_index("event_id", unique=True)
        except Exception as idx_error:
            print(f"⚠️  Advertencia al crear índices: {idx_error}")
        
        print("✅ Conectado exitosamente a Mongo Atlas")
        return True
        
    except ConnectionFailure as e:
        print(f"❌ Error al conectar a MongoDB: {e}")
        return False
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        return False

def close_mongo_connection():
    """Cierra la conexión a MongoDB"""
    global client
    if client:
        client.close()
        print("🔌 Conexión a MongoDB cerrada")

def get_database():
    """Retorna la instancia de la base de datos"""
    return db