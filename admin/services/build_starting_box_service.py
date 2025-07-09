from datetime import datetime, timedelta
from typing import List, Optional  # Import Optional
from collections import defaultdict
from motor.motor_asyncio import AsyncIOMotorClient
from pprint import pprint
from collections import Counter
from admin.models.customers_model import SnackItem 

async def build_starting_box(
    customerID: str,
    new_signup: bool,
    repeat_customer: bool,
    off_cycle: bool,
    is_reset_box: bool,
    reset_total: int,
    repeat_monthly: Optional[List[SnackItem]],  # Make repeat_monthly optional
    monthly_draft_box_collection,
    all_customers_collection,
    all_snacks_collection,
):
    
    # Convert repeat_monthly to list of dicts if provided
    serialized_repeat_monthly = (
        [snack.dict() for snack in repeat_monthly] if repeat_monthly is not None else None
    )
    
    # Context variables to store shared data
    context = {
        "staples": None,
        "customer_allergens": None,
        "vetoed_flavors": None,
        "priority_setting": None,
        "category_dislikes": None,
        "repeat_monthly": None,
        "subscription_type": None,
        "repeat_monthly": serialized_repeat_monthly,  # Use serialized version
        "month_start_box": []
    }

# ============================================================================================================== PREPARE: GET CUSTOMER INFO 
    
    async def get_customer_by_customerID(customerID, is_reset_box, reset_total):
        try:
            customer_document = await all_customers_collection.find_one(
                {"customerID": customerID},
                {
                    "_id": 0, 
                    "allergens": 1, 
                    "dislikes": 1, 
                    "staples": 1, 
                    "vetoedFlavors": 1,
                    "prioritySetting": 1,
                    "subscription_type": 1
                }
            )

            if customer_document:
                context["customer_allergens"] = customer_document.get("allergens")
                context["vetoed_flavors"] = customer_document.get("vetoedFlavors")
                context["staples"] = customer_document.get("staples")
                context["category_dislikes"] = customer_document.get("dislikes")
                context["priority_setting"] = customer_document.get("prioritySetting")

                # BASE BOX OR RESET BOX
                if is_reset_box:
                    context["subscription_type"] = reset_total
                else:
                    context["subscription_type"] = customer_document.get("subscription_type")

                print(f"CONTEXT: {context}")
                print("\n")

            else:
                print(f"No customer found with ID: {customerID}")
        except Exception as e:
            print(f"An error occurred while retrieving the customer: {e}")

# ========================================================================================================================== 1. FILTER SNACKS
    
    async def fetch_snacks_filtered(allergens=None, vetoedFlavors=None, dislikedCategories=None, off_cycle=False, most_recent_snack_ids=None, repeat_monthly=None):
        try:
            print("FILTERING SNACKS")
            # Initialize query conditions
            query_conditions = {"replacementOnly": {"$ne": True}}  # Exclude snacks where replacementOnly is true

            # Combine all SnackID exclusions
            excluded_snack_ids = set()

            # Add repeat_monthly SnackIDs to excluded list
            if repeat_monthly and isinstance(repeat_monthly, list):
                print("d. Adding Repeat Monthly SnackIDs to query conditions")
                repeat_snack_ids = [str(item["SnackID"]).strip().upper() for item in repeat_monthly if isinstance(item, dict) and "SnackID" in item]
                excluded_snack_ids.update(repeat_snack_ids)
                print(f"Repeat SnackIDs: {repeat_snack_ids}")
            else:
                print("repeat_monthly is empty or invalid")

            # Add most_recent_snack_ids to excluded list
            if most_recent_snack_ids:
                print("d. Adding Most Recent SnackID exclusion to query conditions")
                recent_snack_ids = [str(id).strip().upper() for id in most_recent_snack_ids]
                excluded_snack_ids.update(recent_snack_ids)
                print(f"Most Recent SnackIDs: {recent_snack_ids}")

            # Apply combined SnackID filter
            if excluded_snack_ids:
                query_conditions["SnackID"] = {"$nin": list(excluded_snack_ids)}
                print(f"Excluded SnackIDs: {excluded_snack_ids}")

            # Filter by allergens if provided
            if allergens:
                print("a. Adding Allergens to query conditions")
                query_conditions["allergens"] = {"$nin": allergens}

            # Filter by vetoed flavors if provided
            if vetoedFlavors:
                print("b. Adding Vetoed Flavors to query conditions")
                # Suffixes to handle stripping with transformations
                suffixes_to_strip = ["ies", "s", "es", "ed", "ing", "y"]
                suffixes_to_add = ["", "e", "y", "s", "es", "ed", "ing", "ies"]

                def strip_suffix(word):
                    """
                    Remove the longest matching suffix from a word, based on suffixes_to_strip.
                    """
                    for suffix in sorted(suffixes_to_strip, key=len, reverse=True):  # Longest suffix first
                        if word.endswith(suffix):
                            if suffix == "ies" and len(word) > 3:  # Special handling for "ies"
                                return word[:-3] + "y"
                            return word[: -len(suffix)]
                    return word

                # Step 1: Generate base forms of words
                base_flavors = [strip_suffix(flavor.lower()) for flavor in vetoedFlavors]

                # Step 2: Expand the list with new forms
                expanded_flavors = set()
                for flavor in base_flavors:
                    for suffix in suffixes_to_add:
                        if suffix == "ies" and flavor.endswith("y"):
                            expanded_flavors.add(flavor[:-1] + "ies")
                        else:
                            expanded_flavors.add(flavor + suffix)

                # Step 3: Format the words with capitalized first letter and lowercase everything else
                formatted_flavors = [flavor.capitalize() for flavor in sorted(expanded_flavors)]

                # Add vetoed flavors condition to the query
                query_conditions["flavorTags"] = {"$nin": formatted_flavors}

            # Filter by disliked categories if provided
            if dislikedCategories:
                print("c. Adding Disliked Categories to query conditions")
                query_conditions["primaryCategory"] = {"$nin": dislikedCategories}

            # Filter by off-cycle if provided
            if off_cycle:
                print("c. Adding Off-Cycle to query conditions")
                query_conditions["$or"] = [{"inStock": True}, {"approved": True}]

            # Log final query conditions
            print(f"Final query conditions: {query_conditions}")

            # Query the collection with the combined filters
            snacks = await all_snacks_collection.find(query_conditions).to_list(length=500)

            # Log returned SnackIDs for debugging
            returned_snack_ids = [snack["SnackID"] for snack in snacks]
            print(f"Returned SnackIDs: {returned_snack_ids}")

            # Check if any excluded SnackIDs are in results
            if excluded_snack_ids and any(snack_id in excluded_snack_ids for snack_id in returned_snack_ids):
                print(f"Warning: Excluded SnackIDs found in results: {set(returned_snack_ids) & excluded_snack_ids}")

            # Print the count of snacks returned
            print(f"e. Number of snacks returned: {len(snacks)}")

            return snacks

        except Exception as e:
            print(f"An error occurred while retrieving snacks: {e}")
            return []

