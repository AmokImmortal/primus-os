# ingest.py
"""
PRIMUS RAG - Document ingestion pipeline
Upgraded to use:
- embedder.py (GPU embeddings + model selector)
- vector_store.py (FAISS or fallback)
"""

import os
import argparse
from pathlib import Path

from embedder import get_embedder
from vector_store import VectorStore


def load_text_files(folder):
    """Load all .txt files recursively."""
    files = []
    for root, _, filenames in os.walk(folder):
        for f in filenames:
            if f.lower().endswith(".txt"):
                full_path = os.path.join(root, f)
                with open(full_path, "r", encoding="utf-8", errors="ignore") as file:
                    files.append((full_path, file.read()))
    return files


def chunk_text(text, chunk_size=500, overlap=50):
    """Simple fixed-size chunking."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start += (chunk_size - overlap)
    return chunks


def ingest_folder(path, chunk_size, overlap, model_name):
    print(f"[PRIMUS RAG] Loading files from: {path}")
    print(f"[PRIMUS RAG] Using embedding model: {model_name}")

    files = load_text_files(path)
    if not files:
        print("[ERROR] No .txt files found.")
        return

    all_chunks = []
    all_metadata = []

    for file_path, text in files:
        print(f" - Chunking file: {file_path}")
        chunks = chunk_text(text, chunk_size, overlap)

        for i, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            all_metadata.append({
                "source_file": file_path,
                "chunk_index": i,
                "text": chunk
            })

    print(f"[PRIMUS RAG] Total chunks: {len(all_chunks)}")

    # --- Embedding ---
    embedder = get_embedder(model_name)
    vectors = embedder.embed(all_chunks)
    print(f"[PRIMUS RAG] Embedded {len(vectors)} vectors.")

    # --- Vector Store ---
    backend_type = "faiss" if embedder.using_gpu else "fallback"
    print(f"[PRIMUS RAG] Vector store backend: {backend_type}")

    store = VectorStore(backend=backend_type)
    result = store.add(vectors, all_metadata)

    if result["status"] != "ok":
        print("[ERROR] Failed to add vectors:", result)
        return

    store.save()
    print("[PRIMUS RAG] Ingest complete.")
    print(f"Stored {len(all_chunks)} chunks.")
    print("Files saved to: rag/vector_store/")


def main():
    parser = argparse.ArgumentParser(description="PRIMUS RAG Ingest System")

    parser.add_argument("--path", type=str, required=True,
                        help="Folder of text files to ingest")

    parser.add_argument("--chunk-size", type=int, default=500)
    parser.add_argument("--overlap", type=int, default=50)

    # NEW ARGUMENT HERE
    parser.add_argument("--model", type=str, default="all-MiniLM-L6-v2",
                        help="Embedding model (ex: all-MiniLM-L6-v2, bge-small-en-v1.5)")

    args = parser.parse_args()
    ingest_folder(args.path, args.chunk_size, args.overlap, args.model)


if __name__ == "__main__":
    main()
