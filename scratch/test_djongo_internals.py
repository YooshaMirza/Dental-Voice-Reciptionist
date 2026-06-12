import os
import sys
import django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'instabus_backend.settings')
django.setup()

from django.db import connection
from api.models import Call

qs = Call.objects.filter(sentiment="positive")
compiler = qs.query.get_compiler(using=connection.alias)
sql, params = compiler.as_sql()
print("SQL:", sql)
print("Params:", params)

cursor = connection.cursor()
print("Cursor:", cursor)
print("Cursor.cursor:", cursor.cursor)
