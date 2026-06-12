from api.db import firoz_lalani_collection
import pymongo

print("Checking firoz_lalani collection records...")
cursor = firoz_lalani_collection.find()
for doc in cursor:
    doc_id = doc['_id']
    created_at = doc.get('created_at')
    updated_at = doc.get('updated_at')
    
    if created_at is None:
        new_created_at = updated_at
        if new_created_at is None:
            # If updated_at is also None, use fallback
            import datetime
            new_created_at = datetime.datetime.utcnow()
        
        print(f"Fixing doc {doc_id}: setting created_at to {new_created_at}")
        firoz_lalani_collection.update_one(
            {"_id": doc_id},
            {"$set": {"created_at": new_created_at}}
        )

print("Done fixing created_at dates.")
