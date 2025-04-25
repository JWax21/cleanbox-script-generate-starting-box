from datetime import datetime, timedelta
from collections import defaultdict
from motor.motor_asyncio import AsyncIOMotorClient
from pprint import pprint
from collections import Counter

async def build_starting_box(
    customerID: str,
    new_signup: bool,
    off_cycle: bool,
    is_reset_box: bool,
    reset_total: int,
    monthly_draft_box_collection,
    all_customers_collection,
    all_snacks_collection,
):
    # Context variables to store shared data
    context = {
        "staples": None,
        "customer_allergens": None,
        "vetoed_flavors": None,
        "priority_setting": None,
        "category_dislikes": None,
        "repeat_monthly": None,
        "subscription_type": None,
        "month_start_box": []
    }

# ========================================================================================================================== PRE: GET CUSTOMER INFO 
    
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
                    "repeatMonthly": 1, 
                    "subscription_type": 1
                }
            )

            if customer_document:
                context["customer_allergens"] = customer_document.get("allergens")
                context["vetoed_flavors"] = customer_document.get("vetoedFlavors")
                context["staples"] = customer_document.get("staples")
                context["category_dislikes"] = customer_document.get("dislikes")
                context["repeat_monthly"] = customer_document.get("repeatMonthly")
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
    
    async def fetch_snacks_filtered(allergens=None, vetoedFlavors=None, off_cycle=False):
        try:
            print("FILTERING SNACKS")
            # Initialize query conditions
            query_conditions = {"replacementOnly": {"$ne": True}}  # Exclude snacks where replacementOnly is true

            # Filter by allergens if provided
            if allergens:
                print("a. Adding Allergens to query conditons")
                query_conditions["allergens"] = {"$nin": allergens}

            # Filter by vetoed flavors if provided
            if vetoedFlavors:
                print("b. Adding Vetoed Flavors to query conditons")
                # Suffixes to handle stripping and transformations
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

            # Filter by off-cycle if provided
            if off_cycle:
                print("c. Adding Off-Cycle to query conditions")
                query_conditions["$or"] = [{"inStock": True}, {"approved": True}]
                
            # Query the collection with the combined filters
            return await all_snacks_collection.find(query_conditions).to_list(length=200)

        except Exception as e:
            print(f"An error occurred while retrieving snacks: {e}")
            return []

# ============================================================================================ PREPARE: SORT BY SCORE
    
    def get_score(snack, priority_setting):
        total_score = snack.get("totalScore", 0)
        protein_boost = snack.get("highProteinBoost", 0)
        low_carb_boost = snack.get("lowCarbBoost", 0)
        low_calorie_boost = snack.get("lowCalorieBoost", 0)

        if priority_setting == 0:
            return total_score
        elif priority_setting == 1:
            return total_score + protein_boost
        elif priority_setting == 2:
            return total_score + low_carb_boost
        elif priority_setting == 3:
            return total_score + low_calorie_boost
        else:
            return total_score


    
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
    
    def transform_staples_object(staples, subscription_type, category_dislikes):
        # COUNTS
        staples_count = len(staples)
        dislikes_count = len(category_dislikes)
        grey_categories = 10 - staples_count - dislikes_count

        if grey_categories < 0:
            raise ValueError("Invalid inputs: staples and category dislikes exceed available categories.")

        print(f"Grey: {grey_categories}")

        # Score placeholders for base mappings
        score_placeholders = {
            20: {"many": 5, "a few": 3, "one": 1},
            16: {"many": 4, "a few": 2, "one": 1},
            12: {"many": 3, "a few": 2, "one": 1},
        }

        # Get the base mapping for the given subscription type
        base_staples_mapping = score_placeholders.get(subscription_type)
        if not base_staples_mapping:
            raise ValueError(f"Unsupported subscription type: {subscription_type}")

        # Calculate base staples score
        base_staples_score = sum(base_staples_mapping[v] for v in staples.values() if v in base_staples_mapping)

        # Determine the value mapping based on grey categories and subscription type
        adjustment_factor = (subscription_type - base_staples_score) / grey_categories if grey_categories > 0 else 0

        if adjustment_factor > 2:
            mapping_type = "heavy_mapping"
            value_mapping = {
                20: {"many": 6, "a few": 4, "one": 1},
                16: {"many": 5, "a few": 3, "one": 1},
                12: {"many": 4, "a few": 3, "one": 1},
            }
        elif 1 < adjustment_factor <= 2:
            mapping_type = "base_mapping"
            value_mapping = score_placeholders
        else:
            mapping_type = "light_mapping"
            value_mapping = {
                20: {"many": 4, "a few": 2, "one": 1},
                16: {"many": 3, "a few": 2, "one": 1},
                12: {"many": 3, "a few": 2, "one": 1},
            }

        print(f"Using {mapping_type} for value mapping.")

        # Get the mapping for the given subscription type
        mapping = value_mapping.get(subscription_type)
        if not mapping:
            raise ValueError(f"Unsupported subscription type: {subscription_type}")

        # Apply the mapping to the staples
        transformed_staples = {k: mapping[v] for k, v in staples.items() if v in mapping}

        # Calculate the total value after transformation
        total_value = sum(transformed_staples.values())

        # Adjust values if the total exceeds the subscription type
        if total_value > subscription_type:
            print(f"Total value ({total_value}) exceeds subscription type ({subscription_type}). Adjusting...")

            # Sort items by their values in descending order to target the highest value first
            sorted_items = sorted(transformed_staples.items(), key=lambda item: item[1], reverse=True)

            for key, value in sorted_items:
                if value > 1:  # Ensure the value doesn't drop below 1
                    transformed_staples[key] -= 1
                    total_value -= 1  # Update total value
                    if total_value <= subscription_type:
                        break  # Stop once the total is adjusted

        return transformed_staples

