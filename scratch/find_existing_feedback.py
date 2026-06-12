import os
import pymongo

mongo_uri = "mongodb+srv://password:password%40123@cluster0.dzpoxpl.mongodb.net/job_agent?retryWrites=true&w=majority"
client = pymongo.MongoClient(mongo_uri)
db = client["firoz_lalani"]
feedbacks_col = db["feedback"]
calls_col = db["api_calls"]

feedback = feedbacks_col.find_one({"call_sid": "CAb5ebd0e0f8dc4bacfecacf97c05e0eab"})
if feedback:
    print("Found feedback in DB:")
    for k, v in feedback.items():
         print(f"{k}: {v}")
    
    sentiment = feedback.get("sentiment", "neutral")
    print(f"Updating call sentiment to: {sentiment}")
    calls_col.update_one(
         {"call_sid": "CAb5ebd0e0f8dc4bacfecacf97c05e0eab"},
         {"$set": {"sentiment": sentiment}}
    )
    print("Call sentiment updated successfully!")
else:
    print("No feedback found for this call in 'feedback' collection.")
