#!/usr/bin/env python3
"""Create the payload indexes on an existing cluster, without re-ingesting.

    python scripts/fix_indexes.py

Use when you hit: 400 Bad Request "Index required but not found for <field>".
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from retrieval.store import client, PAYLOAD_INDEXES, verify_indexes, is_local_mode  # noqa

if is_local_mode():
    print("in-memory mode — indexes are not enforced, nothing to do")
    sys.exit(0)

print(f"cluster: {os.getenv('QDRANT_URL')}\n")
for coll, fields in PAYLOAD_INDEXES.items():
    if not client.collection_exists(coll):
        print(f"  {coll}: collection missing — run ingest.py --wipe first")
        continue
    for field, schema in fields:
        try:
            client.create_payload_index(collection_name=coll, field_name=field,
                                        field_schema=schema, wait=True)
            print(f"  ok   {coll}.{field}")
        except Exception as e:
            m = str(e).lower()
            print(f"  {'ok  ' if 'already exists' in m else 'FAIL'} {coll}.{field}"
                  f"{'' if 'already exists' in m else ': ' + str(e)[:100]}")

missing = verify_indexes()
print("\n" + ("all indexes present" if not missing else "STILL MISSING: " + ", ".join(missing)))
