"""
Constraint validation system for call scheduling
Handles availability conflicts, workload limits, and scheduling rules
"""

from datetime import date, timedelta
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, field
from src.api_client import SpinSchedulesAPIClient


@dataclass
class SchedulingConstraints:
    """Configuration for scheduling constraints"""
    min_days_between_calls: int = 2
    max_calls_per_month: int = 8
    max_consecutive_days: int = 1
    enforce_weekend_rules: bool = True
    allow_holiday_assignments: bool = True
    fairness_weight: float = 1.0


@dataclass
class UserAvailability:
    """Availability information for a user"""
    user_id: int
    user_name: str
    fte: float = 1.0
    vacation_dates: Set[date] = field(default_factory=set)
    no_call_dates: Set[date] = field(default_factory=set)
    part_time_dates: Set[date] = field(default_factory=set)
    existing_assignments: Dict[date, str] = field(default_factory=dict)
    
    def is_available(self, date_obj: date) -> bool:
        """Check if user is available on a specific date"""
        return (date_obj not in self.vacation_dates and 
                date_obj not in self.no_call_dates and
                date_obj not in self.part_time_dates)


class ConstraintValidator:
    """Validates scheduling constraints and manages user availability"""
    
    def __init__(self, api_client: SpinSchedulesAPIClient):
        self.api_client = api_client
        
        # Schedule IDs from your system
        self.CALL_SCHEDULE_ID = 383
        self.VACATION_SCHEDULE_ID = 384
        self.NO_CALL_SCHEDULE_ID = 385
        self.PART_TIME_SCHEDULE_ID = 386
    
    def load_user_availabilities(self, user_ids: List[int], 
                                start_date: str, end_date: str) -> Dict[int, UserAvailability]:
        """
        Load availability data for users from the API
        
        Args:
            user_ids: List of user IDs to load
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            
        Returns:
            Dictionary mapping user_id to UserAvailability
        """
        user_availabilities = {}
        
        print(f"Loading availability data for {len(user_ids)} users...")
        
        for user_id in user_ids:
            user_avail = UserAvailability(
                user_id=user_id,
                user_name=self._get_user_name(user_id),
                fte=self._get_user_fte(user_id)
            )
            
            # Load vacation dates (schedule 384)
            try:
                vacation_assignments = self.api_client.get_assignments_by_schedule(
                    [self.VACATION_SCHEDULE_ID], start_date, end_date
                )
                for assignment in vacation_assignments:
                    if int(assignment['uId']) == user_id:
                        vacation_date = date.fromisoformat(assignment['date'])
                        user_avail.vacation_dates.add(vacation_date)
            except Exception as e:
                print(f"Warning: Could not load vacation data for user {user_id}: {e}")
            
            # Load no-call request dates (schedule 385)
            try:
                no_call_assignments = self.api_client.get_assignments_by_schedule(
                    [self.NO_CALL_SCHEDULE_ID], start_date, end_date
                )
                for assignment in no_call_assignments:
                    if int(assignment['uId']) == user_id:
                        no_call_date = date.fromisoformat(assignment['date'])
                        user_avail.no_call_dates.add(no_call_date)
            except Exception as e:
                print(f"Warning: Could not load no-call data for user {user_id}: {e}")
            
            # Load part-time dates (schedule 386)
            try:
                part_time_assignments = self.api_client.get_assignments_by_schedule(
                    [self.PART_TIME_SCHEDULE_ID], start_date, end_date
                )
                for assignment in part_time_assignments:
                    if int(assignment['uId']) == user_id:
                        part_time_date = date.fromisoformat(assignment['date'])
                        user_avail.part_time_dates.add(part_time_date)
            except Exception as e:
                print(f"Warning: Could not load part-time data for user {user_id}: {e}")
            
            # Load existing call assignments (schedule 383)
            try:
                call_assignments = self.api_client.get_assignments_by_schedule(
                    [self.CALL_SCHEDULE_ID], start_date, end_date
                )
                for assignment in call_assignments:
                    if int(assignment['uId']) == user_id:
                        call_date = date.fromisoformat(assignment['date'])
                        call_type = assignment.get('aName', 'Unknown')
                        user_avail.existing_assignments[call_date] = call_type
            except Exception as e:
                print(f"Warning: Could not load existing assignments for user {user_id}: {e}")
            
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
    
    def _get_user_name(self, user_id: int) -> str:
        """Get user name from ID"""
        try:
            users = self.api_client.get_user_roster()
            for user in users:
                if int(user['userid']) == user_id:
                    fname = user.get('fname', '')
                    lname = user.get('lname', '')
                    return f"{fname} {lname}".strip()
            return f"User {user_id}"
        except:
            return f"User {user_id}"
    
    def validate_assignment(self, user_id: int, date_obj: date, call_type: str,
                           user_availabilities: Dict[int, UserAvailability],
                           existing_assignments: Dict[date, Dict[int, str]],
                           constraints: SchedulingConstraints) -> List[str]:
        """
        Validate if an assignment is allowed
        
        Args:
            user_id: User being assigned
            date_obj: Date of assignment
            call_type: Type of call being assigned
            user_availabilities: User availability data
            existing_assignments: Dictionary of existing assignments
            constraints: Scheduling constraints
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        user_avail = user_availabilities.get(user_id)
        
        if not user_avail:
            errors.append(f"No availability data for user {user_id}")
            return errors
        
        # Check basic availability
        if not user_avail.is_available(date_obj):
            if date_obj in user_avail.vacation_dates:
                errors.append(f"User {user_avail.user_name} has vacation on {date_obj}")
            if date_obj in user_avail.no_call_dates:
                errors.append(f"User {user_avail.user_name} has no-call request on {date_obj}")
            if date_obj in user_avail.part_time_dates:
                errors.append(f"User {user_avail.user_name} is part-time on {date_obj}")
        
        # Check minimum days between calls
        if constraints.min_days_between_calls > 0:
            for i in range(1, constraints.min_days_between_calls + 1):
                # Check previous days
                prev_date = date_obj - timedelta(days=i)
                if (prev_date in existing_assignments and 
                    user_id in existing_assignments[prev_date]):
                    errors.append(
                        f"User {user_avail.user_name} has assignment on {prev_date}, "
                        f"violates minimum {constraints.min_days_between_calls} days between calls"
                    )
                
                # Check future days
                future_date = date_obj + timedelta(days=i)
                if (future_date in existing_assignments and 
                    user_id in existing_assignments[future_date]):
                    errors.append(
                        f"User {user_avail.user_name} has assignment on {future_date}, "
                        f"violates minimum {constraints.min_days_between_calls} days between calls"
                    )
        
        # Check if user already has assignment on this date
        if (date_obj in existing_assignments and 
            user_id in existing_assignments[date_obj]):
            existing_call = existing_assignments[date_obj][user_id]
            errors.append(
                f"User {user_avail.user_name} already assigned to {existing_call} on {date_obj}"
            )
        
        return errors
    
    def calculate_max_calls_for_period(self, user_id: int, period_days: int,
                                      total_call_slots: int, total_users: int,
                                      user_availabilities: Dict[int, UserAvailability]) -> int:
        """
        Calculate maximum calls for a user based on FTE and fairness
        
        Args:
            user_id: User ID
            period_days: Number of days in scheduling period
            total_call_slots: Total number of call slots to fill
            total_users: Total number of eligible users
            user_availabilities: User availability data
            
        Returns:
            Maximum number of calls for this user
        """
        user_avail = user_availabilities.get(user_id)
        if not user_avail:
            return 0
        
        # Calculate fair share based on FTE
        avg_calls = total_call_slots / total_users if total_users > 0 else 0
        fte_adjusted_calls = avg_calls * user_avail.fte
        
        # Add 20% buffer to allow for optimization flexibility
        max_calls = int(fte_adjusted_calls * 1.2)
        
        # Ensure at least 1 call if FTE > 0
        if user_avail.fte > 0 and max_calls < 1:
            max_calls = 1
        
        return max_calls


def get_default_constraints() -> SchedulingConstraints:
    """Get default scheduling constraints"""
    return SchedulingConstraints()