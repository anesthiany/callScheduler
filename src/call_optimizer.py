"""
OR-Tools optimizer for anesthesia call scheduling
Generates optimal call schedules based on constraints and weekend rules
"""

from ortools.sat.python import cp_model
from datetime import date, timedelta
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass
import json
from collections import defaultdict

from src.api_client import SpinSchedulesAPIClient
from src.constraint_validator import ConstraintValidator, SchedulingConstraints
from src.weekend_rules_engine import WeekendRulesEngine


@dataclass
class ScheduleResult:
    """Result of optimization run"""
    success: bool
    assignments: List[Dict]  # List of {date, user_id, call_type, user_name}
    statistics: Dict
    violations: List[str]
    solve_time_seconds: float


class CallScheduleOptimizer:
    """OR-Tools based call schedule optimizer"""
    
    def __init__(self, api_client: SpinSchedulesAPIClient):
        self.api_client = api_client
        self.constraint_validator = ConstraintValidator(api_client)
        self.weekend_rules = WeekendRulesEngine()
        
        # Core schedule IDs from your system
        self.CALL_SCHEDULE_ID = 383
        self.VACATION_SCHEDULE_ID = 384
        self.NO_CALL_SCHEDULE_ID = 385
        self.PART_TIME_SCHEDULE_ID = 386
        
        # Employment group IDs
        self.EMPLOYMENT_GROUPS = [1000, 1020, 11327, 1030]  # Full Time, Part Time, Part Time + Self Select, PRN
        
    def optimize_schedule(self, start_date: str, end_date: str, 
                         call_types: List[str] = None,
                         constraints: SchedulingConstraints = None) -> ScheduleResult:
        """
        Generate optimal call schedule for given date range
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD) 
            call_types: List of call types to schedule (e.g., ['CMCG', 'CMCO', 'LPG'])
            constraints: Custom constraints (uses defaults if None)
            
        Returns:
            ScheduleResult with assignments and statistics
        """
        print(f"Optimizing call schedule from {start_date} to {end_date}")
        
        # Set default call types if none provided
        if call_types is None:
            call_types = ['CMCG', 'CMCO', 'LPG', 'LPO', 'MCKC_N']
            
        # Use default constraints if none provided
        if constraints is None:
            constraints = SchedulingConstraints()
            
        # Get eligible users
        eligible_users = self._get_eligible_users()
        if not eligible_users:
            return ScheduleResult(False, [], {}, ["No eligible users found"], 0.0)
            
        print(f"Found {len(eligible_users)} eligible physicians")
        
        # Load user availabilities and constraints
        user_availabilities = self.constraint_validator.load_user_availabilities(
            eligible_users, start_date, end_date
        )
        
        # Get call type IDs from API
        call_type_mapping = self._get_call_type_mapping(start_date, end_date)
        
        # Generate date range
        dates = self._generate_date_range(start_date, end_date)
        
        # Create optimization model
        model = cp_model.CpModel()
        
        # Decision variables: assignment[user_id][date][call_type] = 1 if assigned
        assignments = {}
        for user_id in eligible_users:
            assignments[user_id] = {}
            for date_obj in dates:
                assignments[user_id][date_obj] = {}
                for call_type in call_types:
                    assignments[user_id][date_obj][call_type] = model.NewBoolVar(
                        f'assign_{user_id}_{date_obj}_{call_type}'
                    )
        
        # Constraint 1: Each call type must be covered exactly once per day
        for date_obj in dates:
            for call_type in call_types:
                model.Add(
                    sum(assignments[user_id][date_obj][call_type] 
                        for user_id in eligible_users) == 1
                )
        
        # Constraint 2: No user can have multiple assignments on same day
        for user_id in eligible_users:
            for date_obj in dates:
                model.Add(
                    sum(assignments[user_id][date_obj][call_type] 
                        for call_type in call_types) <= 1
                )
        
        # Constraint 3: Respect availability (vacation, no-call requests)
        for user_id in eligible_users:
            user_avail = user_availabilities.get(user_id)
            if user_avail:
                for date_obj in dates:
                    if (date_obj in user_avail.vacation_dates or 
                        date_obj in user_avail.no_call_dates):
                        # User not available on this date
                        for call_type in call_types:
                            model.Add(assignments[user_id][date_obj][call_type] == 0)
        
        # Constraint 4: Minimum days between calls
        if constraints.min_days_between_calls > 0:
            for user_id in eligible_users:
                for i, date_obj in enumerate(dates[:-constraints.min_days_between_calls]):
                    # If assigned on date_obj, cannot be assigned for next min_days_between_calls days
                    for j in range(1, constraints.min_days_between_calls + 1):
                        if i + j < len(dates):
                            future_date = dates[i + j]
                            for call_type1 in call_types:
                                for call_type2 in call_types:
                                    model.AddImplication(
                                        assignments[user_id][date_obj][call_type1],
                                        assignments[user_id][future_date][call_type2].Not()
                                    )
        
        # Constraint 5: Weekend sandwich rules
        self._add_weekend_sandwich_constraints(model, assignments, dates, call_types, eligible_users)
        
        # Constraint 6: FTE-based maximum calls per period
        self._add_fte_based_constraints(model, assignments, dates, call_types, 
                                       eligible_users, user_availabilities, constraints)
        
        # Objective: Minimize variance in call distribution (fairness)
        total_assignments_per_user = {}
        for user_id in eligible_users:
            total_assignments_per_user[user_id] = sum(
                assignments[user_id][date_obj][call_type]
                for date_obj in dates
                for call_type in call_types
            )
        
        # Add penalty for uneven distribution
        max_assignments = model.NewIntVar(0, len(dates) * len(call_types), 'max_assignments')
        min_assignments = model.NewIntVar(0, len(dates) * len(call_types), 'min_assignments')
        
        for user_id in eligible_users:
            model.AddMaxEquality(max_assignments, [total_assignments_per_user[uid] for uid in eligible_users])
            model.AddMinEquality(min_assignments, [total_assignments_per_user[uid] for uid in eligible_users])
        
        fairness_penalty = model.NewIntVar(0, len(dates) * len(call_types), 'fairness_penalty')
        model.Add(fairness_penalty == max_assignments - min_assignments)
        
        # Minimize unfairness
        model.Minimize(fairness_penalty)
        
        # Solve the model
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 300.0  # 5 minute timeout
        
        print("Starting optimization...")
        status = solver.Solve(model)
        solve_time = solver.WallTime()
        
        # Process results
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            print(f"Solution found in {solve_time:.2f} seconds")
            
            # Extract assignments
            result_assignments = []
            assignment_stats = defaultdict(int)
            
            for user_id in eligible_users:
                for date_obj in dates:
                    for call_type in call_types:
                        if solver.Value(assignments[user_id][date_obj][call_type]) == 1:
                            # Get user name
                            user_name = self._get_user_name(user_id)
                            
                            result_assignments.append({
                                'date': date_obj.strftime('%Y-%m-%d'),
                                'user_id': user_id,
                                'user_name': user_name,
                                'call_type': call_type,
                                'call_type_id': call_type_mapping.get(call_type, 0),
                                'weekday': date_obj.strftime('%A')
                            })
                            assignment_stats[user_id] += 1
            
            # Generate statistics
            statistics = {
                'total_assignments': len(result_assignments),
                'assignments_per_user': dict(assignment_stats),
                'date_range_days': len(dates),
                'call_types_scheduled': call_types,
                'fairness_score': solver.Value(fairness_penalty) if status == cp_model.OPTIMAL else None,
                'solve_status': 'OPTIMAL' if status == cp_model.OPTIMAL else 'FEASIBLE'
            }
            
            return ScheduleResult(
                success=True,
                assignments=result_assignments,
                statistics=statistics,
                violations=[],
                solve_time_seconds=solve_time
            )
            
        else:
            # No solution found
            print(f"No solution found. Status: {solver.StatusName(status)}")
            return ScheduleResult(
                success=False,
                assignments=[],
                statistics={},
                violations=[f"Optimization failed: {solver.StatusName(status)}"],
                solve_time_seconds=solve_time
            )
    
    def _get_eligible_users(self) -> List[int]:
        """Get list of eligible user IDs for call scheduling"""
        try:
            # Get only active users (includeInactive=False is the default)
            all_users = self.api_client.get_user_roster(include_inactive=False)
            eligible_users = []
            
            print("Filtering for active physicians with call credentials...")
            
            for user in all_users:
                # Check if user is a physician using the coregroup field
                if user.get('coregroup', '').lower() == 'physician':
                    user_id = int(user['userid'])
                    user_name = f"{user.get('fname', '')} {user.get('lname', '')}"
                    
                    # Check if they have call credentials
                    try:
                        response = self.api_client._make_request(
                            'GET', 
                            '/External/get_users_userGroups',
                            params={'userId': user_id}
                        )
                        
                        if response.get('success'):
                            groups = response.get('groups', [])
                            
                            # Check if they have any call credentials
                            has_call_creds = any(
                                'cred call:' in group.get('groupName', '').lower()
                                for group in groups
                            )
                            
                            if has_call_creds:
                                eligible_users.append(user_id)
                                print(f"  Added: {user_name} (ID: {user_id})")
                            
                    except Exception as e:
                        print(f"  Error checking credentials for {user_name}: {e}")
                        continue
            
            print(f"Found {len(eligible_users)} eligible physicians")
            return eligible_users
            
        except Exception as e:
            print(f"Error getting eligible users: {e}")
            return []
    
    def _get_call_type_mapping(self, start_date: str, end_date: str) -> Dict[str, int]:
        """Get mapping of call type names to IDs"""
        try:
            assign_codes = self.api_client.get_assign_codes_in_range(
                [self.CALL_SCHEDULE_ID], start_date, end_date
            )
            
            mapping = {}
            for code_info in assign_codes:
                if len(code_info) >= 2:
                    name = code_info[0]
                    code_id = int(code_info[1])
                    mapping[name] = code_id
            
            return mapping
            
        except Exception as e:
            print(f"Error getting call type mapping: {e}")
            return {}
    
    def _generate_date_range(self, start_date: str, end_date: str) -> List[date]:
        """Generate list of date objects in range"""
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        
        dates = []
        current = start
        while current <= end:
            dates.append(current)
            current += timedelta(days=1)
        
        return dates
    
    def _add_weekend_sandwich_constraints(self, model, assignments, dates, call_types, eligible_users):
        """Add weekend sandwich rule constraints"""
        date_to_index = {d: i for i, d in enumerate(dates)}
        
        for i, date_obj in enumerate(dates):
            weekday = date_obj.weekday()  # 0=Monday, 4=Friday, 5=Saturday, 6=Sunday
            
            # Friday rules (if Friday and not last day)
            if weekday == 4 and i < len(dates) - 2:  # Friday
                saturday = dates[i + 1] if i + 1 < len(dates) else None
                sunday = dates[i + 2] if i + 2 < len(dates) else None
                
                if saturday and sunday:
                    for user_id in eligible_users:
                        # Apply weekend sandwich rules using the rules engine
                        friday_assignments = [assignments[user_id][date_obj][ct] for ct in call_types]
                        
                        for call_type in call_types:
                            friday_var = assignments[user_id][date_obj][call_type]
                            
                            # Get weekend assignments for this call type
                            weekend_call_type = self.weekend_rules.get_weekend_assignment(call_type, 'friday')
                            if weekend_call_type and weekend_call_type in call_types:
                                if 'saturday' in weekend_call_type.lower():
                                    saturday_var = assignments[user_id][saturday][weekend_call_type]
                                    model.AddImplication(friday_var, saturday_var)
                                elif 'sunday' in weekend_call_type.lower():
                                    sunday_var = assignments[user_id][sunday][weekend_call_type]
                                    model.AddImplication(friday_var, sunday_var)
            
            # Saturday rules
            if weekday == 5 and i < len(dates) - 1:  # Saturday
                sunday = dates[i + 1] if i + 1 < len(dates) else None
                
                if sunday:
                    for user_id in eligible_users:
                        for call_type in call_types:
                            saturday_var = assignments[user_id][date_obj][call_type]
                            
                            # Get Sunday assignment for this Saturday call type
                            sunday_call_type = self.weekend_rules.get_weekend_assignment(call_type, 'saturday')
                            if sunday_call_type and sunday_call_type in call_types:
                                sunday_var = assignments[user_id][sunday][sunday_call_type]
                                model.AddImplication(saturday_var, sunday_var)
    
    def _add_fte_based_constraints(self, model, assignments, dates, call_types, 
                                  eligible_users, user_availabilities, constraints):
        """Add FTE-based maximum calls constraints"""
        period_days = len(dates)
        
        for user_id in eligible_users:
            user_avail = user_availabilities.get(user_id)
            if user_avail:
                # Calculate max calls for this user based on FTE
                total_call_slots = len(call_types) * period_days
                avg_calls_per_user = total_call_slots / len(eligible_users)
                max_calls_for_user = int(avg_calls_per_user * user_avail.fte * 1.2)  # 20% buffer
                
                # Add constraint
                total_assignments = sum(
                    assignments[user_id][date_obj][call_type]
                    for date_obj in dates
                    for call_type in call_types
                )
                model.Add(total_assignments <= max_calls_for_user)
    
    def _get_user_name(self, user_id: int) -> str:
        """Get user name from ID"""
        try:
            users = self.api_client.get_user_roster()
            for user in users:
                if int(user['userid']) == user_id:
                    return f"{user.get('fname', '')} {user.get('lname', '')}"
            return f"User {user_id}"
        except:
            return f"User {user_id}"


