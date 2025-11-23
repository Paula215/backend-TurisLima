from fastapi import APIRouter, Depends, HTTPException, status, Body, Query 
import bcrypt
from app.database.database import get_collections_dependency, users_collection
from app.utils.cold_start import initialize_user_recommendations
from app.utils.recommender_engine import update_user_recommendations  
from pymongo.errors import DuplicateKeyError
from bson import ObjectId
from typing import List, Optional
from pydantic import BaseModel

# IMPORTANTE: Importar el módulo completo, no las variables directamente
from app.database import database
from app.models.user_model import UserRegister, UserLogin


router = APIRouter()


@router.get("/ping")
def ping():
    """Endpoint de prueba para verificar que el servicio de usuarios está activo"""
    return {"message": "Pong! User service is active."}\


@router.get("/pingdb")
def ping_db():
    """Verifica la conexión general a MongoDB"""
    try:
        # Comando oficial de prueba
        database.client.admin.command("ping")
        return {"message": "Pong! Database connection is active."}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo conectar con la base de datos"
        )


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(user: UserRegister):
    """Registra un nuevo usuario Y genera recomendaciones iniciales"""
    
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
        "preferences": user.preferences if hasattr(user, 'preferences') else [],
        "avatar": None,
        "likes": [],
        "visits": [],
        "saves": [],
        "interactions": [],
        "recommendations": [],
    }
    
    try:
        result = database.users_collection.insert_one(new_user)
        user_id = str(result.inserted_id)
        
        # 🔥 Generar recomendaciones iniciales
        try:
            rec_result = initialize_user_recommendations(user_id, database.users_collection)
            return {
                "message": "Usuario registrado exitosamente",
                "user_id": user_id,
                "recommendations_initialized": rec_result.get("success", False),
                "num_recommendations": rec_result.get("num_recommendations", 0)
            }
        except Exception as e:
            print(f"⚠️  Error al generar recomendaciones iniciales: {e}")
            return {
                "message": "Usuario registrado exitosamente (sin recomendaciones iniciales)",
                "user_id": user_id
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
def saves(user_id: str, combined_id: str):
    """Añade un item a saved y actualiza recomendaciones unificadas"""

    if database.users_collection is None:
        raise HTTPException(503, "Base de datos no disponible")

    if not ObjectId.is_valid(user_id):
        raise HTTPException(400, "ID de usuario inválido")

    result = database.users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$addToSet": {"saves": combined_id}}
    )

    if result.matched_count == 0:
        raise HTTPException(404, "Usuario no encontrado")

    # 🔥 Recomendaciones unificadas
    try:
        from app.utils.unified_recommender import UnifiedRecommender

        recommender = UnifiedRecommender()
        new_recommendations = recommender.generate_unified_recommendations(
            user_id=user_id,
            users_collection=database.users_collection,
            n_recommendations=20
        )

        database.users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"recommendations": new_recommendations}}
        )

        return {
            "message": "Item guardado",
            "recommendations_updated": True,
            "num_recommendations": len(new_recommendations),
            "recommendation_phase": "cold_start"
                if recommender.is_cold_start_user(user_id, database.users_collection)
                else "hybrid"
        }

    except Exception as e:
        print("⚠️ Error al actualizar recomendaciones (saves):", e)
        return {"message": "Item guardado (recomendaciones no actualizadas)"}

@router.get("/{user_id}/saves")
def get_saves(user_id: str):
    """
    Obtiene los lugares guardados CON información completa (título, imagen, etc.)
    """
    if database.users_collection is None or database.db is None:
        raise HTTPException(503, "Base de datos no disponible")
    
    if not ObjectId.is_valid(user_id):
        raise HTTPException(400, "ID de usuario inválido")
    
    # 1. Obtener usuario y sus saves
    user = database.users_collection.find_one(
        {"_id": ObjectId(user_id)},
        {"saves": 1}
    )
    
    if not user:
        raise HTTPException(404, "Usuario no encontrado")
    
    saved_ids = user.get("saves", [])
    
    if not saved_ids:
        return {
            "success": True,
            "saved_places": [],
            "count": 0
        }
    
    # 2. Convertir IDs a ObjectId
    object_ids = []
    for sid in saved_ids:
        if ObjectId.is_valid(sid):
            object_ids.append(ObjectId(sid))
    
    # 3. Buscar items completos en combined
    combined_col = database.db["combined"]
    items = list(combined_col.find({"_id": {"$in": object_ids}}))
    
    # 4. Formatear respuesta
    formatted_items = []
    for item in items:
        formatted_item = {
            "id": str(item["_id"]),
            "type": item.get("type", "place"),
            "title": item.get("title", "Sin título"),
            "category": item.get("category") or item.get("categoria"),
        }
        
        # Extraer imagen
        if "images" in item and isinstance(item["images"], list) and len(item["images"]) > 0:
            formatted_item["image"] = item["images"][0]
        elif "image" in item:
            formatted_item["image"] = item["image"]
        else:
            formatted_item["image"] = None
        
        formatted_items.append(formatted_item)
    
    return {
        "success": True,
        "saved_places": formatted_items,
        "count": len(formatted_items)
    }

