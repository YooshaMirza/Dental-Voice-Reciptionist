with open(r"c:\Users\ASUS\Downloads\firoz lalani\voice_agent\views.py", "r", encoding="utf-8") as f:
    content = f.read()

lines = content.splitlines()
matches = []
for idx, line in enumerate(lines):
    if "KnowledgeBase" in line or "kb" in line.lower():
        matches.append((idx + 1, line))

print("Found matches in voice_agent/views.py:")
for num, line in matches:
    print(f"Line {num}: {line}")
