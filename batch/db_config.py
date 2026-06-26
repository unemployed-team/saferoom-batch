import os
import psycopg2
from dotenv import dotenv_values

config = dotenv_values(".env")

def get_conn():
    return psycopg2.connect(
        host=config.get("DB_HOST", "saferoom"),
        port=config.get("DB_PORT", 5433),
        dbname="saferoom",
        user=config["DB_USERNAME"],
        password=config["DB_PASSWORD"]
    )