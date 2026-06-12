from api.db import db, candidates_collection
import json

print("--- Database Info ---")
print(f"DB Name: {db.name}")
print(f"Collections: {db.list_collection_names()}")

print("\n--- Candidates Collection (First 5) ---")
candidates = list(candidates_collection.find().limit(5))
for c in candidates:
    c['_id'] = str(c['_id'])
    print(json.dumps(c, indent=2))

print(f"\nTotal Candidates: {candidates_collection.count_documents({})}")
