from pathlib import Path

from dotenv import load_dotenv

# agent.py reads its settings at import time, so the .env has to load first.
load_dotenv(Path(__file__).with_name(".env"))

from .server import main  # noqa: E402

main()
