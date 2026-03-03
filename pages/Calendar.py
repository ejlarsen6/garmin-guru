import streamlit as st
from streamlit_calendar import calendar
from calendar_manager import CalendarManager
from data_utils import update_calendar
from style_utils import apply_custom_style
from datetime import datetime

apply_custom_style()

st.set_page_config(page_title="Training Calendar", page_icon="📅", layout="wide")

st.title("📅 Training Calendar")

# Check if user is logged in
if "logged_in" not in st.session_state or not st.session_state.logged_in:
    st.warning("Please log in on the Home page first.")
    st.stop()

# Get user email for calendar persistence
user_email = st.session_state.get("garmin_email", "default")
calendar_manager = CalendarManager(user_email)

# Sidebar for adding events
with st.sidebar:
    st.header("Add New Event")
    
    with st.form("add_event_form"):
        event_date = st.date_input("Date")
        workout_type = st.selectbox(
            "Workout Type",
            ["Easy Run", "Tempo Run", "Long Run", "Interval Training", 
             "Recovery Run", "Cross Training", "Rest Day", "Race Day"]
        )
        details = st.text_area("Details (pace, distance, notes)")
        
        submitted = st.form_submit_button("Add to Calendar")
        if submitted:
            if event_date and workout_type:
                result = update_calendar(
                    action="add",
                    date=str(event_date),
                    workout_type=workout_type,
                    details=details,
                    user_id=user_email
                )
                st.success(result)
                st.rerun()
    
    st.header("Manage Events")
    if st.button("Clear All Events", type="secondary"):
        if st.checkbox("I'm sure I want to clear all events"):
            calendar_manager.clear_events()
            st.success("All events cleared.")
            st.rerun()

# Display calendar
st.header("Your Training Schedule")

calendar_options = {
    "editable": True,
    "selectable": True,
    "headerToolbar": {
        "left": "today prev,next",
        "center": "title",
        "right": "dayGridMonth,timeGridWeek,timeGridDay,listWeek"
    },
    "initialView": "dayGridMonth",
    "height": 700,
}

# Get current events and update their titles to show completion status
raw_events = calendar_manager.get_events()
display_events = []
for event in raw_events:
    display_event = event.copy()
    if display_event.get('completed', False):
        # Add a checkmark to the title
        display_event['title'] = f"✓ {display_event.get('title')}"
        # Change the background color to indicate completion
        display_event['backgroundColor'] = '#10B981'  # Green color for completed events
    else:
        # Ensure the background color is appropriate
        if 'Hard' in display_event.get('description', ''):
            display_event['backgroundColor'] = '#FF4B4B'
        else:
            display_event['backgroundColor'] = '#3D9DF3'
    display_events.append(display_event)

# Display the calendar
calendar_state = calendar(
    events=display_events,
    options=calendar_options,
    key="training_calendar"
)

# Handle calendar interactions
if calendar_state and "eventClick" in calendar_state:
    clicked_event = calendar_state["eventClick"]["event"]
    st.info(f"**{clicked_event.get('title')}** on {clicked_event.get('start')}")
    if clicked_event.get('description'):
        st.write(f"Details: {clicked_event.get('description')}")
    
    # Option to remove the clicked event
    if st.button("Remove this event"):
        if calendar_manager.remove_event(clicked_event.get('id')):
            st.success("Event removed.")
            st.rerun()

if calendar_state and "dateClick" in calendar_state:
    clicked_date = datetime.fromisoformat(calendar_state["dateClick"]["date"]).date()
    st.info(f"Date selected: {clicked_date}")
    
    # Quick add form for the clicked date
    with st.expander(f"Add event on {clicked_date}", expanded=True):
        quick_type = st.selectbox(
            "Workout Type",
            ["Easy Run", "Tempo Run", "Long Run", "Interval Training", 
             "Recovery Run", "Cross Training", "Rest Day", "Race Day"],
            key="quick_type"
        )
        quick_details = st.text_input("Details", key="quick_details")
        if st.button("Add Event", key="quick_add"):
            result = update_calendar(
                action="add",
                date=clicked_date,
                workout_type=quick_type,
                details=quick_details,
                user_id=user_email
            )
            st.success(result)
            st.rerun()

# Display events list
st.header("Upcoming Events")
if raw_events:
    # Sort events by date
    sorted_events = sorted(raw_events, key=lambda x: x.get('start', ''))
    
    for event in sorted_events[:10]:  # Show next 10 events
        # Create columns for checkbox, event details, and remove button
        col_check, col_details, col_remove = st.columns([1, 5, 2])
        
        with col_check:
            # Display checkbox for completion
            completed = event.get('completed', False)
            # Create a unique key for the checkbox
            checkbox_key = f"completed_{event.get('id')}"
            # Use a button to toggle completion status
            if st.button("✅" if completed else "⬜", key=checkbox_key):
                calendar_manager.toggle_completion(event.get('id'))
                st.rerun()
        
        with col_details:
            # Strike through if completed
            title = event.get('title')
            start_date = event.get('start')
            if completed:
                st.markdown(f"~~**{title}** - {start_date}~~")
                st.caption("✓ Completed")
            else:
                st.markdown(f"**{title}** - {start_date}")
            if event.get('description'):
                st.caption(event.get('description'))
        
        with col_remove:
            if st.button("Remove", key=f"remove_{event.get('id')}"):
                if calendar_manager.remove_event(event.get('id')):
                    st.success("Removed")
                    st.rerun()
else:
    st.info("No events scheduled. Add some workouts to your calendar!")