# ============================================================================================ 3. ADD SNACKS

    def add_snacks_loop(category, desired_count, grouped_snacks, context):
        """
        Loops through the snacks in a single category and adds snacks to the context's month_start_box
        until either the desired count is reached or the secondary category increment exceeds 5.

        Parameters:
        - category: The category of snacks to process (string).
        - desired_count: Integer specifying the number of snacks to add for the category.
        - grouped_snacks: Dict where keys are categories, and values are lists of snacks for the specific category.
        - context: Dict to hold the output, specifically the 'month_start_box'.

        Returns:
        - None (modifies the context in place).
        """

        print("RUNNING")
        
        # Initialize counters and sets for tracking usage
        brand_usage_count = Counter()
        flavor_tag_usage_count = Counter()
        form_usage_count = Counter()
        next_snacks = []
        secondary_category_increment = 0
        most_recent_saved_secondary_category = 0

        print("RUNNING")
        
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
            if secondary_category_increment > 5:
                print(f"Warning: Secondary category increment exceeded limit for category '{category}'. Breaking loop.")
                break

            # Determine the current category and form
            current_category = secondary_category_values[(secondary_category_increment+most_recent_saved_secondary_category) % len(secondary_category_values)]

            least_used_brands = get_least_used(brand_usage_count)
            least_used_flavor_tags = get_least_used(flavor_tag_usage_count)
            least_used_forms = get_least_used(form_usage_count)

            # Filter snacks based on criteria
            matching_snacks = [
                snack for snack in grouped_snacks
                if snack["secondaryCategory"] == current_category and
                   snack["form"] in least_used_forms and
                   snack["brand"] in least_used_brands and
                   all(tag in least_used_flavor_tags for tag in snack.get("flavorTags", []))
            ]

            # Relax criteria step-by-step if no matches
            if not matching_snacks:
                matching_snacks = [
                    snack for snack in grouped_snacks
                    if snack["secondaryCategory"] == current_category and
                       snack["form"] in least_used_forms and
                       snack["brand"] in least_used_brands
                ]

            if not matching_snacks:
                matching_snacks = [
                    snack for snack in grouped_snacks
                    if snack["secondaryCategory"] == current_category and
                       snack["form"] in least_used_forms
                ]

            if not matching_snacks:
                matching_snacks = [
                    snack for snack in grouped_snacks
                    if snack["secondaryCategory"] == current_category
                ]

            # If still no matches, increment secondary category and continue
            if not matching_snacks:
                print(f"No matches found for category '{category}', secondary category '{current_category}'. Incrementing.")
                secondary_category_increment += 1
                continue


            # ADDED
            selected_snack = matching_snacks[0]
            next_snacks.append(selected_snack)

            # Log the SnackID of the added snack
            print(f"Added to next_snacks: {selected_snack['SnackID']}")

            # Print all SnackIDs in next_snacks, each on a new line
            print("NEXT SNACKS:")
            for snack in next_snacks:
                print(snack["SnackID"])


            brand_usage_count[selected_snack["brand"]] += 1
            for tag in selected_snack.get("flavorTags", []):
                flavor_tag_usage_count[tag] += 1

            # Remove selected snack from the category list
            grouped_snacks.remove(selected_snack)

            # Reset increment and rotate form
            most_recent_saved_secondary_category +=1
            secondary_category_increment = 0

        # Add results to the context
        context["month_start_box"].extend(
            {
                "SnackID": snack["SnackID"],
                "primaryCategory": category,
                "count": 1,
                "premium": snack["premium"],
            }
            for snack in next_snacks
        )

        print(f"Final snacks added for category '{category}':")
        print(context["month_start_box"])
        print("\n")

    ### STAPLES
    
    def process_staples(transformed_staples, grouped_snacks, context):
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
                context=context
            )

        print("\n")    

    ### REMAINING CATEGORIES

    def process_remaining_categories(remaining_categories, count_to_fill, grouped_snacks, context):
        """
        Processes each category in remaining_categories by calling add_snacks_loop
        to dynamically distribute snacks across categories and add them to the context's month_start_box.

        Parameters:
        - remaining_categories (list): A list of category names to process.
        - count_to_fill (int): Total number of snacks to be added across all categories.
        - grouped_snacks (dict): A dictionary where keys are category names and values are lists of snacks.
        - context (dict): A dictionary to hold the output, specifically the 'month_start_box'.

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

        # Calculate the dynamic count for each category
        num_categories = len(remaining_categories)
        if num_categories == 0:
            print("No categories to process.")
            return

        # Distribute counts evenly and handle any remainder
        base_count = count_to_fill // num_categories
        remainder = count_to_fill % num_categories

        for idx, category in enumerate(remaining_categories):
            # Get the snacks for the current category
            snacks_for_category = grouped_snacks.get(category, [])

            # Process only if snacks are available
            if len(snacks_for_category) > 0:
                # Add 1 to the base count for the first 'remainder' categories
                dynamic_count = base_count + (1 if idx < remainder else 0)

                print(f"Processing category: {category}")
                print(f"Number of snacks available for category '{category}': {len(snacks_for_category)}")
                print(f"Dynamic count for category '{category}': {dynamic_count}")

                # Call add_snacks_loop with the calculated dynamic count
                add_snacks_loop(
                    category=category,
                    desired_count=dynamic_count,
                    grouped_snacks=snacks_for_category,
                    context=context
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
        print("\n")
        
        transformed_staples = transform_staples_object(context["staples"], context["subscription_type"], context["category_dislikes"])
        
        # Fetch the safe snacks
        safe_snacks = await fetch_snacks_filtered(context["customer_allergens"], context["vetoed_flavors"], off_cycle)

        # Get priority_setting from context
        priority_setting = context.get("priority_setting", 0)  # Default to 0 if not set
        print(f"PRIORITY SETTING: {priority_setting}")

        # Validate the structure of safe_snacks
        if not isinstance(safe_snacks, list):
            raise ValueError("safe_snacks must be a list.")

        # Sort the safe_snacks using the external get_score function
        sorted_safe_snacks = sorted(
            safe_snacks, 
            key=lambda snack: get_score(snack, priority_setting), 
            reverse=True
        )
        
        grouped_snacks = group_snacks_by_primary_category(sorted_safe_snacks)

# ======= 2. ADD STAPLES
        
        # Call the function
        process_staples(transformed_staples, grouped_snacks, context)

        # Print the remaining categories in the month_start_box
        print("EXTEND 2 (REMAINING CATEGORIES):")
        for item in context["month_start_box"]:
            print(item)


# ======= 3. COMPLETE BOX WITH REMAINING CATEGORIES

        # ADD REMAINING CATEGORIES
        remaining_categories = [
            cat for cat in grouped_snacks if cat not in transformed_staples and cat not in (context["category_dislikes"] or [])
        ]
        
        count_to_fill = context["subscription_type"] - len(context["month_start_box"])
        
        process_remaining_categories(remaining_categories, count_to_fill, grouped_snacks, context)

        # CHECK: BOX IS FULLL
        if len(context["month_start_box"]) != context["subscription_type"]:
            # Recalculate count_to_fill and call the function again
            count_to_fill = context["subscription_type"] - len(context["month_start_box"])
            process_remaining_categories(remaining_categories, count_to_fill, grouped_snacks, context)

        # Print the extended list
        print("EXTEND 3 (REMAINING CATEGORIES):")
        for index, item in enumerate(context["month_start_box"], start=1):
            print(f"{index}: {item}")


# ========================================================================================================================== SAVE
            
    async def save_month_start_box(off_cycle):
        print(f'Saving Box: {context["month_start_box"]}')

        # Determine the correct month
        current_date = datetime.now()
        target_date = current_date.replace(day=1) + timedelta(days=32) if off_cycle else current_date
        month_as_int = int(target_date.strftime("%m%y"))

        document = {
            "customerID": customerID,
            "snacks": context["month_start_box"],
            "originalSnacks": context["month_start_box"],
            "month": month_as_int,
            "size": context["subscription_type"],
            "popped": False,
            "createdAt": datetime.utcnow(),
        }

        if context["month_start_box"]:
            await monthly_draft_box_collection.insert_one(document)
            print(f"Box saved successfully for customer: {customerID}")
        else:
            print("Box is empty. Nothing to save.")


# ========================================================================================================================== RUN
    
    await get_customer_by_customerID(customerID, is_reset_box, reset_total)
    await build_month_start_box(off_cycle)
    await save_month_start_box(off_cycle)
    