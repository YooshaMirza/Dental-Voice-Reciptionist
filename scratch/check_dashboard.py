import os
import sys
import django
import datetime
import pytz

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'instabus_backend.settings')
django.setup()

from api.models import Call

# Let's check for June 2, 2026.
central_tz = pytz.timezone('US/Central')
selected_date = datetime.date(2026, 6, 2)

start_local = central_tz.localize(datetime.datetime.combine(selected_date, datetime.time.min))
end_local = central_tz.localize(datetime.datetime.combine(selected_date, datetime.time.max))

start_utc = start_local.astimezone(pytz.UTC)
end_utc = end_local.astimezone(pytz.UTC)

print(f"\n=== DASHBOARD QUERIES FOR {selected_date} ===")
print(f"UTC Range: {start_utc} to {end_utc}")

calls_on_date = Call.objects.filter(call_created_at__gte=start_utc, call_created_at__lte=end_utc)
print(f"Total calls on date count: {calls_on_date.count()}")
for c in calls_on_date:
    print(f"Call SID: {c.call_sid}, created_at: {c.call_created_at}, sentiment: {c.sentiment}")

positive_sentiment = calls_on_date.filter(sentiment="positive").count()
neutral_sentiment = calls_on_date.filter(sentiment="neutral").count()
negative_sentiment = calls_on_date.filter(sentiment="negative").count()

print(f"Dashboard query counts:")
print(f"Positive: {positive_sentiment}")
print(f"Neutral: {neutral_sentiment}")
print(f"Negative: {negative_sentiment}")
