from datetime import datetime, timedelta
from collections import defaultdict
from motor.motor_asyncio import AsyncIOMotorClient
from pprint import pprint

async def build_starting_box(
    phone: str,
    new_signup: bool,
    monthly_draft_box_collection,
    all_customers_collection,
    all_snacks_collection,
):
    # Context variables to store shared data
    context = {
        "staples": None,
        "customer_allergens": None,
        "category_dislikes": None,
        "repeat_monthly": None,
        "subscription_type": None,
        "month_start_box": []
    }

    async def get_customer_by_phone(phone):
        try:
            customer_document = await all_customers_collection.find_one(
                {"phone": phone},
                {"_id": 0, "staples": 1, "allergens": 1, "category_dislikes": 1, "repeatMonthly": 1, "subscription_type": 1}
            )

            if customer_document:
                context["staples"] = customer_document.get("staples")
                context["customer_allergens"] = customer_document.get("allergens")
                context["category_dislikes"] = customer_document.get("category_dislikes")
                context["repeat_monthly"] = customer_document.get("repeatMonthly")
                context["subscription_type"] = customer_document.get("subscription_type")
                print(f"Updated context: {context}")

                print(f"Customer found")
            else:
                print(f"No customer found with phone number: {phone}")
        except Exception as e:
            print(f"An error occurred while retrieving the customer: {e}")

    async def fetch_snacks_not_containing_allergens(allergens):
        try:
            if not allergens:
                return []
            return await all_snacks_collection.find(
                {"allergens": {"$nin": allergens}}
            ).to_list(length=100)
        except Exception as e:
            print(f"An error occurred while retrieving snacks: {e}")
            return []

    from collections import defaultdict

    def group_snacks_by_primary_category(snacks):
        """
        Groups snacks by their primary category.

        Args:
            snacks (list): A list of dictionaries where each dictionary contains
                           'primaryCategory' and 'SnackID' keys.

        Returns:
            dict: A dictionary where keys are categories and values are lists of SnackIDs.
        """
        grouped_snacks = defaultdict(list)

        for snack in snacks:
            # Check if snack has a primaryCategory and SnackID
            primary_category = snack.get("primaryCategory")
            snack_id = snack.get("SnackID")

            if not primary_category:
                print(f"Skipping snack with missing primaryCategory: {snack}")
                continue
            if not snack_id:
                print(f"Skipping snack with missing SnackID: {snack}")
                continue

            # Normalize category and group snacks
            normalized_category = primary_category.strip().lower()
            grouped_snacks[normalized_category].append(snack_id)

        # Convert defaultdict to dict for output
        return dict(grouped_snacks)

    def transform_staples_object(staples, subscription_type):
        value_mapping = {
            20: {"many": 5, "a few": 3, "one": 1},
            16: {"many": 4, "a few": 2, "one": 1},
            12: {"many": 3, "a few": 2, "one": 1},
        }
        mapping = value_mapping.get(subscription_type)
        if not mapping:
            raise ValueError(f"Unsupported subscription type: {subscription_type}")
        return {k.lower(): mapping[v] for k, v in staples.items() if v in mapping}

    async def build_month_start_box():

        context["month_start_box"].extend(context["repeat_monthly"] or [])

        print(f'EXTEND 1: {context["month_start_box"]}')
        
        transformed_staples = transform_staples_object(context["staples"], context["subscription_type"])      
        safe_snacks = await fetch_snacks_not_containing_allergens(context["customer_allergens"])      
        grouped_snacks = group_snacks_by_primary_category(safe_snacks)

        for category, count in transformed_staples.items():
            if category in grouped_snacks:
                context["month_start_box"].extend(
                    {
                        "SnackID": snack,
                        "primaryCategory": category,
                        "count": 1
                    }
                    for snack in grouped_snacks[category][:count]
                )
            else:
                print(f"Warning: Category '{category}' not found in grouped_snacks.")

        print(f'EXTEND 2: {context["month_start_box"]}')

        remaining_categories = [
            cat for cat in grouped_snacks if cat not in transformed_staples and cat not in (context["category_dislikes"] or [])
        ]
        
        for category in remaining_categories:
            if len(context["month_start_box"]) >= context["subscription_type"]:
                break  # Exit the loop if month_start_box reaches the subscription limit

            # Add the first item from normalized_grouped_snacks[category] to month_start_box
            if category in grouped_snacks and grouped_snacks[category]:
                context["month_start_box"].append(
                    {
                        "SnackID": grouped_snacks[category][0],
                        "primaryCategory": category,
                        "count": 1
                    }
                )

        print("EXTEND 3:")
        for item in context["month_start_box"]:
            print(item)

    async def save_month_start_box():
        print(f'Saving Box: {context["month_start_box"]}')
        date = datetime.now() if new_signup else datetime.now() + timedelta(days=30)
        month_as_int = int(date.strftime("%m%y"))

        
        document = {
            "phone": phone,
            "snacks": context["month_start_box"],
            "month": month_as_int,
            "size": context["subscription_type"]
        }
        if context["month_start_box"]:
            await monthly_draft_box_collection.insert_one(document)
            print(f"Box saved successfully for phone: {phone}")
        else:
            print("Box is empty. Nothing to save.")

    await get_customer_by_phone(phone)
    await build_month_start_box()
    await save_month_start_box()
    