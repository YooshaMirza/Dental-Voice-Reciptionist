import os
import sys
import django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'instabus_backend.settings')
django.setup()

import pymongo
original_find = pymongo.collection.Collection.find
original_count_documents = pymongo.collection.Collection.count_documents

def patched_find(self, *args, **kwargs):
    print(f"[pymongo find] Args: {args}, Kwargs: {kwargs}")
    return original_find(self, *args, **kwargs)

pymongo.collection.Collection.find = patched_find

from api.models import Call
print("--- Querying for positive ---")
list(Call.objects.filter(sentiment="positive"))
