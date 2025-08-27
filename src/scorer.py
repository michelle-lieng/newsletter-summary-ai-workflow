from typing import List, Dict, Any
import numpy as np
from sentence_transformers import SentenceTransformer

class Scorer():
    @staticmethod
    def score_chunks_against_interests(
        chunks: List[Dict[str, Any]],
        interests: List[str],
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        include_heading: bool = False,   # set True to include "heading" in text
        batch_size: int = 64,
    ) -> List[Dict[str, Any]]:
        """
        For each chunk, compute cosine similarity to EACH interest.
        Returns the original chunk fields plus:
        - scores: {interest -> score}
        - best_interest, best_score
        """
        interests_clean = [s.strip() for s in interests if str(s).strip()]
        if not interests_clean:
            raise ValueError("interests list is empty.")

        # Build the text to score per chunk
        texts = []
        for ch in chunks:
            parts = []
            if include_heading and ch.get("heading"):
                parts.append(str(ch["heading"]))
            if ch.get("content"):
                parts.append(str(ch["content"]))
            texts.append(" ".join(parts).strip())

        model = SentenceTransformer(model_name)
        chunk_embs = model.encode(texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False)
        interest_embs = model.encode(interests_clean, normalize_embeddings=True, show_progress_bar=False)

        # cosine sims = dot product because they're L2-normalized
        sims = np.asarray(chunk_embs) @ np.asarray(interest_embs).T  # [num_chunks, num_interests]

        results = []
        for i, ch in enumerate(chunks):
            per_interest = {interests_clean[j]: round(float(sims[i, j]), 4) for j in range(len(interests_clean))}
            best_j = int(np.argmax(sims[i]))
            out = {
                **ch,
                "scores": per_interest,
                "best_interest": interests_clean[best_j],
                "best_score": round(float(sims[i, best_j]), 4),
            }
            results.append(out)

        return results

    @staticmethod
    def filter_scored_chunks(scored: List[Dict[str, Any]], threshold: float = 0.38) -> List[Dict[str, Any]]:
        """Optional: keep only chunks whose best_score >= threshold."""
        return [c for c in scored if c.get("best_score", 0.0) >= threshold]
