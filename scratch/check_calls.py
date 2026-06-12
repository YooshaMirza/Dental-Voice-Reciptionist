import os
import pymongo
from bson import ObjectId

# Connect to MongoDB
mongo_uri = "mongodb+srv://password:password%40123@cluster0.dzpoxpl.mongodb.net/job_agent?retryWrites=true&w=majority"
client = pymongo.MongoClient(mongo_uri)
db = client["firoz_lalani"]
calls_col = db["api_calls"]

print("=== CALL RECORDS ===")
for call in calls_col.find():
    print(f"ID: {call.get('_id')}")
    print(f"Call SID: {call.get('call_sid')}")
    print(f"Direction: {call.get('direction')}")
    print(f"From Number: {call.get('from_number')}")
    print(f"To Number: {call.get('to_number')}")
    print(f"Phone Number field: {call.get('phone_number')}")
    print(f"Call Created At: {call.get('call_created_at')}")
    print(f"Call Date: {call.get('call_date')}")
    print(f"Sentiment: {call.get('sentiment')}")
    print(f"AI Analysis Status: {call.get('ai_analysis_status')}")
    print("-" * 40)
