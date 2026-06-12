with open(r"c:\Users\ASUS\Downloads\firoz lalani\voice_agent\templates\voice_agent\dashboard.html", "r", encoding="utf-8") as f:
    content = f.read()

lines = content.splitlines()

overlay_lines = []
for idx, line in enumerate(lines):
    if "call-details-overlay" in line:
        overlay_lines.append((idx + 1, line))

print("Found call-details-overlay:")
for num, line in overlay_lines:
    print(f"Line {num}: {line}")
