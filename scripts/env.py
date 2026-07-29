"""Load .env file for non-production environments."""

import os

if os.environ.get("APP_ENV", "") != "production":
    from dotenv import load_dotenv

    load_dotenv()
