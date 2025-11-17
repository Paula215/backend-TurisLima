from fastapi import APIRouter,Depends, HTTPException, Query
from app.database.database import users_collection, get_collections_dependency
from bson import ObjectId
from typing import Optional
import random

router = APIRouter()
def get_user_by_id(user_id: str, collections: dict):
    """Obtener usuario por ID"""
    
    users_collection = collections["users"] # Obtiene la colección users
    
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="ID de usuario inválido")
    
    # La consulta debe ser con _id como ObjectId
    user = users_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    return user

# ---------------------------
#  ENDPOINT PRINCIPAL FEED
# ---------------------------
@router.get("/")
def get_personalized_feed(
    user_id: Optional[str] = Query(None, description="ID del usuario para personalizar"),
    limit: int = Query(20, ge=1, le=50),
    skip: int = Query(0, ge=0),
    mix_ratio: float = Query(0.6, ge=0, le=1, description="Ratio de places vs events (0.6 = 60% places)"),
    # CRÍTICO: Inyectar las colecciones aquí
    collections: dict = Depends(get_collections_dependency)
):
    """
    Feed personalizado: Prioriza recomendaciones del usuario, si existen.
    Si no hay, usa el feed general combinado.
    """
    # Definir variables locales de colección para el endpoint
    combined_collection = collections["combined"]
    
    user = None
    feed_items = []
    
    # --- 1. Obtener usuario y chequear recomendaciones ---
    if user_id:
        # Aquí 'collections' está definido y se pasa a la función auxiliar
        try:
            user = get_user_by_id(user_id, collections)
        except HTTPException as e:
            # Si el usuario no es válido o no existe, continuamos con el feed general
            if e.status_code != 404:
                raise
            user = None

    if user and user.get("recommendations"):
        recommendation_ids = user["recommendations"]
        
        # Convertir IDs a ObjectId y filtrar solo los válidos
        valid_object_ids = []
        for rid in recommendation_ids:
            if ObjectId.is_valid(rid):
                valid_object_ids.append(ObjectId(rid))

        if valid_object_ids:
            # Consultar la colección combinada por los IDs recomendados
            recommended_items = list(
                combined_collection
                .find({"_id": {"$in": valid_object_ids}})
                .limit(limit * 2) # Limite temporal para mezclar
            )
            
            # Mezclar y limitar para obtener el feed final basado en recomendaciones
            random.shuffle(recommended_items)
            recommended_items = recommended_items[:limit]

            for item in recommended_items:
                item["id"] = str(item["_id"])
                
                # Usar lógica de formato simplificada o unificadora
                
                # Lógica para Place (si el tipo existe y es 'place')
                if item.get("type") == "place":
                    image = item.get("images", [None])[0]
                    feed_items.append({
                        "id": item["id"],
                        "item_id": item.get("place_id"),
                        "type": "place",
                        "title": item.get("title", "Sin título"),
                        "image": image,
                        "rating": item.get("rating"),
                        "category": item.get("categoria", ""),
                        "location": item.get("distrito", "Lima"),
                        "address": item.get("address", ""),
                        "coordinates": item.get("location", {}),
                        "tags": item.get("types", [])
                    })
                
                # Lógica para Event
                elif item.get("type") == "event":
                    image = item.get("images", [None])[0]
                    feed_items.append({
                        "id": item["id"],
                        "item_id": item.get("event_id"),
                        "type": "event",
                        "title": item.get("title", "Sin título"),
                        "image": image,
                        "category": item.get("category", ""),
                        "location": item.get("city", "Lima"),
                        "address": item.get("address", ""),
                        "start_date": item.get("start_date"),
                        "end_date": item.get("end_date"),
                        "price": {
                            "min": item.get("price_min"),
                            "currency": item.get("price_currency", "PEN")
                        }
                    })
            
            # Si encontramos recomendaciones, las devolvemos y terminamos aquí
            feed_items = feed_items[skip: skip + limit]
            return {"feed": feed_items, "count": len(feed_items)}

    # --- 2. Lógica de Feed General (Fallback si no hay usuario o recomendaciones) ---
    
    # Calcular proporción entre lugares y eventos
    places_count = int(limit * mix_ratio)
    events_count = limit - places_count

    # ============================
    #       CONSULTA DE PLACES
    # ============================
    places_query = {"type": "place"}
    
    # NOTA: La lógica anterior de 'preferences' se ha ELIMINADO para evitar el 'AttributeError'.
    # Si deseas reintroducirla, el campo 'preferences' en la DB debe ser un DICCIONARIO.
    
    # Consulta Places General
    places = list(
        combined_collection
        .find(places_query, {"_id": 1, "place_id": 1, "title": 1, "images": 1, 
                              "rating": 1, "categoria": 1, "distrito": 1, "address": 1, 
                              "location": 1, "types": 1})
        .sort("rating", -1)
        .limit(places_count * 2)
    )
    random.shuffle(places)
    places = places[:places_count]

    for place in places:
        image = place.get("images", [None])[0]
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

    # ============================
    #       CONSULTA DE EVENTS
    # ============================
    events_query = {"type": "event"}
    events = list(
        combined_collection
        .find(events_query, {"_id": 1, "event_id": 1, "title": 1, "images": 1, 
                              "category": 1, "address": 1, "city": 1, 
                              "start_date": 1, "end_date": 1, "price_min": 1, "price_currency": 1})
        .sort("start_date", -1)
        .limit(events_count * 2)
    )
    random.shuffle(events)
    events = events[:events_count]

    for event in events:
        image = event.get("images", [None])[0]
        feed_items.append({
            "id": str(event["_id"]),
            "item_id": event.get("event_id"),
            "type": "event",
            "title": event.get("title", "Sin título"),
            "image": image,
            "category": event.get("category", ""),
            "location": event.get("city", "Lima"),
            "address": event.get("address", ""),
            "start_date": event.get("start_date"),
            "end_date": event.get("end_date"),
            "price": {
                "min": event.get("price_min"),
                "currency": event.get("price_currency", "PEN")
            }
        })

    # Mezclar todo el feed general
    random.shuffle(feed_items)
    feed_items = feed_items[skip: skip + limit]

    return {"feed": feed_items, "count": len(feed_items)}