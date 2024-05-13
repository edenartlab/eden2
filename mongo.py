import os
# import pymongo
from pymongo import MongoClient
from bson.objectid import ObjectId
# from dotenv import load_dotenv

def connect():
    MONGO_URI = os.getenv("MONGO_URI")
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME")
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB_NAME]
    return db
