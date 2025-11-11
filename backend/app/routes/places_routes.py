from fastapi import APIRouter, HTTPException, Query, status
from app.database.database import places_collection
from bson import ObjectId
from typing import Optional, List
from pydantic import BaseModel, Field
import json

from app.database import database

router = APIRouter()

# Modelos Pydantic para validación
class LocationModel(BaseModel):
    lat: float
    lng: float

class PlaceResponse(BaseModel):
    id: str = Field(alias="_id")
    place_id: int
    title: str
    address: str
    rating: Optional[float] = None
    types: List[str]
    url: str
    images: List[str]
    location: LocationModel
    categoria: str
    distrito: str
    archivo: Optional[str] = None
    photos: Optional[List[str]] = None

    class Config:
        populate_by_name = True


def serialize_place(place: dict) -> dict:
    """Serializa un lugar de MongoDB al formato de respuesta"""
    # Parsear el campo types si es string
    if isinstance(place.get("types"), str):
        try:
            place["types"] = json.loads(place["types"].replace("'", '"'))
        except:
            place["types"] = []
    
    # Parsear el campo photos si es string
    if isinstance(place.get("photos"), str):
        try:
            place["photos"] = json.loads(place["photos"].replace("'", '"'))
        except:
            place["photos"] = []
    
    # Convertir ObjectId a string
    place["_id"] = str(place["_id"])
    
    # Asegurar que location tenga el formato correcto
    if "location.lat" in place and "location.lng" in place:
        place["location"] = {
            "lat": place.pop("location.lat"),
            "lng": place.pop("location.lng")
        }
    
    return place


@router.get("/", response_model=dict)
def get_all_places(
    categoria: Optional[str] = Query(None, description="Filtrar por categoría"),
    distrito: Optional[str] = Query(None, description="Filtrar por distrito"),
    min_rating: Optional[float] = Query(None, ge=0, le=5, description="Rating mínimo"),
    limit: int = Query(50, ge=1, le=100, description="Cantidad de resultados"),
    skip: int = Query(0, ge=0, description="Saltar resultados (paginación)")
):
    """
    Obtiene todos los lugares con filtros opcionales
    
    - **categoria**: Filtra por tipo (ej: laguna, centro_cultural, etc)
    - **distrito**: Filtra por distrito (ej: independencia, chorrillos)
    - **min_rating**: Rating mínimo (0-5)
    - **limit**: Cantidad máxima de resultados
    - **skip**: Para paginación
    """
    
    if database.places_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    # Construir query
    query = {}
    if categoria:
        query["categoria"] = categoria.lower()
    if distrito:
        query["distrito"] = distrito.lower()
    if min_rating is not None:
        query["rating"] = {"$gte": min_rating}
    
    # Obtener total de documentos que coinciden
    total = database.places_collection.count_documents(query)
    
    # Obtener lugares
    places = []
    cursor = database.places_collection.find(query).skip(skip).limit(limit)
    
    for place in cursor:
        places.append(serialize_place(place))
    
    return {
        "total": total,
        "count": len(places),
        "skip": skip,
        "limit": limit,
        "places": places
    }


@router.get("/categorias", response_model=dict)
def get_categories():
    """Obtiene todas las categorías disponibles"""
    
    if database.places_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    categorias = database.places_collection.distinct("categoria")
    return {
        "total": len(categorias),
        "categorias": sorted(categorias)
    }


@router.get("/distritos", response_model=dict)
def get_districts():
    """Obtiene todos los distritos disponibles"""
    
    if database.places_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    distritos = database.places_collection.distinct("distrito")
    return {
        "total": len(distritos),
        "distritos": sorted(distritos)
    }


