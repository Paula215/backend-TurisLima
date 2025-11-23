"""
Compatibility shim: same implementation as `cf-aux.py` but with a valid module name (`cf_aux`).
This file duplicates the logic to allow imports using `app.utils.cf_aux`.
"""
from collections import Counter
import datetime
import os
import sys
from pymongo import MongoClient
from bson import ObjectId
import numpy as np
import math

# ============================================================================
# CONFIGURACIÓN Y CONEXIÓN A BD
# ============================================================================

# Interaction strength weights
LIKE_STRENGTH = 1.0
SAVE_STRENGTH = 2.0
VISIT_STRENGTH = 0.5
LAMBDA_DECAY = 0.01

# Inicialización perezosa de conexiones para evitar errores de importación
_client = None
_user_db = None
_data_db = None

def get_database_connections(mongo_uri=None, db_name="turislima_db"):
    """
    Obtiene conexiones a la base de datos de forma lazy.
    """
    global _client, _user_db, _data_db
    
    if _client is None:
        try:
            _client = MongoClient(mongo_uri or os.getenv("MONGO_URI"))
            _user_db = _client[db_name].users
            _data_db = _client[db_name].combined
        except Exception as e:
            print(f"❌ Error conectando a MongoDB: {e}")
            raise
    
    return _user_db, _data_db

# ============================================================================
# FUNCIONES BÁSICAS DE SIMILARIDAD (sin cambios)
# ============================================================================

def cosine_similarity(a, b):
    a = np.array(a, dtype=float)
    b = np.array(b, dtype=float)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
    
    return float(np.dot(a, b) / (norm_a * norm_b))

def dot_similarity(a, b):
    a = np.array(a, dtype=float)
    b = np.array(b, dtype=float)
    return float(np.dot(a, b))

# ============================================================================
# FUNCIONES ADAPTADAS PARA USO MODULAR
# ============================================================================

def get_user_vector_from_db(user_id, user_db=None):
    """
    Obtiene el vector de usuario desde la base de datos.
    
    Args:
        user_id: ObjectId o string del usuario
        user_db: Colección de usuarios (opcional)
    
    Returns:
        tuple: (vector, total_weight) o (None, 0) si no existe
    """
    if user_db is None:
        user_db, _ = get_database_connections()
    
    if isinstance(user_id, str):
        user_id = ObjectId(user_id)
    
    user = user_db.find_one({'_id': user_id}, {'vector': 1, 'total_weight': 1})
    
    if user and user.get('vector'):
        vector = np.array(user['vector'], dtype=float)
        total_weight = user.get('total_weight', 0.0)
        return vector, total_weight
    
    return None, 0.0

def calculate_user_vector(user_id, user_db=None, data_db=None, force_recalc=False):
    """
    Calcula o obtiene el vector de usuario.
    
    Args:
        user_id: ID del usuario
        user_db: Colección de usuarios
        data_db: Colección de datos
        force_recalc: Si True, recalcula desde cero
    
    Returns:
        tuple: (vector, total_weight)
    """
    if user_db is None or data_db is None:
        user_db, data_db = get_database_connections()
    
    # Si no forzar recálculo, intentar obtener de la BD
    if not force_recalc:
        vector, weight = get_user_vector_from_db(user_id, user_db)
        if vector is not None:
            return vector, weight
    
    # Recalcular desde cero
    return get_full_recalc_user_vector(user_id, user_db=user_db, data_db=data_db)

def get_full_recalc_user_vector(user_id, user_db=None, data_db=None, now=None, lambda_decay=0.05):
    """
    Versión adaptada que acepta conexiones externas.
    """
    if user_db is None or data_db is None:
        user_db, data_db = get_database_connections()
    
    # Convertir user_id si es string
    if isinstance(user_id, str):
        user_id = ObjectId(user_id)
    
    # Obtener interacciones del usuario
    likes, saves, visits = get_all_user_interactions(user_id, user_db, data_db)
    
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)

    total_weight = 0.0
    vector_sum = None

    def add_items(items, strength):
        nonlocal vector_sum, total_weight
        for item in items:
            ts = item["ts"]
            
            if isinstance(ts, datetime.datetime) and ts.tzinfo is None:
                ts = ts.replace(tzinfo=datetime.timezone.utc)
            
            vec = np.array(item["vector"], dtype=float)
            age_days = (now - ts).total_seconds() / 86400.0
            decay = math.exp(-lambda_decay * age_days)
            weight = strength * decay
            weighted_vec = vec * weight

            if vector_sum is None:
                vector_sum = weighted_vec
            else:
                vector_sum += weighted_vec

            total_weight += weight

    add_items(likes, strength=LIKE_STRENGTH)
    add_items(saves, strength=SAVE_STRENGTH)
    add_items(visits, strength=VISIT_STRENGTH)

    if vector_sum is None:
        return None, 0.0

    norm = np.linalg.norm(vector_sum)
    if norm == 0:
        normalized = vector_sum
    else:
        normalized = vector_sum / norm

    return normalized, total_weight

