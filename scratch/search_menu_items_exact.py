with open(r"c:\Users\ASUS\Downloads\firoz lalani\voice_agent\templates\voice_agent\dashboard.html", "r", encoding="utf-8") as f:
    html = f.read()

lines = html.splitlines()
matches = []
for idx, line in enumerate(lines):
    if "menu-item" in line:
        matches.append((idx + 1, line))

print("Occurrences of menu-item in dashboard.html:")
for num, line in matches:
    print(f"Line {num}: {line}")
