with open(r"c:\Users\ASUS\Downloads\firoz lalani\voice_agent\templates\voice_agent\dashboard.html", "r", encoding="utf-8") as f:
    html = f.read()

lines = html.splitlines()
matches = []
for idx, line in enumerate(lines):
    if "drawer" in line.lower():
        matches.append((idx + 1, line))

print("Drawer style occurrences:")
for num, line in matches[:40]:
    print(f"Line {num}: {line}")
