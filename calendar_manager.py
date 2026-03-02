import json
import os
from datetime import datetime
from typing import List, Dict, Optional
import streamlit as st

class CalendarManager:
    """Manages calendar events with JSON persistence."""
    
    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self.data_dir = "calendar_data"
        os.makedirs(self.data_dir, exist_ok=True)
        self.file_path = os.path.join(self.data_dir, f"{user_id}_events.json")
        self.events = self._load_events()
    
    def _load_events(self) -> List[Dict]:
        """Load events from JSON file."""
        try:
            if os.path.exists(self.file_path):
                with open(self.file_path, 'r') as f:
                    events = json.load(f)
                    # Ensure each event has required fields
                    for event in events:
                        # Convert date strings to datetime for consistency
                        if 'start' in event:
                            event['start'] = str(event['start'])
                    return events
        except (json.JSONDecodeError, FileNotFoundError):
            pass
        return []
    
    def _save_events(self):
        """Save events to JSON file."""
        try:
            with open(self.file_path, 'w') as f:
                json.dump(self.events, f, indent=2)
        except Exception as e:
            st.error(f"Error saving calendar events: {e}")
    
    def add_event(self, date: str, workout_type: str, details: str = "") -> Dict:
        """Add a new event to the calendar."""
        new_event = {
            "title": workout_type,
            "start": date,
            "description": details,
            "backgroundColor": "#FF4B4B" if "Hard" in details else "#3D9DF3",
            "id": f"event_{len(self.events)}_{datetime.now().timestamp()}"
        }
        self.events.append(new_event)
        self._save_events()
        return new_event
    
    def remove_event(self, event_id: str) -> bool:
        """Remove an event by ID."""
        initial_length = len(self.events)
        self.events = [event for event in self.events if event.get('id') != event_id]
        if len(self.events) < initial_length:
            self._save_events()
            return True
        return False
    
    def edit_event(self, event_id: str, **kwargs) -> Optional[Dict]:
        """Edit an existing event."""
        for event in self.events:
            if event.get('id') == event_id:
                for key, value in kwargs.items():
                    if value is not None:
                        event[key] = value
                self._save_events()
                return event
        return None
    
    def get_events(self) -> List[Dict]:
        """Get all events."""
        return self.events
    
    def clear_events(self):
        """Clear all events."""
        self.events = []
        self._save_events()

def update_calendar(action: str, date: str, workout_type: str, details: str = "", user_id: str = "default") -> str:
    """
    Update calendar events with JSON persistence.
    
    Args:
        action: 'add', 'remove', 'edit', 'clear'
        date: Date string in YYYY-MM-DD format
        workout_type: Type of workout
        details: Additional details
        user_id: User identifier for persistence
    
    Returns:
        Status message
    """
    manager = CalendarManager(user_id)
    
    if action == "add":
        manager.add_event(date, workout_type, details)
        return f"Successfully added {workout_type} on {date}."
    elif action == "remove":
        # For remove, we need an event_id, but we can use date and workout_type to find it
        events = manager.get_events()
        removed = False
        for event in events:
            if event.get('start') == date and event.get('title') == workout_type:
                if manager.remove_event(event.get('id')):
                    removed = True
        if removed:
            return f"Successfully removed {workout_type} on {date}."
        else:
            return f"No event found matching {workout_type} on {date}."
    elif action == "edit":
        # For edit, we need to specify which event to edit
        # This is a simplified version - in practice, we'd need more parameters
        return "Edit functionality requires event ID. Use the CalendarManager directly for more control."
    elif action == "clear":
        manager.clear_events()
        return "Successfully cleared all calendar events."
    else:
        return f"Unknown action: {action}"

def get_calendar_events(user_id: str = "default") -> List[Dict]:
    """Get all calendar events for a user."""
    manager = CalendarManager(user_id)
    return manager.get_events()
