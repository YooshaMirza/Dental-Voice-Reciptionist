import os
import django

# Setup django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "instabus_backend.settings")
django.setup()

from api.db import calls_collection, firoz_lalani_collection

def repair():
    # 1. Fix call record phone_number and transcript
    call = calls_collection.find_one({'call_sid': 'CAb5ebd0e0f8dc4bacfecacf97c05e0eab'})
    if call:
        print(f"Repairing call record {call['call_sid']}: setting phone_number to 9528114494")
        
        # Clean the transcript turns and text
        transcript = call.get('transcript') or {}
        turns = transcript.get('turns') or []
        for turn in turns:
            if 'trial account' in turn.get('text', ''):
                turn['speaker'] = 'agent'
                text = turn.get('text', '')
                if text.startswith('**'):
                    text = text[2:].strip()
                turn['text'] = text
        
        new_transcript = {
            'text': 'Agent: You have a trial account. You can remove this message at any time by upgrading to a full account. Press any key to execute your code.',
            'turns': turns
        }
        
        calls_collection.update_one(
            {'_id': call['_id']},
            {'$set': {
                'phone_number': '9528114494',
                'transcript': new_transcript
            }}
        )
        print("Call record updated in MongoDB successfully!")
    else:
        print("Call CAb5ebd0e0f8dc4bacfecacf97c05e0eab not found!")

    # 2. Fix patient profile record
    patient = firoz_lalani_collection.find_one({'phone': '8576783571'})
    if patient:
        print(f"Repairing patient profile: changing phone from 8576783571 to 9528114494")
        firoz_lalani_collection.update_one(
            {'_id': patient['_id']},
            {'$set': {
                'phone': '9528114494'
            }}
        )
        print("Patient profile updated in MongoDB successfully!")
    else:
        print("Patient with phone 8576783571 not found!")

    print("Repair complete!")

if __name__ == "__main__":
    repair()
