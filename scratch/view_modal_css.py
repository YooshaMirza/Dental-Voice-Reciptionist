with open(r"c:\Users\ASUS\Downloads\firoz lalani\voice_agent\templates\voice_agent\dashboard.html", "r", encoding="utf-8") as f:
    content = f.read()

lines = content.splitlines()

def print_range(start, end):
    print(f"--- LINES {start} to {end} ---")
    for i in range(start-1, min(end, len(lines))):
        print(f"{i+1}: {lines[i]}")

print_range(770, 820)
print_range(1650, 1690)