@router.delete("/{user_id}/saves/{combined_id}")
def unsave(user_id: str, combined_id: str):
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
def visits(user_id: str, combined_id: str):
    """Registra una visita y actualiza recomendaciones unificadas"""

    if database.users_collection is None:
        raise HTTPException(503, "Base de datos no disponible")

    if not ObjectId.is_valid(user_id):
        raise HTTPException(400, "ID de usuario inválido")

    result = database.users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$addToSet": {"visits": combined_id}}
    )

    if result.matched_count == 0:
        raise HTTPException(404, "Usuario no encontrado")

    # 🔥 Recomendaciones unificadas
    try:
        from app.utils.unified_recommender import UnifiedRecommender

        recommender = UnifiedRecommender()
        new_recommendations = recommender.generate_unified_recommendations(
            user_id=user_id,
            users_collection=database.users_collection,
            n_recommendations=20
        )

        database.users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"recommendations": new_recommendations}}
        )

        return {
            "message": "Visita registrada",
            "recommendations_updated": True,
            "num_recommendations": len(new_recommendations),
            "recommendation_phase": "cold_start"
                if recommender.is_cold_start_user(user_id, database.users_collection)
                else "hybrid"
        }

    except Exception as e:
        print("⚠️ Error al actualizar recomendaciones (visits):", e)
        return {"message": "Visita registrada (recomendaciones no actualizadas)"}


@router.get("/{user_id}/visits")
def get_visits(user_id: str):
    """
    Obtiene los lugares visitados CON información completa
    """
    if database.users_collection is None or database.db is None:
        raise HTTPException(503, "Base de datos no disponible")
    
    if not ObjectId.is_valid(user_id):
        raise HTTPException(400, "ID de usuario inválido")
    
    # 1. Obtener usuario y sus visits
    user = database.users_collection.find_one(
        {"_id": ObjectId(user_id)},
        {"visits": 1}
    )
    
    if not user:
        raise HTTPException(404, "Usuario no encontrado")
    
    visited_ids = user.get("visits", [])
    
    if not visited_ids:
        return {
            "success": True,
            "visited_places": [],
            "count": 0
        }
    
    # 2. Convertir IDs a ObjectId
    object_ids = []
    for vid in visited_ids:
        if ObjectId.is_valid(vid):
            object_ids.append(ObjectId(vid))
    
    # 3. Buscar items completos en combined
    combined_col = database.db["combined"]
    items = list(combined_col.find({"_id": {"$in": object_ids}}))
    
    # 4. Formatear respuesta
    formatted_items = []
    for item in items:
        formatted_item = {
            "id": str(item["_id"]),
            "type": item.get("type", "place"),
            "title": item.get("title", "Sin título"),
            "category": item.get("category") or item.get("categoria"),
        }
        
        # Extraer imagen
        if "images" in item and isinstance(item["images"], list) and len(item["images"]) > 0:
            formatted_item["image"] = item["images"][0]
        elif "image" in item:
            formatted_item["image"] = item["image"]
        else:
            formatted_item["image"] = None
        
        formatted_items.append(formatted_item)
    
    return {
        "success": True,
        "visited_places": formatted_items,
        "count": len(formatted_items)
    }

@router.delete("/{user_id}/visits/{combined_id}")
def unvisits(user_id: str, combined_id: str):
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

# En user_routes.py - ACTUALIZAR las funciones de interacción

@router.post("/{user_id}/likes/{combined_id}")
def likes(user_id: str, combined_id: str):
    """Añade un evento/lugar a favoritos Y actualiza recomendaciones UNIFICADAS"""
    
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
    
    # 1. Guardar like en la base de datos
    result = database.users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$addToSet": {"likes": combined_id}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    # 2. 🔥 ACTUALIZACIÓN UNIFICADA - Usar el sistema unificado
    try:
        from app.utils.unified_recommender import UnifiedRecommender
        
        recommender = UnifiedRecommender()
        new_recommendations = recommender.generate_unified_recommendations(
            user_id=user_id,
            users_collection=database.users_collection,
            n_recommendations=20
        )
        
        # Guardar nuevas recomendaciones
        database.users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"recommendations": new_recommendations}}
        )
        
        return {
            "message": "Item añadido a favoritos",
            "recommendations_updated": True,
            "num_recommendations": len(new_recommendations),
            "recommendation_phase": "cold_start" if recommender.is_cold_start_user(user_id, database.users_collection) else "hybrid"
        }
        
    except Exception as e:
        print(f"⚠️  Error al actualizar recomendaciones unificadas: {e}")
        import traceback
        traceback.print_exc()
        return {"message": "Item añadido a favoritos (recomendaciones no actualizadas)"}


