"""
Analyze SpinSchedules data to understand scheduling structure
"""

import json
from src.api_client import SpinSchedulesAPIClient
from datetime import date, timedelta
from collections import defaultdict

def analyze_schedules_and_groups():
    """Analyze saved schedule and group data"""
    try:
        with open('data/schedules.json', 'r') as f:
            schedules = json.load(f)
        
        with open('data/user_groups.json', 'r') as f:
            user_groups = json.load(f)
    except FileNotFoundError:
        print("Run the API test first to generate data files")
        return None, None
    
    print("=" * 60)
    print("SCHEDULE ANALYSIS")
    print("=" * 60)
    
    # Analyze schedules
    call_related = []
    other_schedules = []
    
    for schedule in schedules:
        name = schedule.get('name', '').lower()
        call_keywords = ['call', 'coverage', 'duty', 'night', 'weekend', 'holiday', 'emergency']
        
        if any(keyword in name for keyword in call_keywords):
            call_related.append(schedule)
        else:
            other_schedules.append(schedule)
    
    print(f"Total schedules: {len(schedules)}")
    print(f"Call-related schedules: {len(call_related)}")
    print(f"Other schedules: {len(other_schedules)}")
    
    print("\nCall-related schedules:")
    for schedule in call_related:
        print(f"  - {schedule['name']} (ID: {schedule['id']})")
    
    print("\n" + "=" * 60)
    print("USER GROUP ANALYSIS")
    print("=" * 60)
    
    # Analyze user groups
    core_groups = [g for g in user_groups if g.get('coreGroup', False)]
    non_core_groups = [g for g in user_groups if not g.get('coreGroup', False)]
    
    print(f"Total groups: {len(user_groups)}")
    print(f"Core groups: {len(core_groups)}")
    print(f"Non-core groups: {len(non_core_groups)}")
    
    print("\nCore groups (main job classifications):")
    for group in core_groups:
        print(f"  - {group['groupName']} (ID: {group['groupId']})")
    
    # Look for anesthesia-related groups
    anesthesia_groups = []
    anesthesia_keywords = ['anesthesi', 'anesth', 'attending', 'resident', 'fellow', 'crna']
    
    for group in user_groups:
        name = group.get('groupName', '').lower()
        if any(keyword in name for keyword in anesthesia_keywords):
            anesthesia_groups.append(group)
    
    print(f"\nPotential anesthesia-related groups: {len(anesthesia_groups)}")
    for group in anesthesia_groups:
        group_type = "Core" if group.get('coreGroup', False) else "Non-core"
        print(f"  - {group['groupName']} (ID: {group['groupId']}) [{group_type}]")
    
    return call_related, anesthesia_groups

def get_current_assignments(client, schedule_ids, days_back=30):
    """Get recent assignments to understand assignment patterns"""
    end_date = date.today()
    start_date = end_date - timedelta(days=days_back)
    
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    
    print(f"\nGetting assignments from {start_str} to {end_str}...")
    
    try:
        assignments = client.get_assignments_by_schedule(
            schedule_ids=schedule_ids,
            start_date=start_str,
            end_date=end_str
        )
        
        print(f"Found {len(assignments)} assignments")
        
        # Analyze assignment patterns
        if assignments:
            assignment_codes = defaultdict(int)
            users_with_assignments = defaultdict(int)
            dates_with_assignments = defaultdict(int)
            
            for assignment in assignments:
                assignment_codes[assignment.get('aName', 'Unknown')] += 1
                users_with_assignments[f"{assignment.get('fName', '')} {assignment.get('lName', '')}"] += 1
                dates_with_assignments[assignment.get('date', '')] += 1
            
            print(f"\nMost common assignment types:")
            for code, count in sorted(assignment_codes.items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"  - {code}: {count} times")
            
            print(f"\nUsers with most assignments (top 5):")
            for user, count in sorted(users_with_assignments.items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"  - {user}: {count} assignments")
            
            # Save assignment data
            with open('data/recent_assignments.json', 'w') as f:
                json.dump(assignments, f, indent=2)
            print(f"\nAssignment data saved to data/recent_assignments.json")
        
        return assignments
    
    except Exception as e:
        print(f"Error getting assignments: {e}")
        return []

def main():
    # Initialize API client
    try:
        client = SpinSchedulesAPIClient()
        print("API client initialized successfully")
    except Exception as e:
        print(f"API initialization failed: {e}")
        return
    
    # Analyze existing data
    call_schedules, employment_groups = analyze_schedules_and_groups()
    
    if not call_schedules:
        print("\nNo call-related schedules identified. Please review the schedule list manually.")
        return
    
    # Get user roster to test FTE data
    try:
        users = client.get_user_roster()
        sample_user_ids = [int(user['userid']) for user in users[:5]]  # Get first 5 user IDs
        
        # Test FTE data retrieval
        test_fte_data_retrieval(client, sample_user_ids)
        
    except Exception as e:
        print(f"Error getting user roster for FTE testing: {e}")
    
    # Ask user to confirm which schedules to analyze
    print(f"\nFound {len(call_schedules)} call-related schedules.")
    print("Would you like to analyze recent assignments for these schedules? (y/n)")
    
    # For now, let's analyze the first call schedule if available
    if call_schedules:
        schedule_ids = [schedule['id'] for schedule in call_schedules[:2]]  # Analyze first 2
        print(f"\nAnalyzing schedules: {[s['name'] for s in call_schedules[:2]]}")
        assignments = get_current_assignments(client, schedule_ids)
    
    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Review the identified call schedules")
    print("2. Review the employment-related user groups")
    print("3. Check FTE field names for your system")
    print("4. Look at recent assignments to understand your current patterns")
    print("5. Define scheduling constraints for the optimizer")

if __name__ == "__main__":
    main()