import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.server_api import ServerApi

# Replace the placeholder with your Atlas connection string
connection_string = os.environ['MONGO_BOXES_URI']
uri = connection_string

# Set the Stable API version when creating a new client
client = AsyncIOMotorClient(uri, server_api=ServerApi('1'))

# DEFINE COLLECTIONS
boxes_db = client["Boxes"]

all_snacks_collection = boxes_db["snacks"]
all_customers_collection = boxes_db["customers"]
monthly_base_box_collection = boxes_db["monthly_base_box"]
monthly_draft_box_collection = boxes_db["draftboxes"]
internal_orders_collection = boxes_db["internal_orders"]