import streamlit as st
import pandas as pd
import garminconnect
from datetime import date, timedelta
import matplotlib.pyplot as plt
import folium
from streamlit_folium import st_folium
from folium.plugins import HeatMap
import os
from garth.exc import GarthException

def get_garmin_client(email, password):
    """Saves login info so that IP doesn't get soft-blocked"""
    # Define a directory to save the session tokens
    token_store = "~/.garth" 
    token_store = os.path.expanduser(token_store)
    
    client = garminconnect.Garmin(email, password)
    
    try:
        # Try to load an existing session from the folder
        client.login(token_store)
        print("Login successful using stored tokens.")
    except (GarthException, Exception):
        # If tokens are missing or expired, do a fresh login
        print("Token login failed. Attempting fresh email/password login...")
        try:
            client.login()
            # Save the new tokens so we don't have to do this next time
            client.garth.dump(token_store)
        except Exception as e:
            print(f"Total login failure: {e}")
            return None
            
    return client

# data fetching
def get_workout_dataframe_n_days(n_days, email, password):
    try:
        client = get_garmin_client(email, password)
        client.login()
        
        today = date.today()
        start = str(today - timedelta(days=n_days))
        activities = client.get_activities_by_date(startdate=start, enddate=str(today))

        if not activities:
            return None

        data_list = []
        for act in activities:
            # Check if it's a running activity (including treadmill)
            activity_type = act.get("activityType", {}).get("typeKey", "")
            if "running" not in activity_type:
                continue
            
            # Check if it's a manual activity
            is_manual = act.get('manualActivity', False)
            
            # Distance and duration
            dist_mi = act.get('distance', 0) / 1609.34
            dur_min = act.get('duration', 0) / 60
            
            # Calculate pace if distance > 0 and not manual (manual may have inaccurate pace)
            if dist_mi > 0 and not is_manual:
                pace_decimal = round(dur_min / dist_mi, 2)
            else:
                pace_decimal = 0
            
            # Heart rate data may not be present for manual activities
            avg_hr = act.get('averageHR')
            if is_manual:
                avg_hr = None
            
            # VO2 Max may not be present for treadmill or manual activities
            vo2_max = act.get('vO2MaxValue')
            
            # Elevation gain - may be None for treadmill
            elev_gain = act.get('elevationGain')
            if elev_gain is None:
                elev_gain_ft = 0.0
            else:
                elev_gain_ft = round(elev_gain * 3.28084, 1)
            
            # GPS data may be missing for treadmill runs
            latitude = act.get('startLatitude')
            longitude = act.get('startLongitude')
            
            # Heart rate zones - may be None for manual activities
            hr_zones = {}
            for i in range(1, 6):
                zone_key = f'hrTimeInZone_{i}'
                zone_time = act.get(zone_key)
                if zone_time is None or is_manual:
                    hr_zones[f'Z{i}_Min'] = 0.0
                else:
                    hr_zones[f'Z{i}_Min'] = round(zone_time / 60, 2)
            
            data_list.append({
                "Activity Name": act.get('activityName'),
                "Date": pd.to_datetime(act.get('startTimeLocal')),
                "Distance (mi)": round(dist_mi, 2),
                "Duration (min)": round(dur_min, 2),
                "Pace_Decimal": pace_decimal,
                "Avg HR": avg_hr,
                "VO2 Max": vo2_max,
                "Elev Gain (ft)": elev_gain_ft,
                "Latitude": latitude,
                "Longitude": longitude,
                "Z1_Min": hr_zones.get('Z1_Min', 0.0),
                "Z2_Min": hr_zones.get('Z2_Min', 0.0),
                "Z3_Min": hr_zones.get('Z3_Min', 0.0),
                "Z4_Min": hr_zones.get('Z4_Min', 0.0),
                "Z5_Min": hr_zones.get('Z5_Min', 0.0),
                "Is Manual": is_manual,
                "Activity Type": activity_type
            })
        return pd.DataFrame(data_list)
    except Exception as e:
        st.error(f"Garmin Connection Error: {e}")
        return None

