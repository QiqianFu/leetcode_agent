from pathlib import Path
import os

from dotenv import load_dotenv

# Load .env from project root or home data dir
_project_env = Path(__file__).resolve().parents[2] / ".env"
_data_env = Path.home() / ".leetcode_agent" / ".env"

for p in (_project_env, _data_env):
    if p.exists():
        load_dotenv(p)
        break

DATA_DIR = Path.home() / ".leetcode_agent"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "leetcode.db"

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql"

MAX_NEW_PROBLEMS_PER_DAY = 3
MAX_TOTAL_PROBLEMS_PER_DAY = 10