# ============================================================================================================================ 2. SCORE EACH SNACK

    async def get_previous_snack_ids(customerID):
        
        """
        Query monthly_draft_box_collection for all SnackIDs associated with a customerID.

        Args:
            customer_id (str): The customer ID to query for

        Returns:
            List[str]: List of unique SnackIDs from all matching documents
        """
        try:
            snack_ids = []
            async for doc in monthly_draft_box_collection.find({"customerID": customerID}):
                snacks = doc.get("snacks", [])
                for snack in snacks:
                    snack_id = snack.get("SnackID")
                    if snack_id and snack_id not in snack_ids:
                        snack_ids.append(snack_id)
            print(f"Previous SnackIDs for customer {customerID}:")
            for snack_id in snack_ids:
                print(f" - {snack_id}")
            print("\n")
            return snack_ids
        except Exception as e:
            print(f"Error querying previous snacks: {e}")
            return []

    async def get_most_recent_box(customerID):
        """
        Query monthly_draft_box_collection for SnackIDs in customerID's most recent box based on createdAt.

        Args:
            customerID (str): The customer ID to query for

        Returns:
            List[str]: List of unique SnackIDs from the most recent box
        """
        try:
            # Find the most recent document for the customer, sorted by createdAt in descending order
            doc = await monthly_draft_box_collection.find_one(
                {"customerID": customerID},
                sort=[("createdAt", -1)]
            )

            snack_ids = []
            if doc:
                snacks = doc.get("snacks", [])
                for snack in snacks:
                    snack_id = snack.get("SnackID")
                    if snack_id and snack_id not in snack_ids:
                        snack_ids.append(snack_id)

                print(f"Most recent SnackIDs for customer {customerID}:")
                for snack_id in snack_ids:
                    print(f" - {snack_id}")
                print("\n")

            return snack_ids
        except Exception as e:
            print(f"Error querying most recent box: {e}")
            return []

    def get_score(snack, priority_setting, previous_snack_ids):
        
        total_score = snack.get("totalScore", 0)
        protein_boost = snack.get("highProteinBoost", 0)
        low_carb_boost = snack.get("lowCarbBoost", 0)
        low_calorie_boost = snack.get("lowCalorieBoost", 0)

        # 01. BOOST (PREFERENCE)
        if priority_setting == 0:
            score = total_score
        elif priority_setting == 1:
            score = total_score + protein_boost
        elif priority_setting == 2:
            score = total_score + low_carb_boost
        elif priority_setting == 3:
            score = total_score + low_calorie_boost
        else:
            score = total_score

        # 02. PENALTY (PREVIOUSLY RECEIVED)
        
        snack_id = snack.get("SnackID")
        if snack_id in previous_snack_ids:
            print(f"Applying penalty to previously received snack: {snack_id}")
            score -= 50

        print(f"SnackID: {snack_id}, Priority: {priority_setting}, Score: {score}")
        return score


    
