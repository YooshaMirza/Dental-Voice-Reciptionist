with open("scratch/extracted_script_2.js", "r", encoding="utf-8") as f:
    js = f.read()

lines = js.splitlines()
start = max(0, 310)
end = min(len(lines), 340)

print(f"=== LINES {start} to {end} ===")
for i in range(start-1, end):
    print(f"{i+1}: {lines[i]}")
