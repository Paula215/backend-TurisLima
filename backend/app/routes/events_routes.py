from fastapi import APIRouter, HTTPException, Query, status
from bson import ObjectId
from app.database.database import events_collection
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, timedelta

from app.database import database

router = APIRouter()

# Modelos Pydantic para validación
class EventResponse(BaseModel):
    id: str = Field(alias="_id")
    event_id: int
    url: str
    category: str
    title: str
    description: Optional[str] = None
    city: Optional[str] = None
    location_venue: Optional[str] = None
    address: Optional[str] = None
    organizer: Optional[str] = None
    organizer_ruc: Optional[str] = None
    rating: Optional[str] = None
    event_type: Optional[str] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    price_currency: Optional[str] = None
    tags: List[str] = []
    images: List[str] = []
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    times: List[str] = []
    extracted_at: Optional[str] = None

    class Config:
        populate_by_name = True


def serialize_event(event: dict) -> dict:
    """Serializa un evento de MongoDB al formato de respuesta"""
    # Convertir ObjectId a string
    event["_id"] = str(event["_id"])
    
    # Convertir fechas a string ISO si son datetime
    if isinstance(event.get("start_date"), datetime):
        event["start_date"] = event["start_date"].isoformat()
    if isinstance(event.get("end_date"), datetime):
        event["end_date"] = event["end_date"].isoformat()
    
    # Asegurar que arrays existan
    if "tags" not in event:
        event["tags"] = []
    if "images" not in event:
        event["images"] = []
    if "times" not in event:
        event["times"] = []
    
    return event


def is_event_active(event: dict) -> bool:
    """Verifica si un evento está activo (no ha terminado)"""
    if not event.get("end_date"):
        return True
    
    try:
        if isinstance(event["end_date"], str):
            end_date = datetime.fromisoformat(event["end_date"].replace('Z', '+00:00'))
        else:
            end_date = event["end_date"]
        
        return end_date >= datetime.now()
    except:
        return True


@router.get("/", response_model=dict)
def get_all_events(
    category: Optional[str] = Query(None, description="Filtrar por categoría"),
    city: Optional[str] = Query(None, description="Filtrar por ciudad"),
    min_price: Optional[float] = Query(None, ge=0, description="Precio mínimo"),
    max_price: Optional[float] = Query(None, ge=0, description="Precio máximo"),
    active_only: bool = Query(True, description="Solo eventos activos (no finalizados)"),
    rating: Optional[str] = Query(None, description="Filtrar por rating (G, PG, etc)"),
    limit: int = Query(50, ge=1, le=100, description="Cantidad de resultados"),
    skip: int = Query(0, ge=0, description="Saltar resultados (paginación)")
):
    """
    Obtiene todos los eventos con filtros opcionales
    
    - **category**: Categoría del evento (ej: Art & Culture, Trip & Adventure)
    - **city**: Ciudad del evento
    - **min_price/max_price**: Rango de precios
    - **active_only**: Si es True, solo muestra eventos que aún no han terminado
    - **rating**: Rating del evento (G, PG, etc)
    - **limit**: Cantidad máxima de resultados
    - **skip**: Para paginación
    """
    
    if database.events_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    # Construir query
    query = {}
    
    if category:
        query["category"] = {"$regex": category, "$options": "i"}
    
    if city:
        query["city"] = {"$regex": city, "$options": "i"}
    
    if rating:
        query["rating"] = rating.upper()
    
    # Filtro de precio
    if min_price is not None or max_price is not None:
        price_query = {}
        if min_price is not None:
            price_query["$gte"] = min_price
        if max_price is not None:
            price_query["$lte"] = max_price
        query["price_min"] = price_query
    
    # Filtro de eventos activos
    if active_only:
        query["$or"] = [
            {"end_date": {"$gte": datetime.now()}},
            {"end_date": None}
        ]
    
    # Obtener total de documentos que coinciden
    total = database.events_collection.count_documents(query)
    
    # Obtener eventos ordenados por fecha de inicio
    events = []
    cursor = database.events_collection.find(query).sort("start_date", 1).skip(skip).limit(limit)
    
    for event in cursor:
        events.append(serialize_event(event))
    
    return {
        "total": total,
        "count": len(events),
        "skip": skip,
        "limit": limit,
        "events": events
    }