# ============================================================================================ PREPARE: GROUP INTO CATEGORIES

    def group_snacks_by_primary_category(snacks):
        grouped_snacks = defaultdict(list)

        for snack in snacks:
            # Check if snack has a primaryCategory
            primary_category = snack.get("primaryCategory")

            if not primary_category:
                print(f"Skipping snack with missing primaryCategory: {snack}")
                continue

            # Use the category as is (no normalization)
            grouped_snacks[primary_category.strip()].append(snack)

        # Convert defaultdict to dict for output
        return dict(grouped_snacks)


# ============================================================================================ PREPARE: ACTUAL COUNT FOR STAPLES
    
    def transform_staples_object(staples, subscription_type, category_dislikes, adjusted_subscription_type):
        try:
            print("Starting transform_staples_object function...")
            print(f"Input staples: {staples}")
            print(f"Subscription type: {subscription_type}")
            print(f"Category dislikes: {category_dislikes}")
            print(f"Adjusted subscription type: {adjusted_subscription_type}")
            print("\n")

            # Validate inputs
            if not isinstance(staples, dict):
                raise ValueError("Staples must be a dictionary.")
            if not all(v in ["one", "a few", "many"] for v in staples.values()):
                raise ValueError("Staples values must be 'one', 'a few', or 'many'.")
            if not isinstance(subscription_type, int) or not isinstance(adjusted_subscription_type, int):
                raise ValueError("Subscription types must be integers.")
            if subscription_type < 0 or adjusted_subscription_type < 0:
                raise ValueError("Subscription types cannot be negative.")

            # COUNTS
            staples_count = len(staples)
            dislikes_count = len(category_dislikes) if category_dislikes is not None else 0
            optional_categories = 10 - staples_count - dislikes_count
            print(f"Staples count: {staples_count}, Dislikes count: {dislikes_count}, Optional categories: {optional_categories}")
            print("\n")

            if optional_categories < 0:
                raise ValueError("Invalid inputs: staples and category dislikes exceed available categories (10).")

            # Count occurrences of each value in staples
            many_count = sum(1 for v in staples.values() if v == "many")
            few_count = sum(1 for v in staples.values() if v == "a few")
            one_count = sum(1 for v in staples.values() if v == "one")
            print(f"Many count: {many_count}, Few count: {few_count}, One count: {one_count}")

            # Initialize value mapping
            # Calculate total for each condition
            if many_count * 2 + few_count * 1 + one_count * 1 < adjusted_subscription_type:
                value_mapping = {"many": 2, "a few": 1, "one": 1}
                total = many_count * 2 + few_count * 1 + one_count * 1
                print(f"Condition 1: Total={total}, value_mapping={value_mapping}")
                remaining = adjusted_subscription_type - total
                print(f"Remaining after Condition 1: {remaining}")
                if remaining > 0 and few_count > 0:
                    value_mapping["a few"] = min(2, 1 + remaining // few_count)
                    print(f"Adjusted 'a few': {value_mapping['a few']}, new value_mapping={value_mapping}")
            elif many_count * 2 + few_count * 2 + one_count * 1 < adjusted_subscription_type:
                value_mapping = {"many": 2, "a few": 2, "one": 1}
                total = many_count * 2 + few_count * 2 + one_count * 1
                print(f"Condition 2: Total={total}, value_mapping={value_mapping}")
                remaining = adjusted_subscription_type - total
                print(f"Remaining after Condition 2: {remaining}")
                if remaining > 0 and many_count > 0:
                    value_mapping["many"] = min(3, 2 + remaining // many_count)
                    print(f"Adjusted 'many': {value_mapping['many']}, new value_mapping={value_mapping}")
            elif many_count * 3 + few_count * 2 + one_count * 1 < adjusted_subscription_type:
                value_mapping = {"many": 3, "a few": 2, "one": 1}
                total = many_count * 3 + few_count * 2 + one_count * 1
                print(f"Condition 3: Total={total}, value_mapping={value_mapping}")
                remaining = adjusted_subscription_type - total
                print(f"Remaining after Condition 3: {remaining}")
                if remaining > 0 and many_count > 0:
                    value_mapping["many"] = min(4, 3 + remaining // many_count)
                    print(f"Adjusted 'many': {value_mapping['many']}, new value_mapping={value_mapping}")
            elif many_count * 4 + few_count * 2 + one_count * 1 < adjusted_subscription_type:
                value_mapping = {"many": 4, "a few": 2, "one": 1}
                total = many_count * 4 + few_count * 2 + one_count * 1
                print(f"Condition 4: Total={total}, value_mapping={value_mapping}")
                remaining = adjusted_subscription_type - total
                print(f"Remaining after Condition 4: {remaining}")
                if remaining > 0 and many_count > 0:
                    value_mapping["many"] = min(5, 4 + remaining // many_count)
                    print(f"Adjusted 'many': {value_mapping['many']}, new value_mapping={value_mapping}")
            elif many_count * 5 + few_count * 2 + one_count * 1 < adjusted_subscription_type:
                value_mapping = {"many": 5, "a few": 2, "one": 1}
                total = many_count * 5 + few_count * 2 + one_count * 1
                print(f"Condition 5: Total={total}, value_mapping={value_mapping}")
                remaining = adjusted_subscription_type - total
                print(f"Remaining after Condition 5: {remaining}")
                if remaining > 0 and few_count > 0:
                    value_mapping["a few"] = min(3, 2 + remaining // few_count)
                    print(f"Adjusted 'a few': {value_mapping['a few']}, new value_mapping={value_mapping}")
            elif many_count * 5 + few_count * 3 + one_count * 1 < adjusted_subscription_type:
                value_mapping = {"many": 5, "a few": 3, "one": 1}
                total = many_count * 5 + few_count * 3 + one_count * 1
                print(f"Condition 6: Total={total}, value_mapping={value_mapping}")
                remaining = adjusted_subscription_type - total
                print(f"Remaining after Condition 6: {remaining}")
                if remaining > 0 and many_count > 0:
                    value_mapping["many"] = min(6, 5 + remaining // many_count)
                    print(f"Adjusted 'many': {value_mapping['many']}, new value_mapping={value_mapping}")
            else:
                value_mapping = {"many": 1, "a few": 1, "one": 1}
                total = many_count * 1 + few_count * 1 + one_count * 1
                print(f"Else Condition: Total={total}, value_mapping={value_mapping}")
                remaining = adjusted_subscription_type - total
                print(f"Remaining in Else: {remaining}")
                if remaining < 0:
                    if many_count > 0:
                        value_mapping["many"] = max(4, (adjusted_subscription_type - few_count * 3 - one_count * 1) // many_count)
                        print(f"Adjusted 'many' in Else: {value_mapping['many']}, new value_mapping={value_mapping}")
                    elif few_count > 0:
                        value_mapping["a few"] = max(2, (adjusted_subscription_type - many_count * 5 - one_count * 1) // few_count)
                        print(f"Adjusted 'a few' in Else: {value_mapping['a few']}, new value_mapping={value_mapping}")

            # Apply the mapping to the staples
            transformed_staples = {k: value_mapping[v] for k, v in staples.items()}
            print(f"Transformed staples: {transformed_staples}")

            # Calculate the total value after transformation
            total_value = sum(transformed_staples.values())
            print(f"Total value after transformation: {total_value}")

            # Adjust values if the total exceeds the subscription_type
            if total_value > subscription_type:
                print(f"Total value ({total_value}) exceeds subscription type ({subscription_type}). Adjusting...")

                # Sort items by their values in descending order to target the highest value first
                sorted_items = sorted(transformed_staples.items(), key=lambda item: item[1], reverse=True)
                print(f"Sorted items for adjustment: {sorted_items}")

                for key, value in sorted_items:
                    if total_value <= subscription_type:
                        break
                    if value > 1:  # Ensure the value doesn't drop below 1
                        transformed_staples[key] -= 1
                        total_value -= 1
                        print(f"Adjusted {key} from {value} to {transformed_staples[key]}, new total: {total_value}")

                print("Adjustment complete.")

            print(f"Final transformed staples: {transformed_staples}")
            return transformed_staples

        except Exception as e:
            print(f"Error occurred: {str(e)}")
            raise

# ============================================================================================ 3. ADD SNACKS

    def add_snacks_loop(category, desired_count, grouped_snacks, context, previous_snack_ids):
        """
        Loops through the snacks in a single category and adds snacks to the context's month_start_box
        until either the desired count is reached or the secondary category increment exceeds 5.

        Parameters:
        - category: The category of snacks to process (string).
        - desired_count: Integer specifying the number of snacks to add for the category.
        - grouped_snacks: Dict where keys are categories, and values are lists of snacks for the specific category.
        - context: Dict to hold the output, specifically the 'month_start_box'.
        - previous_snack_ids: Set of SnackIDs to avoid reusing.

        Returns:
        - None (modifies the context in place).
        """

        # Initialize counters and sets for tracking usage
        brand_usage_count = Counter()
        flavor_tag_usage_count = Counter()
        form_usage_count = Counter()
        next_snacks = []
        secondary_category_increment = 0
        most_recent_saved_secondary_category = 0

        # Extract unique values for secondary categories, forms, brands, and flavor tags
        secondary_category_values = list(set(snack["secondaryCategory"] for snack in grouped_snacks))
        form_values = list(set(snack["form"] for snack in grouped_snacks))
        brand_values = list(set(snack["brand"] for snack in grouped_snacks))
        flavor_tag_values = list(set(tag for snack in grouped_snacks for tag in snack.get("flavorTags", [])))

        # Print the unique values
        print("Unique Secondary Categories:", secondary_category_values)
        print("Unique Forms:", form_values)
        print("Unique Brands:", brand_values)
        print("Unique Flavor Tags:", flavor_tag_values)
        print(f"\n")

        # Initialize usage count
        brand_usage_count.update({brand: 0 for brand in brand_values})
        flavor_tag_usage_count.update({tag: 0 for tag in flavor_tag_values})
        form_usage_count.update({form: 0 for form in form_values})

        def get_least_used(usage_count):
            """
            Returns the keys with the least usage from the given usage_count dictionary.
            """
            min_usage = min(usage_count.values(), default=0)
            return {key for key, count in usage_count.items() if count == min_usage}

        # Build the box
        while len(next_snacks) < desired_count:
            if secondary_category_increment > 15:
                print(f"Warning: Secondary category increment exceeded limit for category '{category}'. Breaking loop.")
                break

            # Determine the current category and form
            current_category = secondary_category_values[(secondary_category_increment + most_recent_saved_secondary_category) % len(secondary_category_values)]

            least_used_brands = get_least_used(brand_usage_count)
            least_used_flavor_tags = get_least_used(flavor_tag_usage_count)
            least_used_forms = get_least_used(form_usage_count)

            # Print the least used values
            print(f"\n")
            print(f"Searching for:")
            print(f"Current Category: {current_category}")
            print(f"Least Used Brands: {least_used_brands}")
            print(f"Least Used Forms: {least_used_forms}")
            print(f"Least Used Flavor Tags: {least_used_flavor_tags}")
            print(f"\n")

            # Define priority condition based on context["priority_setting"]
            priority_setting = context.get("priority_setting", 0)  # Default to 0 if not specified
            priority_condition = lambda snack: (
                priority_setting == 0 or
                (priority_setting == 1 and (
                    snack.get("protein", 0) > 7 or
                    snack.get("carbs", float('inf')) < 10 or
                    snack.get("primaryCategory") in ["Dried Fruit", "Fruit Gummies"]
                )) or
                (priority_setting == 2 and (
                    snack.get("carbs", float('inf')) < 10 or
                    snack.get("primaryCategory") in ["Dried Fruit", "Fruit Gummies"]
                )) or
                (priority_setting == 3 and snack.get("calories", float('inf')) < 150)
            )

            # Filter snacks based on criteria, including priority setting
            matching_snacks = [
                snack for snack in grouped_snacks
                if snack["secondaryCategory"] == current_category and
                   (secondary_category_increment >= 10 or snack["itemOfMonthBoost"] > 0) and
                   snack["form"] in least_used_forms and
                   snack["brand"] in least_used_brands and
                   (secondary_category_increment >= 12 or snack["SnackID"] not in previous_snack_ids) and
                   all(tag in least_used_flavor_tags for tag in snack.get("flavorTags", [])) and
                   priority_condition(snack)  # Added priority condition
            ]

            # Relax criteria step-by-step if no matches
            if not matching_snacks:
                matching_snacks = [
                    snack for snack in grouped_snacks
                    if snack["secondaryCategory"] == current_category and
                       (secondary_category_increment >= 10 or snack["itemOfMonthBoost"] > 0) and
                       snack["form"] in least_used_forms and
                       snack["brand"] in least_used_brands and
                       (secondary_category_increment >= 12 or snack["SnackID"] not in previous_snack_ids) and
                       priority_condition(snack)  # Added priority condition
                ]

            if not matching_snacks:
                matching_snacks = [
                    snack for snack in grouped_snacks
                    if snack["secondaryCategory"] == current_category and
                       (secondary_category_increment >= 10 or snack["itemOfMonthBoost"] > 0) and
                       snack["form"] in least_used_forms and
                       (secondary_category_increment >= 12 or snack["SnackID"] not in previous_snack_ids) and
                       priority_condition(snack)  # Added priority condition
                ]

            if not matching_snacks:
                matching_snacks = [
                    snack for snack in grouped_snacks
                    if snack["secondaryCategory"] == current_category and
                       (secondary_category_increment >= 10 or snack["itemOfMonthBoost"] > 0) and
                       (secondary_category_increment >= 12 or snack["SnackID"] not in previous_snack_ids) and
                       priority_condition(snack)  # Added priority condition
                ]

            # If still no matches, increment secondary category and continue
            if not matching_snacks:
                print(f"No matches found for category '{category}', secondary category '{current_category}'. Incrementing.")
                secondary_category_increment += 1
                continue

            # Print all matching snacks
            print("ALL MATCHING SNACKS:")
            for snack in matching_snacks:
                print(
                    f"SnackID: {snack.get('SnackID')}, "
                    f"Item Of Month Boost: {snack.get('itemOfMonthBoost')}, "
                    f"productLine: {snack.get('productLine')}, "
                    f"ounces: {snack.get('ounces')}, "
                    f"primaryCategory: {snack.get('primaryCategory')}, "
                    f"secondaryCategory: {snack.get('secondaryCategory')}, "
                    f"form: {snack.get('form')}, "
                    f"brand: {snack.get('brand')}, "
                    f"flavor: {snack.get('flavor')}, "
                    f"protein: {snack.get('protein', 'N/A')}, "  # Added for debugging
                    f"carbs: {snack.get('carbs', 'N/A')}, "    # Added for debugging
                    f"calories: {snack.get('calories', 'N/A')}" # Added for debugging
                )

            selected_snack = matching_snacks[0]
            next_snacks.append(selected_snack)

            # Log the SnackID of the added snack
            print(f"\n")
            print(f"Added to next_snacks: {selected_snack['SnackID']}")

            # Print all SnackIDs in next_snacks, each on a new line
            print(f"\n")
            print("NEXT SNACKS:")
            for snack in next_snacks:
                print(snack["SnackID"])
            print(f"\n")

            # Update usage counts
            brand_usage_count[selected_snack["brand"]] += 1
            for tag in selected_snack.get("flavorTags", []):
                flavor_tag_usage_count[tag] += 1
            form_usage_count[selected_snack["form"]] += 1

            # Remove selected snack from the category list
            grouped_snacks.remove(selected_snack)

            # Reset increment and rotate form
            most_recent_saved_secondary_category += 1
            secondary_category_increment = 0

        # Add results to the context
        context["month_start_box"].extend(
            {
                "SnackID": snack["SnackID"],
                "primaryCategory": category,
                "productLine": snack["productLine"],
                "count": 1,
                "premium": snack["premium"],
            }
            for snack in next_snacks
        )

        print(f"Final snacks added for category '{category}':")
        print(context["month_start_box"])
        print("\n")

    ### STAPLES
    
    def process_staples(transformed_staples, grouped_snacks, context, previous_snack_ids):
        """
        Processes each category in transformed_staples by calling add_snacks_loop
        to add snacks to the context's month_start_box.

        Parameters:
        - transformed_staples: Dict of staples with their respective counts.
        - grouped_snacks: Dict where keys are categories, and values are lists of snacks.
        - context: Dict to hold the output, specifically the 'month_start_box'.

        Returns:
        - None (modifies the context in place).
        """
        for category, count in transformed_staples.items():
            print(f"Processing category: {category} with desired count: {count}")

            # Pass only the snacks for the current category
            snacks_for_category = grouped_snacks.get(category, [])

            # Print the length of snacks for the current category
            print(f"Number of snacks available for category '{category}': {len(snacks_for_category)}")

            if not snacks_for_category:
                print(f"Warning: No snacks found for category '{category}'. Skipping...")
                continue

            # Call add_snacks_loop with the filtered snacks
            add_snacks_loop(
                category=category,
                desired_count=count,
                grouped_snacks=snacks_for_category,
                context=context,
                previous_snack_ids=previous_snack_ids
            )

        print("\n")    

    ### REMAINING CATEGORIES

    def process_remaining_categories(remaining_categories, count_to_fill, grouped_snacks, context, previous_snack_ids):
        """
        Processes each category in remaining_categories by calling add_snacks_loop
        to dynamically distribute snacks across categories and add them to the context's month_start_box.

        Parameters:
        - remaining_categories (list): A list of category names to process.
        - count_to_fill (int): Total number of snacks to be added across all categories.
        - grouped_snacks (dict): A dictionary where keys are category names and values are lists of snacks.
        - context (dict): A dictionary to hold the output, specifically the 'month_start_box'.
        - previous_snack_ids (list): List of previously selected snack IDs to avoid duplicates.

        Returns:
        - None: Modifies the context in place.
        """
        # Validate inputs
        if not isinstance(remaining_categories, list):
            raise ValueError("remaining_categories must be a list.")
        if not isinstance(grouped_snacks, dict):
            raise ValueError("grouped_snacks must be a dictionary.")
        if not isinstance(count_to_fill, int) or count_to_fill <= 0:
            raise ValueError("count_to_fill must be a positive integer.")

        # Filter out categories in context["category_dislikes"]
        disliked_categories = context.get("category_dislikes", [])
        print(f"Disliked categories: {disliked_categories}")
        valid_categories = [category for category in remaining_categories if category not in disliked_categories]

        # Calculate the dynamic count for each category
        num_categories = len(valid_categories)
        if num_categories == 0:
            print("No valid categories to process after filtering dislikes.")
            return

        # Distribute counts evenly and handle any remainder
        base_count = count_to_fill // num_categories
        remainder = count_to_fill % num_categories

        for idx, category in enumerate(valid_categories):
            # Get the snacks for the current category
            snacks_for_category = grouped_snacks.get(category, [])

            # Process only if snacks are available
            if len(snacks_for_category) > 0:
                # Add 1 to the base count for the first 'remainder' categories
                dynamic_count = base_count + (1 if idx < remainder else 0)

                print(f"** PROCESSING CATEGORY: {category}, Available: {len(snacks_for_category)}, Selecting: {dynamic_count}")
                print("\n")

                # Call add_snacks_loop with the calculated dynamic count
                add_snacks_loop(
                    category=category,
                    desired_count=dynamic_count,
                    grouped_snacks=snacks_for_category,
                    context=context,
                    previous_snack_ids=previous_snack_ids
                )
            else:
                print(f"Skipping category '{category}' as no snacks are available.")

        print("\n")
        
    # ========================================================================================================================== BUILD
    
    async def build_month_start_box(off_cycle):

        context["month_start_box"].extend(context["repeat_monthly"] or [])

        # LOGGING
        print("===============")
        print("START: BUILDING DRAFT BOX\n")
        print(f'EXTEND 1: {context["month_start_box"]}')
        print("--------------------------------------------------------------------------")
        print("\n")

        total_repeat_count = sum(item['count'] for item in context["repeat_monthly"])
        print(f"REPEAT COUNT: {total_repeat_count}") 

        adjusted_subscription_type = context["subscription_type"] - total_repeat_count

        # Check if adjusted_subscription_type is negative
        if adjusted_subscription_type < 0:
            print(f"Adjusted subscription type is negative ({adjusted_subscription_type}). Skipping snack selection and proceeding to save.")
            return  # Exit early to skip to saving
                
        transformed_staples = transform_staples_object(context["staples"], context["subscription_type"], context["category_dislikes"], adjusted_subscription_type)
        print(f"Transformed Staples: {transformed_staples}")
        
        # Fetch the safe snacks
        most_recent_snack_ids = await get_most_recent_box(customerID)
        
        safe_snacks = await fetch_snacks_filtered(context["customer_allergens"], context["vetoed_flavors"], context["category_dislikes"], off_cycle, most_recent_snack_ids, context["repeat_monthly"])

        # Get priority_setting from context
        priority_setting = context.get("priority_setting", 0)  # Default to 0 if not set
        print(f"PRIORITY SETTING: {priority_setting}")

        # Validate the structure of safe_snacks
        if not isinstance(safe_snacks, list):
            raise ValueError("safe_snacks must be a list.")

        # GET PREVIOUS SNACK IDS (PENALTY)
        previous_snack_ids = await get_previous_snack_ids(customerID)
        
        # CALCULATE SCORE
        sorted_safe_snacks = sorted(
            safe_snacks, 
            key=lambda snack: get_score(snack, priority_setting, previous_snack_ids), 
            reverse=True
        )
        
        grouped_snacks = group_snacks_by_primary_category(sorted_safe_snacks)

# ======= 2. ADD STAPLES
        
        # Call the function
        process_staples(transformed_staples, grouped_snacks, context, previous_snack_ids)

        # Print the remaining categories in the month_start_box
        print("EXTEND 2 (REMAINING CATEGORIES):")
        print("--------------------------------------------------------------------------")
        print("\n")
        for item in context["month_start_box"]:
            print(item)
        print("\n")
        print("MOVING")

# ======= 3. COMPLETE BOX WITH REMAINING CATEGORIES

        # ADD REMAINING CATEGORIES
        remaining_categories = [
            cat for cat in grouped_snacks if cat not in transformed_staples and cat not in (context["category_dislikes"] or [])
        ]

        print(f"Remaining categories to fill: {remaining_categories}")
        
        # Calculate running tally of 'count' fields in month_start_box
        month_start_box_count = sum(item.get('count', 0) for item in context["month_start_box"])
        print(f"Running tally of count fields in month_start_box: {month_start_box_count}")

        # Calculate count_to_fill using the sum of 'count' fields
        count_to_fill = context["subscription_type"] - month_start_box_count
        print(f"Count to fill: {count_to_fill}")


        # Only process remaining categories if count_to_fill is greater than 0
        if count_to_fill > 0:
            process_remaining_categories(remaining_categories, count_to_fill, grouped_snacks, context, previous_snack_ids)

        # CHECK: BOX IS FULL
        if len(context["month_start_box"]) != context["subscription_type"]:
            print(f"EXTEND 3 (REMAINING CATEGORIES): Box still not full: {len(context['month_start_box'])}/{context['subscription_type']}. Adding remaining snacks.")
            
            # RECALCULATE count_to_fill
            month_start_box_count = sum(item.get('count', 0) for item in context["month_start_box"])
            print(f"Running tally of count fields in month_start_box: {month_start_box_count}")
            count_to_fill = context["subscription_type"] - month_start_box_count
            print(f"Count to fill: {count_to_fill}")
            
            # Only process remaining categories if count_to_fill is greater than 0
            if count_to_fill > 0:
                process_remaining_categories(remaining_categories, count_to_fill, grouped_snacks, context, previous_snack_ids)

        # Print the extended list
        print("EXTEND 3 (REMAINING CATEGORIES):")
        print("--------------------------------------------------------------------------")
        print("\n")
        for index, item in enumerate(context["month_start_box"], start=1):
            print(f"{index}: {item}")
        print("\n")

        # NEW: EXTEND 4 (CATCH-ALL)
        month_start_box_count = sum(item.get('count', 0) for item in context["month_start_box"])
        if month_start_box_count != context["subscription_type"]:
            count_to_fill = context["subscription_type"] - month_start_box_count
            print(f"EXTEND 4 (CATCH-ALL): Box still not full: {month_start_box_count}/{context['subscription_type']}. Adding {count_to_fill} snacks with highest total score.")
            print("--------------------------------------------------------------------------")
    
            # Get SnackIDs already in the box to avoid duplicates
            current_snack_ids = {item["SnackID"] for item in context["month_start_box"]}
    
            # Filter sorted_safe_snacks to exclude already selected snacks
            available_snacks = [
                snack for snack in sorted_safe_snacks 
                if snack["SnackID"] not in current_snack_ids
            ]
    
            print(f"Available snacks for EXTEND 4: {len(available_snacks)}")
    
            # Add highest-scoring snacks until the box is full or no snacks remain
            added_snacks = 0
            for snack in available_snacks:
                if added_snacks >= count_to_fill:
                    break
                context["month_start_box"].append({
                    "SnackID": snack["SnackID"],
                    "primaryCategory": snack["primaryCategory"],
                    "productLine": snack["productLine"],
                    "count": 1,
                    "premium": snack["premium"],
                })
                added_snacks += 1
                print(f"Added snack in EXTEND 4: {snack['SnackID']} (Score: {snack.get('totalScore', 0)})")
    
            if added_snacks < count_to_fill:
                print(f"Warning: Could only add {added_snacks} snacks in EXTEND 4. Insufficient snacks available.")
    
        print("EXTEND 4 (FINAL BOX):")
        print("--------------------------------------------------------------------------")
        for index, item in enumerate(context["month_start_box"], start=1):
            print(f"{index}: {item}")
        month_start_box_count = sum(item.get('count', 0) for item in context["month_start_box"])
        print(f"Final box size: {month_start_box_count}/{context['subscription_type']}")

# ========================================================================================================================== SAVE
            
    async def save_month_start_box(off_cycle):
        print(f'Saving Box: {context["month_start_box"]}')

        # MONTH
        current_date = datetime.now()
        months_to_add = 2 if off_cycle else 1
        year = current_date.year + (current_date.month + months_to_add - 1) // 12
        month = (current_date.month + months_to_add - 1) % 12 + 1
        target_date = datetime(year, month, 1)
        month_as_int = int(target_date.strftime("%m%y"))

        # ORDER STATUS
        order_status = "Locked" if off_cycle else "Customize"
        
        
        created_at = datetime.utcnow()
        timestamp = created_at.strftime("%Y%m%d%H%M%S")

        boxID = f"box_{month_as_int}_{context['subscription_type']}_{customerID}_{timestamp}"

        document = {
            "boxID": boxID,
            "customerID": customerID,
            "month": month_as_int,
            "size": context["subscription_type"],
            "order_status": order_status,
            "snacks": context["month_start_box"],
            "originalSnacks": context["month_start_box"],
            "popped": False,
            "createdAt": created_at,
        }

        if context["month_start_box"]:
            await monthly_draft_box_collection.insert_one(document)
            print(f"Box saved successfully for customer: {customerID}")
            return document["snacks"]  # Return only the snacks field
        else:
            print("Box is empty. Nothing to save.")


# ========================================================================================================================== RUN
    
    await get_customer_by_customerID(customerID, is_reset_box, reset_total)
    await build_month_start_box(off_cycle)
    snacks = await save_month_start_box(off_cycle)  # Capture the snacks field
    return snacks  # Return the snacks to the endpoint