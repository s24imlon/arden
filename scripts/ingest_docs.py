from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from app.vectorstore.index import VectorStore
from app.utils.helpers import (
    _read_pdf,
    _read_docx,
    get_documents_from_folder,
    chunk_text
)
import logging
from typing import List, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
BATCH_SIZE = 100  # Optimal for Weaviate performance
MAX_FILE_THREADS = 4  # Parallel file processing
RETRY_ATTEMPTS = 3  # For transient failures

def process_file(filepath: str, doc_type: str, vs: VectorStore) -> int:
    """Process a single file with retry logic and proper error handling"""
    for attempt in range(RETRY_ATTEMPTS):
        try:
            # Read file
            text = _read_pdf(filepath) if filepath.endswith(".pdf") else _read_docx(filepath)

            # Chunk and prepare batches
            chunks = chunk_text(text, doc_type=doc_type, method="legal_headers")
            batches = []
            current_batch = []

            for i, (_chunk_text, metadata) in enumerate(chunks):
                current_batch.append({
                    "text": _chunk_text,
                    "doc_type": doc_type,
                    "section": f"section_{i}",
                    **metadata
                })

                if len(current_batch) >= BATCH_SIZE:
                    batches.append(current_batch)
                    current_batch = []

            if current_batch:
                batches.append(current_batch)

            # Store all batches
            total = 0
            for batch in batches:
                vs.batch_store(batch)
                total += len(batch)

            return total

        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed for {filepath}: {str(e)}")
            if attempt == RETRY_ATTEMPTS - 1:
                logger.error(f"Failed to process {filepath} after {RETRY_ATTEMPTS} attempts")
                raise
            continue

    return 0

def batch_ingest():
    """Main ingestion pipeline with comprehensive error handling"""
    vs = VectorStore()
    files = get_documents_from_folder("contracts")

    if not files:
        logger.warning("No documents found in contracts folder")
        return

    total_chunks = 0
    failed_files = []

    try:
        with ThreadPoolExecutor(max_workers=MAX_FILE_THREADS) as executor:
            # Submit all files for processing
            future_to_file = {
                executor.submit(process_file, fp, dt, vs): (fp, dt)
                for fp, dt in files
            }

            # Process with progress bar
            with tqdm(total=len(files), desc="Processing files") as pbar:
                for future in as_completed(future_to_file):
                    filepath, doc_type = future_to_file[future]
                    try:
                        total_chunks += future.result()
                    except Exception as e:
                        logger.error(f"Failed processing {filepath}: {str(e)}")
                        failed_files.append((filepath, str(e)))
                    finally:
                        pbar.update(1)

        # Verification
        if total_chunks > 0:
            sample = vs.client.query.get(
                "ComplianceClause",
                ["_additional {vector}"]
            ).with_limit(1).do()

            if sample["data"]["Get"]["ComplianceClause"][0]["_additional"]["vector"]:
                logger.info(f"Success! Ingested {total_chunks} chunks from {len(files) - len(failed_files)} files")
            else:
                logger.error("Vectors not stored in Weaviate - check schema configuration")

        if failed_files:
            logger.warning(f"Failed to process {len(failed_files)} files:")
            for f, e in failed_files:
                logger.warning(f"- {f}: {e}")

    except Exception as e:
        logger.error(f"Fatal ingestion error: {str(e)}")
        raise
    finally:
        # Clean up any resources if needed
        pass

if __name__ == "__main__":
    batch_ingest()