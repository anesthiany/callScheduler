"""
Credential-aware optimizer that matches users to call types they can actually do
"""

from src.call_optimizer import CallScheduleOptimizer
from src.api_client import SpinSchedulesAPIClient
from src.constraint_validator import SchedulingConstraints
from typing import Dict, List, Set


def get_user_call_credentials(api_client: SpinSchedulesAPIClient, user_id: int) -> Set[str]:
    """
    Get the call types a user is credentialed for
    
    Args:
        api_client: API client instance
        user_id: User ID to check
        
    Returns:
        Set of call types the user can take (e.g., {'CMCG', 'CMCO'})
    """
    try:
        # Get user's groups
        response = api_client._make_request(
            'GET', 
            '/External/get_users_userGroups',
            params={'userId': user_id}
        )
        
        if not response.get('success'):
            return set()
        
        user_groups = response.get('groups', [])
        credentials = set()
        
        # Map credential groups to call types
        credential_mapping = {
            'Cred Call: CMCG Call Pool': ['CMCG'],
            'Cred Call: CMCO Call Pool': ['CMCO'],
            'Cred Call: LPH Call Pool': ['LP7', 'LPG', 'LPO'],
            'Cred Call: MCL Call Pool': ['MCL7', 'MCLG', 'MCLO'],
            'Cred Call: MCK Call Pool': ['MCKC_N', 'MCKT_D', 'MCKG_D'],
            'Cred Call: THDN Call Pool': ['THDN7', 'THDNG', 'THDNO'],
            'Cred Call: NE Call Pool': ['NE'],
            'Cred Call: PHR Call Pool': ['PHR7', 'PHRG', 'PHRO'],
        }
        
        # Check which credential groups the user belongs to
        for group in user_groups:
            group_name = group.get('groupName', '')
            if group_name in credential_mapping:
                credentials.update(credential_mapping[group_name])
        
        return credentials
        
    except Exception as e:
        print(f"Error getting credentials for user {user_id}: {e}")
        return set()


def get_credentialed_users_by_call_type(api_client: SpinSchedulesAPIClient) -> Dict[str, List[int]]:
    """
    Get users organized by the call types they can handle
    
    Returns:
        Dictionary mapping call_type -> list of user_ids who can do that call type
    """
    print("Loading user credentials...")
    
    # Get all users
    all_users = api_client.get_user_roster()
    
    # Get employment groups to filter to relevant users
    employment_groups = {1000, 1020, 11327, 1030}  # Full Time, Part Time, etc.
    
    call_type_users = {
        'CMCG': [], 'CMCO': [], 
        'LP7': [], 'LPG': [], 'LPO': [],
        'MCL7': [], 'MCLG': [], 'MCLO': [],
        'MCKC_N': [], 'MCKT_D': [], 'MCKG_D': [],
        'THDN7': [], 'THDNG': [], 'THDNO': [],
        'NE': [],
        'PHR7': [], 'PHRG': [], 'PHRO': []
    }
    
    for user in all_users[:20]:  # Limit to first 20 users for testing
        user_id = int(user['userid'])
        
        # Check if user is in employment groups (simplified for now)
        # In production, you'd check group membership properly
        
        # Get credentials for this user
        credentials = get_user_call_credentials(api_client, user_id)
        
        if credentials:
            user_name = f"{user.get('fname', '')} {user.get('lname', '')}"
            print(f"  User {user_name}: {sorted(credentials)}")
            
            # Add user to appropriate call type lists
            for call_type in credentials:
                if call_type in call_type_users:
                    call_type_users[call_type].append(user_id)
    
    # Show summary
    print(f"\nCredential summary:")
    for call_type, users in call_type_users.items():
        if users:
            print(f"  {call_type}: {len(users)} users")
    
    return call_type_users


def test_credential_aware_optimizer():
    """Test the optimizer with proper credential matching"""
    
    client = SpinSchedulesAPIClient()
    
    # Get users organized by credentials
    credentialed_users = get_credentialed_users_by_call_type(client)
    
    # Find a call type with enough users for testing
    viable_call_types = []
    for call_type, users in credentialed_users.items():
        if len(users) >= 2:  # Need at least 2 users for a multi-day test
            viable_call_types.append(call_type)
    
    if not viable_call_types:
        print("No call types have enough credentialed users for testing")
        return None
    
    # Pick the first viable call type for testing
    test_call_type = viable_call_types[0]
    test_users = credentialed_users[test_call_type][:5]  # Use first 5 users
    
    print(f"\nTesting with call type: {test_call_type}")
    print(f"Using {len(test_users)} credentialed users")
    
    # Create a modified optimizer that uses only these credentialed users
    optimizer = CallScheduleOptimizer(client)
    
    # Override the eligible users method to return only credentialed users
    optimizer._get_eligible_users = lambda: test_users
    
    # Test with a simple date range
    start_date = "2030-01-01"
    end_date = "2030-01-03"  # 3 days
    
    # Create relaxed constraints for testing
    test_constraints = SchedulingConstraints(
        min_days_between_calls=1,  # 1 day minimum
        max_calls_per_month=10,
        enforce_weekend_rules=False  # Disable weekend rules for initial test
    )
    
    # Run optimization
    result = optimizer.optimize_schedule(
        start_date=start_date,
        end_date=end_date,
        call_types=[test_call_type],  # Only test one call type
        constraints=test_constraints
    )
    
    if result.success:
        print(f"\n✓ SUCCESS! Generated {len(result.assignments)} assignments")
        print(f"Solve time: {result.solve_time_seconds:.2f} seconds")
        
        print(f"\nSchedule for {test_call_type}:")
        for assignment in result.assignments:
            print(f"  {assignment['date']}: {assignment['user_name']}")
        
        print(f"\nStatistics:")
        for key, value in result.statistics.items():
            print(f"  {key}: {value}")
            
        return result
    else:
        print(f"✗ FAILED with credentialed users")
        for violation in result.violations:
            print(f"  - {violation}")
        return None


if __name__ == "__main__":
    test_credential_aware_optimizer()