import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(".env"), override=True)
k = os.getenv("API_FOOTBALL_KEY", "")
print(f"Key length: {len(k)}")
print(f"Is replace_me: {k == 'replace_me'}")
print(f"Is empty: {k == ''}")
