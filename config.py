import os
from dotenv import load_dotenv

load_dotenv()

# Gemini model
GEMINI_MODEL = "gemini-2.5-flash"

# Fallback product label when the manifest has none (entered at capture time)
DEFAULT_PRODUCT = "small electronic device"

# OBS WebSocket connection
OBS_HOST = "localhost"
OBS_PORT = 4455
OBS_PASSWORD = os.environ.get("OBS_WS_PASSWORD", "")