@router.get("/{user_id}/likes")
def get_likes(user_id: str):
    """
    Obtiene los lugares con like CON información completa
    """
    if database.users_collection is None or database.db is None:
        raise HTTPException(503, "Base de datos no disponible")
    
    if not ObjectId.is_valid(user_id):
        raise HTTPException(400, "ID de usuario inválido")
    
    # 1. Obtener usuario y sus likes
    user = database.users_collection.find_one(
        {"_id": ObjectId(user_id)},
        {"likes": 1}
    )
    
    if not user:
        raise HTTPException(404, "Usuario no encontrado")
    
    liked_ids = user.get("likes", [])
    
    if not liked_ids:
        return {
            "success": True,
            "liked_places": [],
            "count": 0
        }
    
    # 2. Convertir IDs a ObjectId
    object_ids = []
    for lid in liked_ids:
        if ObjectId.is_valid(lid):
            object_ids.append(ObjectId(lid))
    
    # 3. Buscar items completos en combined
    combined_col = database.db["combined"]
    items = list(combined_col.find({"_id": {"$in": object_ids}}))
    
    # 4. Formatear respuesta
    formatted_items = []
    for item in items:
        formatted_item = {
            "id": str(item["_id"]),
            "type": item.get("type", "place"),
            "title": item.get("title", "Sin título"),
            "category": item.get("category") or item.get("categoria"),
        }
        
        # Extraer imagen
        if "images" in item and isinstance(item["images"], list) and len(item["images"]) > 0:
            formatted_item["image"] = item["images"][0]
        elif "image" in item:
            formatted_item["image"] = item["image"]
        else:
            formatted_item["image"] = None
        
        formatted_items.append(formatted_item)
    
    return {
        "success": True,
        "liked_places": formatted_items,
        "count": len(formatted_items)
    }

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


class InteractionModel(BaseModel):
    combined_id: str
    type: str  # share, click, open, etc

@router.post("/{user_id}/interact")
def interact(user_id: str, data: InteractionModel):
    """Registra una interacción del usuario y actualiza recomendaciones"""

    if database.users_collection is None:
        raise HTTPException(503, "Base de datos no disponible")

    if not ObjectId.is_valid(user_id):
        raise HTTPException(400, "ID de usuario inválido")

    result = database.users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$addToSet": {"interactions": {"id": data.combined_id, "type": data.type}}}
    )

    if result.matched_count == 0:
        raise HTTPException(404, "Usuario no encontrado")

    # 🔥 Recomendaciones unificadas
    try:
        from app.utils.unified_recommender import UnifiedRecommender

        recommender = UnifiedRecommender()
        new_recommendations = recommender.generate_unified_recommendations(
            user_id=user_id,
            users_collection=database.users_collection,
            n_recommendations=20
        )

        database.users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"recommendations": new_recommendations}}
        )

        return {
            "message": "Interacción registrada",
            "recommendations_updated": True,
            "num_recommendations": len(new_recommendations),
            "recommendation_phase": "cold_start"
                if recommender.is_cold_start_user(user_id, database.users_collection)
                else "hybrid"
        }

    except Exception as e:
        print("⚠️ Error al actualizar recomendaciones (interact):", e)
        return {"message": "Interacción registrada (recomendaciones no actualizadas)"}

# ==================== RECOMMENDATIONS ====================

@router.put("/{user_id}/recommendations")
def update_recommendations(user_id: str, data: dict = Body(...)):
    """
    Actualiza o reemplaza completamente las recomendaciones del usuario.
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


@router.post("/{user_id}/initialize-recommendations")
def initialize_recommendations_endpoint(user_id: str):
    """
    Genera recomendaciones iniciales para un usuario existente.
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
    
    result = initialize_user_recommendations(user_id, database.users_collection)
    
    if result["success"]:
        return {
            "message": "Recomendaciones inicializadas",
            "num_recommendations": result["num_recommendations"],
            "new_initialization": result.get("new_initialization", False)
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "Error al inicializar recomendaciones")
        )
    
    # En user_routes.py - AÑADIR nuevo endpoint

@router.post("/{user_id}/refresh-recommendations")
def refresh_recommendations(user_id: str):
    """Fuerza el recálculo de recomendaciones usando el sistema unificado"""
    
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
    
    try:
        from app.utils.unified_recommender import UnifiedRecommender
        
        recommender = UnifiedRecommender()
        new_recommendations = recommender.generate_unified_recommendations(
            user_id=user_id,
            users_collection=database.users_collection,
            n_recommendations=20
        )
        
        # Guardar nuevas recomendaciones
        database.users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"recommendations": new_recommendations}}
        )
        
        interaction_count = recommender.get_user_interaction_count(user_id, database.users_collection)
        
        return {
            "success": True,
            "message": "Recomendaciones actualizadas",
            "num_recommendations": len(new_recommendations),
            "interaction_count": interaction_count,
            "phase": "cold_start" if interaction_count < 5 else "hybrid"
        }
        
    except Exception as e:
        print(f"❌ Error al refrescar recomendaciones: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar recomendaciones: {str(e)}"
        )
