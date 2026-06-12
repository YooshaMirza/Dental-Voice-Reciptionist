import os
from pymongo import MongoClient
from datetime import datetime

# Connection details - Using the dev URI from your config
MONGO_URI = "mongodb+srv://password:password%40123@cluster0.dzpoxpl.mongodb.net/job_agent?retryWrites=true&w=majority"
DB_NAME = "job_agent"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

def populate_jobs():
    jobs_collection = db["jobs"]
    jobs_collection.delete_many({}) # Clear existing
    
    sample_jobs = [
        {
            "job_id": "job_001",
            "title": "Lead Carpenter",
            "company": "Build-IT Solutions",
            "location_city": "Johannesburg",
            "category": "Construction",
            "salary_est": "R15,000 - R22,000 per month",
            "skills_required": ["Carpentry", "Roofing", "Blueprint Reading"],
            "description": "Looking for an experienced carpenter for residential projects in Sandton.",
            "is_active": True,
            "created_at": datetime.utcnow()
        },
        {
            "job_id": "job_002",
            "title": "Retail Sales Associate",
            "company": "V&A Waterfront Mall",
            "location_city": "Cape Town",
            "category": "Retail",
            "salary_est": "R8,000 - R12,000 per month",
            "skills_required": ["Customer Service", "POS", "English"],
            "description": "Join our dynamic team at one of the world's premier shopping destinations.",
            "is_active": True,
            "created_at": datetime.utcnow()
        },
        {
            "job_id": "job_003",
            "title": "Delivery Driver",
            "company": "FastTrack Logistics",
            "location_city": "Durban",
            "category": "Logistics",
            "salary_est": "R10,000 - R14,000 per month",
            "skills_required": ["Driving License", "GPS Navigation", "Punctuality"],
            "description": "Daily package deliveries across the Durban metro area.",
            "is_active": True,
            "created_at": datetime.utcnow()
        },
        {
            "job_id": "job_004",
            "title": "Junior Web Developer",
            "company": "TechHub Sandton",
            "location_city": "Johannesburg",
            "category": "Tech",
            "salary_est": "R25,000 - R35,000 per month",
            "skills_required": ["React", "Python", "Problem Solving"],
            "description": "Great opportunity for a fresh graduate to work on international projects.",
            "is_active": True,
            "created_at": datetime.utcnow()
        },
        {
            "job_id": "job_005",
            "title": "Security Guard",
            "company": "SecureSA",
            "location_city": "Pretoria",
            "category": "Security",
            "salary_est": "R7,500 - R11,000 per month",
            "skills_required": ["Physical Fitness", "Observation", "Vigilance"],
            "description": "Night shift security for a corporate campus in Pretoria East.",
            "is_active": True,
            "created_at": datetime.utcnow()
        }
    ]
    
    jobs_collection.insert_many(sample_jobs)
    print(f"DONE: Populated {len(sample_jobs)} jobs in {DB_NAME}")

def populate_prompts():
    prompts_collection = db["prompts"]
    prompts_collection.delete_many({})
    
    onboarding_prompts = [
        {
            "prompt_id": "onboarding_greeting",
            "text": "Hello! Welcome to the South African Job Onboarding Portal. I'm your AI career assistant. To help you find the best roles, may I have your name and what kind of work you're looking for?",
            "category": "greeting"
        },
        {
            "prompt_id": "returning_greeting",
            "text": "Welcome back {name}! It's great to see you again. Based on your interest in {interest}, I've found some new vacancies in {city}. Would you like to hear about them?",
            "category": "greeting"
        }
    ]
    
    prompts_collection.insert_many(onboarding_prompts)
    print(f"DONE: Populated onboarding prompts in {DB_NAME}")

def populate_test_user():
    users_collection = db["users"]
    users_collection.delete_many({})
    
    test_user = {
        "phone": "8908620603", # Using your test number
        "name": "Sbal",
        "email": "sbal@example.com",
        "city": "Johannesburg",
        "interests": ["Carpentry", "Construction"],
        "onboarding_completed": True,
        "created_at": datetime.utcnow()
    }
    
    users_collection.insert_one(test_user)
    print(f"DONE: Populated test user (Sbal) in {DB_NAME}")

if __name__ == "__main__":
    populate_jobs()
    populate_prompts()
    populate_test_user()
    print("\nDatabase Initialization Complete!")