@st.cache_data(ttl=3600)
def get_cached_workout_data(days, email, password):
    return get_workout_dataframe_n_days(days, email, password)

def check_fitness_trend(query: str):
    df = st.session_state.get("df_master")
    # Sort by date
    df = df.sort_values('Date')
    # Calculate "Efficiency Index" (Pace / Avg HR)
    df['Efficiency'] = (1 / df['Pace_Decimal']) / df['Avg HR'] * 1000
    
    # Compare first 2 weeks vs last 2 weeks
    recent = df.tail(14)['Efficiency'].mean()
    older = df.iloc[:-14].tail(14)['Efficiency'].mean()
    improvement = ((recent - older) / older) * 100
    
    return f"In the last 14 days, your aerobic efficiency has changed by {improvement:.1f}% compared to the prior period."

def most_active_month(df):
    df['Month'] = df['Date'].dt.month
    monthly_miles = df.groupby("Month")["Distance (mi)"].sum()
    month = monthly_miles.idxmax()
    miles = monthly_miles.max()
    return month, miles

def summarize_n_days(df):
    if isinstance(df, tuple) or df is None or df.empty:
        return {"Total Distance Run (mi)": 0,
            "Total Elevation Gained (ft)": 0,
            "Current VO2 Max": "N/A",
            "Longest Run (mi)": 0}
    
    summary = {
        "Total Distance Run (mi)": df["Distance (mi)"].sum(),
        "Total Elevation Gained (ft)": df["Elev Gain (ft)"].sum(),
        "Current VO2 Max": df["VO2 Max"].dropna().iloc[0] if not df["VO2 Max"].dropna().empty else "N/A",
        "Longest Run (mi)": df["Distance (mi)"].max()
    }
    if len(df) > 1:
        clean_df = df.dropna()
        if len(clean_df) > 1:
            summary["VO2 Max Progress"] = clean_df["VO2 Max"].iloc[0] - clean_df["VO2 Max"].iloc[-1]
    if len(df) >= 31:
        summary["Most Active Month"] = most_active_month(df)
    return summary

# Plotting

def plot_vo2max_over_time(df, color="#10B981"):
    df_plot = df.copy().dropna(subset=["VO2 Max"]).sort_values("Date")
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(df_plot["Date"], df_plot["VO2 Max"], color=color, linewidth=3, marker='o')
    ax.set_title("VO₂ Max Trend")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    st.pyplot(fig, width='stretch')

def plot_weekly_training_time(df, color="#6366F1"):
    import plotly.graph_objects as go
    import plotly.express as px
    from plotly.subplots import make_subplots
    
    df_plot = df.copy()
    # Group by week
    df_plot["week"] = df_plot["Date"].dt.to_period("W").apply(lambda r: r.start_time)
    # Calculate weekly mileage (sum of Distance (mi))
    wk = df_plot.groupby("week").agg(
        total_miles=("Distance (mi)", "sum"),
        total_minutes=("Duration (min)", "sum")
    ).reset_index()
    
    # Create interactive bar chart with Plotly
    fig = go.Figure()
    
    # Add mileage bars
    fig.add_trace(go.Bar(
        x=wk["week"],
        y=wk["total_miles"],
        name="Weekly Mileage (mi)",
        marker_color=color,
        hovertemplate="<b>Week of %{x|%Y-%m-%d}</b><br>" +
                      "Mileage: %{y:.1f} mi<br>" +
                      "<extra></extra>"
    ))
    
    # Update layout
    fig.update_layout(
        title="Weekly Training Mileage",
        xaxis_title="Week",
        yaxis_title="Miles",
        hovermode="x unified",
        template="plotly_dark",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#fafafa"),
        xaxis=dict(
            showgrid=False,
            tickangle=45
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="rgba(255,255,255,0.1)"
        ),
        height=500
    )
    
    # Display in Streamlit
    st.plotly_chart(fig, use_container_width=True)

