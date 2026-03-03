import json
import os
from datetime import datetime
from typing import List, Dict, Optional
import streamlit as st
from pydantic import BaseModel, Field

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
            "id": f"event_{len(self.events)}_{datetime.now().timestamp()}",
            "completed": False
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
    
    def toggle_completion(self, event_id: str) -> Optional[Dict]:
        """Toggle the completion status of an event."""
        for event in self.events:
            if event.get('id') == event_id:
                event['completed'] = not event.get('completed', False)
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

class CalendarInput(BaseModel):
    """Input schema for calendar operations."""
    action: str = Field(
        description="Action to perform: 'add', 'remove', 'edit', or 'clear'"
    )
    date: Optional[str] = Field(
        default=None,
        description="Date in YYYY-MM-DD format. Required for 'add', 'remove', and 'edit' actions."
    )
    workout_type: Optional[str] = Field(
        default=None,
        description="Type of workout (e.g., 'Tempo Run', 'Long Run', 'Recovery Run'). Required for 'add', 'remove', and 'edit' actions."
    )
    details: Optional[str] = Field(
        default="",
        description="Additional details like distance, pace, notes. Optional for 'add' and 'edit' actions."
    )
    user_id: Optional[str] = Field(
        default="default",
        description="User identifier for persistence. Defaults to 'default'."
    )

def update_calendar(action: str, date: str, workout_type: str, details: str = "", user_id: str = "default") -> str:
    """
    Update calendar events with JSON persistence.
    
    Args:
        action: 'add', 'remove', 'edit', 'clear'
        date: Date string in YYYY-MM-DD format (can be empty for 'clear' action)
        workout_type: Type of workout (can be empty for 'clear' action)
        details: Additional details
        user_id: User identifier for persistence
    
    Returns:
        Status message
    """
    manager = CalendarManager(user_id)
    
    if action == "add":
        if not date or not workout_type:
            return "Error: 'date' and 'workout_type' are required for 'add' action."
        manager.add_event(date, workout_type, details)
        return f"Successfully added {workout_type} on {date}."
    elif action == "remove":
        if not date or not workout_type:
            return "Error: 'date' and 'workout_type' are required for 'remove' action."
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
        if not date or not workout_type:
            return "Error: 'date' and 'workout_type' are required for 'edit' action."
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
