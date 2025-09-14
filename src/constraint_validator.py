"""
Constraint validation system for call scheduling
Handles availability conflicts, workload limits, and scheduling rules
"""

from datetime import date, timedelta
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass
import json

@dataclass
class SchedulingConstraints:
    """Global scheduling constraints"""
    max_calls_per_month: int = 10
    min_days_between_calls: int = 2
    max_consecutive_calls: int = 2
    weekend_call_weight: float = 1.5  # Weekend calls count as 1.5x regular calls
    
    # User group constraints
    user_group_max_calls: Dict[str, int] = None
    
    def __post_init__(self):
        if self.user_group_max_calls is None:
            self.user_group_max_calls = {
                'Full Time': 10,
                'Part Time': 6, 
                'Part Time + Self Select': 6,
                'PRN (Call Only)': 12
            }

@dataclass
class UserAvailability:
    """User availability and constraints"""
    user_id: int
    user_name: str
    user_group: str
    fte: float  # 0.0 to 1.0
    
    # Unavailable dates
    vacation_dates: Set[date] = None
    no_call_dates: Set[date] = None
    part_time_dates: Set[date] = None  # Dates marked as part-time work
    
    # Current workload (for fairness calculation)
    current_call_count: int = 0
    
    def __post_init__(self):
        if self.vacation_dates is None:
            self.vacation_dates = set()
        if self.no_call_dates is None:
            self.no_call_dates = set()
        if self.part_time_dates is None:
            self.part_time_dates = set()
    
    def is_available(self, target_date: date) -> bool:
        """Check if user is available on a specific date"""
        return (target_date not in self.vacation_dates and 
                target_date not in self.no_call_dates)
    
    def get_max_calls_for_period(self, constraints: SchedulingConstraints) -> int:
        """Calculate max calls based on FTE and user group"""
        base_max = constraints.user_group_max_calls.get(self.user_group, 
                                                       constraints.max_calls_per_month)
        return int(base_max * self.fte)

class ConstraintValidator:
    """Validates scheduling constraints"""
    
    def __init__(self, constraints: SchedulingConstraints):
        self.constraints = constraints
    
    def validate_user_availability(self, user_availability: UserAvailability, 
                                 assignment_date: date) -> Tuple[bool, str]:
        """
        Validate if a user is available for assignment on a specific date
        
        Args:
            user_availability: User's availability data
            assignment_date: Date to check
            
        Returns:
            Tuple of (is_valid, reason)
        """
        if assignment_date in user_availability.vacation_dates:
            return False, f"User on vacation on {assignment_date}"
        
        if assignment_date in user_availability.no_call_dates:
            return False, f"User requested no call on {assignment_date}"
        
        return True, "Available"
    
    def validate_call_frequency(self, user_availability: UserAvailability,
                              existing_assignments: List[date],
                              new_assignment_date: date) -> Tuple[bool, str]:
        """
        Validate call frequency constraints
        
        Args:
            user_availability: User's availability data
            existing_assignments: List of dates user already has assignments
            new_assignment_date: Date of proposed new assignment
            
        Returns:
            Tuple of (is_valid, reason)
        """
        # Check maximum calls limit
        max_calls = user_availability.get_max_calls_for_period(self.constraints)
        if len(existing_assignments) >= max_calls:
            return False, f"User already has {len(existing_assignments)} calls (max: {max_calls})"
        
        # Check minimum days between calls
        for existing_date in existing_assignments:
            days_diff = abs((new_assignment_date - existing_date).days)
            if days_diff < self.constraints.min_days_between_calls:
                return False, f"Too close to existing call on {existing_date} ({days_diff} days)"
        
        # Check consecutive calls limit
        consecutive_count = self._count_consecutive_calls(existing_assignments, new_assignment_date)
        if consecutive_count > self.constraints.max_consecutive_calls:
            return False, f"Would exceed max consecutive calls ({self.constraints.max_consecutive_calls})"
        
        return True, "Valid frequency"
    
    def _count_consecutive_calls(self, existing_assignments: List[date], 
                               new_date: date) -> int:
        """Count consecutive calls including the new assignment"""
        all_dates = sorted(existing_assignments + [new_date])
        
        max_consecutive = 1
        current_consecutive = 1
        
        for i in range(1, len(all_dates)):
            if (all_dates[i] - all_dates[i-1]).days == 1:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 1
        
        return max_consecutive
    
    def validate_workload_fairness(self, all_user_assignments: Dict[int, List[date]],
                                 user_availabilities: Dict[int, UserAvailability]) -> List[str]:
        """
        Validate that call distribution is fair across users
        
        Args:
            all_user_assignments: Dict of user_id -> list of assigned dates
            user_availabilities: Dict of user_id -> UserAvailability
            
        Returns:
            List of fairness warnings
        """
        warnings = []
        
        # Calculate call counts adjusted for FTE
        adjusted_call_counts = {}
        for user_id, assignments in all_user_assignments.items():
            if user_id in user_availabilities:
                user_avail = user_availabilities[user_id]
                # Adjust call count by FTE (lower FTE should have proportionally fewer calls)
                adjusted_count = len(assignments) / user_avail.fte if user_avail.fte > 0 else len(assignments)
                adjusted_call_counts[user_id] = adjusted_count
        
        if len(adjusted_call_counts) < 2:
            return warnings
        
        min_calls = min(adjusted_call_counts.values())
        max_calls = max(adjusted_call_counts.values())
        call_difference = max_calls - min_calls
        
        # Check if distribution is unfair
        if call_difference > 3:  # Threshold for unfairness
            warnings.append(f"Uneven call distribution: {call_difference:.1f} call difference between users")
            
            # Identify users with too many/few calls
            avg_calls = sum(adjusted_call_counts.values()) / len(adjusted_call_counts)
            for user_id, adj_count in adjusted_call_counts.items():
                if user_id in user_availabilities:
                    user_name = user_availabilities[user_id].user_name
                    actual_count = len(all_user_assignments.get(user_id, []))
                    if adj_count > avg_calls + 2:
                        warnings.append(f"  {user_name}: {actual_count} calls (high)")
                    elif adj_count < avg_calls - 2:
                        warnings.append(f"  {user_name}: {actual_count} calls (low)")
        
        return warnings