def get_pbs(df):
  df["Date"] = pd.to_datetime(df["Date"])

  df["distance_km"] = df["Distance (mi)"] * 1.60934

  df["pace_sec_per_km"] = df["Pace_Decimal"] * 60 / 1.0
  df["pace_sec_per_km"] /= 1.60934

  dcm = {
      "1 Mile": (1.60934, "#3B82F6"),
      "5K": (5.0, "#F59E0B"),
      "10K": (10.0, "#6366F1"),
  }

  rows = []
  for dist_label, (dist_km, color) in dcm.items():
      sub = df[df["distance_km"] >= dist_km].copy()
      if len(sub) == 0:
          continue

      sub["T"] = sub["pace_sec_per_km"] * dist_km
      rows.append(sub[["Date", "T"]].assign(Distance=dist_label, Color=color))

  mlt = pd.concat(rows).sort_values("Date")

  mlt["PR"] = mlt.groupby("Distance")["T"].cummin()
  mlt["isPR"] = mlt["T"] == mlt["PR"]
  final_pbs = mlt[mlt["isPR"]].groupby("Distance").tail(1)
  return final_pbs[['Date', 'T', 'Distance']]

def format_seconds(seconds):
    """Helper to turn raw seconds into MM:SS or HH:MM:SS."""
    if pd.isna(seconds): return "N/A"
    td = timedelta(seconds=int(seconds))
    # Returns 00:00:00, we slice to 00:00 if under an hour
    ts = str(td)
    return ts if seconds >= 3600 else ts[2:]

