
from typing import List, Dict, Optional
from bson import ObjectId
import numpy as np
from app.utils.cf_aux import hybrid_recommendations
from datetime import datetime
from pymongo import MongoClient
import os

class UnifiedRecommender:
    def __init__(self):
        self.cold_start_threshold = 5  # Mínimo de interacciones para salir de cold start
        self.hybrid_weights = {
            'cold_start': 0.0,
            'content': 0.4,
            'collaborative': 0.6
        }
    
    def get_user_interaction_count(self, user_id: str, users_collection) -> int:
        """Cuenta las interacciones totales del usuario"""
        user = users_collection.find_one(
            {"_id": ObjectId(user_id)},
            {"likes": 1, "saves": 1, "visits": 1}
        )
        if not user:
            return 0
        
        total_interactions = (
            len(user.get('likes', [])) +
            len(user.get('saves', [])) +
            len(user.get('visits', []))
        )
        return total_interactions
    
    def is_cold_start_user(self, user_id: str, users_collection) -> bool:
        """Determina si el usuario está en fase cold start"""
        return self.get_user_interaction_count(user_id, users_collection) < self.cold_start_threshold
    
    def generate_unified_recommendations(
        self,
        user_id: str,
        users_collection,
        n_recommendations: int = 20
    ) -> List[str]:
        """
        Genera recomendaciones unificadas según el estado del usuario
        """
        # Verificar fase del usuario
        if self.is_cold_start_user(user_id, users_collection):
            print(f"🎯 Usuario {user_id} en COLD START")
            return self._get_cold_start_recommendations(user_id, users_collection, n_recommendations)
        else:
            print(f"🎯 Usuario {user_id} en FASE HÍBRIDA")
            return self._get_hybrid_recommendations(user_id, users_collection, n_recommendations)
    
    def _get_cold_start_recommendations(
        self,
        user_id: str,
        users_collection,
        n_recommendations: int
    ) -> List[str]:
        """Recomendaciones para usuarios nuevos"""
        from app.utils.cold_start import generate_cold_start_recommendations
        
        user = users_collection.find_one({"_id": ObjectId(user_id)})
        preferences = user.get('preferences', []) if user else []
        
        # Conectar a la base de datos para cold start
        client = MongoClient(os.getenv("MONGO_URI"))
        db = client[os.getenv("DB_NAME")]
        combined_collection = db["combined"]
        
        recommendations = generate_cold_start_recommendations(
            preferences,
            combined_collection,
            n_recommendations
        )
        
        client.close()
        return recommendations
    
    def _get_hybrid_recommendations(
        self,
        user_id: str,
        users_collection,
        n_recommendations: int
    ) -> List[str]:
        """Combina recomendaciones content-based y collaborative filtering"""
        # 1. Obtener recomendaciones content-based
        content_recs = self._get_content_based_recommendations(user_id, users_collection, n_recommendations * 2)
        
        # 2. Obtener recomendaciones collaborative filtering
        cf_recs = self._get_collaborative_recommendations(user_id, users_collection, n_recommendations * 2)
        
        # 3. Combinar y rankear
        combined_recs = self._combine_recommendations(content_recs, cf_recs, n_recommendations)
        
        return combined_recs
    
    def _get_content_based_recommendations(
        self,
        user_id: str,
        users_collection,
        n_recommendations: int
    ) -> Dict[str, float]:
        """Obtiene recomendaciones del sistema content-based existente"""
        from app.utils.recommender_engine import get_user_vector, get_top_similar_items
        
        user_vector = get_user_vector(user_id, users_collection)
        if user_vector is None:
            return {}
        
        recommended_ids = get_top_similar_items(user_vector, n=n_recommendations)
        
        # Convertir a diccionario con scores (simulados para ranking)
        content_scores = {}
        for i, item_id in enumerate(recommended_ids):
            # Score decay basado en posición (mejores primeros)
            score = 1.0 - (i * 0.1 / len(recommended_ids))
            content_scores[item_id] = score * self.hybrid_weights['content']
        
        return content_scores
    
    def _get_collaborative_recommendations(
        self,
        user_id: str,
        users_collection,
        n_recommendations: int
    ) -> Dict[str, float]:
        """Obtiene recomendaciones del sistema collaborative filtering"""
        try:
            
            # Convertir user_id a ObjectId para cf-aux
            user_oid = ObjectId(user_id)
            
            # Obtener recomendaciones híbridas de cf-aux
            cf_results = hybrid_recommendations(
                user_id=user_oid,
                n=n_recommendations,
                cf_weight=0.6,
                content_weight=0.4
            )
            
            # Convertir a diccionario con scores normalizados
            cf_scores = {}
            max_score = max([score for _, score in cf_results]) if cf_results else 1.0
            
            for item_id, score in cf_results:
                cf_scores[str(item_id)] = (score / max_score) * self.hybrid_weights['collaborative']
            
            return cf_scores
            
        except Exception as e:
            print(f"⚠️  Error en collaborative filtering: {e}")
            return {}
    
    def _combine_recommendations(
        self,
        content_scores: Dict[str, float],
        cf_scores: Dict[str, float],
        n_recommendations: int
    ) -> List[str]:
        """Combina y rankea recomendaciones de ambos sistemas"""
        combined_scores = {}
        
        # Combinar scores de content-based
        for item_id, score in content_scores.items():
            combined_scores[item_id] = combined_scores.get(item_id, 0) + score
        
        # Combinar scores de collaborative filtering
        for item_id, score in cf_scores.items():
            combined_scores[item_id] = combined_scores.get(item_id, 0) + score
        
        # Ordenar por score y retornar top N
        sorted_items = sorted(
            combined_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:n_recommendations]
        
        return [item_id for item_id, score in sorted_items]