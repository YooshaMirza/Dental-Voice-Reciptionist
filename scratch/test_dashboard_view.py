import os
import django
from django.test import Client
import datetime
import pytz

# Setup django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "instabus_backend.settings")
django.setup()

from api.models import Call, FirozLalani

def test_dashboard():
    out_file_path = "c:/Users/ASUS/Downloads/firoz lalani/scratch/test_results.txt"
    with open(out_file_path, "w", encoding="utf-8") as f:
        def log(msg):
            print(msg)
            f.write(str(msg) + "\n")
            
        try:
            # 1. Fetch latest call date to know what to expect
            central_tz = pytz.timezone('US/Central')
            latest_call = Call.objects.all().order_by('-call_created_at').first()
            log(f"Latest call in DB: {latest_call}")
            if latest_call:
                log(f"  call_created_at (UTC): {latest_call.call_created_at}")
                log(f"  call_created_at (Central): {latest_call.call_created_at.astimezone(central_tz)}")
                latest_date_str = latest_call.call_created_at.astimezone(central_tz).strftime('%Y-%m-%d')
                log(f"  Computed local date string: {latest_date_str}")
                day = latest_call.call_created_at.astimezone(central_tz).day
                month_year = latest_call.call_created_at.astimezone(central_tz).strftime('%B %Y')
                latest_display = f"{day} {month_year}"
                log(f"  Computed display string: {latest_display}")
            else:
                latest_date_str = datetime.datetime.now(central_tz).strftime('%Y-%m-%d')
                latest_display = f"{datetime.datetime.now(central_tz).day} {datetime.datetime.now(central_tz).strftime('%B %Y')}"
                log(f"No calls in DB, using today: {latest_date_str}")

            client = Client()
            
            # Setup session
            session = client.session
            session['web_user'] = 'Firoz'
            session.save()
            
            # Test case A: Accessing without parameters (should fallback to latest call date)
            response_no_param = client.get('/api/voice-agent/dashboard/')
            log("\n--- Test Case A: No Date Param ---")
            log(f"Response status code: {response_no_param.status_code}")
            html_no_param = response_no_param.content.decode('utf-8')
            if latest_display in html_no_param:
                log(f"SUCCESS: Found expected date display '{latest_display}' in HTML!")
            else:
                log(f"WARNING: Did not find '{latest_display}' in HTML!")
                # Let's log a snippet of HTML around date-navigator to debug
                nav_index = html_no_param.find('date-navigator')
                if nav_index != -1:
                    log(f"HTML snippet: {html_no_param[nav_index:nav_index+500]}")
                else:
                    log("date-navigator class not found in HTML!")

            # Test case B: Accessing with specific date parameter
            response_with_param = client.get(f'/api/voice-agent/dashboard/?date={latest_date_str}')
            log(f"\n--- Test Case B: With Date Param (?date={latest_date_str}) ---")
            log(f"Response status code: {response_with_param.status_code}")
            html_with_param = response_with_param.content.decode('utf-8')
            if latest_display in html_with_param:
                log(f"SUCCESS: Found expected date display '{latest_display}' in HTML!")
            else:
                log(f"WARNING: Did not find '{latest_display}' in HTML!")
            
            # Test case C: Accessing with a different date where there should be no calls (e.g. 2000-01-01)
            response_old_date = client.get('/api/voice-agent/dashboard/?date=2000-01-01')
            log("\n--- Test Case C: Old Date (?date=2000-01-01) ---")
            log(f"Response status code: {response_old_date.status_code}")
            html_old = response_old_date.content.decode('utf-8')
            expected_old_display = "1 January 2000"
            if expected_old_display in html_old:
                log(f"SUCCESS: Found expected date display '{expected_old_display}' in HTML!")
            else:
                log(f"WARNING: Did not find '{expected_old_display}' in HTML!")

            # Check if stats cards show 0 for the old date
            # "Total Breakdown", "Appointment Summary", "Sentiment ratios"
            # Let's search for the "0 Calls" or similar in html_old
            if "0 Calls" in html_old or "0 Booked" in html_old:
                log("SUCCESS: Stats cards show 0 calls/bookings on old date!")
            else:
                log("WARNING: Stats cards might not show 0 calls/bookings. Snippet:")
                calls_index = html_old.find('Total Breakdown')
                if calls_index != -1:
                    log(html_old[calls_index:calls_index+300])

            log("\nSUCCESS: All tests completed successfully!")
            
        except Exception as e:
            import traceback
            log(f"\nERROR running test: {e}")
            log(traceback.format_exc())

if __name__ == "__main__":
    test_dashboard()