def plot_pr_only(df):
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    
    # 1. Conversion Logic
    df["distance_km"] = df["Distance (mi)"] * 1.60934
    df["pace_sec_per_km"] = df["Pace_Decimal"] * 60 / 1.60934

    dcm = {
        "1 Mile": (1.609, "#3B82F6"),
        "5K": (5.0, "#F59E0B"),
        "10K": (10.0, "#6366F1"),
    }

    rows = []
    for dist_label, (dist_km, color) in dcm.items():
        # Look for runs that are at least the target distance
        sub = df[df["distance_km"] >= (dist_km - 0.1)].copy() 
        if sub.empty:
            continue

        # Calculate total time for that distance based on pace
        sub["T"] = sub["pace_sec_per_km"] * dist_km
        rows.append(sub[["Date", "T"]].assign(Distance=dist_label, Color=color))

    if not rows:
        st.warning("Not enough data to calculate PRs for these distances.")
        return

    mlt = pd.concat(rows).sort_values("Date")
    
    # 2. PR Calculation: Only keep times that are the "Cumulative Minimum" (the new PR)
    mlt["PR"] = mlt.groupby("Distance")["T"].cummin()
    prs = mlt[mlt["T"] == mlt["PR"]]

    # 3. Plotting
    fig, ax = plt.subplots(figsize=(14, 7))

    for dist_label, (_, color) in dcm.items():
        grp = prs[prs["Distance"] == dist_label]
        if grp.empty:
            continue

        ax.scatter(
            grp["Date"],
            grp["T"],
            s=180, # Made slightly bigger for the stars
            color=color,
            marker="*",
            edgecolor="black",
            linewidth=0.8,
            label=f"{dist_label} PR ★"
        )

    ax.invert_yaxis() # Faster times (lower seconds) are at the top
    ax.set_title("Personal Bests Progression (PRs Only)", fontsize=16)
    ax.set_xlabel("Date")
    ax.set_ylabel("Estimated Time (seconds)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    
    plt.tight_layout()
    st.pyplot(fig, width='stretch')

def get_user_profile_data(email, password):
    try:
        client = get_garmin_client(email, password)
        client.login()
        
        user_profile = client.get_user_profile()
        user_data = user_profile.get('userData', {})
        
        return {
            'Full Name': client.full_name,
            'Username': client.username,
            'Gender': user_data.get('gender'),
            'Weight (lbs)': round(user_data.get('weight', 0) / 453.592, 1),
            'Height (ft)': round(user_data.get('height', 0) / 30.48, 1),
            'Location': user_profile.get('location')
        }
    except Exception as e:
        return None

def get_race_predictions(email, password, startdate=None, enddate=None):
    """Fetch race predictions from Garmin API for a date range."""
    try:
        client = get_garmin_client(email, password)
        client.login()
        
        # If startdate and enddate are provided, use them
        if startdate and enddate:
            # Note: The actual implementation may vary based on the Garmin API
            # Let's assume the client method supports these parameters
            # We'll need to check the actual method signature
            # For now, we'll try to call it with these parameters
            try:
                predictions = client.get_race_predictions(startdate=startdate, enddate=enddate)
            except TypeError:
                # If the method doesn't support these parameters, fall back to default
                predictions = client.get_race_predictions()
        else:
            predictions = client.get_race_predictions()
        
        return predictions
    except Exception as e:
        st.error(f"Error fetching race predictions: {e}")
        return None

def format_prediction_time(seconds):
    """Convert seconds to HH:MM:SS or MM:SS format."""
    if seconds is None:
        return "N/A"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{int(hours):02d}:{int(minutes):02d}:{int(secs):02d}"
    else:
        return f"{int(minutes):02d}:{int(secs):02d}"

def get_race_predictions_history(n_days, email, password):
    """Get race predictions for multiple days to track trends."""
    try:
        client = get_garmin_client(email, password)
        client.login()
        
        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=n_days)
        
        # Try to get predictions with date range
        # The actual implementation may vary
        # Let's try to call the method with date parameters
        try:
            # Check if the method supports these parameters
            predictions_data = client.get_race_predictions(
                startdate=str(start_date), 
                enddate=str(end_date)
            )
        except TypeError:
            # If not, we'll need to get daily predictions another way
            # For now, let's create a mock implementation
            st.warning("Date range not supported for race predictions. Using current predictions only.")
            predictions = client.get_race_predictions()
            if predictions:
                data = {
                    'date': pd.Timestamp.now(),
                    '5K': predictions.get('time5K'),
                    '10K': predictions.get('time10K'),
                    'HalfMarathon': predictions.get('timeHalfMarathon'),
                    'Marathon': predictions.get('timeMarathon')
                }
                return pd.DataFrame([data])
            return pd.DataFrame()
        
        # Process the predictions data
        # The structure may vary, so we need to handle it carefully
        if isinstance(predictions_data, dict):
            # If it's a single dictionary, wrap it in a list
            predictions_data = [predictions_data]
        
        records = []
        for pred in predictions_data:
            # Extract date from prediction
            # The structure may vary, so we need to be flexible
            pred_date = pred.get('date', end_date)
            if isinstance(pred_date, str):
                pred_date = pd.to_datetime(pred_date)
            
            record = {
                'date': pred_date,
                '5K': pred.get('time5K'),
                '10K': pred.get('time10K'),
                'HalfMarathon': pred.get('timeHalfMarathon'),
                'Marathon': pred.get('timeMarathon')
            }
            records.append(record)
        
        return pd.DataFrame(records)
    except Exception as e:
        st.error(f"Error fetching race predictions history: {e}")
        # Return empty DataFrame
        return pd.DataFrame()

