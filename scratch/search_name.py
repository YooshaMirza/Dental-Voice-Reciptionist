from api.db import db
import json

search_term = "Yusha" # From the user's logs
print(f"Searching for '{search_term}' across all collections...")

for coll_name in db.list_collection_names():
    coll = db[coll_name]
    found = list(coll.find({"$or": [
        {"name": {"$regex": search_term, "$options": "i"}},
        {"customerName": {"$regex": search_term, "$options": "i"}},
        {"transcript.text": {"$regex": search_term, "$options": "i"}}
    ]}))
    if found:
        print(f"\n--- Found in {coll_name} ({len(found)} docs) ---")
        for f in found:
            f['_id'] = str(f['_id'])
            print(json.dumps(f, indent=2))
    else:
        print(f"No match in {coll_name}")
