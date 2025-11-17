from fastapi import APIRouter, HTTPException, status, Body 
import bcrypt
from app.database.database import users_collection
from pymongo.errors import DuplicateKeyError
from bson import ObjectId
from typing import List, Optional

# IMPORTANTE: Importar el módulo completo, no las variables directamente
from app.database import database
from app.models.user_model import UserRegister, UserLogin

router = APIRouter()

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(user: UserRegister):
    """Registra un nuevo usuario"""
    
    if database.users_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    password_bytes = user.password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password_bytes, salt)
    
    new_user = {
        "username": user.username,
        "email": user.email,
        "password": hashed_password.decode('utf-8'),
        "gender": user.gender,
        "age": user.age,
        "avatar": None,
        "likes": [],
        "visits": [],
        "saves": [],
        "interactions": [],
        "recommendations": [],
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

# ==================== USUARIOS ====================

@router.get("/all")
def get_all_users():
    """Obtiene todos los usuarios registrados"""
    
    if database.users_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    users = []
    for user in database.users_collection.find({}, {"password": 0}):
        user["_id"] = str(user["_id"])
        users.append(user)
    
    return {"total": len(users), "users": users}

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
    
    user.pop("password", None)
    user["_id"] = str(user["_id"])
    
    return user

@router.put("/{user_id}")
def update_user(user_id: str, updates: dict):
    """Actualiza información del usuario"""
    
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
    
    # No permitir actualizar ciertos campos
    forbidden_fields = ["_id", "password", "email"]
    for field in forbidden_fields:
        if field in updates:
            del updates[field]
    
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No hay campos válidos para actualizar"
        )
    
    result = database.users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": updates}
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    return {"message": "Usuario actualizado exitosamente"}

@router.delete("/{user_id}")
def delete_user(user_id: str):
    """Elimina un usuario"""
    
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
    
    result = database.users_collection.delete_one({"_id": ObjectId(user_id)})
    
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    return {"message": "Usuario eliminado exitosamente"}


@router.post("/{user_id}/saves/{combined_id}")
def save_place(user_id: str, combined_id: str):
    """Guarda un lugar para visitar después"""
    
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
    
    result = database.users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$addToSet": {"saves": combined_id}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    return {"message": "Lugar guardado"}

@router.delete("/{user_id}/saves/{combined_id}")
def unsave_place(user_id: str, combined_id: str):
    """Elimina un lugar guardado"""
    
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
    
    result = database.users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$pull": {"saves": combined_id}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    return {"message": "Lugar eliminado de guardados"}

@router.post("/{user_id}/visits/{combined_id}")
def mark_place_visited(user_id: str, combined_id: str):
    """Marca un lugar como visitado"""
    
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
    
    result = database.users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$addToSet": {"visits": combined_id}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    return {"message": "Lugar marcado como visitado"}

@router.delete("/{user_id}/visits/{combined_id}")
def mark_place_unvisited(user_id: str, combined_id: str):
    """Desmarca un lugar como visitado"""
    
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
    
    result = database.users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$pull": {"visits": combined_id}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    return {"message": "Lugar desmarcado como visitado"}

# ==================== EVENTOS/PLACES ====================

@router.post("/{user_id}/likes/{combined_id}")
def likes(user_id: str, combined_id: str):
    """Añade un evento a los favoritos"""
    
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
    
    result = database.users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$addToSet": {"likes": combined_id}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    return {"message": "Evento añadido a favoritos"}

@router.delete("/{user_id}/likes/{combined_id}")
def unlikes(user_id: str, combined_id: str):
    """Elimina un evento de favoritos"""
    
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
    
    result = database.users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$pull": {"likes": combined_id}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    return {"message": "Evento eliminado de favoritos"}


# ==================== INTERACCIONES ====================

@router.post("/{user_id}/interactions")
def add_interaction(user_id: str, interaction: str):
    """Registra una interacción del usuario para el sistema de recomendaciones"""
    
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
    
    result = database.users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$push": {"interactions": interaction}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    return {"message": "Interacción registrada"}

# ==================== RECOMMENDATIONS ====================

@router.put("/{user_id}/recommendations")
def update_recommendations(user_id: str, data: dict = Body(...)):
    """
    Actualiza o reemplaza completamente las recomendaciones del usuario.
    Espera un JSON como:
    {
        "recommended_ids": ["67300c3c5678abcd9012ef34", "67300d2a9012abcd3456ef78"]
    }
    """
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

    recommended_ids = data.get("recommended_ids")
    if not isinstance(recommended_ids, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El campo 'recommended_ids' debe ser una lista"
        )

    result = database.users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"recommendations": recommended_ids}}
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )

    return {"message": "Recomendaciones actualizadas correctamente"}


@router.get("/{user_id}/recommendations")
def get_recommendations(user_id: str):
    """Obtiene la lista de recomendaciones del usuario"""

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

    user = database.users_collection.find_one(
        {"_id": ObjectId(user_id)},
        {"recommendations": 1}
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )

    return {"recommendations": user.get("recommendations", [])}
