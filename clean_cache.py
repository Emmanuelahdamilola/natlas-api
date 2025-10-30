import json
import os

# --- IMPORTANT: Set the correct local path to your cache folder ---
# Assuming your repository structure is: natlas-api/cache/natlas_responses_complete.json
CACHE_PATH = './cache/natlas_responses_complete.json' 
OUTPUT_PATH = './cache/natlas_responses_complete.json' 

print("Starting cache cleanup...")

# 1. Load the corrupted data
try:
    with open(CACHE_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
except FileNotFoundError:
    print(f"❌ ERROR: Cache file not found at {CACHE_PATH}. Check your path!")
    exit()

# 2. Initialize a clean data structure
cleaned_data = {"metadata": data.get("metadata", {}), 
                "yoruba": [], "igbo": [], "hausa": [], "english": []}

# 3. Iterate and filter the corrupt entries
print("Filtering corrupted string entries...")
for lang in ['yoruba', 'igbo', 'hausa', 'english']:
    original_list = data.get(lang, [])
    original_count = len(original_list)
    
    # Filter: Keep only items that are dictionaries AND have the 'success' key
    cleaned_cases = [
        case for case in original_list
        if isinstance(case, dict) and 'success' in case
    ]
    
    cleaned_count = len(cleaned_cases)
    cleaned_data[lang] = cleaned_cases
    
    print(f"[{lang.upper()}]: Removed {original_count - cleaned_count} corrupted entries.")

# 4. Save the cleaned data, overwriting the original file
with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(cleaned_data, f, ensure_ascii=False, indent=2)

print("\n✅ Cache file successfully cleaned and saved. Ready for commit!")