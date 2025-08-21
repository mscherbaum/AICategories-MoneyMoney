import subprocess
import plistlib
import os
import datetime
import json
from openai import OpenAI
import anthropic
# The 'deepseek' library is used by the OpenAI client via the base_url, so no direct import is needed.
from pathlib import Path


# --- CONFIGURATION ---
# ❗ CHOOSE YOUR AI PROVIDER HERE
# Options: "openai", "anthropic", "deepseek"
AI_PROVIDER = "deepseek" 

# Replace with the UUID for your "Uncategorized" category in MoneyMoney.
UNCATGEGORIZED_CATEGORY_UUID = "a2fea395-d50a-41f9-913a-4a73dec89e72"

# The number of days back to look for transactions.
DAYS_TO_EXPORT = 20 #90

AVAILABLE_CATEGORIES = ["Uncategorized","Auto","Family","Health & Personal Care","Household & Home","Leisure & Entertainment","Miscellaneous","Pets","Shopping","Tax","Travel & Transportation","AVC","Pension","Real Estate","Rental Income", "Savings", "Online Services", "Deposit", "Insurance", "Business Expenses", "Utilities", "Investments"]

# --- Main Functions ---

def export_transactions_from_moneymoney(category_uuid):
    """
    Executes an AppleScript to export all transactions from a specific category UUID AND a date range.
    """
    print(f"👉 Step 1: Exporting transactions from category '{category_uuid}' for the last {DAYS_TO_EXPORT} days...")
    
    from_date = datetime.date.today() - datetime.timedelta(days=DAYS_TO_EXPORT)
    from_date_str = from_date.strftime('%Y-%m-%d')

    applescript_code = f'tell application "MoneyMoney" to export transactions from category "{category_uuid}" from date "{from_date_str}" as "plist"'
    command = ['osascript', '-e', applescript_code]
    
    try:
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as pipe:
            stdout, stderr = pipe.communicate()
            if pipe.returncode != 0:
                print(f"❌ ERROR: Failed to export transactions. Error: {stderr.decode().strip()}")
                return None
            if not stdout:
                print("❌ ERROR: Export returned no data. Check if there are transactions in this category within the date range.")
                return None
            parsed_data = plistlib.loads(stdout)
            print(f"✅ Transactions successfully exported and captured.")
            return parsed_data
    except Exception as e:
        print(f"❌ ERROR: An unexpected error occurred during export. Error: {e}")
        return None

def get_ai_categories_batch(client, provider, transactions_to_process):
    """
    Sends a batch of transactions to the selected AI provider.
    """
    print(f"Formatting batch for AI provider: {provider}...")
    input_json_list = []
    for trx in transactions_to_process:
        purpose = trx.get("purpose", "")
        recipient = trx.get("name", "")
        detail_for_ai = f"{recipient} - {purpose}"
        input_json_list.append({"id": trx["id"], "detail": detail_for_ai})
    
    input_json_string = json.dumps(input_json_list, indent=2)

    system_prompt = f"""
    You are an expert financial assistant. You will be given a JSON array of bank transactions.
    Your task is to categorize each transaction and return a valid JSON object as a response.
    The JSON object MUST contain a single key, "categorized_transactions", which is an array of objects.
    Each object in the response array MUST contain the original 'id' and a 'category' key.
    The category MUST be one of the following: {AVAILABLE_CATEGORIES}. When in doubt, categorize as "Uncategorized".
    Do not include any other text or explanations in your response.
    """
    print(system_prompt)
    print(f"Sending batch to {provider} for categorization...")
    try:
        response_content = ""
        # OpenAI and DeepSeek use the same API structure
        if provider == "openai" or provider == "deepseek":
            model_name = "gpt-4o" if provider == "openai" else "deepseek-chat"
            response = client.chat.completions.create(
                model=model_name,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": input_json_string}
                ]
            )
            response_content = response.choices[0].message.content
        
        elif provider == "anthropic":
            response = client.messages.create(
                model="claude-3-sonnet-20240229",
                max_tokens=4096,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": input_json_string}
                ]
            )
            response_content = response.content[0].text
        
        print("✅ AI call successful. Parsing response...")
        categorized_list = json.loads(response_content).get("categorized_transactions", [])
        id_to_category_map = {item['id']: item['category'] for item in categorized_list}
        return id_to_category_map
        
    except Exception as e:
        print(f"❌ ERROR: Could not get AI categories for batch. Error: {e}")
        return {}

