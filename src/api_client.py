"""
SpinSchedules API Client for Call Scheduler
Handles all interactions with the SpinSchedules/SpinFusion API
"""

import requests
import os
from datetime import datetime, date
from typing import List, Dict, Optional, Any
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

class SpinSchedulesAPIClient:
    def __init__(self):
        self.api_key = os.getenv('SPINSCHEDULES_API_KEY')
        self.base_url = os.getenv('SPINSCHEDULES_BASE_URL', 
                                  'https://www.spinfusion.com/SpinSchedulev2.0/api')
        
        if not self.api_key:
            raise ValueError("SPINSCHEDULES_API_KEY not found in .env file")
        
        # Set up headers for all requests
        self.headers = {
            'Authorization': f'Basic {self.api_key}',
            'Content-Type': 'application/json',
            'User-Agent': 'CallScheduler-Python'  # Required for .NET integration
        }
    
    def _make_request(self, method: str, endpoint: str, params: Dict = None, 
                     data: Any = None) -> Dict:
        """
        Make HTTP request to SpinSchedules API
        
        Args:
            method: HTTP method (GET, POST, DELETE)
            endpoint: API endpoint (without base URL)
            params: Query parameters
            data: Request body data
        
        Returns:
            JSON response as dictionary
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method.upper() == 'GET':
                response = requests.get(url, headers=self.headers, params=params)
            elif method.upper() == 'POST':
                if isinstance(data, dict):
                    response = requests.post(url, headers=self.headers, 
                                           params=params, json=data)
                else:
                    response = requests.post(url, headers=self.headers, 
                                           params=params, data=data)
            elif method.upper() == 'DELETE':
                response = requests.delete(url, headers=self.headers, params=params)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            
            # Handle empty responses
            if not response.text:
                return {"success": True}
                
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"API request failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response status: {e.response.status_code}")
                print(f"Response text: {e.response.text}")
            raise
    
    # ==================== USER MANAGEMENT ====================
    
    def get_user_roster(self, include_inactive: bool = False) -> List[Dict]:
        """
        Get list of all users in the system
        
        Args:
            include_inactive: Include terminated/inactive users
            
        Returns:
            List of user dictionaries with basic info
        """
        params = {'includeInactive': str(include_inactive).lower()}
        response = self._make_request('GET', '/External/get_users_roster', params=params)
        
        if response.get('success'):
            return response.get('users', [])
        return []
    
    def get_user_groups(self, user_id: int = None, group_id: int = None) -> List[Dict]:
        """
        Get user group information
        
        Args:
            user_id: Filter to groups for specific user
            group_id: Filter to specific group
            
        Returns:
            List of group dictionaries
        """
        params = {}
        if user_id:
            params['userId'] = user_id
        if group_id:
            params['groupId'] = group_id
            
        response = self._make_request('GET', '/External/get_users_userGroups', params=params)
        
        if response.get('success'):
            return response.get('groups', [])
        return []
    
    # ==================== SCHEDULE MANAGEMENT ====================
    
    def get_available_schedules(self) -> List[Dict]:
        """
        Get list of available primary schedules
        
        Returns:
            List of schedule dictionaries with id and name
        """
        response = self._make_request('GET', '/External/get_system_schedulesForSystem')
        
        if response.get('success'):
            return response.get('schedules', [])
        return []
    
    def get_assignments_by_schedule(self, schedule_ids: List[int], 
                                   start_date: str, end_date: str,
                                   use_snapshot: bool = False) -> List[Dict]:
        """
        Get assignments for specific schedules in date range
        
        Args:
            schedule_ids: List of schedule IDs to query
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            use_snapshot: Use snapshot data instead of live data
            
        Returns:
            List of assignment dictionaries
        """
        # Convert schedule_ids to comma-separated string
        schedule_ids_str = ','.join(map(str, schedule_ids))
        
        params = {
            'scheduleIds': schedule_ids_str,
            'startDate': start_date,
            'endDate': end_date,
            'useSnapshotData': str(use_snapshot).lower()
        }
        
        response = self._make_request('GET', '/External/get_schedules_assignmentsBySchedule', 
                                    params=params)
        
        return response.get('assignments', [])
    
    def get_assign_codes_in_range(self, schedule_ids: List[int], 
                                 start_date: str, end_date: str) -> List[List]:
        """
        Get assignment codes in use during date range
        
        Args:
            schedule_ids: List of schedule IDs
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            
        Returns:
            List of [assignCodeName, assignCodeId] pairs
        """
        params = {
            'startDate': start_date,
            'endDate': end_date
        }
        
        # Add multiple schedule IDs
        for schedule_id in schedule_ids:
            params[f'scheduleIds'] = schedule_id
            
        response = self._make_request('GET', 
                                    '/External/get_schedules_assignCodesInUseInDateRange',
                                    params=params)
        
        if response.get('success'):
            return response.get('assignCodeObjs', [])
        return []
    
    def add_assignment(self, date: str, user_id: int, assign_code_id: int,
                      override: bool = False, background_color: str = None,
                      text_color: str = None, note: str = None) -> Dict:
        """
        Add a new schedule assignment
        
        Args:
            date: Assignment date (YYYY-MM-DD)
            user_id: ID of user being assigned
            assign_code_id: ID of assignment code (call type)
            override: Allow override of conflicts
            background_color: Background color for assignment
            text_color: Text color for assignment
            note: Note to add to assignment
            
        Returns:
            API response dictionary
        """
        data = {
            'date': date,
            'userId': user_id,
            'assignCodeId': assign_code_id,
            'override': override
        }
        
        if background_color:
            data['backgroundColor'] = background_color
        if text_color:
            data['textColor'] = text_color
        if note:
            data['note'] = note
            
        return self._make_request('POST', '/External/add_schedules_assignment', data=data)
    
    def delete_assignment(self, date: str, assign_code_id: int, 
                         user_id: int = None, override: bool = True,
                         ignore_linkages: bool = True) -> Dict:
        """
        Delete a schedule assignment
        
        Args:
            date: Assignment date (YYYY-MM-DD)
            assign_code_id: ID of assignment code to delete
            user_id: Specific user to remove (optional)
            override: Allow override of restrictions
            ignore_linkages: Ignore linked assignments
            
        Returns:
            API response dictionary
        """
        data = {
            'date': date,
            'assignCodeId': assign_code_id,
            'override': override,
            'ignoreLinkages': ignore_linkages
        }
        
        if user_id:
            data['userId'] = user_id
            
        return self._make_request('POST', '/External/delete_schedules_assignment', data=data)
    
    # ==================== TESTING & UTILITIES ====================
    
    def test_connection(self, test_data: str = "Hello from Call Scheduler!") -> Dict:
        """
        Test API connection using echo endpoint
        
        Args:
            test_data: Data to echo back
            
        Returns:
            Echo response
        """
        return self._make_request('POST', '/External/echo', data=test_data)

# Utility functions
def format_date(date_obj: date) -> str:
    """Convert date object to API format string"""
    return date_obj.strftime('%Y-%m-%d')

def parse_date(date_str: str) -> date:
    """Parse API date string to date object"""
    return datetime.strptime(date_str, '%Y-%m-%d').date()