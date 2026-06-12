import os
import pymongo

mongo_uri = "mongodb+srv://password:password%40123@cluster0.dzpoxpl.mongodb.net/job_agent?retryWrites=true&w=majority"
client = pymongo.MongoClient(mongo_uri)
db = client["firoz_lalani"]
calls_col = db["api_calls"]

doc = calls_col.find_one({"call_sid": "CAb5ebd0e0f8dc4bacfecacf97c05e0eab"})
if doc:
    print("--- RAW CALL METADATA ---")
    exclude = {'transcript', 'recording_chunks', 'audio_data', 'mp3_data', 'binary_audio_data'}
    for k, v in doc.items():
        if k not in exclude:
            print(f"{k}: {repr(v)}")
else:
    print("Call not found!")
