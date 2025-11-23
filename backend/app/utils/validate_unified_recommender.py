"""
Script de validación para `UnifiedRecommender`.

Este script crea mocks ligeros de las dependencias para verificar que:
- Usuarios con pocas interacciones usan la ruta "cold start".
- Usuarios con suficientes interacciones usan la ruta híbrida
  (content + collaborative) y combinan resultados.

Ejecutar:
    python validate_unified_recommender.py

No requiere MongoDB en ejecución porque las dependencias se simulan.
"""
from bson import ObjectId
import numpy as np
import os
import sys

"""
Compatibilidad al ejecutar el script directamente desde `backend/app/utils`:
- Inserta la carpeta `backend` en `sys.path` para que `import app...` funcione.
"""

# Añadir project root (la carpeta `backend`) al path si no está
here = os.path.dirname(os.path.abspath(__file__))
# subir dos niveles: utils -> app -> backend
backend_root = os.path.abspath(os.path.join(here, '..', '..'))
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

import app.utils.unified_recommender as ur_mod
import app.utils.cold_start as cold_start_mod
import app.utils.recommender_engine as re_mod
import app.utils.cf_aux as cf_mod


class MockUsersCollection:
    def __init__(self, docs):
        # docs: dict of ObjectId -> document
        self.docs = {ObjectId(k) if not isinstance(k, ObjectId) else k: v for k, v in docs.items()}

    def find_one(self, query, projection=None):
        # soporta consultas por {'_id': ObjectId(...)}
        _id = query.get('_id')
        if isinstance(_id, ObjectId):
            return self.docs.get(_id)
        # si pasaron string, intentar convertir
        try:
            oid = ObjectId(_id)
            return self.docs.get(oid)
        except Exception:
            return None

    def update_one(self, query, update):
        # operación mínima para evitar errores si se llama
        _id = query.get('_id')
        if isinstance(_id, ObjectId) and _id in self.docs:
            # aplicar $set simple
            if isinstance(update, dict) and '$set' in update:
                self.docs[_id].update(update['$set'])
        # Simular el resultado de pymongo UpdateResult
        class Result:
            def __init__(self, modified_count):
                self.modified_count = modified_count

        # Si el documento existe y se actualizó, devolver modified_count=1
        if isinstance(_id, ObjectId) and _id in self.docs:
            return Result(modified_count=1)
        # Si no existe, simular que no se modificó
        return Result(modified_count=0)


class MockMongoClient:
    def __init__(self, *args, **kwargs):
        pass

    def __getitem__(self, name):
        # retornar un objeto que tenga la colección 'combined'
        class DB:
            def __getitem__(self, coll_name):
                # coleccion dummy
                class Coll:
                    def find(self, *args, **kwargs):
                        return []

                    def find_one(self, *args, **kwargs):
                        return None

                    def aggregate(self, *args, **kwargs):
                        return []

                    def limit(self, *args, **kwargs):
                        return []
                return Coll()
        return DB()

    def close(self):
        pass


