with open(r"c:\Users\ASUS\Downloads\firoz lalani\voice_agent\templates\voice_agent\dashboard.html", "r", encoding="utf-8") as f:
    content = f.read()

print("File read successfully, length:", len(content))
lines = content.splitlines()

# Search for styling of modal-overlay
styling_lines = []
for idx, line in enumerate(lines):
    if "modal-overlay" in line:
        styling_lines.append((idx + 1, line))

print(f"Found {len(styling_lines)} occurrences:")
for num, line in styling_lines:
    print(f"Line {num}: {line}")
