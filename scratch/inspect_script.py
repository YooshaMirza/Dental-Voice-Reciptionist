with open("scratch/extracted_script_2.js", "r", encoding="utf-8") as f:
    js = f.read()

lines = js.splitlines()
listeners = []
for idx, line in enumerate(lines):
    if "addEventListener" in line:
        listeners.append((idx + 1, line))

print("=== Event Listeners ===")
for num, line in listeners:
    print(f"Line {num}: {line}")
