import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrieval.store import resolve

# Test: resolve a course using real Qdrant
res = resolve("cse", kind="course")
print(res)