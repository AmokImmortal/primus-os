# query.py
"""
PRIMUS RAG - Query System
Search FAISS vector index and return relevant chunks
"""

import argparse
from embedder import get_embedder
from vector_store import VectorStore


def main():
    parser = argparse.ArgumentParser(description="PRIMUS RAG Query System")
    parser.add_argument("--query", type=str, required=True, help="Your question")
    parser.add_argument("--model", type=str, default="all-MiniLM-L6-v2")
    parser.add_argument("--top-k", type=int, default=5)

    args = parser.parse_args()

    # Load embedder
    print(f"[PRIMUS RAG] Loading embedder: {args.model}")
    embedder = get_embedder(args.model)

    # Load vector store
    print("[PRIMUS RAG] Loading vector store...")
    store = VectorStore(backend="faiss")

    loaded = store.load()
    if loaded["status"] != "ok":
        print(f"[ERROR] Could not load vector store: {loaded['message']}")
        return

    # Embed query
    print(f"[PRIMUS RAG] Embedding query text: \"{args.query}\"")
    query_vec = embedder.embed([args.query])[0]

    # Perform search
    print("[PRIMUS RAG] Running similarity search...")
    results = store.search(query_vec, top_k=args.top_k)

    if not results:
        print("\n[PRIMUS RAG] No results found.\n")
        return

    # Print results
    print("\n=== SEARCH RESULTS ===")
    for i, res in enumerate(results, start=1):
        print(f"\nResult {i}:")
        print(f"  Score: {res['score']}")
        print(f"  Source File: {res['metadata']['source_file']}")
        print("  Text Chunk:")
        print("  ---------------------------")
        print(res['metadata']['text'])
        print("  ---------------------------")


if __name__ == "__main__":
    main()