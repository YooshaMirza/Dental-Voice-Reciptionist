import os
import pymongo
from bson import ObjectId

mongo_uri = "mongodb+srv://password:password%40123@cluster0.dzpoxpl.mongodb.net/job_agent?retryWrites=true&w=majority"
client = pymongo.MongoClient(mongo_uri)
db = client["firoz_lalani"]
calls_col = db["api_calls"]

doc = calls_col.find_one({"call_sid": "CAb5ebd0e0f8dc4bacfecacf97c05e0eab"})
if doc:
    print("sentiment key in doc:", "sentiment" in doc)
    print("sentiment value:", repr(doc.get("sentiment")))
else:
    print("Doc not found")

# Test raw pymongo queries
print("\n--- PyMongo count matching 'positive' ---")
print(calls_col.count_documents({"call_sid": "CAb5ebd0e0f8dc4bacfecacf97c05e0eab", "sentiment": "positive"}))

print("\n--- PyMongo count matching 'negative' ---")
print(calls_col.count_documents({"call_sid": "CAb5ebd0e0f8dc4bacfecacf97c05e0eab", "sentiment": "negative"}))

print("\n--- PyMongo count matching 'neutral' ---")
print(calls_col.count_documents({"call_sid": "CAb5ebd0e0f8dc4bacfecacf97c05e0eab", "sentiment": "neutral"}))

print("\n--- PyMongo count matching null/missing sentiment ---")
print(calls_col.count_documents({"call_sid": "CAb5ebd0e0f8dc4bacfecacf97c05e0eab", "sentiment": None}))
print(calls_col.count_documents({"call_sid": "CAb5ebd0e0f8dc4bacfecacf97c05e0eab", "sentiment": {"$exists": False}}))
