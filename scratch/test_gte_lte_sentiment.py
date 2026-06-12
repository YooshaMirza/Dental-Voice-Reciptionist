import os
import sys
import django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'instabus_backend.settings')
django.setup()

import pymongo
original_find = pymongo.collection.Collection.find
original_aggregate = pymongo.collection.Collection.aggregate

def patched_find(self, *args, **kwargs):
    print(f"[pymongo find] Args: {args}, Kwargs: {kwargs}")
    return original_find(self, *args, **kwargs)

def patched_aggregate(self, *args, **kwargs):
    print(f"[pymongo aggregate] Args: {args}, Kwargs: {kwargs}")
    return original_aggregate(self, *args, **kwargs)

pymongo.collection.Collection.find = patched_find
pymongo.collection.Collection.aggregate = patched_aggregate

from api.models import Call
import datetime
import pytz

central_tz = pytz.timezone('US/Central')
selected_date = datetime.date(2026, 6, 2)
start_local = central_tz.localize(datetime.datetime.combine(selected_date, datetime.time.min))
end_local = central_tz.localize(datetime.datetime.combine(selected_date, datetime.time.max))
start_utc = start_local.astimezone(pytz.UTC)
end_utc = end_local.astimezone(pytz.UTC)

print("--- Testing gte and lte with positive ---")
calls = Call.objects.filter(call_created_at__gte=start_utc, call_created_at__lte=end_utc, sentiment="positive")
print("Count:", calls.count())
print("List:", list(calls))
