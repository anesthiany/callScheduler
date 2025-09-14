"""
Weekend sandwich rules engine for call scheduling
Handles complex pairing logic for weekend call assignments
"""

from datetime import date, timedelta
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass

@dataclass
class WeekendAssignment:
    """Represents a weekend call assignment"""
    user_id: int
    date: date
    call_type: str
    is_required_pair: bool = False  # True if this is automatically assigned due to sandwich rule

class WeekendRulesEngine:
    """Handles weekend sandwich pairing rules"""
    
    def __init__(self):
        # Define the sandwich pairing rules
        self.friday_to_weekend_rules = {
            # Pattern 1: 7-day calls (Friday night) get G-day (Saturday day)
            'LP7': 'LPG',
            'MCL7': 'MCLG', 
            'THDN7': 'THDNG',
            'THRW7': 'THRWG',
            
            # Pattern 2: G-day calls (Friday day) get O-day (Sunday day)
            'LPG': 'LPO',
            'MCLG': 'MCLO',
            'THDNG': 'THDNO',
            'THRWG': 'THROB',
            
            # Pattern 3: O-day calls (Friday day) get G-day (Sunday day)
            'LPO': 'LPG',
            'MCLO': 'MCLG',
            'THDNO': 'THDNG',
            'THROB': 'THRWG',
            
            # Special pairs
            'CMCG': 'CMCO',
            'CMCO': 'CMCG'
        }
        
        # Weekend consecutive pairs (same person both days)
        self.weekend_consecutive_rules = {
            'NE': ['NE'],  # NE Saturday gets NE Sunday
            'MCKT_D': 'MCKG_D',  # MCKT_D Saturday gets MCKG_D Sunday
            'MCKG_D': 'MCKT_D'   # MCKG_D Saturday gets MCKT_D Sunday
        }
    
    def get_friday_pairing(self, friday_call_type: str) -> Optional[Tuple[str, str]]:
        """
        Get the required weekend pairing for a Friday call
        
        Args:
            friday_call_type: The call type assigned on Friday
            
        Returns:
            Tuple of (weekend_day, call_type) or None if no pairing required
            weekend_day is 'saturday' or 'sunday'
        """
        if friday_call_type in self.friday_to_weekend_rules:
            weekend_call_type = self.friday_to_weekend_rules[friday_call_type]
            
            # Determine which day based on the pattern
            if friday_call_type.endswith('7'):  # Night calls get Saturday
                return ('saturday', weekend_call_type)
            elif friday_call_type in ['CMCG', 'CMCO']:  # Special Sunday pairs
                return ('sunday', weekend_call_type)
            else:  # Day calls get Sunday
                return ('sunday', weekend_call_type)
        
        return None
    
    def get_weekend_consecutive_pairing(self, saturday_call_type: str) -> Optional[str]:
        """
        Get the required Sunday pairing for a Saturday call
        
        Args:
            saturday_call_type: The call type assigned on Saturday
            
        Returns:
            Sunday call type or None if no consecutive pairing required
        """
        if saturday_call_type in self.weekend_consecutive_rules:
            sunday_type = self.weekend_consecutive_rules[saturday_call_type]
            if isinstance(sunday_type, list):
                return sunday_type[0]  # Same call type
            else:
                return sunday_type
        
        return None
    
    def apply_sandwich_rules(self, assignments: List[WeekendAssignment], 
                           unavailable_users: Set[int]) -> List[WeekendAssignment]:
        """
        Apply weekend sandwich rules to existing assignments
        
        Args:
            assignments: List of current weekend assignments
            unavailable_users: Set of user IDs who are unavailable (vacation, no-call requests)
            
        Returns:
            Updated list of assignments with sandwich rules applied
        """
        updated_assignments = assignments.copy()
        
        # Group assignments by date for easy lookup
        assignments_by_date = {}
        for assignment in assignments:
            date_key = assignment.date
            if date_key not in assignments_by_date:
                assignments_by_date[date_key] = []
            assignments_by_date[date_key].append(assignment)
        
        # Apply Friday → Weekend rules
        for assignment in assignments:
            # Skip if user is unavailable
            if assignment.user_id in unavailable_users:
                continue
                
            # Check if this is a Friday assignment that triggers a sandwich rule
            if assignment.date.weekday() == 4:  # Friday = 4
                pairing = self.get_friday_pairing(assignment.call_type)
                
                if pairing:
                    weekend_day, weekend_call_type = pairing
                    
                    # Calculate the target weekend date
                    if weekend_day == 'saturday':
                        target_date = assignment.date + timedelta(days=1)
                    else:  # sunday
                        target_date = assignment.date + timedelta(days=2)
                    
                    # Check if this user is already assigned that weekend day
                    existing_weekend_assignment = None
                    if target_date in assignments_by_date:
                        for weekend_assign in assignments_by_date[target_date]:
                            if weekend_assign.user_id == assignment.user_id:
                                existing_weekend_assignment = weekend_assign
                                break
                    
                    # If no existing assignment, create the paired assignment
                    if not existing_weekend_assignment:
                        new_assignment = WeekendAssignment(
                            user_id=assignment.user_id,
                            date=target_date,
                            call_type=weekend_call_type,
                            is_required_pair=True
                        )
                        updated_assignments.append(new_assignment)
                        
                        # Add to lookup dict
                        if target_date not in assignments_by_date:
                            assignments_by_date[target_date] = []
                        assignments_by_date[target_date].append(new_assignment)
        
        # Apply Saturday → Sunday consecutive rules
        for assignment in assignments:
            # Skip if user is unavailable
            if assignment.user_id in unavailable_users:
                continue
                
            # Check if this is a Saturday assignment that requires Sunday pairing
            if assignment.date.weekday() == 5:  # Saturday = 5
                sunday_call_type = self.get_weekend_consecutive_pairing(assignment.call_type)
                
                if sunday_call_type:
                    sunday_date = assignment.date + timedelta(days=1)
                    
                    # Check if this user is already assigned Sunday
                    existing_sunday_assignment = None
                    if sunday_date in assignments_by_date:
                        for sunday_assign in assignments_by_date[sunday_date]:
                            if sunday_assign.user_id == assignment.user_id:
                                existing_sunday_assignment = sunday_assign
                                break
                    
                    # If no existing assignment, create the paired assignment
                    if not existing_sunday_assignment:
                        new_assignment = WeekendAssignment(
                            user_id=assignment.user_id,
                            date=sunday_date,
                            call_type=sunday_call_type,
                            is_required_pair=True
                        )
                        updated_assignments.append(new_assignment)
        
        return updated_assignments
    
    def validate_sandwich_compliance(self, assignments: List[WeekendAssignment]) -> List[str]:
        """
        Validate that assignments comply with sandwich rules
        
        Args:
            assignments: List of weekend assignments to validate
            
        Returns:
            List of violation messages (empty if compliant)
        """
        violations = []
        
        # Group assignments by user and date
        user_assignments = {}
        for assignment in assignments:
            user_id = assignment.user_id
            if user_id not in user_assignments:
                user_assignments[user_id] = {}
            user_assignments[user_id][assignment.date] = assignment.call_type
        
        # Check each user's assignments for sandwich rule compliance
        for user_id, user_dates in user_assignments.items():
            dates = sorted(user_dates.keys())
            
            for date in dates:
                call_type = user_dates[date]
                
                # Check Friday → Weekend rules
                if date.weekday() == 4:  # Friday
                    pairing = self.get_friday_pairing(call_type)
                    if pairing:
                        weekend_day, expected_call_type = pairing
                        target_date = date + timedelta(days=1 if weekend_day == 'saturday' else 2)
                        
                        if target_date not in user_dates:
                            violations.append(
                                f"User {user_id}: Friday {call_type} on {date} requires "
                                f"{expected_call_type} on {target_date}, but no assignment found"
                            )
                        elif user_dates[target_date] != expected_call_type:
                            violations.append(
                                f"User {user_id}: Friday {call_type} on {date} requires "
                                f"{expected_call_type} on {target_date}, but assigned "
                                f"{user_dates[target_date]}"
                            )
                
                # Check Saturday → Sunday consecutive rules
                if date.weekday() == 5:  # Saturday
                    expected_sunday_type = self.get_weekend_consecutive_pairing(call_type)
                    if expected_sunday_type:
                        sunday_date = date + timedelta(days=1)
                        
                        if sunday_date not in user_dates:
                            violations.append(
                                f"User {user_id}: Saturday {call_type} on {date} requires "
                                f"{expected_sunday_type} on {sunday_date}, but no assignment found"
                            )
                        elif user_dates[sunday_date] != expected_sunday_type:
                            violations.append(
                                f"User {user_id}: Saturday {call_type} on {date} requires "
                                f"{expected_sunday_type} on {sunday_date}, but assigned "
                                f"{user_dates[sunday_date]}"
                            )
        
        return violations

def get_weekend_rules_engine() -> WeekendRulesEngine:
    """Get an instance of the weekend rules engine"""
    return WeekendRulesEngine()