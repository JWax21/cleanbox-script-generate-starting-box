
import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.server_api import ServerApi

connection_string = os.environ.get('MONGO_BOXES_URI')
if not connection_string:
    raise ValueError("MONGO_BOXES_URI environment variable is not set")

client = AsyncIOMotorClient(connection_string, server_api=ServerApi('1'))

boxes_db = client["Boxes"]

all_snacks_collection = boxes_db["snacks"]
all_customers_collection = boxes_db["customers"]
monthly_base_box_collection = boxes_db["monthly_base_box"]
monthly_draft_box_collection = boxes_db["draftboxes"]
internal_orders_collection = boxes_db["internal_orders"]
