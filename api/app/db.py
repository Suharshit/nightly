import os

from dotenv import load_dotenv
from psycopg_pool import ConnectionPool

load_dotenv()


def make_pool() -> ConnectionPool:
    # Small: the free hosts have little RAM, and Supabase's pooler caps connections.
    return ConnectionPool(os.environ["DATABASE_URL"], min_size=1, max_size=4, open=True,
                          kwargs={"autocommit": True})