def get_all_user_interactions(user_id, user_db=None, data_db=None):
    """
    Versión adaptada que acepta conexiones externas.
    """
    if user_db is None or data_db is None:
        user_db, data_db = get_database_connections()
    
    if isinstance(user_id, str):
        user_id = ObjectId(user_id)
    
    user = user_db.find_one({'_id': user_id})
    if user is None:
        raise ValueError(f"user not found: {user_id}")

    likes = user.get('likes', [])
    saves = user.get('saves', [])
    visits = user.get('visits', [])

    def _fetch_embeddings(actions: list[dict]):
        if not actions:
            return []
        
        ids = [ObjectId(action['id']) for action in actions]
        docs = data_db.find({'_id': {'$in': ids}}, {'vector': 1})
        id_to_emb = {doc['_id']: doc.get('vector') for doc in docs}
        
        return [{**action, 'vector': id_to_emb[ObjectId(action['id'])]} 
                for action in actions]

    likes = _fetch_embeddings(likes)
    saves = _fetch_embeddings(saves)
    visits = _fetch_embeddings(visits)

    return likes, saves, visits

def get_user_seen_event_ids(user_id, user_db=None):
    """Versión adaptada"""
    if user_db is None:
        user_db, _ = get_database_connections()
    
    if isinstance(user_id, str):
        user_id = ObjectId(user_id)
    
    user = user_db.find_one({'_id': user_id}, {'seen': 1})
    return user.get('seen', []) if user else []

def get_events_from_user(user_id, user_db=None, interaction_types=None):
    """Versión adaptada"""
    if user_db is None:
        user_db, _ = get_database_connections()
    
    if isinstance(user_id, str):
        user_id = ObjectId(user_id)
        
    if interaction_types is None:
        interaction_types = ['likes', 'saves', 'visits']
    
    user = user_db.find_one({'_id': user_id}, {'likes': 1, 'saves': 1, 'visits': 1})
    if user is None:
        return []
    
    interaction_weights = {
        'likes': LIKE_STRENGTH,
        'saves': SAVE_STRENGTH,
        'visits': VISIT_STRENGTH
    }
    
    events = []
    for interaction_type in interaction_types:
        weight = interaction_weights.get(interaction_type, 1.0)
        for interaction in user.get(interaction_type, []):
            event_id = ObjectId(interaction['id'])
            events.append((event_id, interaction_type, weight))
    
    return events

# ============================================================================
# SISTEMA DE RECOMENDACIÓN COLABORATIVO - FUNCIONES PRINCIPALES
# ============================================================================

def get_collaborative_recommendations(
    user_id,
    n=10,
    num_similar_users=20,
    min_similarity=0.0,
    exclude_interacted=True,
    user_db=None,
    data_db=None
):
    """
    Versión adaptada del sistema colaborativo.
    
    Args:
        user_id: ID del usuario (string o ObjectId)
        n: Número de recomendaciones
        user_db: Colección de usuarios (opcional)
        data_db: Colección de datos (opcional)
    
    Returns:
        List of tuples: [(event_id, score), ...]
    """
    if user_db is None or data_db is None:
        user_db, data_db = get_database_connections()
    
    # Obtener vector del usuario
    user_vector, _ = calculate_user_vector(user_id, user_db, data_db)
    if user_vector is None:
        print(f"⚠️  Usuario {user_id} sin vector, no se pueden generar recomendaciones colaborativas")
        return []
    
    # Obtener eventos ya interactuados
    excluded_event_ids = set()
    if exclude_interacted:
        excluded_event_ids = set(get_user_seen_event_ids(user_id, user_db))
    
    # Encontrar usuarios similares
    similar_users = get_top_similar_users(
        user_vector,
        n=num_similar_users,
        user_db=user_db
    )
    
    # Filtrar por similitud mínima
    similar_users = [(uid, sim) for uid, sim in similar_users if sim >= min_similarity]
    
    if not similar_users:
        print("ℹ️  No se encontraron usuarios similares")
        return []
    
    # Agregar eventos de usuarios similares
    event_scores = {}
    
    for similar_user_id, similarity_score in similar_users:
        user_events = get_events_from_user(similar_user_id, user_db)
        
        for event_id, interaction_type, interaction_weight in user_events:
            if event_id in excluded_event_ids:
                continue
            
            score = similarity_score * interaction_weight
            
            if event_id not in event_scores:
                event_scores[event_id] = 0.0
            event_scores[event_id] += score
    
    # Ordenar y retornar
    sorted_events = sorted(
        event_scores.items(),
        key=lambda x: x[1],
        reverse=True
    )
    
    print(f"✅ Recomendaciones colaborativas generadas: {len(sorted_events[:n])}")
    return sorted_events[:n]

