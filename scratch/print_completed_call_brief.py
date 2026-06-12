import os
import pymongo

mongo_uri = "mongodb+srv://password:password%40123@cluster0.dzpoxpl.mongodb.net/job_agent?retryWrites=true&w=majority"
client = pymongo.MongoClient(mongo_uri)
db = client["firoz_lalani"]
calls_col = db["api_calls"]

doc = calls_col.find_one({"call_sid": "CAb5ebd0e0f8dc4bacfecacf97c05e0eab"})
if doc:
    print("--- BRIEF CALL METADATA ---")
    keys_of_interest = [
        'call_sid', 'direction', 'from_number', 'to_number', 'phone_number',
        'sentiment', 'ai_analysis_status', 'ai_analysis_error', 'didnt_interact'
    ]
    for k in keys_of_interest:
        print(f"{k}: {repr(doc.get(k))}")
else:
    print("Call not found!")
