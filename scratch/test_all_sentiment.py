import os
import sys
import django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'instabus_backend.settings')
django.setup()

from api.models import Call

all_calls = list(Call.objects.all())
print(f"Total calls in DB: {len(all_calls)}")

pos_calls = list(Call.objects.filter(sentiment="positive"))
print(f"Total positive calls in DB: {len(pos_calls)}")
for c in pos_calls:
    print(f"SID: {c.call_sid}, Sentiment field: {c.sentiment}")
