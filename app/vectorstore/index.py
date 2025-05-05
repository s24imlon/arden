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
        self._create_schema("ComplianceClause", force=False)
        self._create_schema("ContractClause", force=False)

    def _create_schema(self, class_name, force=False):
        schema = {
            "class": class_name,
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
                self.client.schema.delete_class(class_name)
            except:
                pass
            self.client.schema.create_class(schema)

    def batch_store(self, objects: List[dict], class_name="ComplianceClause"):
        if not objects:
            return

        uuids = [str(uuid.uuid4()) for _ in objects]

        # Generate vectors
        vectors = []
        for obj in objects:
            if isinstance(obj["text"], list):
                logging.warning(f"Malformed text detected: {obj['text']}")
                text = " ".join(obj["text"])  # Convert list to string
            else:
                text = obj["text"]

            vector = self.encoder.encode(text).tolist()
            vectors.append(vector)

        logging.info(f"Generated {len(vectors)} vectors")
        logging.info(f"Sample vector length: {len(vectors[0])}")  # Should be 384 for all-MiniLM-L6-v2
        logging.info(f"Sample vector sum: {sum(vectors[0])}")

        # Batch upload with verification
        successful_ids = []
        with self.client.batch(
            batch_size=1,
            dynamic=False,
            callback=self._handle_batch_errors
        ) as batch:
            for obj, vector, _uuid in zip(objects, vectors, uuids):
                batch.add_data_object(
                    data_object=obj,
                    class_name=class_name,
                    uuid=_uuid,
                    vector=vector  # Ensure this is included
                )
                successful_ids.append(_uuid)

        # Immediate verification
        for _uuid in successful_ids:
            obj = self.client.data_object.get_by_id(
                _uuid,
                class_name=class_name,
                with_vector=True  # Important!
            )
            if not obj or "vector" not in obj:
                raise RuntimeError(f"Vector not attached to object {_uuid}")

        return successful_ids

    def _handle_batch_errors(self, results, *args):
        """Handle batch errors with proper signature for Weaviate 1.23.4"""
        if results is not None:
            for result in results:
                if 'errors' in result.get('result', {}):
                    error = result['result']['errors']['error'][0]
                    logging.error(f"Batch error: {error}")
                elif 'status' in result and result['status'] != 'SUCCESS':
                    logging.error(f"Batch status failure: {result}")

    def _verify_vectors(self, ids: List[str], class_name):
        """Verify vectors were stored"""
        results = self.client.query.get(
            class_name,
            []
        ).with_additional(["id", "vector"]).with_where({
            "path": ["id"],
            "operator": "ContainsAny",
            "valueStringArray": ids
        }).do()

        for obj in results["data"]["Get"][class_name]:
            if not obj["_additional"]["vector"]:
                raise RuntimeError(f"Vector missing for {obj['_additional']['id']}")

    def search(self, query: str, limit: int = 10, class_name="ComplianceClause"):
        vector = self.encoder.encode(query).tolist()
        return self.client.query.get(
            class_name,
            ["text", "doc_type", "section"]
        ).with_additional(["distance"]).with_near_vector({
            "vector": vector,
            "certainty": 0.55
        }).with_limit(limit).do()

    def __del__(self):
        """Clean up executor when VectorStore is destroyed"""
        self._executor.shutdown(wait=True)