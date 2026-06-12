with open("voice_agent/views.py", "r", encoding="utf-8") as f:
    lines = f.readlines()
for idx, line in enumerate(lines):
    if "sentiment" in line.lower():
        print(f"Line {idx+1}: {line.strip()}")
