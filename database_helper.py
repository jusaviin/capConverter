import os
import psycopg2
from dotenv import dotenv_values


def get_connection(remote = False):
    """
    Open a new Postgres connection using POSTGRES_URL.

    This is the single place connection logic lives -- dotenv_values()
    reads a local .env file directly, merged with real process
    environment variables so this works both locally (via .env) and
    in production (via Render's dashboard-set environment variables,
    where there is no .env file at all). Every module that needs a
    database connection (salary_cap.py, app.py's player/contract
    routes) imports get_connection() from here rather than
    duplicating this logic.
    """
    config = {**dotenv_values(), **os.environ}
    
    if remote:
        url_slug = "REMOTE_URL"
    else:
        url_slug = "POSTGRES_URL"
    
    postgres_url = config.get(url_slug)
    if not postgres_url:
        raise RuntimeError(
            f"{url_slug} is not set. Define it in your .env file "
            "(locally) or as an environment variable (in production)."
        )
    return psycopg2.connect(postgres_url, connect_timeout=5)
