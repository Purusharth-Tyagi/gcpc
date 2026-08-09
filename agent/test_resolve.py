import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrieval.mocks import resolve, route

# Test: resolve a course
res = resolve("cse", kind="course")
print(res)

# Test: resolve an exam
res2 = resolve("jee", kind="exam")
print(res2)

# Test: route an intent
intent = route("can he get eligibility for cse")
print(intent)