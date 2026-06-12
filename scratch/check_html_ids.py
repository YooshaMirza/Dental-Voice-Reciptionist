import re

with open(r"c:\Users\ASUS\Downloads\firoz lalani\voice_agent\templates\voice_agent\dashboard.html", "r", encoding="utf-8") as f:
    html = f.read()

# Let's find all document.getElementById calls in the JS block
ids_referenced = re.findall(r"document\.getElementById\(['\"]([^'\"]+)['\"]\)", html)
# Also find elements with an id attribute in HTML
ids_in_html = set(re.findall(r'id=["\']([^"\']+)["\']', html))

print("=== DOM IDs Checked ===")
for ref_id in sorted(set(ids_referenced)):
    exists = ref_id in ids_in_html
    print(f"ID '{ref_id}': {'EXISTS' if exists else 'NOT FOUND'}")
