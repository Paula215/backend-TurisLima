from fastapi import APIRouter, HTTPException, Query, Depends
from app.database.database import users_collection, places_collection, events_collection
from bson import ObjectId
from typing import Optional, List
import random

router = APIRouter()

def get_user_by_id(user_id: str):
    """Obtener usuario por ID"""
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="ID de usuario inválido")
    
    user = users_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    return user

@router.get("/")
def get_personalized_feed(
    user_id: Optional[str] = Query(None, description="ID del usuario para personalizar"),
    limit: int = Query(20, ge=1, le=50),
    skip: int = Query(0, ge=0),
    mix_ratio: float = Query(0.6, ge=0, le=1, description="Ratio de places vs events (0.6 = 60% places)")
):
    """
    Feed personalizado tipo TikTok con places y events
    - Si hay user_id: usa preferencias del usuario
    - Si no hay user_id: feed general con items populares
    """
    try:
        feed_items = []
        user = None
        
        # Obtener usuario si existe
        if user_id:
            user = get_user_by_id(user_id)
        
        # Calcular cuántos items de cada tipo
        places_count = int(limit * mix_ratio)
        events_count = limit - places_count
        
        # === OBTENER PLACES ===
        places_query = {}
        places_sort = [("rating", -1)]  # Por defecto, ordenar por rating
        
        if user and user.get("preferences", {}).get("favorite_categories"):
            # Filtrar por categorías favoritas del usuario
            places_query["categoria"] = {"$in": user["preferences"]["favorite_categories"]}
        
        if user and user.get("preferences", {}).get("favorite_districts"):
            # Filtrar por distritos favoritos
            places_query["distrito"] = {"$in": user["preferences"]["favorite_districts"]}
        
        # Excluir lugares ya vistos/guardados para más variedad
        if user:
            excluded_ids = user.get("liked_places", []) + user.get("saved_places", [])
            if excluded_ids:
                # Mezclar: 70% nuevos, 30% pueden repetirse
                if random.random() > 0.3:
                    places_query["place_id"] = {"$nin": [int(pid) for pid in excluded_ids if pid.isdigit()]}
        
        places = list(
            places_collection
            .find(places_query, {"_id": 1, "place_id": 1, "title": 1, "images": 1, 
                                 "rating": 1, "categoria": 1, "distrito": 1, "address": 1, 
                                 "location": 1, "types": 1})
            .sort(places_sort)
            .limit(places_count * 2)  # Obtener más para tener variedad
        )
        
        # Mezclar aleatoriamente y tomar solo la cantidad necesaria
        random.shuffle(places)
        places = places[:places_count]
        
        for place in places:
            # Usar la primera imagen disponible o imagen por defecto
            image = None
            if place.get("images") and len(place["images"]) > 0:
                image = place["images"][0]
            
            feed_items.append({
                "id": str(place["_id"]),
                "item_id": place.get("place_id"),
                "type": "place",
                "title": place.get("title", "Sin título"),
                "image": image,
                "rating": place.get("rating"),
                "category": place.get("categoria", ""),
                "location": place.get("distrito", "Lima"),
                "address": place.get("address", ""),
                "coordinates": place.get("location", {}),
                "tags": place.get("types", [])
            })
        
        # === OBTENER EVENTS ===
        events_query = {}
        events_sort = [("rating", -1), ("start_date", -1)]
        
        if user and user.get("preferences", {}).get("interests"):
            # Filtrar por intereses (tags)
            events_query["tags"] = {"$in": user["preferences"]["interests"]}
        
        # Excluir eventos ya vistos
        if user:
            excluded_event_ids = user.get("liked_events", []) + user.get("saved_events", [])
            if excluded_event_ids:
                if random.random() > 0.3:
                    events_query["event_id"] = {"$nin": [int(eid) for eid in excluded_event_ids if str(eid).isdigit()]}
        
        events = list(
            events_collection
            .find(events_query, {"_id": 1, "event_id": 1, "title": 1, "images": 1,
                                "rating": 1, "category": 1, "city": 1, "address": 1,
                                "start_date": 1, "end_date": 1, "price_min": 1, "tags": 1})
            .sort(events_sort)
            .limit(events_count * 2)
        )
        
        random.shuffle(events)
        events = events[:events_count]
        
        for event in events:
            image = None
            if event.get("images") and len(event["images"]) > 0:
                image = event["images"][0]
            
            feed_items.append({
                "id": str(event["_id"]),
                "item_id": event.get("event_id"),
                "type": "event",
                "title": event.get("title", "Sin título"),
                "image": image,
                "rating": event.get("rating"),
                "category": event.get("category", ""),
                "location": event.get("city", "Lima"),
                "address": event.get("address", ""),
                "start_date": event.get("start_date"),
                "end_date": event.get("end_date"),
                "price": event.get("price_min"),
                "tags": event.get("tags", [])
            })
        
        # Mezclar todo el feed
        random.shuffle(feed_items)
        
        # Aplicar paginación
        feed_items = feed_items[skip:skip + limit]
        
        return {
            "feed": feed_items,
            "total": len(feed_items),
            "user_personalized": user_id is not None,
            "limit": limit,
            "skip": skip
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al generar feed: {str(e)}")

@router.post("/interaction")
def record_interaction(
    user_id: str,
    item_id: str,
    item_type: str,
    action: str
):
    """
    Registrar interacción del usuario
    action: "like", "unlike", "save", "unsave", "view", "share"
    """
    try:
        user = get_user_by_id(user_id)
        
        # Actualizar según la acción
        update_query = {}
        
        if action == "like":
            if item_type == "place":
                update_query = {"$addToSet": {"liked_places": item_id}}
            else:
                update_query = {"$addToSet": {"liked_events": item_id}}
        
        elif action == "unlike":
            if item_type == "place":
                update_query = {"$pull": {"liked_places": item_id}}
            else:
                update_query = {"$pull": {"liked_events": item_id}}
        
        elif action == "save":
            if item_type == "place":
                update_query = {"$addToSet": {"saved_places": item_id}}
            else:
                update_query = {"$addToSet": {"saved_events": item_id}}
        
        elif action == "unsave":
            if item_type == "place":
                update_query = {"$pull": {"saved_places": item_id}}
            else:
                update_query = {"$pull": {"saved_events": item_id}}
        
        # Agregar interacción al historial
        interaction = {
            "item_id": item_id,
            "item_type": item_type,
            "action": action,
            "timestamp": {"$date": {"$numberLong": str(int(__import__("time").time() * 1000))}}
        }
        update_query["$push"] = {"interactions": interaction}
        
        # Actualizar usuario
        result = users_collection.update_one(
            {"_id": ObjectId(user_id)},
            update_query
        )
        
        if result.modified_count == 0:
            return {"success": False, "message": "No se pudo actualizar"}
        
        return {"success": True, "action": action, "item_id": item_id}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al registrar interacción: {str(e)}")

@router.get("/saved")
def get_saved_items(user_id: str):
    """Obtener todos los items guardados del usuario"""
    try:
        user = get_user_by_id(user_id)
        
        saved_items = []
        
        # Obtener lugares guardados
        saved_place_ids = [int(pid) for pid in user.get("saved_places", []) if pid.isdigit()]
        if saved_place_ids:
            places = places_collection.find({"place_id": {"$in": saved_place_ids}})
            for place in places:
                saved_items.append({
                    "id": str(place["_id"]),
                    "type": "place",
                    "data": place
                })
        
        # Obtener eventos guardados
        saved_event_ids = [int(eid) for eid in user.get("saved_events", []) if str(eid).isdigit()]
        if saved_event_ids:
            events = events_collection.find({"event_id": {"$in": saved_event_ids}})
            for event in events:
                saved_items.append({
                    "id": str(event["_id"]),
                    "type": "event",
                    "data": event
                })
        
        return {
            "saved_items": saved_items,
            "total": len(saved_items)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener guardados: {str(e)}")