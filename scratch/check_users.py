from api.db import db
import json

print("\n--- Users Collection (First 1) ---")
user_coll = db['users']
users = list(user_coll.find().limit(1))
for u in users:
    u['_id'] = str(u['_id'])
    print(json.dumps(u, indent=2))

print(f"\nTotal Users: {user_coll.count_documents({})}")