def get_hybrid_recommendations_cf(
    user_id,
    n=10,
    cf_weight=0.5,
    content_weight=0.5,
    num_similar_users=20,
    user_db=None,
    data_db=None
):
    """
    Sistema híbrido adaptado desde cf-aux.
    
    Returns:
        List of tuples: [(event_id, final_score), ...]
    """
    if user_db is None or data_db is None:
        user_db, data_db = get_database_connections()
    
    # Recomendaciones colaborativas
    cf_recs = dict(get_collaborative_recommendations(
        user_id=user_id,
        n=n * 2,
        num_similar_users=num_similar_users,
        user_db=user_db,
        data_db=data_db
    ))
    
    # Recomendaciones basadas en contenido (usando vector del usuario)
    user_vector, _ = calculate_user_vector(user_id, user_db, data_db)
    if user_vector is None:
        return []
    
    content_recs = dict(get_top_similar_events(
        user_vector,
        n=n * 2,
        user_id=user_id,
        data_db=data_db
    ))
    
    # Combinar recomendaciones
    all_event_ids = set(cf_recs.keys()) | set(content_recs.keys())
    
    if not all_event_ids:
        return []
    
    # Normalizar scores CF
    if cf_recs:
        max_cf = max(cf_recs.values())
        min_cf = min(cf_recs.values())
        cf_range = max_cf - min_cf if max_cf != min_cf else 1.0
        cf_recs = {eid: (score - min_cf) / cf_range for eid, score in cf_recs.items()}
    
    # Normalizar scores de contenido
    if content_recs:
        max_content = max(content_recs.values())
        min_content = min(content_recs.values())
        content_range = max_content - min_content if max_content != min_content else 1.0
        content_recs = {eid: (score - min_content) / content_range 
                       for eid, score in content_recs.items()}
    
    # Combinar con pesos
    hybrid_scores = {}
    for event_id in all_event_ids:
        cf_score = cf_recs.get(event_id, 0.0) * cf_weight
        content_score = content_recs.get(event_id, 0.0) * content_weight
        hybrid_scores[event_id] = cf_score + content_score
    
    # Ordenar y retornar
    sorted_events = sorted(
        hybrid_scores.items(),
        key=lambda x: x[1],
        reverse=True
    )
    
    return sorted_events[:n]


# Wrapper compatibility function
def hybrid_recommendations(user_id, n=10, cf_weight=0.5, content_weight=0.5, **kwargs):
    """
    Compatibility wrapper used by `unified_recommender`.
    Calls `get_hybrid_recommendations_cf` and returns the same format
    (list of tuples: [(event_id, score), ...]).
    """
    return get_hybrid_recommendations_cf(
        user_id=user_id,
        n=n,
        cf_weight=cf_weight,
        content_weight=content_weight,
        user_db=kwargs.get('user_db'),
        data_db=kwargs.get('data_db'),
        num_similar_users=kwargs.get('num_similar_users', 20)
    )

# ============================================================================
# FUNCIONES DE BÚSQUEDA DE SIMILARIDAD ADAPTADAS
# ============================================================================

def get_top_similar_events(vector, n=10, num_candidates=200, user_id=None, data_db=None, max_fetch_multiplier=5):
    """Versión adaptada"""
    if data_db is None:
        _, data_db = get_database_connections()
    
    exclude_event_ids = None
    if user_id is not None:
        seen_events = get_user_seen_event_ids(user_id)
        exclude_event_ids = set(seen_events) if seen_events else set()
    
    fetch_limit = n * 2 if exclude_event_ids else n
    max_fetch = n * max_fetch_multiplier
    
    results = []
    
    current_fetch = 0
    
    while len(results) < n and current_fetch < max_fetch:
        remaining = n - len(results)
        batch_size = min(remaining * 2, max_fetch - current_fetch)
        
        pipeline = [
            {
                "$vectorSearch": {
                    "queryVector": vector.tolist() if hasattr(vector, 'tolist') else vector,
                    "path": "vector",
                    "numCandidates": num_candidates,
                    "limit": batch_size,
                    "index": "vector_index_events"
                }
            },
            {
                "$project": {
                    "_id": 1,
                    "vector": 1,
                }
            }
        ]
        
        processed_ids = {event_id for event_id, _ in results}
        
        for doc in data_db.aggregate(pipeline):
            event_id = doc["_id"]
            
            if event_id in processed_ids:
                continue
            
            processed_ids.add(event_id)
            
            if exclude_event_ids and event_id in exclude_event_ids:
                continue
            
            similarity = cosine_similarity(vector, doc["vector"])
            results.append((event_id, similarity))
            
            if len(results) >= n:
                break
        
        current_fetch += batch_size
        
        if batch_size == 0:
            break
    
    return results

