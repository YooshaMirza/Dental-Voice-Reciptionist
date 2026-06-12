with open(r"c:\Users\ASUS\Downloads\firoz lalani\voice_agent\templates\voice_agent\dashboard.html", "r", encoding="utf-8") as f:
    html = f.read()

import re
items = re.findall(r"<[^>]*class=[\"'][^\"']*menu-item[^\"']*[\"'][^>]*>(.*?)<\/", html)
print("Menu items found:")
for item in items:
    print("-", item.strip())
