import os
from dotenv import load_dotenv

load_dotenv()

# Gemini model
GEMINI_MODEL = "gemini-2.5-flash"

# OBS WebSocket connection
OBS_HOST = "localhost"
OBS_PORT = 4455
OBS_PASSWORD = os.environ["OBS_WS_PASSWORD"]
