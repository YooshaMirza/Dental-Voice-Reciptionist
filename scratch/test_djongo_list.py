import os
import sys
import django
import datetime
import pytz

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'instabus_backend.settings')
django.setup()

from api.models import Call

# Query for June 2, 2026.
central_tz = pytz.timezone('US/Central')
selected_date = datetime.date(2026, 6, 2)

start_local = central_tz.localize(datetime.datetime.combine(selected_date, datetime.time.min))
end_local = central_tz.localize(datetime.datetime.combine(selected_date, datetime.time.max))

start_utc = start_local.astimezone(pytz.UTC)
end_utc = end_local.astimezone(pytz.UTC)

calls_on_date = Call.objects.filter(call_created_at__range=(start_utc, end_utc))

print("List positive:", list(calls_on_date.filter(sentiment="positive")))
print("List negative:", list(calls_on_date.filter(sentiment="negative")))
print("List neutral:", list(calls_on_date.filter(sentiment="neutral")))