# Usage example and testing function
def test_optimizer():
    """Test the optimizer with sample data"""
    from src.api_client import SpinSchedulesAPIClient
    
    # Initialize
    client = SpinSchedulesAPIClient()
    optimizer = CallScheduleOptimizer(client)
    
    # Test with a one-week period in 2030 (safe for testing)
    start_date = "2030-01-01"  
    end_date = "2030-01-07"
    
    # Run optimization
    result = optimizer.optimize_schedule(
        start_date=start_date,
        end_date=end_date,
        call_types=['CMCG', 'CMCO', 'LPG']  # Start with fewer call types for testing
    )
    
    if result.success:
        print(f"\nOptimization successful!")
        print(f"Generated {len(result.assignments)} assignments")
        print(f"Solve time: {result.solve_time_seconds:.2f} seconds")
        
        # Print assignments by date
        assignments_by_date = {}
        for assignment in result.assignments:
            date_str = assignment['date']
            if date_str not in assignments_by_date:
                assignments_by_date[date_str] = []
            assignments_by_date[date_str].append(assignment)
        
        print("\nSchedule:")
        for date_str in sorted(assignments_by_date.keys()):
            print(f"\n{date_str}:")
            for assignment in assignments_by_date[date_str]:
                print(f"  {assignment['call_type']}: {assignment['user_name']}")
        
        # Print statistics
        print(f"\nStatistics:")
        for key, value in result.statistics.items():
            print(f"  {key}: {value}")
            
        return result
    else:
        print("Optimization failed!")
        for violation in result.violations:
            print(f"  - {violation}")
        return None


if __name__ == "__main__":
    # Run test
    test_optimizer()