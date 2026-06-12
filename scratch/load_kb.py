import os
import sys
import django
import pandas as pd

# Bootstrap Django
sys.path.append("c:\\Users\\ASUS\\Downloads\\firoz lalani")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "instabus_backend.settings")
django.setup()

from api.db import knowledge_base_collection, prompts_collection

def seed_database():
    print("[1/5] Cleaning existing Knowledge Base collection...")
    knowledge_base_collection.delete_many({})
    
    kb_entries = []
    
    # ── 1. PARSE EXCEL PRICING DATA ──────────────────────────────────────────
    excel_path = r"c:\Users\ASUS\Downloads\firoz lalani\DCAI pricing sheet.xlsx"
    print(f"[2/5] Reading pricing sheet from: {excel_path}")
    
    try:
        df = pd.read_excel(excel_path, sheet_name="$tart price")
        # Column names: 'Procedure name ', 'starting prices', 'Notes'
        for idx, row in df.iterrows():
            proc_name = row.get('Procedure name ')
            price = row.get('starting prices')
            notes = row.get('Notes')
            
            # Check if name is null/empty or float nan
            if not isinstance(proc_name, str) or pd.isna(proc_name):
                continue
                
            proc_clean = proc_name.strip()
            
            # Determine if this row is a header/category instead of a procedure
            # Row has nan price and nan notes
            is_header = (pd.isna(price) or not str(price).strip()) and (pd.isna(notes) or not str(notes).strip())
            
            if is_header:
                print(f"  Skipping category header: {proc_clean}")
                continue
                
            price_str = str(price).strip() if not pd.isna(price) else ""
            notes_str = str(notes).strip() if not pd.isna(notes) else ""
            
            # Build systematic question and answer
            question = f"What is the starting price of {proc_clean}?"
            
            # Create keywords based on name
            keywords = [w.lower().replace(",", "").replace("/", "").strip() for w in proc_clean.split()]
            keywords.append(proc_clean.lower())
            
            # Additional custom keywords
            if "rct" in proc_clean.lower() or "root canal" in proc_clean.lower():
                keywords.extend(["root canal", "rct", "endodontics"])
            if "extraction" in proc_clean.lower():
                keywords.extend(["extraction", "extractions", "pull", "tooth removal"])
            if "cleaning" in proc_clean.lower():
                keywords.extend(["cleaning", "cleanings", "srp"])
            if "implant" in proc_clean.lower():
                keywords.extend(["implant", "implants", "abutment"])
            if "denture" in proc_clean.lower():
                keywords.extend(["denture", "dentures", "partials"])
            if "whitening" in proc_clean.lower():
                keywords.extend(["whitening", "bleaching", "zoom"])
            if "crown" in proc_clean.lower():
                keywords.extend(["crown", "crowns", "cap"])
                
            keywords = list(set(keywords))  # deduplicate
            
            # Build direct answer
            ans_parts = [f"The starting price for {proc_clean} is ${price_str}."]
            if notes_str:
                ans_parts.append(f"Note: {notes_str}")
            ans_parts.append("Remember, initial diagnostic exam and x-rays are included in our consultation special.")
            answer = " ".join(ans_parts)
            
            kb_entries.append({
                "category": "pricing",
                "question": question,
                "answer": answer,
                "keywords": keywords,
                "procedure_name": proc_clean,
                "starting_price": price_str,
                "notes": notes_str
            })
            print(f"  Parsed pricing rule: {proc_clean} -> ${price_str}")
    except Exception as e:
        print(f"Error parsing Excel: {e}")
        
    # ── 2. SEED LOCATION RULES ───────────────────────────────────────────────
    print("[3/5] Seeding location and address guidelines...")
    
    # Primary Location
    kb_entries.append({
        "category": "location",
        "question": "Where are you located? / What is your address?",
        "answer": "We are located off: 165 Greens Rd, Houston 77060, on 45 and Greens Rd, across from Greenspoint Mall, behind IHOP.",
        "keywords": ["location", "address", "where are you", "located", "find you", "greens rd", "clinic", "office"]
    })
    
    # ZIP Code Deflection (Too far / Other locations)
    kb_entries.append({
        "category": "location",
        "question": "Do you have other locations? / The office is too far.",
        "answer": "We have multiple locations in Houston. Could you please provide me with your ZIP code so I can find our location nearest to you?",
        "keywords": ["too far", "other locations", "nearest location", "another location", "multiple locations", "other clinics", "other offices", "alternative location"]
    })
    
    # Text Address Deflection (1.3 - Politely declining because text service is unavailable)
    kb_entries.append({
        "category": "location",
        "question": "Can you text me your address?",
        "answer": "I'm sorry, I don't have the ability to send text messages right now. However, I can read the address of our locations for you, or you can find them on our website.",
        "keywords": ["text", "text me", "send address", "text address", "sms", "message address"]
    })
    
    # All Locations Insist List
    kb_entries.append({
        "category": "location",
        "question": "What are the addresses of all your locations?",
        "answer": "Absolutely, our direct addresses are: 165 Greens Rd, Houston, TX 77060; 4654 Hwy 6 N Ste 401, Houston, TX 77084; 1811 Louetta RD, Spring, TX 77388; and 6888 Gulf Fwy, Houston, TX 77087. Please note we are only operating at our 165 Greens Rd location currently.",
        "keywords": ["list locations", "all locations", "every location", "all addresses", "list addresses", "insist"]
    })
    
    # ── 3. SEED GENERAL FAQ RULES ────────────────────────────────────────────
    print("[4/5] Seeding general practice FAQ guidelines...")
    
    faqs = [
        {
            "question": "What are your office hours?",
            "answer": "We are open Monday through Friday from 8:00 AM to 5:00 PM. We are closed on Saturdays and Sundays.",
            "keywords": ["hours", "open", "schedule", "timing", "close", "days"]
        },
        {
            "question": "Are you open on Saturdays or Sundays?",
            "answer": "We are closed on Saturdays and Sundays. Appointments are only available Monday through Friday from 8:00 AM to 5:00 PM.",
            "keywords": ["saturday", "sunday", "weekend", "weekends"]
        },
        {
            "question": "What is your phone number?",
            "answer": "Our phone number is +1 (857) 678-3571.",
            "keywords": ["phone", "number", "call", "contact", "telephone"]
        },
        {
            "question": "Who is the dentist / doctor?",
            "answer": "All treatments are performed by our highly experienced, board-certified dentist and professional dental team.",
            "keywords": ["doctor", "dentist", "board-certified", "team", "surgeon", "specialist"]
        },
        {
            "question": "What kind of parking do you have?",
            "answer": "We have plenty of free parking available directly in front of our clinic building for all patients.",
            "keywords": ["parking", "park", "car", "garage", "lot"]
        },
        {
            "question": "Do you accept insurance? Which ones?",
            "answer": "We work with the majority of PPO dental insurances (such as Delta Dental, Cigna, Aetna, MetLife, Guardian, Humana, and United Healthcare). We do not participate with Medicaid, HMO, or DHMO plans.",
            "keywords": ["insurance", "ppo", "medicaid", "hmo", "dhmo", "aetna", "cigna", "delta", "metlife"]
        },
        {
            "question": "How can I pay for my visit? Do you have payment plans?",
            "answer": "We accept cash, major credit cards, and most PPO insurances. For patients without insurance, we offer special savings, discount plans, and financing options. Our treatment coordinator will help you choose a plan that works best for you when you come in.",
            "keywords": ["payment", "accept", "pay", "cash", "card", "credit", "financing", "plan", "plans", "finance"]
        }
    ]
    
    for faq in faqs:
        faq["category"] = "general"
        kb_entries.append(faq)
        
    # Write to collection
    print(f"[5/5] Inserting {len(kb_entries)} Knowledge Base rules into MongoDB...")
    knowledge_base_collection.insert_many(kb_entries)
    print("Success: Knowledge Base seeded successfully!")

    # ── 4. SEED SYSTEM PROMPTS IF NOT EXISTING ───────────────────────────────
    print("Seeding system prompts...")
    from voice_agent.call_prompts import INBOUND_SYSTEM_PROMPT, OUTBOUND_SYSTEM_PROMPT
    
    # Seed Inbound
    inbound_exists = prompts_collection.find_one({"prompt_type": "inbound"})
    if not inbound_exists:
        prompts_collection.insert_one({
            "prompt_type": "inbound",
            "title": "Inbound Assistant (Alice)",
            "prompt_text": INBOUND_SYSTEM_PROMPT,
            "updated_at": django.utils.timezone.now()
        })
        print("Success: Seeded Inbound Assistant Prompt.")
    else:
        print("Info: Inbound Prompt already exists in DB, skipping.")

    # Seed Outbound
    outbound_exists = prompts_collection.find_one({"prompt_type": "outbound"})
    if not outbound_exists:
        prompts_collection.insert_one({
            "prompt_type": "outbound",
            "title": "Outbound Patient Advocate (Dentina)",
            "prompt_text": OUTBOUND_SYSTEM_PROMPT,
            "updated_at": django.utils.timezone.now()
        })
        print("Success: Seeded Outbound Assistant Prompt.")
    else:
        print("Info: Outbound Prompt already exists in DB, skipping.")

if __name__ == "__main__":
    seed_database()
