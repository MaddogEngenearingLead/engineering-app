from pymongo import MongoClient
from app.core.config import settings

MONGODB_URL = "mongodb://localhost:27017"
MONGO_DB_NAME = "engineering_pid"

client = MongoClient(MONGODB_URL)
db = client[MONGO_DB_NAME]


def get_mongo_db():
    return db