def get_top_similar_users(vector, n=10, num_candidates=200, user_db=None):
    """Versión adaptada"""
    if user_db is None:
        user_db, _ = get_database_connections()
    
    pipeline = [
        {
            "$vectorSearch": {
                "queryVector": vector.tolist() if hasattr(vector, 'tolist') else vector,
                "path": "vector",
                "numCandidates": num_candidates,
                "limit": n,
                "index": "vector_index_user"
            }
        },
        {
            "$project": {
                "_id": 1,
                "vector": 1,
            }
        }
    ]

    results = []
    for doc in user_db.aggregate(pipeline):
        similarity = dot_similarity(vector, doc["vector"])
        results.append((doc["_id"], similarity))

    return results

# ============================================================================
# FUNCIONES DE ACTUALIZACIÓN PARA INTEGRACIÓN
# ============================================================================

def update_user_vector_in_db(user_id, user_db=None, data_db=None):
    """
    Función para actualizar el vector de usuario en la BD.
    Útil para llamar desde el sistema unificado.
    """
    if user_db is None or data_db is None:
        user_db, data_db = get_database_connections()
    
    try:
        vector, total_weight = calculate_user_vector(user_id, user_db, data_db, force_recalc=True)
        
        if vector is not None:
            user_db.update_one(
                {'_id': ObjectId(user_id) if isinstance(user_id, str) else user_id}, 
                {'$set': {'vector': vector.tolist(), 'total_weight': total_weight}}
            )
            print(f"✅ Vector actualizado para usuario {user_id}")
            return True
        else:
            print(f"⚠️  No se pudo calcular vector para usuario {user_id}")
            return False
            
    except Exception as e:
        print(f"❌ Error actualizando vector de usuario {user_id}: {e}")
        return False
            
# ============================================================================
# INTERFAZ SIMPLIFICADA PARA EL SISTEMA UNIFICADO
# ============================================================================

def get_cf_recommendations_simple(user_id, n_recommendations=10, user_db=None, data_db=None):
    """
    Interfaz simplificada para el sistema unificado.
    
    Args:
        user_id: string del ID de usuario
        n_recommendations: número de recomendaciones
        user_db: colección de usuarios (opcional)
        data_db: colección de datos (opcional)
    
    Returns:
        Dict con event_id como string y score: {event_id_str: score}
    """
    try:
        recommendations = get_collaborative_recommendations(
            user_id=user_id,
            n=n_recommendations,
            user_db=user_db,
            data_db=data_db
        )
        
        # Convertir a formato simple: {event_id_str: score}
        result = {}
        for event_id, score in recommendations:
            result[str(event_id)] = float(score)
        
        return result
        
    except Exception as e:
        print(f"❌ Error en get_cf_recommendations_simple: {e}")
        return {}

# ============================================================================
# TEST Y EJEMPLOS DE USO
# ============================================================================

if __name__ == '__main__':
    """Ejemplos de uso para testing"""
    
    # Ejemplo 1: Obtener recomendaciones colaborativas
    test_user_id = "692223968f85b548309145d3"
    
    print("🧪 Probando sistema colaborativo...")
    cf_recs = get_cf_recommendations_simple(test_user_id, n_recommendations=5)
    print(f"Recomendaciones colaborativas: {cf_recs}")
    
    # Ejemplo 2: Actualizar vector de usuario
    print("\n🧪 Actualizando vector de usuario...")
    success = update_user_vector_in_db(test_user_id)
    print(f"Actualización exitosa: {success}")
    
    # Ejemplo 3: Recomendaciones híbridas
    print("\n🧪 Probando sistema híbrido...")
    hybrid_recs = get_hybrid_recommendations_cf(
        test_user_id,
        n=5,
        cf_weight=0.6,
        content_weight=0.4
    )
    print(f"Recomendaciones híbridas: {hybrid_recs}")
