import numpy as np
from bson import ObjectId
from app.database.database import users_collection, combined_collection
from app.funcs import update_user_vector, get_top_similar_vector_search

# Pesos por tipo de interacción
INTERACTION_WEIGHTS = {
    "save": 0.8,
    "like": 0.5,
    "visit": 1.2
}


def update_user_embedding_and_recommend(user_id: str, item_id: str, interaction: str):
    """Actualiza embedding del usuario + ejecuta vector search + guarda recomendaciones."""

    if not ObjectId.is_valid(user_id) or not ObjectId.is_valid(item_id):
        raise ValueError("Invalid user_id or item_id")

    # ===================
    # 1. Recuperar embedding del item
    # ===================
    item = combined_collection.find_one(
        {"_id": ObjectId(item_id)},
        {"embedding": 1}
    )
    if not item or "embedding" not in item:
        raise ValueError("Item does not contain a valid embedding")

    item_vec = np.array(item["embedding"], dtype=float)

    # ===================
    # 2. Recuperar embedding del usuario
    # ===================
    user = users_collection.find_one(
        {"_id": ObjectId(user_id)},
        {"embedding": 1}
    )

    if user and "embedding" in user:
        user_vec = np.array(user["embedding"], dtype=float)
    else:
        # Si no tiene embedding → inicializar con el del item
        user_vec = item_vec.copy()

    # ===================
    # 3. Actualizar con el peso según interacción
    # ===================
    weight = INTERACTION_WEIGHTS.get(interaction, 0.3)
    new_vec = update_user_vector(user_vec, item_vec, weight=weight)

    # Guardar en BD
    users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"embedding": new_vec.tolist()}}
    )

    # ===================
    # 4. Vector search (Mongo Atlas)
    # ===================
    recommendations = get_top_similar_vector_search(
        embedding=new_vec.tolist(),
        n=20,
        num_candidates=200,
        connection_string="mongodb+srv://mrclpgg_db_user:K9NMlwFHZpeltCwI@cluster0.qdopesi.mongodb.net/?appName=Cluster0",
        db_name="recommendations-system",
        collection_name="combined_vectors",
        index_name="vector_index"
    )

    # Extraer solo IDs
    recommended_ids = [r[0] for r in recommendations]

    # ===================
    # 5. Guardar recomendaciones al usuario
    # ===================
    users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"recommendations": recommended_ids}}
    )

    return {
        "updated_vector": new_vec.tolist(),
        "recommended_ids": recommended_ids
    }