def plot_race_predictions_trend(df_history):
    """Plot race prediction trends over time using Plotly."""
    if df_history.empty or len(df_history) < 1:
        st.info("No race prediction data available to plot.")
        return
    
    # Ensure we have a 'date' column
    if 'date' not in df_history.columns:
        st.error("Race prediction data missing 'date' column.")
        return
    
    # Convert date to datetime if it's not already
    df_plot = df_history.copy()
    df_plot['date'] = pd.to_datetime(df_plot['date'])
    
    # Sort by date
    df_plot = df_plot.sort_values('date')
    
    import plotly.graph_objects as go
    
    fig = go.Figure()
    
    # Add traces for each race distance
    distances = ['5K', '10K', 'HalfMarathon', 'Marathon']
    colors = ['#3B82F6', '#F59E0B', '#6366F1', '#10B981']
    
    for dist, color in zip(distances, colors):
        if dist in df_plot.columns:
            # Filter out None values
            valid_data = df_plot[['date', dist]].dropna(subset=[dist])
            if len(valid_data) > 0:
                # Convert seconds to minutes for better y-axis scaling
                fig.add_trace(go.Scatter(
                    x=valid_data['date'],
                    y=valid_data[dist] / 60,  # Convert to minutes
                    mode='lines+markers',
                    name=dist,
                    line=dict(color=color, width=3),
                    marker=dict(size=8),
                    hovertemplate=f"<b>{dist}</b><br>" +
                                  "Date: %{x|%Y-%m-%d}<br>" +
                                  "Time: %{customdata}<br>" +
                                  "<extra></extra>",
                    customdata=[format_prediction_time(t) for t in valid_data[dist]]
                ))
    
    if len(fig.data) == 0:
        st.info("No valid race prediction data to plot.")
        return
    
    fig.update_layout(
        title="Race Prediction Trends Over Time",
        xaxis_title="Date",
        yaxis_title="Predicted Time (minutes)",
        hovermode="x unified",
        template="plotly_dark",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#fafafa"),
        xaxis=dict(
            showgrid=False,
            tickangle=45
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="rgba(255,255,255,0.1)"
        ),
        height=500
    )
    
    st.plotly_chart(fig, use_container_width=True)

def get_training_stress(df):
    """Calculates the ratio of last 7 days volume vs last 30 days."""
    if df is None or df.empty:
        return None
    
    today = pd.Timestamp.now()
    
    # Acute Load 
    acute_mask = (df['Date'] >= (today - pd.Timedelta(days=7)))
    acute_load = df.loc[acute_mask, 'Distance (mi)'].sum()
    
    # Chronic Load 
    chronic_mask = (df['Date'] >= (today - pd.Timedelta(days=30)))
    chronic_load = df.loc[chronic_mask, 'Distance (mi)'].sum() / 4.28 # Avg weeks in a month
    
    if chronic_load == 0:
        return 0.0
        
    ratio = acute_load / chronic_load
    return round(ratio, 2)

def plot_activity_map(df):
    # Filter for rows that have GPS data (non-null latitude and longitude)
    if "Latitude" not in df.columns or "Longitude" not in df.columns:
        st.warning("GPS data not found in the current dataset.")
        return None

    # Filter out rows where either latitude or longitude is None
    coords = df[["Activity Name", "Latitude", "Longitude", "Distance (mi)", "Date"]].dropna(subset=["Latitude", "Longitude"])
    
    if coords.empty:
        st.info("No GPS coordinate data available to map. This may be due to treadmill or indoor activities.")
        return None

    # Center map on the mean location of available coordinates
    m = folium.Map(
        location=[coords["Latitude"].mean(), coords["Longitude"].mean()],
        zoom_start=12,
        tiles="CartoDB positron" # Clean, professional look
    )

    # Add markers for activity start points
    marker_group = folium.FeatureGroup(name="Individual Runs").add_to(m)
    for _, row in coords.iterrows():
        popup_info = f"""
            <strong>{row['Activity Name']}</strong><br>
            Distance: {row['Distance (mi)']} mi<br>
            Date: {row['Date'].strftime('%Y-%m-%d')}
        """
        folium.CircleMarker(
            location=[row["Latitude"], row["Longitude"]],
            radius=4,
            color="#3B82F6",
            fill=True,
            fill_opacity=0.7,
            popup=folium.Popup(popup_info, max_width=250)
        ).add_to(marker_group)
    
    # Prepare heatmap data
    heat_data = coords[["Latitude", "Longitude"]].values.tolist()
    if heat_data:
        HeatMap(heat_data, name="Heatmap (Density)", min_opacity=0.4, radius=16).add_to(m)

    folium.LayerControl().add_to(m)
    
    st_folium(m, width='stretch', height=600, returned_objects=[])
