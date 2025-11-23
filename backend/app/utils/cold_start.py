"""
Sistema de Cold Start para nuevos usuarios
Genera recomendaciones iniciales basadas en preferencias del usuario
"""
from pymongo import MongoClient
from typing import List, Dict
from bson import ObjectId
import random
import os
from dotenv import load_dotenv

from app.utils.logging_config import get_logger
logger = get_logger(__name__)

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")

# Mapeo de preferencias del usuario a categorías/tipos en la BD
PREFERENCE_MAPPINGS = {
    "playas": {
        "place_categories": ["playa", "costa", "balneario"],
        "event_categories": ["Deportes", "Outdoor", "Naturaleza"],
        "place_types": ["beach", "natural_feature"],
        "tags": ["playa", "mar", "surf", "outdoor"]
    },
    "cultura": {
        "place_categories": ["museo", "galería", "centro cultural", "teatro", "biblioteca"],
        "event_categories": ["Art & Culture", "Música", "Teatro", "Exposiciones"],
        "place_types": ["museum", "art_gallery", "cultural_center"],
        "tags": ["cultura", "arte", "museo", "historia", "exposición"]
    },
    "museos": {  # ✅ AGREGADO
        "place_categories": ["museo", "galería", "centro cultural"],
        "event_categories": ["Art & Culture", "Exposiciones"],
        "place_types": ["museum", "art_gallery"],
        "tags": ["museo", "arte", "historia", "exposición"]
    },
    "gastronomía": {
        "place_categories": ["restaurante", "café", "bar", "mercado"],
        "event_categories": ["Gastronomía", "Food & Drink"],
        "place_types": ["restaurant", "cafe", "bar", "food"],
        "tags": ["comida", "gastronomía", "chef", "cocina"]
    },
    "naturaleza": {
        "place_categories": ["parque", "jardín", "reserva", "laguna"],
        "event_categories": ["Outdoor", "Naturaleza", "Aventura"],
        "place_types": ["park", "natural_feature"],
        "tags": ["naturaleza", "outdoor", "verde", "eco"]
    },
    "aventura": {
        "place_categories": ["parque", "zona recreativa"],
        "event_categories": ["Deportes", "Aventura", "Outdoor"],
        "place_types": ["amusement_park", "tourist_attraction"],
        "tags": ["aventura", "deporte", "adrenalina"]
    },
    "vida nocturna": {
        "place_categories": ["bar", "discoteca", "club"],
        "event_categories": ["Vida Nocturna", "Música", "Fiestas"],
        "place_types": ["night_club", "bar"],
        "tags": ["noche", "música", "fiesta", "bar"]
    },
    "compras": {
        "place_categories": ["centro comercial", "mercado", "tienda"],
        "event_categories": ["Ferias", "Shopping"],
        "place_types": ["shopping_mall", "store"],
        "tags": ["compras", "shopping", "tienda"]
    },
    "deportes": {
        "place_categories": ["estadio", "gimnasio", "complejo deportivo"],
        "event_categories": ["Deportes", "Fitness"],
        "place_types": ["stadium", "gym"],
        "tags": ["deporte", "fitness", "actividad"]
    }
}

# Categorías populares para diversificar
POPULAR_CATEGORIES = {
    "places": ["restaurante", "museo", "parque", "café", "playa"],
    "events": ["Art & Culture", "Música", "Gastronomía", "Deportes", "Outdoor"]
}


def get_related_items_for_preference(
    preference: str,
    combined_collection,
    n_items: int = 5
) -> List[str]:
    """
    Obtiene items relacionados a una preferencia específica del usuario.
    """
    mapping = PREFERENCE_MAPPINGS.get(preference.lower(), {})
    
    if not mapping:
        logger.warning("Preferencia '%s' no tiene mapping, usando items populares", preference)
        return []
    
    
    place_categories = mapping.get("place_categories", [])
    event_categories = mapping.get("event_categories", [])
    tags = mapping.get("tags", [])
    
    items = []
    
    # Buscar places relacionados (50%)
    n_places = n_items // 2
    if place_categories:
        places_query = {
            "type": "place",
            "$or": [
                {"categoria": {"$in": place_categories}},
                {"title": {"$regex": "|".join(tags), "$options": "i"}}
            ]
        }
        places = list(combined_collection.find(places_query).limit(n_places * 2))
        random.shuffle(places)
        items.extend([str(p["_id"]) for p in places[:n_places]])
    
    # Buscar events relacionados (50%)
    n_events = n_items - len(items)
    if event_categories or tags:
        events_query = {
            "type": "event",
            "$or": [
                {"category": {"$in": event_categories}},
                {"tags": {"$in": tags}},
                {"title": {"$regex": "|".join(tags), "$options": "i"}}
            ]
        }
        events = list(combined_collection.find(events_query).limit(n_events * 2))
        random.shuffle(events)
        items.extend([str(e["_id"]) for e in events[:n_events]])
    
    return items


