import requests
import itertools
import json
from decimal import Decimal, getcontext, ROUND_HALF_UP
from fuzzywuzzy import process
import time


# Fetches collection data from the CSFloat-compatible API.
def fetch_collections():
    url = "https://bymykel.github.io/CSGO-API/api/en/collections.json"
    response = requests.get(url)
    collections = response.json()
    return collections


# Determines the next higher rarity level for a given skin rarity.
def next_higher_rarity(current_rarity):
    rarity_order = [
        "rarity_common_weapon",
        "rarity_uncommon_weapon",
        "rarity_rare_weapon",
        "rarity_mythical_weapon",
        "rarity_legendary_weapon",
        "rarity_ancient_weapon",
    ]
    try:
        return rarity_order[rarity_order.index(current_rarity) + 1]
    except (ValueError, IndexError):
        return current_rarity


# Finds skin details from the collection data, using fuzzy string matching to handle slight mismatches in names.
def find_skin_details(name, collections):
    all_skins = [(skin['name'], skin, col['name']) for col in collections for skin in col['contains']]
    best_match = process.extractOne(name, [skin_name for skin_name, _, _ in all_skins], score_cutoff=60)
    if best_match:
        matched_name = best_match[0]
        if matched_name != name:
            print(f"{name} not recognized, using {matched_name} instead.")
        for skin_name, skin, col_name in all_skins:
            if skin_name == matched_name:
                skin['collection_name'] = col_name
                return skin
    else:
        print(f"No close match found for {name}.")
        return None


# Finds possible higher-tier skins that can result from trading up a set of skins.
def find_possible_outcomes(input_skins, collections):
    unique_outcomes = set()
    for skin_input in input_skins:
        skin_details = find_skin_details(skin_input['name'], collections)
        if skin_details:
            current_rarity = skin_details['rarity']['id']
            higher_rarity = next_higher_rarity(current_rarity)
            relevant_collections = [col for col in collections if col['name'] == skin_details['collection_name']]

            for collection in relevant_collections:
                for potential_outcome in collection['contains']:
                    if potential_outcome['rarity']['id'] == higher_rarity:
                        unique_outcomes.add((potential_outcome['name'], potential_outcome['rarity']['name']))

    return sorted(list(unique_outcomes), key=lambda x: x[0])


# Reads skin data from a local file.
def read_skins_from_file(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)


# Calculates the required float value ranges for the 10th skin needed to achieve a target float when trading up.
def find_required_float_for_tenth_skin(input_skins, target_float, precision=8):
    num_chosen_skins = 9
    target_float_decimal = Decimal(target_float).quantize(Decimal('1.' + '0' * precision), rounding=ROUND_HALF_UP)

    results = []
    for combo in itertools.combinations(input_skins, num_chosen_skins):
        current_total_float = sum(Decimal(skin['actual_float']) for skin in combo)
        exact_required_float = (target_float_decimal * (num_chosen_skins + 1) - current_total_float) / Decimal(1)

        min_valid_float = exact_required_float - Decimal('0.00001')
        max_valid_float = exact_required_float + Decimal('0.00001')

        if min_valid_float < Decimal('0'):
            min_valid_float = Decimal('0')
        if max_valid_float > Decimal('1'):
            max_valid_float = Decimal('1')

        if Decimal('0') <= exact_required_float <= Decimal('1'):
            results.append({
                'combination': combo,
                'min_required_float': min_valid_float,
                'max_required_float': max_valid_float
            })

    return results


# Fetches market listings from CSFloat API, respecting API rate limits by pausing after every 20 requests.
def fetch_skins_from_market(min_float, max_float, market_hash_name, api_key):
    url = 'https://csfloat.com/api/v1/listings'
    headers = {'Authorization': api_key}
    params = {
        'min_float': min_float,
        'max_float': max_float,
        'market_hash_name': market_hash_name,
        'sort_by': 'lowest_float',
        'limit': 10
    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to fetch data: {response.status_code}, {response.text}")
        return None


# The main function orchestrates the trade-up calculation and market fetch process.
def main(api_key):
    collections = fetch_collections()
    input_skins = read_skins_from_file('input_skins.json')
    target_float = Decimal('0.069696969')

    possible_outcomes = find_possible_outcomes(input_skins, collections)

    print("Possible outcome skins:")
    for idx, (name, rarity) in enumerate(possible_outcomes, 1):
        print(f"{idx}. {name} - Rarity: {rarity}")

    try:
        selection = int(input("Enter the number of the skin you are interested in: ")) - 1
        selected_skin_name, selected_skin_rarity = possible_outcomes[selection]
        print(f"You selected: {selected_skin_name} - Rarity: {selected_skin_rarity}")
    except (IndexError, ValueError):
        print("Invalid selection. Please run the program again with a valid number.")
        return

    print(f"Calculating trade-up combinations for {selected_skin_name}...")
    results = find_required_float_for_tenth_skin(input_skins, target_float)
    total_floats_checked = 0
    found_listings = 0
    valid_combinations = []
    request_count = 0

    for result in results:
        combo_description = ', '.join([f"{skin['name']} ({skin['actual_float']})" for skin in result['combination']])
        min_required_float = result['min_required_float']
        max_required_float = result['max_required_float']

        current_float = min_required_float
        increment = Decimal('0.00001')

        while current_float <= max_required_float:
            if request_count >= 20:
                print("Pausing for 30 seconds to manage API rate limits...")
                time.sleep(30)  # Pause the execution for 30 seconds
                request_count = 0  # Reset the request count after the pause

            total_floats_checked += 1
            listings = fetch_skins_from_market(float(current_float), float(current_float), selected_skin_name, api_key)
            request_count += 1

            if listings and listings.get('listings', []):
                found_listings += 1
                valid_combinations.append((combo_description, listings['listings']))

            current_float += increment

        print(f"Combination: {combo_description}")
        print(f"Valid float range for 10th skin: {min_required_float} to {max_required_float}")

    print(f"Checked {total_floats_checked} floats and found {found_listings} listings on the market.")
    for combo, listings in valid_combinations:
        print(f"Valid Recipe: {combo}")
        for listing in listings:
            print(f"Market Link: {listing['inspect_link']}")


if __name__ == "__main__":
    api_key = 'yehJbtkTKfH-TdwevpZTyRTyvtP4IwKM'
    main(api_key)