class AvailabilityLoader:
    """Load user availability data from API"""
    
    def __init__(self, api_client):
        self.api_client = api_client
    
    def load_user_availability(self, start_date: str, end_date: str) -> Dict[int, UserAvailability]:
        """
        Load user availability from API
        
        Args:
            start_date: Start date for availability check (YYYY-MM-DD)
            end_date: End date for availability check (YYYY-MM-DD)
            
        Returns:
            Dict of user_id -> UserAvailability
        """
        # Get user roster
        users = self.api_client.get_user_roster()
        
        # Filter to eligible user groups
        eligible_groups = {'Full Time', 'Part Time', 'Part Time + Self Select', 'PRN (Call Only)'}
        
        user_availabilities = {}
        
        for user in users:
            user_id = int(user['userid'])
            user_group = user['coregroup']
            
            # Skip users not in eligible groups
            if user_group not in eligible_groups:
                continue
            
            user_name = f"{user['fname']} {user['lname']}"
            
            # Get FTE data
            fte = self._get_user_fte(user_id)
            
            # Create user availability object
            user_avail = UserAvailability(
                user_id=user_id,
                user_name=user_name,
                user_group=user_group,
                fte=fte
            )
            
            # Load vacation dates (schedule 384)
            vacation_assignments = self.api_client.get_assignments_by_schedule(
                [384], start_date, end_date
            )
            for assignment in vacation_assignments:
                if int(assignment['uId']) == user_id:
                    vacation_date = date.fromisoformat(assignment['date'])
                    user_avail.vacation_dates.add(vacation_date)
            
            # Load no-call request dates (schedule 385)
            no_call_assignments = self.api_client.get_assignments_by_schedule(
                [385], start_date, end_date
            )
            for assignment in no_call_assignments:
                if int(assignment['uId']) == user_id:
                    no_call_date = date.fromisoformat(assignment['date'])
                    user_avail.no_call_dates.add(no_call_date)
            
            # Load part-time dates (schedule 386)
            part_time_assignments = self.api_client.get_assignments_by_schedule(
                [386], start_date, end_date
            )
            for assignment in part_time_assignments:
                if int(assignment['uId']) == user_id:
                    part_time_date = date.fromisoformat(assignment['date'])
                    user_avail.part_time_dates.add(part_time_date)
            
            user_availabilities[user_id] = user_avail
        
        return user_availabilities
    
    def _get_user_fte(self, user_id: int) -> float:
        """Get FTE value for a user"""
        try:
            response = self.api_client._make_request(
                'GET', 
                '/External/get_users_editableFieldValue',
                params={'userId': user_id, 'fieldName': 'FTE'}
            )
            
            if response.get('success'):
                fte_value = response.get('value')
                if fte_value is not None:
                    # Handle both percentage (100) and decimal (1.0) formats
                    fte_float = float(fte_value)
                    if fte_float > 1.0:  # Assume percentage format
                        return fte_float / 100.0
                    else:
                        return fte_float
            
            # Default to 1.0 if FTE not found
            return 1.0
            
        except Exception:
            # Default to 1.0 if error
            return 1.0

def get_default_constraints() -> SchedulingConstraints:
    """Get default scheduling constraints"""
    return SchedulingConstraints()