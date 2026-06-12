import sys
import os

print(f"Python version: {sys.version}")
print(f"CWD: {os.getcwd()}")
print(f"sys.path: {sys.path}")

try:
    import voice_agent
    print(f"voice_agent file: {voice_agent.__file__}")
    from voice_agent import concurrency
    print(f"voice_agent.concurrency file: {concurrency.__file__}")
    from voice_agent import consumers
    print("Successfully imported consumers")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
