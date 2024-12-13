from dotenv import load_dotenv
from pathlib import Path
from pydantic import SecretStr
import os

home_dir = str(Path.home())

# Load env variables from ~/.eve if it exists
eve_path = os.path.join(home_dir, '.eve')
if os.path.exists(eve_path):
    load_dotenv(eve_path)

# Load env variables from .env file if it exists
env_path = ".env"
if os.path.exists(env_path):
    load_dotenv(env_path, override=True)

# load api keys
EDEN_API_KEY_STAGE = SecretStr(os.getenv("EDEN_API_KEY_STAGE", ""))
EDEN_API_KEY_PROD = SecretStr(os.getenv("EDEN_API_KEY_PROD", ""))

if not EDEN_API_KEY_STAGE:
    print("WARNING: EDEN_API_KEY_STAGE is not set")
if not EDEN_API_KEY_PROD:
    print("WARNING: EDEN_API_KEY_PROD is not set")
