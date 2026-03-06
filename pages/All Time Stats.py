import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os
from data_utils import (
    get_cached_workout_data, 
    summarize_n_days, 
    plot_weekly_training_time, 
    plot_vo2max_over_time, 
    get_personal_records, 
    plot_pr_only, 
    get_training_stress,
    get_race_predictions_history,
    plot_race_predictions_trend
)
from style_utils import apply_custom_style
apply_custom_style()

st.set_page_config(page_title="Long Term Analytics", layout="wide")

# UI
if "logged_in" not in st.session_state or not st.session_state.logged_in:
    st.warning("Please log in on the Home page first to access analytics.")
    st.stop()

st.title("Long-Term Training Analytics")

# Check if we have data from the Home page
if "df_data" in st.session_state and st.session_state.df_data is not None:
    df = st.session_state.df_data

# Input for N Days
with st.sidebar:
    st.header("Settings")
    n_days = st.number_input("Lookback Period (Days)", min_value=1, max_value=5000, value=365)
    refresh = st.button("🔄 Refresh Data")

# Fetch Data
with st.spinner(f"Analyzing last {n_days} days..."):
    email = st.session_state.garmin_email
    password = st.session_state.garmin_password

    # refresh data
    if refresh:
        st.cache_data.clear()
        
    df_analytics = get_cached_workout_data(n_days, email, password)

if df_analytics is not None and not df_analytics.empty:
    # Remove columns to make graphs full width
    # Personal Best Progression
    st.subheader("🏆 Personal Best Progression")
    # Fetch and display personal records directly
    try:
        pr_data = get_personal_records(email, password)
        if pr_data:
            # Create a better visualization
            import plotly.graph_objects as go
            import plotly.express as px
            
            # Convert to DataFrame
            df_pr = pd.DataFrame(pr_data)
            
            if not df_pr.empty:
                # Format time for display
                def format_time(seconds):
                    if pd.isna(seconds):
                        return "N/A"
                    mins = int(seconds // 60)
                    secs = int(seconds % 60)
                    return f"{mins}:{secs:02d}"
                
                df_pr['time_formatted'] = df_pr['time_seconds'].apply(format_time)
                df_pr['time_minutes'] = df_pr['time_seconds'] / 60
                
                # Create bar chart with Plotly for better interactivity
                fig = go.Figure()
                
                # Add bars
                fig.add_trace(go.Bar(
                    x=df_pr['distance'],
                    y=df_pr['time_minutes'],
                    text=df_pr['time_formatted'],
                    textposition='auto',
                    marker_color=px.colors.sequential.Viridis,
                    hovertemplate='<b>%{x}</b><br>Time: %{text}<br>Date: %{customdata}<extra></extra>',
                    customdata=df_pr['date'].apply(lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) else 'N/A')
                ))
                
                fig.update_layout(
                    title='Personal Records by Distance',
                    xaxis_title='Distance',
                    yaxis_title='Time (minutes)',
                    template='plotly_dark',
                    height=500,
                    showlegend=False
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Display table
                with st.expander("View Personal Record Details"):
                    display_df = df_pr[['distance', 'time_formatted', 'date']].copy()
                    display_df['date'] = display_df['date'].apply(lambda x: x.strftime('%Y-%m-%d') if pd.notnull(x) else 'N/A')
                    display_df.columns = ['Distance', 'Time', 'Date']
                    st.dataframe(display_df, use_container_width=True)
            else:
                st.info("No personal records found.")
        else:
            st.info("Could not load personal records. Try refreshing.")
    except Exception as e:
        st.error(f"Error loading personal records: {e}")
        # Fall back to the original plot
        plot_pr_only(df_analytics, email, password)
    
    st.divider()
    
    st.subheader("Aerobic Efficiency")
    plot_vo2max_over_time(df_analytics)

    st.divider()
    
    st.subheader("Weekly Volume")
    plot_weekly_training_time(df_analytics)

    st.divider()
    
    st.subheader("Race Predictions Trend")
    # Get race predictions history
    with st.spinner("Fetching race predictions..."):
        pred_history = get_race_predictions_history(n_days, email, password)
        plot_race_predictions_trend(pred_history)

    st.divider()

    with st.expander("View Raw Data for this Range"):
        st.dataframe(df_analytics)
else:
    st.error("No running activities found in this date range.")