def run_validation():
    # Preparar ids
    cold_user_id = ObjectId()
    hybrid_user_id = ObjectId()

    # Usuarios de prueba
    users = {
        cold_user_id: {
            '_id': cold_user_id,
            'preferences': ['cultura', 'gastronomía'],
            'likes': [],
            'saves': [],
            'visits': []
        },
        hybrid_user_id: {
            '_id': hybrid_user_id,
            'preferences': ['playas'],
            # total interactions = 5 (>= threshold 5 => híbrido)
            'likes': [{'id': '1'}, {'id': '2'}, {'id': '3'}],
            'saves': [{'id': '4'}],
            'visits': [{'id': '5'}]
        }
    }

    users_collection = MockUsersCollection({str(k): v for k, v in users.items()})

    # 1) Mock cold_start.generate_cold_start_recommendations
    def mock_generate_cold_start_recommendations(preferences, combined_collection, n_recommendations):
        # devolver lista fija para comprobar flujo
        return [f'cold_{i}' for i in range(min(n_recommendations, 6))]

    cold_start_mod.generate_cold_start_recommendations = mock_generate_cold_start_recommendations

    # 2) Mock recommender_engine.get_user_vector y get_top_similar_items
    def mock_get_user_vector(user_id, users_collection_param):
        # retornar vector simple (dim 3) no-nulo
        return np.array([1.0, 0.0, 0.0])

    def mock_get_top_similar_items(user_vector, n=10):
        return [f'cb_{i}' for i in range(n)]

    re_mod.get_user_vector = mock_get_user_vector
    re_mod.get_top_similar_items = mock_get_top_similar_items

    # 3) Mock cf_aux.hybrid_recommendations
    cf_item_a = ObjectId('a' * 24)
    cf_item_b = ObjectId('b' * 24)

    def mock_hybrid_recommendations(user_id, n, cf_weight, content_weight):
        # retornar tuplas (ObjectId, score)
        return [(cf_item_a, 0.9), (cf_item_b, 0.5)]

    # Reemplazar en cf_aux (por si alguien importa desde allí)
    cf_mod.hybrid_recommendations = mock_hybrid_recommendations
    # Reemplazar también la referencia que `unified_recommender` importó al iniciar
    # (unified_recommender hace `from app.utils.cf_aux import hybrid_recommendations`)
    ur_mod.hybrid_recommendations = mock_hybrid_recommendations

    # 4) Evitar conexiones reales en unified_recommender (para cold_start crea MongoClient)
    ur_mod.MongoClient = MockMongoClient

    # Instanciar el recomendador
    ur = ur_mod.UnifiedRecommender()

    print("\n-- Probando Cold Start --")
    cold_recs = ur.generate_unified_recommendations(str(cold_user_id), users_collection, n_recommendations=5)
    print("Recomendaciones (cold):", cold_recs)
    assert isinstance(cold_recs, list), "Cold start debe retornar una lista"
    assert all(r.startswith('cold_') for r in cold_recs), "Cold start debe usar generate_cold_start_recommendations mock"

    print("OK: Cold start pasó las comprobaciones")

    print("\n-- Probando Ruta Híbrida --")
    hybrid_recs = ur.generate_unified_recommendations(str(hybrid_user_id), users_collection, n_recommendations=5)
    print("Recomendaciones (híbridas):", hybrid_recs)

    assert isinstance(hybrid_recs, list), "Híbrido debe retornar una lista"
    # Debe contener al menos elementos provenientes del content-based o del cf mock
    has_cb = any(r.startswith('cb_') for r in hybrid_recs)
    has_cf = any(r == str(cf_item_a) or r == str(cf_item_b) for r in hybrid_recs)
    assert has_cb or has_cf, "Resultados híbridos deben contener id de content o collaborative mock"

    print("OK: Ruta híbrida pasó las comprobaciones")

    print("\nTodos los tests de validación pasaron correctamente.")


    # ---------------------------
    # Prueba adicional: interacciones
    # ---------------------------
    print("\n-- Probando efecto de likes/saves/visits en recomendaciones --")

    # Crear conjunto de items en 'combined' con vectores conocidos
    dim = getattr(re_mod, 'EMBEDDING_DIM', 384)
    combined_items = {
        'item0': (np.array([1.0] + [0.0] * (dim - 1), dtype=np.float32)),
        'item1': (np.array([0.9, 0.1] + [0.0] * (dim - 2), dtype=np.float32)),
        'item2': (np.array([0.0, 1.0] + [0.0] * (dim - 2), dtype=np.float32)),
        'item3': (np.array([0.0, 0.9, 0.1] + [0.0] * (dim - 3), dtype=np.float32)) if dim >= 3 else np.zeros(dim, dtype=np.float32),
        'item4': (np.array([0.0] * (dim - 1) + [1.0], dtype=np.float32)),
    }

    # Mock get_item_embedding para usar combined_items
    def mock_get_item_embedding(item_id, item_type, *args, **kwargs):
        vec = combined_items.get(item_id)
        if vec is None:
            return None
        # Asegurar dimension correcta (padding/truncation)
        if vec.shape[0] != dim:
            v = np.zeros(dim, dtype=np.float32)
            copy_len = min(dim, vec.shape[0])
            v[:copy_len] = vec[:copy_len]
            return v
        return vec

    # Mock búsqueda vectorial: retorna ids ordenados por coseno
    def mock_get_top_similar_items(user_vector, n=10):
        def cosine(a, b):
            a = np.array(a, dtype=float)
            b = np.array(b, dtype=float)
            na = np.linalg.norm(a)
            nb = np.linalg.norm(b)
            if na == 0 or nb == 0:
                return 0.0
            return float(np.dot(a, b) / (na * nb))

        scores = [(iid, cosine(user_vector, vec)) for iid, vec in combined_items.items()]
        scores.sort(key=lambda x: x[1], reverse=True)
        return [iid for iid, _ in scores[:n]]

    # Mock get_user_vector to read from users_collection or initialize
    def mock_get_user_vector(user_id, users_collection_param):
        user = users_collection_param.find_one({"_id": ObjectId(user_id)})
        if user and user.get('embedding'):
            return np.array(user['embedding'], dtype=np.float32)
        # inicializar mediante la función real (usa users_collection.update_one mock)
        return re_mod.initialize_user_vector(user_id, users_collection_param)

    # Reemplazar funciones en recommender_engine
    re_mod.get_item_embedding = mock_get_item_embedding
    re_mod.get_top_similar_items = mock_get_top_similar_items
    re_mod.get_user_vector = mock_get_user_vector

    # Preparar usuario de prueba
    interaction_user_id = ObjectId()
    users_collection.docs[interaction_user_id] = {
        '_id': interaction_user_id,
        'preferences': ['cultura'],
        'likes': [],
        'saves': [],
        'visits': []
    }

    # Instanciar un UnifiedRecommender nuevo para aislar configuración
    ur2 = ur_mod.UnifiedRecommender()
    # Forzar que el híbrido priorice content-based para esta prueba
    ur2.hybrid_weights = {'cold_start': 0.0, 'content': 1.0, 'collaborative': 0.0}
    # Bajar umbral para que las pocas interacciones de la prueba salgan de cold-start
    ur2.cold_start_threshold = 1

    # Recs antes de interacciones
    recs_before = ur2.generate_unified_recommendations(str(interaction_user_id), users_collection, n_recommendations=5)
    print("Recs antes:", recs_before)

    # Simular like en item0, save en item1, visit en item2 (esto usa recommender_engine.update_user_recommendations)
    re_mod.update_user_recommendations(str(interaction_user_id), 'like', 'item0', 'event', users_collection, n_recommendations=5)
    re_mod.update_user_recommendations(str(interaction_user_id), 'save', 'item1', 'event', users_collection, n_recommendations=5)
    re_mod.update_user_recommendations(str(interaction_user_id), 'visit', 'item2', 'event', users_collection, n_recommendations=5)

    # Añadir las interacciones al documento del usuario para salir de cold-start
    import datetime as _dt
    users_collection.docs[interaction_user_id].setdefault('likes', []).append({'id': 'item0', 'ts': _dt.datetime.now()})
    users_collection.docs[interaction_user_id].setdefault('saves', []).append({'id': 'item1', 'ts': _dt.datetime.now()})
    users_collection.docs[interaction_user_id].setdefault('visits', []).append({'id': 'item2', 'ts': _dt.datetime.now()})

    # Recs después de interacciones
    recs_after = ur2.generate_unified_recommendations(str(interaction_user_id), users_collection, n_recommendations=5)
    print("Recs después:", recs_after)

    # Comprobaciones: al menos uno de los items interactuados debe aparecer en las recomendaciones content-based
    interacted = {'item0', 'item1', 'item2'}
    found = any(r in interacted for r in recs_after)
    assert found, f"Las recomendaciones no reflejan las interacciones: {recs_after}"

    print("OK: Prueba de interacciones pasó — recomendaciones reflejan likes/saves/visits")


if __name__ == '__main__':
    run_validation()
