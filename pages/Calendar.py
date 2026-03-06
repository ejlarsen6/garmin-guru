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

# Get events early so they're available in the sidebar
raw_events = calendar_manager.get_events()

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
    
    # Weekly Mileage Counter
    st.header("📊 Weekly Mileage")
    
    # Get current week's events
    from datetime import datetime, timedelta
    today = datetime.now().date()
    # Find Monday of this week (first day is Monday)
    start_of_week = today - timedelta(days=today.weekday())  # Monday is 0
    end_of_week = start_of_week + timedelta(days=6)  # Sunday
    
    # Filter events for this week
    weekly_events = []
    weekly_mileage = 0.0
    
    for event in raw_events:
        event_date_str = event.get('start')
        if event_date_str:
            try:
                event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()
                if start_of_week <= event_date <= end_of_week:
                    weekly_events.append(event)
                    # Try to extract mileage from description
                    description = event.get('description', '')
                    if description:
                        # Look for patterns like "5 miles", "10 mi", "3.5 miles"
                        import re
                        # Find numbers followed by "mi" or "miles"
                        matches = re.findall(r'(\d+\.?\d*)\s*(?:mi|miles|mile)', description.lower())
                        if matches:
                            weekly_mileage += sum(float(match) for match in matches)
            except:
                pass
    
    st.metric("This Week's Mileage", f"{weekly_mileage:.1f} mi")
    st.caption(f"Week of {start_of_week.strftime('%b %d')} - {end_of_week.strftime('%b %d')}")
    
    # Show weekly events summary
    if weekly_events:
        with st.expander("View This Week's Workouts"):
            for event in weekly_events:
                col1, col2 = st.columns([3, 1])
                with col1:
                    title = event.get('title', '')
                    date_str = event.get('start', '')
                    desc = event.get('description', '')
                    st.write(f"**{title}** ({date_str})")
                    if desc:
                        st.caption(desc)
                with col2:
                    # Extract mileage for this specific event
                    event_mileage = 0.0
                    if desc:
                        import re
                        matches = re.findall(r'(\d+\.?\d*)\s*(?:mi|miles|mile)', desc.lower())
                        if matches:
                            event_mileage = sum(float(match) for match in matches)
                    if event_mileage > 0:
                        st.metric("", f"{event_mileage:.1f} mi")
    else:
        st.info("No workouts scheduled for this week.")
    
    st.divider()
    
    st.header("Manage Events")
    # Use a form to prevent rerun issues
    with st.form("clear_events_form"):
        st.write("Clear all events from the calendar?")
        confirm = st.checkbox("I'm sure I want to clear all events")
        submitted = st.form_submit_button("Clear All Events", type="secondary")
        if submitted and confirm:
            calendar_manager.clear_events()
            st.success("All events cleared.")
            st.rerun()
        elif submitted and not confirm:
            st.warning("Please check the confirmation box to clear all events.")

# Display calendar

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
    "firstDay": 1,  # Monday as first day of week
    "eventDisplay": "block",  # Show more details in month view
    "eventTimeFormat": {
        "hour": "2-digit",
        "minute": "2-digit",
        "meridiem": "short"
    },
}

# Create display events from raw_events
display_events = []
for event in raw_events:
    display_event = event.copy()
    
    # Prepare title with completion status
    title = display_event.get('title', '')
    if display_event.get('completed', False):
        title = f"✓ {title}"
    
    # Add description to title for better visibility in month view
    description = display_event.get('description', '')
    if description:
        # Truncate description if too long
        if len(description) > 30:
            short_desc = description[:27] + "..."
        else:
            short_desc = description
        # Add to title for month view display
        display_event['title'] = f"{title}: {short_desc}"
    else:
        display_event['title'] = title
    
    # Set background color
    if display_event.get('completed', False):
        display_event['backgroundColor'] = '#10B981'  # Green color for completed events
    else:
        if 'Hard' in description:
            display_event['backgroundColor'] = '#FF4B4B'
        else:
            display_event['backgroundColor'] = '#3D9DF3'
    
    # Add extendedProps for more details in tooltips
    display_event['extendedProps'] = {
        'description': description,
        'original_title': event.get('title', ''),
        'completed': display_event.get('completed', False)
    }
    
    display_events.append(display_event)

# Display the calendar
calendar_state = calendar(
    events=display_events,
    options=calendar_options,
    custom_css="""
    .fc-event {
        border-radius: 4px;
        border: none;
        font-size: 0.85em;
        padding: 2px;
    }
    .fc-event-title {
        font-weight: 500;
        white-space: normal !important;
        line-height: 1.2;
    }
    .fc-daygrid-event {
        min-height: 2em;
    }
    """,
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
            description = event.get('description', '')
            
            # Extract mileage from description
            mileage_display = ""
            if description:
                import re
                matches = re.findall(r'(\d+\.?\d*)\s*(?:mi|miles|mile)', description.lower())
                if matches:
                    total_miles = sum(float(match) for match in matches)
                    mileage_display = f" ({total_miles:.1f} mi)"
            
            if completed:
                st.markdown(f"~~**{title}** - {start_date}{mileage_display}~~")
                st.caption("✓ Completed")
            else:
                st.markdown(f"**{title}** - {start_date}{mileage_display}")
            if description:
                st.caption(description)
        
        with col_remove:
            if st.button("Remove", key=f"remove_{event.get('id')}"):
                if calendar_manager.remove_event(event.get('id')):
                    st.success("Removed")
                    st.rerun()
else:
    st.info("No events scheduled. Add some workouts to your calendar!")