def update_transaction_in_moneymoney(transaction_id, new_category):
    """
    Executes an AppleScript to update a single transaction's category.
    """
    # ✨ DEFINITIVE FIX ✨
    # Based on the correct documentation, this is the required command structure.
    # It is a 'set transaction' command, not a generic 'set category of...' command.
    applescript_code = f'tell application "MoneyMoney" to set transaction id {transaction_id} category to "{new_category}"'
    
    try:
        subprocess.run(['osascript', '-e', applescript_code], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ ERROR: Failed to update transaction ID {transaction_id}. AppleScript error: {e.stderr.strip()}")

# --- SCRIPT EXECUTION ---
if __name__ == "__main__":
    ai_client = None
    # Initialize the correct client based on the provider
    if AI_PROVIDER == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            print("❌ FATAL ERROR: AI_PROVIDER is 'openai' but OPENAI_API_KEY environment variable is not set.")
            exit(1)
        ai_client = OpenAI()
    
    elif AI_PROVIDER == "anthropic":
        if not os.getenv("ANTHROPIC_API_KEY"):
            print("❌ FATAL ERROR: AI_PROVIDER is 'anthropic' but ANTHROPIC_API_KEY environment variable is not set.")
            exit(1)
        ai_client = anthropic.Anthropic()
    
    elif AI_PROVIDER == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            print("❌ FATAL ERROR: AI_PROVIDER is 'deepseek' but DEEPSEEK_API_KEY environment variable is not set.")
            exit(1)
        # Use the OpenAI client, but configure it for the DeepSeek API endpoint.
        ai_client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
    
    else:
        print(f"❌ FATAL ERROR: Unknown AI_PROVIDER '{AI_PROVIDER}'. Please choose 'openai', 'anthropic', or 'deepseek'.")
        exit(1)
        
    exported_data = export_transactions_from_moneymoney(UNCATGEGORIZED_CATEGORY_UUID)

    if exported_data:
        all_transactions = exported_data.get('transactions', [])
        print(f"\n--- 📋 Export Report: Found {len(all_transactions)} total transactions to categorize ---")
        for trx in all_transactions:
            date_str = trx.get('bookingDate', datetime.datetime.now()).strftime('%Y-%m-%d')
            name = trx.get('name', 'N/A')
            amount = trx.get('amount', 0.0)
            currency = trx.get('currency', '')
            print(f"- {date_str}: {name} ({amount:.2f} {currency})")
        print("----------------------------------------------------")

        print("\n👉 Step 2: Processing all exported transactions...")
        transactions_to_categorize = [trx for trx in all_transactions if trx.get('booked')]
        updated_transactions_map = {}
        if transactions_to_categorize:
            updated_transactions_map = get_ai_categories_batch(ai_client, AI_PROVIDER, transactions_to_categorize)
            print(f"✅ AI successfully categorized {len(updated_transactions_map)} transactions.")
        else:
            print("No booked transactions found to process.")

        print(f"\n👉 Step 3: Updating {len(updated_transactions_map)} transactions in MoneyMoney...")
        if not updated_transactions_map:
            print("No transactions needed updating.")
        else:
            for trx_id, new_category in updated_transactions_map.items():
                update_transaction_in_moneymoney(trx_id, new_category)
            print("✅ All targeted transactions updated successfully!")
        
        print("\n--- 📊 Final Summary ---")
        print(f"Total Transactions Exported: {len(all_transactions)}")
        print(f"Total Transactions Updated: {len(updated_transactions_map)}")
        print("-------------------------")
        print("All done! 🎉")