import os
import pymongo
from pymongo import MongoClient, DESCENDING
from bson.objectid import ObjectId
# from dotenv import load_dotenv


def connect():
    MONGO_URI = os.getenv("MONGO_URI")
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME")
    print(MONGO_URI)
    print(MONGO_DB_NAME)
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB_NAME]
    return db

# def search_character(name: str):
#     character = db["characters"].find_one(
#         {"$text": {"$search": name}, "logosData": {"$exists": True}},
#         sort=[("createdAt", DESCENDING)],
#     )

#     if character:
#         return character
#     else:
#         print(f"No character found with name: {name}")
#         return None


# def get_character_data(character_id: str):

#     character = db["characters"].find_one({"_id": ObjectId(character_id)})

#     if not character:
#         print(f"---Character not found: {character_id}")
#         raise Exception("Character not found")

#     return character


# def get_user(user_id: str):
#     user = db["users"].find_one({"_id": ObjectId(user_id)})
#     if not user:
#         print(f"---User not found: {user_id}")
#         raise Exception("User not found")
#     return user


# character = search_character("Abraham")
# print(character)
