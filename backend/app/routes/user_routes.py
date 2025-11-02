from fastapi import APIRouter, HTTPException, status
import bcrypt
from pymongo.errors import DuplicateKeyError
from bson import ObjectId

# IMPORTANTE: Importar el módulo completo, no las variables directamente
from app.database import database
from app.models.user_model import UserRegister, UserLogin

router = APIRouter()

# ------------------ Registro ------------------
@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(user: UserRegister):
    """Registra un nuevo usuario"""
    
    # Usar database.users_collection en lugar de users_collection
    if database.users_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    # Hashear contraseña con bcrypt nativo
    password_bytes = user.password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password_bytes, salt)
    
    new_user = {
        "username": user.username,
        "email": user.email,
        "password": hashed_password.decode('utf-8'),
        "gender": user.gender,
        "age": user.age,
        "preferences": user.preferences or [],
        "avatar": None,
        "liked_places": [],
        "liked_events": [],
        "visited_places": [],
        "saved_places": [],
        "interactions": [],
    }
    
    try:
        result = database.users_collection.insert_one(new_user)
        return {
            "message": "Usuario registrado exitosamente",
            "user_id": str(result.inserted_id)
        }
    except DuplicateKeyError as e:
        if "email" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El correo ya está registrado"
            )
        elif "username" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El nombre de usuario ya está en uso"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Error: registro duplicado"
            )

# ------------------ Login ------------------
@router.post("/login")
def login_user(user: UserLogin):
    """Inicia sesión de un usuario"""
    
    if database.users_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    db_user = database.users_collection.find_one({"email": user.email})
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    # Verificar contraseña
    password_bytes = user.password.encode('utf-8')
    hashed_password_bytes = db_user["password"].encode('utf-8')
    
    if not bcrypt.checkpw(password_bytes, hashed_password_bytes):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Contraseña incorrecta"
        )
    
    return {
        "message": "Inicio de sesión exitoso",
        "user_id": str(db_user["_id"]),
        "username": db_user["username"],
        "email": db_user["email"]
    }

# ------------------ Obtener usuario por ID ------------------
@router.get("/{user_id}")
def get_user(user_id: str):
    """Obtiene la información de un usuario por su ID"""
    
    if database.users_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    if not ObjectId.is_valid(user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID de usuario inválido"
        )
    
    user = database.users_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    # No devolver la contraseña
    user.pop("password", None)
    user["_id"] = str(user["_id"])
    
    return user