@router.get("/search", response_model=dict)
def search_places(
    q: str = Query(..., min_length=2, description="Término de búsqueda"),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Busca lugares por título o dirección
    
    - **q**: Término de búsqueda (mínimo 2 caracteres)
    - **limit**: Cantidad máxima de resultados
    """
    
    if database.places_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    # Búsqueda en título y dirección
    query = {
        "$or": [
            {"title": {"$regex": q, "$options": "i"}},
            {"address": {"$regex": q, "$options": "i"}}
        ]
    }
    
    places = []
    for place in database.places_collection.find(query).limit(limit):
        places.append(serialize_place(place))
    
    return {
        "query": q,
        "total": len(places),
        "places": places
    }


@router.get("/nearby", response_model=dict)
def get_nearby_places(
    lat: float = Query(..., ge=-90, le=90, description="Latitud"),
    lng: float = Query(..., ge=-180, le=180, description="Longitud"),
    max_distance_km: float = Query(5, ge=0.1, le=50, description="Distancia máxima en km"),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Obtiene lugares cercanos a una ubicación
    
    - **lat**: Latitud de la ubicación
    - **lng**: Longitud de la ubicación
    - **max_distance_km**: Radio de búsqueda en kilómetros
    - **limit**: Cantidad máxima de resultados
    """
    
    if database.places_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    # Asegúrate de tener un índice geoespacial en tu colección
    # db.places.createIndex({"location.lat": 1, "location.lng": 1})
    
    # Convertir km a grados (aproximado)
    max_distance_degrees = max_distance_km / 111.0
    
    query = {
        "location.lat": {
            "$gte": lat - max_distance_degrees,
            "$lte": lat + max_distance_degrees
        },
        "location.lng": {
            "$gte": lng - max_distance_degrees,
            "$lte": lng + max_distance_degrees
        }
    }
    
    places = []
    for place in database.places_collection.find(query).limit(limit):
        serialized = serialize_place(place)
        
        # Calcular distancia aproximada
        lat_diff = place["location.lat"] - lat
        lng_diff = place["location.lng"] - lng
        distance = ((lat_diff ** 2 + lng_diff ** 2) ** 0.5) * 111
        serialized["distance_km"] = round(distance, 2)
        
        places.append(serialized)
    
    # Ordenar por distancia
    places.sort(key=lambda x: x["distance_km"])
    
    return {
        "location": {"lat": lat, "lng": lng},
        "max_distance_km": max_distance_km,
        "total": len(places),
        "places": places
    }


@router.get("/{place_id}", response_model=dict)
def get_place(place_id: int):
    """
    Obtiene un lugar específico por su place_id
    
    - **place_id**: ID del lugar
    """
    
    if database.places_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    place = database.places_collection.find_one({"place_id": place_id})
    
    if not place:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lugar con place_id {place_id} no encontrado"
        )
    
    return serialize_place(place)


@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_place(place_data: dict):
    """
    Crea un nuevo lugar
    
    Campos requeridos:
    - place_id: int
    - title: str
    - address: str
    - rating: float
    - types: list[str]
    - url: str
    - images: list[str]
    - location.lat: float
    - location.lng: float
    - categoria: str
    - distrito: str
    """
    
    if database.places_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    # Validar que place_id no exista
    if database.places_collection.find_one({"place_id": place_data.get("place_id")}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ya existe un lugar con place_id {place_data.get('place_id')}"
        )
    
    try:
        result = database.places_collection.insert_one(place_data)
        return {
            "message": "Lugar creado exitosamente",
            "place_id": place_data.get("place_id"),
            "_id": str(result.inserted_id)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al crear lugar: {str(e)}"
        )


@router.put("/{place_id}", response_model=dict)
def update_place(place_id: int, place_data: dict):
    """Actualiza un lugar existente"""
    
    if database.places_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    # Eliminar _id si existe en los datos
    place_data.pop("_id", None)
    place_data.pop("place_id", None)
    
    result = database.places_collection.update_one(
        {"place_id": place_id},
        {"$set": place_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lugar con place_id {place_id} no encontrado"
        )
    
    return {
        "message": "Lugar actualizado exitosamente",
        "place_id": place_id,
        "modified": result.modified_count > 0
    }


@router.delete("/{place_id}", response_model=dict)
def delete_place(place_id: int):
    """Elimina un lugar"""
    
    if database.places_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    result = database.places_collection.delete_one({"place_id": place_id})
    
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lugar con place_id {place_id} no encontrado"
        )
    
    return {
        "message": "Lugar eliminado exitosamente",
        "place_id": place_id
    }


@router.get("/stats/summary", response_model=dict)
def get_stats():
    """Obtiene estadísticas generales de los lugares"""
    
    if database.places_collection is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )
    
    total_places = database.places_collection.count_documents({})
    
    # Lugares con rating
    places_with_rating = database.places_collection.count_documents(
        {"rating": {"$exists": True, "$ne": None}}
    )
    
    # Rating promedio
    pipeline = [
        {"$match": {"rating": {"$exists": True, "$ne": None}}},
        {"$group": {"_id": None, "avg_rating": {"$avg": "$rating"}}}
    ]
    avg_result = list(database.places_collection.aggregate(pipeline))
    avg_rating = avg_result[0]["avg_rating"] if avg_result else None
    
    # Top categorías
    top_categories = list(database.places_collection.aggregate([
        {"$group": {"_id": "$categoria", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ]))
    
    # Top distritos
    top_districts = list(database.places_collection.aggregate([
        {"$group": {"_id": "$distrito", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ]))
    
    return {
        "total_places": total_places,
        "places_with_rating": places_with_rating,
        "average_rating": round(avg_rating, 2) if avg_rating else None,
        "top_categories": [
            {"categoria": item["_id"], "count": item["count"]} 
            for item in top_categories
        ],
        "top_districts": [
            {"distrito": item["_id"], "count": item["count"]} 
            for item in top_districts
        ]
    }