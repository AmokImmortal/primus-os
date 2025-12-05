# test_vector_store.py
import numpy as np
from rag.vector_store import VectorStore
import json

# load embeddings saved earlier (if you used ingest.py)
emb = np.load("rag/vector_store/embeddings.npy")
# create dummy metadata if not present
try:
    with open("rag/vector_store/chunks.json","r",encoding="utf-8") as f:
        chunks = json.load(f)
except:
    chunks = ["dummy chunk"]

metas = [{"source": "test", "chunk": i} for i in range(len(emb))]
store = VectorStore(backend=None)
print("Before add:", store.info())
res = store.add(emb, metas)
print("Add result:", res)
print("After add:", store.info())
store.save()
# query with first vector
hits = store.search(emb[0], topk=3)
print("Hits:", hits)