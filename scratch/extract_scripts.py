import re

with open(r"c:\Users\ASUS\Downloads\firoz lalani\voice_agent\templates\voice_agent\dashboard.html", "r", encoding="utf-8") as f:
    html = f.read()

scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)

print(f"Found {len(scripts)} script tags.")
for idx, code in enumerate(scripts):
    filename = f"scratch/extracted_script_{idx}.js"
    with open(filename, "w", encoding="utf-8") as sf:
        sf.write(code)
    print(f"Extracted script {idx} to {filename} (length: {len(code)})")
