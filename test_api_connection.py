"""
Test script for SpinSchedules API connection
Run this to verify your API key works and explore your data
"""

from src.api_client import SpinSchedulesAPIClient
import json
from datetime import date, timedelta

def main():
    # Initialize API client
    try:
        client = SpinSchedulesAPIClient()
        print("✅ API client initialized successfully")
    except ValueError as e:
        print(f"❌ API setup error: {e}")
        print("Make sure your .env file has SPINSCHEDULES_API_KEY=your_actual_key")
        return
    
    print("\n" + "="*50)
    print("TESTING API CONNECTION")
    print("="*50)
    
    # Test 1: Echo endpoint
    try:
        echo_response = client.test_connection("Hello from Call Scheduler!")
        print("✅ Echo test successful")
        print(f"   Response: {echo_response}")
    except Exception as e:
        print(f"❌ Echo test failed: {e}")
        return
    
    # Test 2: Get user roster
    try:
        users = client.get_user_roster()
        print(f"✅ User roster retrieved: {len(users)} users found")
        if users:
            print(f"   Sample user: {users[0]['fname']} {users[0]['lname']} ({users[0]['usercode']})")
    except Exception as e:
        print(f"❌ User roster failed: {e}")
    
    # Test 3: Get available schedules
    try:
        schedules = client.get_available_schedules()
        print(f"✅ Schedules retrieved: {len(schedules)} schedules found")
        if schedules:
            print("   Available schedules:")
            for schedule in schedules[:5]:  # Show first 5
                print(f"     - {schedule['name']} (ID: {schedule['id']})")
    except Exception as e:
        print(f"❌ Schedules failed: {e}")
    
    # Test 4: Get user groups
    try:
        groups = client.get_user_groups()
        print(f"✅ User groups retrieved: {len(groups)} groups found")
        if groups:
            print("   Sample groups:")
            for group in groups[:3]:  # Show first 3
                print(f"     - {group['groupName']} (ID: {group['groupId']})")
            print(f"   ... and {len(groups)-3} more groups")
    except Exception as e:
        print(f"❌ User groups failed: {e}")
    
    print("\n" + "="*50)
    print("API CONNECTION TEST COMPLETE")
    print("="*50)
    
    # Save data for analysis
    if users and schedules and groups:
        # Save individual files for the analyzer
        with open('data/schedules.json', 'w') as f:
            json.dump(schedules, f, indent=2)
        
        with open('data/user_groups.json', 'w') as f:
            json.dump(groups, f, indent=2)
        
        # Also save comprehensive summary
        data_summary = {
            "total_users": len(users),
            "total_schedules": len(schedules),
            "total_groups": len(groups),
            "sample_users": users[:3],
            "available_schedules": schedules,
            "user_groups": groups
        }
        
        with open('data/api_test_results.json', 'w') as f:
            json.dump(data_summary, f, indent=2)
        
        print("\n📊 Data saved to multiple files:")
        print("   - data/schedules.json")
        print("   - data/user_groups.json") 
        print("   - data/api_test_results.json")
        print("\nNext steps:")
        print("1. Review the schedules to identify which ones contain call assignments")
        print("2. Identify which user groups represent anesthesiologists")
        print("3. Look at existing assignments to understand assignment codes")

if __name__ == "__main__":
    main()