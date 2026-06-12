with open(r"c:\Users\ASUS\Downloads\firoz lalani\voice_agent\templates\voice_agent\dashboard.html", "r", encoding="utf-8") as f:
    html = f.read()

lines = html.splitlines()
matches = []
for idx, line in enumerate(lines):
    if "system-drawer-overlay" in line:
        matches.append((idx + 1, line))

print("Occurrences of system-drawer-overlay:")
for num, line in matches:
    print(f"Line {num}: {line}")
