import os
import weaviate
from sentence_transformers import SentenceTransformer
from weaviate.util import generate_uuid5
import numpy as np
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List
import uuid
import time

class VectorStore:
    def __init__(self):
        weaviate_url = os.getenv("WEAVIATE_URL", "http://weaviate:8080")
        retries = 5
        for attempt in range(retries):
            try:
                self.client = weaviate.Client(
                    url=weaviate_url,
                    additional_headers={"X-Vectorize-On-Create": "false"}
                )
                if self.client.is_ready():
                    break
            except Exception as e:
                print(f"Waiting for Weaviate to be ready... attempt {attempt+1}")
                time.sleep(5)
        else:
            raise RuntimeError("Failed to connect to Weaviate after retries")

        self.encoder = SentenceTransformer(
            os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        )
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._create_schema(force=False)

    def _create_schema(self, force=False):
        schema = {
            "class": "ComplianceClause",
            "vectorizer": "none",
            "vectorIndexType": "hnsw",
            "vectorIndexConfig": {
                "skip": False,
                "distance": "cosine"
            },
            "properties": [
                {"name": "text", "dataType": ["text"], "indexSearchable": True},
                {"name": "doc_type", "dataType": ["text"], "indexFilterable": True},
                {"name": "section", "dataType": ["text"], "indexFilterable": True}
            ]
        }

        if force:
            try:
                self.client.schema.delete_class("ComplianceClause")
            except:
                pass
            self.client.schema.create_class(schema)

    def batch_store(self, objects: List[dict]):
        if not objects:
            return

        uuids = [str(uuid.uuid4()) for _ in objects]

        try:
            vectors = list(self._executor.map(
                lambda obj: self.encoder.encode(obj["text"]).tolist(),
                objects
            ))

            successful_ids = []
            with self.client.batch(
                batch_size=50,
                dynamic=True,
                callback=self._handle_batch_errors
            ) as batch:
                for obj, vector, _uuid in zip(objects, vectors, uuids):
                    batch.add_data_object(
                        data_object=obj,
                        class_name="ComplianceClause",
                        uuid=_uuid,
                        vector=vector
                    )
                    successful_ids.append(_uuid)

            if not successful_ids:
                raise RuntimeError("Batch upload failed — no objects stored!")

            self._verify_vectors(successful_ids)

        except Exception as e:
            logging.error(f"Batch store failed: {str(e)}")
            raise

    def _handle_batch_errors(self, results):
        """Handle Weaviate batch errors"""
        if results and 'errors' in results:
            for error in results['errors']:
                logging.error(f"Weaviate error: {error['message']}")
            raise RuntimeError("Batch operation failed")

    def _verify_vectors(self, ids: List[str]):
        """Verify vectors were stored"""
        results = self.client.query.get(
            "ComplianceClause",
            []
        ).with_additional(["id", "vector"]).with_where({
            "path": ["id"],
            "operator": "ContainsAny",
            "valueStringArray": ids
        }).do()

        for obj in results["data"]["Get"]["ComplianceClause"]:
            if not obj["_additional"]["vector"]:
                raise RuntimeError(f"Vector missing for {obj['_additional']['id']}")

    def search(self, query: str, limit: int = 10):
        vector = self.encoder.encode(query).tolist()
        return self.client.query.get(
            "ComplianceClause",
            ["text", "doc_type", "section"]
        ).with_additional(["distance"]).with_near_vector({
            "vector": vector,
            "certainty": 0.7
        }).with_limit(limit).do()

    def __del__(self):
        """Clean up executor when VectorStore is destroyed"""
        self._executor.shutdown(wait=True)