@router.get("/categories", response_model=dict)
def get_categories():
    """Obtiene todas las categorías de eventos disponibles"""
    
    if database.events_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    categories = database.events_collection.distinct("category")
    return {
        "total": len(categories),
        "categories": sorted([c for c in categories if c])
    }


@router.get("/cities", response_model=dict)
def get_cities():
    """Obtiene todas las ciudades con eventos disponibles"""
    
    if database.events_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    cities = database.events_collection.distinct("city")
    return {
        "total": len(cities),
        "cities": sorted([c for c in cities if c])
    }


@router.get("/search", response_model=dict)
def search_events(
    q: str = Query(..., min_length=2, description="Término de búsqueda"),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Busca eventos por título, descripción o dirección
    
    - **q**: Término de búsqueda (mínimo 2 caracteres)
    - **limit**: Cantidad máxima de resultados
    """
    
    if database.events_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    # Búsqueda en múltiples campos
    query = {
        "$or": [
            {"title": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
            {"address": {"$regex": q, "$options": "i"}},
            {"location_venue": {"$regex": q, "$options": "i"}}
        ]
    }
    
    events = []
    for event in database.events_collection.find(query).limit(limit):
        events.append(serialize_event(event))
    
    return {
        "query": q,
        "total": len(events),
        "events": events
    }


@router.get("/upcoming", response_model=dict)
def get_upcoming_events(
    days: int = Query(30, ge=1, le=365, description="Días hacia adelante"),
    category: Optional[str] = Query(None, description="Filtrar por categoría"),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Obtiene eventos próximos a suceder
    
    - **days**: Cantidad de días hacia el futuro (default: 30)
    - **category**: Filtrar por categoría
    - **limit**: Cantidad máxima de resultados
    """
    
    if database.events_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    now = datetime.now()
    future_date = now + timedelta(days=days)
    
    query = {
        "start_date": {
            "$gte": now,
            "$lte": future_date
        }
    }
    
    if category:
        query["category"] = {"$regex": category, "$options": "i"}
    
    events = []
    cursor = database.events_collection.find(query).sort("start_date", 1).limit(limit)
    
    for event in cursor:
        serialized = serialize_event(event)
        
        # Calcular días hasta el evento
        if event.get("start_date"):
            try:
                if isinstance(event["start_date"], str):
                    start_date = datetime.fromisoformat(event["start_date"].replace('Z', '+00:00'))
                else:
                    start_date = event["start_date"]
                
                days_until = (start_date - now).days
                serialized["days_until_event"] = days_until
            except:
                pass
        
        events.append(serialized)
    
    return {
        "days_range": days,
        "from_date": now.isoformat(),
        "to_date": future_date.isoformat(),
        "total": len(events),
        "events": events
    }


@router.get("/happening-now", response_model=dict)
def get_happening_now(
    category: Optional[str] = Query(None, description="Filtrar por categoría"),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Obtiene eventos que están sucediendo ahora
    
    - **category**: Filtrar por categoría
    - **limit**: Cantidad máxima de resultados
    """
    
    if database.events_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    now = datetime.now()
    
    query = {
        "start_date": {"$lte": now},
        "end_date": {"$gte": now}
    }
    
    if category:
        query["category"] = {"$regex": category, "$options": "i"}
    
    events = []
    for event in database.events_collection.find(query).limit(limit):
        events.append(serialize_event(event))
    
    return {
        "current_time": now.isoformat(),
        "total": len(events),
        "events": events
    }


@router.get("/free", response_model=dict)
def get_free_events(
    category: Optional[str] = Query(None, description="Filtrar por categoría"),
    active_only: bool = Query(True, description="Solo eventos activos"),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Obtiene eventos gratuitos (precio_min = 0)
    
    - **category**: Filtrar por categoría
    - **active_only**: Solo eventos que no han terminado
    - **limit**: Cantidad máxima de resultados
    """
    
    if database.events_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    query = {"price_min": 0}
    
    if category:
        query["category"] = {"$regex": category, "$options": "i"}
    
    if active_only:
        query["$or"] = [
            {"end_date": {"$gte": datetime.now()}},
            {"end_date": None}
        ]
    
    events = []
    for event in database.events_collection.find(query).limit(limit):
        events.append(serialize_event(event))
    
    return {
        "total": len(events),
        "events": events
    }


@router.get("/{event_id}", response_model=dict)
def get_event(event_id: int):
    """
    Obtiene un evento específico por su event_id
    
    - **event_id**: ID del evento
    """
    
    if database.events_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    event = database.events_collection.find_one({"event_id": event_id})
    
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evento con event_id {event_id} no encontrado"
        )
    
    serialized = serialize_event(event)
    
    # Agregar información adicional
    if event.get("start_date"):
        try:
            if isinstance(event["start_date"], str):
                start_date = datetime.fromisoformat(event["start_date"].replace('Z', '+00:00'))
            else:
                start_date = event["start_date"]
            
            now = datetime.now()
            serialized["is_upcoming"] = start_date > now
            serialized["is_happening"] = start_date <= now <= event.get("end_date", now)
            serialized["has_ended"] = event.get("end_date", now) < now if event.get("end_date") else False
        except:
            pass
    
    return serialized


@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_event(event_data: dict):
    """
    Crea un nuevo evento
    
    Campos requeridos:
    - event_id: int
    - url: str
    - category: str
    - title: str
    - start_date: datetime
    - end_date: datetime
    """
    
    if database.events_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    # Validar que event_id no exista
    if database.events_collection.find_one({"event_id": event_data.get("event_id")}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ya existe un evento con event_id {event_data.get('event_id')}"
        )
    
    try:
        # Agregar fecha de extracción
        event_data["extracted_at"] = datetime.now().isoformat()
        
        result = database.events_collection.insert_one(event_data)
        return {
            "message": "Evento creado exitosamente",
            "event_id": event_data.get("event_id"),
            "_id": str(result.inserted_id)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al crear evento: {str(e)}"
        )


@router.put("/{event_id}", response_model=dict)
def update_event(event_id: int, event_data: dict):
    """Actualiza un evento existente"""
    
    if database.events_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    # Eliminar campos que no deben actualizarse
    event_data.pop("_id", None)
    event_data.pop("event_id", None)
    event_data.pop("extracted_at", None)
    
    result = database.events_collection.update_one(
        {"event_id": event_id},
        {"$set": event_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evento con event_id {event_id} no encontrado"
        )
    
    return {
        "message": "Evento actualizado exitosamente",
        "event_id": event_id,
        "modified": result.modified_count > 0
    }


@router.delete("/{event_id}", response_model=dict)
def delete_event(event_id: int):
    """Elimina un evento"""
    
    if database.events_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    result = database.events_collection.delete_one({"event_id": event_id})
    
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evento con event_id {event_id} no encontrado"
        )
    
    return {
        "message": "Evento eliminado exitosamente",
        "event_id": event_id
    }


@router.get("/stats/summary", response_model=dict)
def get_stats():
    """Obtiene estadísticas generales de los eventos"""
    
    if database.events_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    now = datetime.now()
    
    total_events = database.events_collection.count_documents({})
    
    # Eventos activos
    active_events = database.events_collection.count_documents({
        "$or": [
            {"end_date": {"$gte": now}},
            {"end_date": None}
        ]
    })
    
    # Eventos gratuitos
    free_events = database.events_collection.count_documents({"price_min": 0})
    
    # Rango de precios
    price_pipeline = [
        {"$match": {"price_min": {"$gt": 0}}},
        {"$group": {
            "_id": None,
            "min_price": {"$min": "$price_min"},
            "max_price": {"$max": "$price_min"},
            "avg_price": {"$avg": "$price_min"}
        }}
    ]
    price_result = list(database.events_collection.aggregate(price_pipeline))
    
    # Top categorías
    top_categories = list(database.events_collection.aggregate([
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ]))
    
    # Eventos por ciudad
    events_by_city = list(database.events_collection.aggregate([
        {"$match": {"city": {"$ne": None}}},
        {"$group": {"_id": "$city", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ]))
    
    return {
        "total_events": total_events,
        "active_events": active_events,
        "free_events": free_events,
        "price_stats": {
            "min": price_result[0]["min_price"] if price_result else None,
            "max": price_result[0]["max_price"] if price_result else None,
            "avg": round(price_result[0]["avg_price"], 2) if price_result else None
        },
        "top_categories": [
            {"category": item["_id"], "count": item["count"]} 
            for item in top_categories
        ],
        "events_by_city": [
            {"city": item["_id"], "count": item["count"]} 
            for item in events_by_city
        ]
    }