def get_diverse_items(
    combined_collection,
    n_items: int = 10,
    exclude_ids: List[str] = []
) -> List[str]:
    """
    Obtiene items diversos y populares para dar variedad.
    
    🔧 CORRECCIÓN: Usa ObjectId correctamente para exclusión
    """
    items = []
    
    # Convertir exclude_ids a ObjectId correctamente
    exclude_object_ids = []
    for eid in exclude_ids:
        try:
            if ObjectId.is_valid(eid):
                exclude_object_ids.append(ObjectId(eid))
        except Exception as e:
            logger.warning("ID inválido ignorado: %s", eid)
    
    # Mitad places, mitad events
    n_places = n_items // 2
    n_events = n_items - n_places
    
    # Places populares de diferentes categorías
    for category in POPULAR_CATEGORIES["places"]:
        if len(items) >= n_places:
            break
        
        try:
            query = {
                "type": "place",
                "categoria": category
            }
            
            # Solo agregar exclusión si hay IDs para excluir
            if exclude_object_ids:
                query["_id"] = {"$nin": exclude_object_ids}
            
            places = list(
                combined_collection
                .find(query)
                .sort("rating", -1)
                .limit(2)
            )
            items.extend([str(p["_id"]) for p in places])
        except Exception as e:
            logger.exception("Error buscando places de categoría %s: %s", category, e)
    
    # Events de diferentes categorías
    for category in POPULAR_CATEGORIES["events"]:
        if len(items) >= n_places + n_events:
            break
        
        try:
            query = {
                "type": "event",
                "category": category
            }
            
            # Solo agregar exclusión si hay IDs para excluir
            if exclude_object_ids:
                query["_id"] = {"$nin": exclude_object_ids}
            
            events = list(
                combined_collection
                .find(query)
                .limit(2)
            )
            items.extend([str(e["_id"]) for e in events])
        except Exception as e:
            logger.exception("Error buscando events de categoría %s: %s", category, e)
    
    random.shuffle(items)
    return items[:n_items]


def generate_cold_start_recommendations(
    user_preferences: List[str],
    combined_collection,
    n_recommendations: int = 20
) -> List[str]:
    """
    Genera recomendaciones iniciales para un usuario nuevo.
    
    Estrategia:
    - 70% basado en preferencias del usuario
    - 30% items diversos y populares
    """
    logger.info("GENERANDO RECOMENDACIONES COLD START | Preferencias: %s | Total a generar: %d", user_preferences, n_recommendations)
    
    all_recommendations = []
    
    # 1. Items basados en preferencias (70%)
    n_preference_items = int(n_recommendations * 0.7)
    
    if user_preferences and len(user_preferences) > 0:
        items_per_preference = n_preference_items // len(user_preferences)
        
        logger.info("Obteniendo %d items basados en preferencias...", n_preference_items)
        
        for preference in user_preferences:
            logger.debug("Buscando items para '%s'...", preference)
            items = get_related_items_for_preference(
                preference,
                combined_collection,
                n_items=items_per_preference
            )
            logger.info("%d items encontrados para %s", len(items), preference)
            all_recommendations.extend(items)
    else:
        logger.warning("Sin preferencias, usando solo items diversos")
    
    # 2. Items diversos (30% o el resto)
    n_diverse_items = n_recommendations - len(all_recommendations)
    
    logger.info("Obteniendo %d items diversos...", n_diverse_items)
    diverse_items = get_diverse_items(
        combined_collection,
        n_items=n_diverse_items,
        exclude_ids=all_recommendations
    )
    logger.info("%d items diversos encontrados", len(diverse_items))
    
    all_recommendations.extend(diverse_items)
    
    # 3. Mezclar y asegurar que no haya duplicados
    all_recommendations = list(dict.fromkeys(all_recommendations))
    random.shuffle(all_recommendations)
    
    # 4. Recortar al tamaño solicitado
    all_recommendations = all_recommendations[:n_recommendations]
    
    logger.info("RECOMENDACIONES GENERADAS | Total: %d", len(all_recommendations))
    
    return all_recommendations


def initialize_user_recommendations(user_id: str, users_collection) -> dict:
    """
    Inicializa las recomendaciones de un usuario nuevo basadas en sus preferencias.
    """
    try:
        # Obtener usuario
        user = users_collection.find_one({"_id": ObjectId(user_id)})
        
        if not user:
            return {"success": False, "error": "Usuario no encontrado"}
        
        # Verificar si ya tiene recomendaciones
        existing_recommendations = user.get("recommendations", [])
        if existing_recommendations and len(existing_recommendations) > 0:
            logger.info("Usuario ya tiene %d recomendaciones", len(existing_recommendations))
            return {
                "success": True,
                "message": "Usuario ya tiene recomendaciones",
                "num_recommendations": len(existing_recommendations),
                "new_initialization": False
            }
        
        # Obtener preferencias
        user_preferences = user.get("preferences", [])
        
        if not user_preferences:
            logger.warning("Usuario sin preferencias, usando categorías populares")
            user_preferences = ["cultura", "gastronomía"]  # Default
        # Conectar a combined
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        combined_collection = db["combined"]
        
        # Generar recomendaciones
        recommendations = generate_cold_start_recommendations(
            user_preferences,
            combined_collection,
            n_recommendations=20
        )
        
        # Guardar en usuario
        users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"recommendations": recommendations}}
        )
        
        client.close()
        
        return {
            "success": True,
            "message": "Recomendaciones iniciales generadas",
            "num_recommendations": len(recommendations),
            "new_initialization": True
        }
        
    except Exception as e:
        print(f"❌ Error en initialize_user_recommendations: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}