with open(r"c:\Users\ASUS\Downloads\firoz lalani\voice_agent\templates\voice_agent\dashboard.html", "r", encoding="utf-8") as f:
    html = f.read()

import re
scripts = re.findall(r"<script[^>]*src=[\"']([^\"']+)[\"']", html)
print("External script sources:")
for s in scripts:
    print("-", s)
