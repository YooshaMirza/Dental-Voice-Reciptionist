import os
import django
from datetime import datetime

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'instabus_backend.settings')
django.setup()

from api.db import prompts_collection

new_prompts = [
    {
        "prompt_id": "onboarding_inbound",
        "title": "New User - Inbound Greeting",
        "text": "Hello! Welcome to {agency}. I'm {agent_name}, and I'll be helping you with your job onboarding today. To start, may I have your full name?",
        "updated_at": datetime.utcnow()
    },
    {
        "prompt_id": "onboarding_outbound",
        "title": "New User - Outbound Greeting",
        "text": "Hello {name}, I'm {agent_name} from {agency}. I'm calling to help you get started with your job application process. Do you have a few minutes to talk?",
        "updated_at": datetime.utcnow()
    },
    {
        "prompt_id": "returning_inbound",
        "title": "Returning User - Inbound Greeting",
        "text": "Welcome back {name}! It's great to hear from you again. I see we have some of your details saved. Is there anything specific you'd like to update, or shall we continue with your job search in {city}?",
        "updated_at": datetime.utcnow()
    },
    {
        "prompt_id": "returning_outbound",
        "title": "Returning User - Outbound Greeting",
        "text": "Hello {name}, this is {agent_name} calling you back from {agency}. I'm following up to see if you're still looking for jobs in {interest}. How can I help you today?",
        "updated_at": datetime.utcnow()
    }
]

print("Populating MongoDB using app's own connection...")

for p in new_prompts:
    result = prompts_collection.update_one(
        {"prompt_id": p["prompt_id"]},
        {"$set": p},
        upsert=True
    )
    if result.upserted_id:
        print(f"Created: {p['prompt_id']}")
    else:
        print(f"Updated: {p['prompt_id']}")

print("\nDone! Scripts are now in MongoDB.")
