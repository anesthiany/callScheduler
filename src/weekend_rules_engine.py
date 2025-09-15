"""
Weekend sandwich rules engine for call scheduling
Handles complex pairing logic for weekend call assignments
"""

from datetime import date, timedelta
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass


@dataclass
class WeekendRule:
    """Represents a weekend sandwich rule"""
    trigger_call: str  # The call that triggers the rule
    trigger_day: str   # 'friday' or 'saturday'
    result_call: str   # The call that should be assigned
    result_day: str    # 'saturday' or 'sunday'


class WeekendRulesEngine:
    """Manages weekend sandwich rules for call scheduling"""
    
    def __init__(self):
        self.rules = self._initialize_rules()
    
    def _initialize_rules(self) -> List[WeekendRule]:
        """Initialize all weekend sandwich rules"""
        rules = []
        
        # LP series rules
        rules.extend([
            WeekendRule('LP7', 'friday', 'LPG', 'saturday'),
            WeekendRule('LPG', 'friday', 'LPO', 'sunday'),
            WeekendRule('LPO', 'friday', 'LPG', 'sunday'),
        ])
        
        # MCL series rules
        rules.extend([
            WeekendRule('MCL7', 'friday', 'MCLG', 'saturday'),
            WeekendRule('MCLG', 'friday', 'MCLO', 'sunday'),
            WeekendRule('MCLO', 'friday', 'MCLG', 'sunday'),
        ])
        
        # THD series rules
        rules.extend([
            WeekendRule('THDN7', 'friday', 'THDNG', 'saturday'),
            WeekendRule('THDNG', 'friday', 'THDNO', 'sunday'),
            WeekendRule('THDNO', 'friday', 'THDNG', 'sunday'),
        ])
        
        # THR series rules
        rules.extend([
            WeekendRule('THRW7', 'friday', 'THRWG', 'saturday'),
            WeekendRule('THRWG', 'friday', 'THROB', 'sunday'),
            WeekendRule('THROB', 'friday', 'THRWG', 'sunday'),
        ])
        
        # CMC series rules
        rules.extend([
            WeekendRule('CMCG', 'friday', 'CMCO', 'sunday'),
            WeekendRule('CMCO', 'friday', 'CMCG', 'sunday'),
        ])
        
        # NE series rules
        rules.extend([
            WeekendRule('NE', 'saturday', 'NE', 'sunday'),
        ])
        
        # MCK series rules
        rules.extend([
            WeekendRule('MCKT_D', 'saturday', 'MCKG_D', 'sunday'),
            WeekendRule('MCKG_D', 'saturday', 'MCKT_D', 'sunday'),
        ])
        
        return rules
    
    def get_weekend_assignment(self, call_type: str, day: str) -> Optional[str]:
        """
        Get the weekend assignment for a given call type and day
        
        Args:
            call_type: The call type (e.g., 'LP7', 'CMCG')
            day: The day of the week ('friday' or 'saturday')
            
        Returns:
            The call type that should be assigned on the weekend, or None
        """
        for rule in self.rules:
            if rule.trigger_call == call_type and rule.trigger_day == day:
                return rule.result_call
        return None
    
    def get_all_weekend_pairs(self, call_type: str, day: str) -> List[Tuple[str, str]]:
        """
        Get all weekend assignments that should be made for a call type
        
        Args:
            call_type: The call type
            day: The trigger day
            
        Returns:
            List of (day, call_type) pairs for weekend assignments
        """
        pairs = []
        for rule in self.rules:
            if rule.trigger_call == call_type and rule.trigger_day == day:
                pairs.append((rule.result_day, rule.result_call))
        return pairs
    
    def validate_weekend_assignment(self, assignments: Dict, date_obj: date, 
                                   user_id: int, call_type: str) -> List[str]:
        """
        Validate if a weekend assignment follows the sandwich rules
        
        Args:
            assignments: Dictionary of existing assignments
            date_obj: Date of the assignment
            user_id: User being assigned
            call_type: Call type being assigned
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        weekday = date_obj.weekday()  # 0=Monday, 6=Sunday
        
        # Check if this is a weekend assignment that should have a trigger
        if weekday in [5, 6]:  # Saturday or Sunday
            day_name = 'saturday' if weekday == 5 else 'sunday'
            
            # Look for rules that result in this assignment
            triggering_rules = [r for r in self.rules 
                              if r.result_call == call_type and r.result_day == day_name]
            
            if triggering_rules:
                # Check if the user has the triggering assignment
                found_trigger = False
                for rule in triggering_rules:
                    trigger_day_offset = -1 if rule.trigger_day == 'friday' and weekday == 5 else -2
                    if rule.trigger_day == 'friday' and weekday == 6:
                        trigger_day_offset = -2
                    elif rule.trigger_day == 'saturday' and weekday == 6:
                        trigger_day_offset = -1
                    
                    trigger_date = date_obj + timedelta(days=trigger_day_offset)
                    if (trigger_date in assignments and 
                        user_id in assignments[trigger_date] and
                        assignments[trigger_date][user_id] == rule.trigger_call):
                        found_trigger = True
                        break
                
                if not found_trigger:
                    trigger_calls = [r.trigger_call for r in triggering_rules]
                    errors.append(
                        f"Weekend assignment {call_type} on {day_name} should be "
                        f"paired with {trigger_calls} assignment"
                    )
        
        return errors