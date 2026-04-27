import os
import time
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import OperationalError

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/customer_db")

Base = declarative_base()


def create_engine_with_retry(url, retries=10, delay=3):
    for i in range(retries):
        try:
            eng = create_engine(url)
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
            return eng
        except OperationalError:
            if i < retries - 1:
                time.sleep(delay)
            else:
                raise


engine = create_engine_with_retry(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
