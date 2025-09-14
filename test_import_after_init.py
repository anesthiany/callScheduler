"""
Test imports after creating __init__.py
"""

try:
    from src.api_client import SpinSchedulesAPIClient
    print("SUCCESS: Import from src.api_client works!")
    
    # Test creating the client
    client = SpinSchedulesAPIClient()
    print("SUCCESS: API client created successfully!")
    print("Module imports are now working properly.")
    
except ImportError as e:
    print(f"IMPORT ERROR: {e}")
    print("The __init__.py method didn't work. Let's try method 2.")
    
except Exception as e:
    print(f"OTHER ERROR: {e}")
    print("Import worked, but there was another issue (likely .env file)")
