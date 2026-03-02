import streamlit as st
from langchain_community.chat_message_histories import StreamlitChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
import pandas as pd
from dotenv import load_dotenv
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.tools import Tool
from langchain.chains import RetrievalQA, LLMChain
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.tools import StructuredTool
from langchain_community.embeddings import GPT4AllEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from langchain.schema import HumanMessage
from langchain_community.vectorstores import Chroma
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain import hub
from langchain.memory import ConversationBufferMemory
from langchain_community.chat_message_histories import StreamlitChatMessageHistory
from garminconnect import Garmin
import garminconnect
from datetime import datetime, date, timedelta
from langchain_core.messages import SystemMessage
from langchain_experimental.agents.agent_toolkits import create_pandas_dataframe_agent
import matplotlib.pyplot as plt
from data_utils import get_cached_workout_data, summarize_n_days, get_training_stress, get_workout_dataframe_n_days, check_fitness_trend, get_efficiency_trend, update_calendar, get_calendar_events
from calendar_manager import CalendarManager
from style_utils import apply_custom_style
from streamlit_calendar import calendar

GARMIN_CACHE = None
load_dotenv("cred.env")

apply_custom_style()

# persists specifically for Streamlit sessions
msgs = StreamlitChatMessageHistory(key="chat_messages")
if "memory" not in st.session_state:
    st.session_state.memory = ConversationBufferMemory(
        memory_key="chat_history", 
        chat_memory=msgs, 
        return_messages=True
    )

# Tool Setup

def coach_retrieval(q, retriever):
    docs = retriever.invoke(q)
    return "\n\n".join([d.page_content for d in docs])

def get_agent():
    load_dotenv("cred.env")
    api_key = os.getenv("GOOGLE_API_KEY")
    # Splitter
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

    # Embeddings
    embeddings = GPT4AllEmbeddings()
        
    # Import CalendarInput here to avoid circular imports
    from calendar_manager import CalendarInput

    # Vector Stores
    # Coaching store
    coaching_store_path = "docs/chroma_coaching_store"
    if os.path.exists(coaching_store_path):
        coaching_store = Chroma(
            persist_directory=coaching_store_path,
            embedding_function=embeddings
        )
        coaching_retriever = coaching_store.as_retriever()
    else:
        all_docs = []
        for file in os.listdir("./docs/"):
            if file.endswith(".pdf"):
                loader = PyPDFLoader(f"./docs/{file}")
                all_docs.extend(loader.load())
        
        coaching_chunks = splitter.split_documents(all_docs)
        coaching_store = Chroma.from_documents(
            documents=coaching_chunks,
            embedding=embeddings,
            persist_directory=coaching_store_path
        )
        coaching_store.persist()
        coaching_retriever = coaching_store.as_retriever()
    
    # Training plans store
    training_plans_path = "docs/training_plans"
    plan_store_path = "docs/chroma_plan_store"
    
    if os.path.exists(plan_store_path):
        plan_store = Chroma(
            persist_directory=plan_store_path,
            embedding_function=embeddings
        )
        plan_retriever = plan_store.as_retriever()
    else:
        plan_docs = []
        # Check if training_plans directory exists
        if os.path.exists(training_plans_path):
            for file in os.listdir(training_plans_path):
                if file.endswith(".pdf"):
                    loader = PyPDFLoader(os.path.join(training_plans_path, file))
                    plan_docs.extend(loader.load())
        else:
            # Create an empty list if directory doesn't exist
            plan_docs = []
        
        if plan_docs:
            plan_chunks = splitter.split_documents(plan_docs)
            plan_store = Chroma.from_documents(
                documents=plan_chunks,
                embedding=embeddings,
                persist_directory=plan_store_path
            )
            plan_store.persist()
            plan_retriever = plan_store.as_retriever()
        else:
            # Create an empty vector store if no documents
            plan_store = Chroma.from_documents(
                documents=[],
                embedding=embeddings,
                persist_directory=plan_store_path
            )
            plan_store.persist()
            plan_retriever = plan_store.as_retriever()

    llm = ChatGoogleGenerativeAI(model="models/gemini-2.5-flash", google_api_key = api_key, temperature=0.15)

    def workout_data_query(query: str):
        try:
            current_df = st.session_state.get("df_data")
            if current_df is None:
                return "Dataframe not found. Please refresh the data."
            
            df_agent = create_pandas_dataframe_agent(
                llm, 
                current_df, 
                verbose=False, 
                allow_dangerous_code=True 
            )
            response = df_agent.invoke({"input": query})
            return response["output"]
        except Exception as e:
            return f"Error analyzing data: {str(e)}"
    
    def calendar_tool_wrapper(calendar_input: CalendarInput) -> str:
        """
        Wrapper for calendar tool that accepts a CalendarInput object.
        """
        # Extract parameters from the structured input
        action = calendar_input.action
        date = calendar_input.date
        workout_type = calendar_input.workout_type
        details = calendar_input.details or ""
        user_id = calendar_input.user_id or st.session_state.get("garmin_email", "default")
        
        return update_calendar(action, date, workout_type, details, user_id)

    def plan_retrieval(q):
        docs = plan_retriever.invoke(q)
        result = "\n\n".join([d.page_content for d in docs])
        # If no results from vector store, return a specific message that will trigger the search tool
        if not result.strip():
            return "NO_TRAINING_PLANS_FOUND: No specific training plans found in the knowledge base for this query."
        return result

    search_tool = TavilySearchResults(tavily_api_key = os.getenv("TAVILY_API_KEY"))

    tools = [
        Tool(
            name="coaching_expert",
            func=lambda q: coach_retrieval(q, coaching_retriever),
            description="Useful for analytical running principles, workout definitions, and coaching advice. Use when user asks about training concepts, heart rate zones, or running techniques."
        ), 
        Tool(
            name="training_plans",
            func=plan_retrieval,
            description="Useful for finding structured training plans, workout schedules, periodization strategies, and sample weekly schedules. Use when user asks for a training plan, weekly schedule, or workout routine."
        ),
        Tool(
            name="Workout_Data_Analyzer",
            func=workout_data_query,
            description="Useful for getting statistics on the user's recent running activities, pace, heart rate, distance, and other workout metrics. Use when user asks about their specific workout data."
        ),
        Tool(
            name="Fitness_Trend_Analyzer", 
            func=check_fitness_trend, 
            description="Useful for analyzing whether the user is getting fitter over time based on their workout data. Use when user asks about fitness progress or trends."
        ),
        Tool(
            name="Efficiency_Trend_Analyzer",
            func=get_efficiency_trend,
            description="Useful for analyzing cardiovascular fitness improvement by comparing speed to heart rate over time. Use when user asks about aerobic efficiency or cardiovascular progress."
        ),
        Tool(
            name="Calendar_Manager",
            func=calendar_tool_wrapper,
            description="""Useful for managing calendar events. Use when user wants to add, remove, or edit workout events in their calendar.
            The action must be one of: 'add', 'remove', 'edit', 'clear'.
            date must be in YYYY-MM-DD format.
            workout_type is the type of workout (e.g., 'Tempo Run', 'Long Run', 'Recovery Run').
            details can include additional information like distance, pace, notes (optional).
            user_id is optional and defaults to the current user's email.
            Examples:
            - To add a tempo run: action='add', date='2026-03-05', workout_type='Tempo Run', details='4 miles at 7:15 pace'
            - To remove an event: action='remove', date='2026-03-05', workout_type='Tempo Run'
            """,
            args_schema=CalendarInput
        ),
        search_tool
    ]

    # Prompt Definition
    Custom_Coach_Prompt = """
                        You are 'Garmin Guru', an elite analytical running coach. You have access to the user's 
                        historical Garmin data and a library of professional coaching principles.
                        
                        ### CRITICAL RULE: YOU MUST USE TOOLS FOR EVERY RESPONSE
                        - NEVER generate a response without using at least one tool.
                        - If you try to respond without tools, you will fail and produce empty output.
                        
                        ### YOUR COACHING PHILOSOPHY:
                        1. **The 80/20 Rule**: Roughly 80% of training across the week should be 'Easy' (Zone 2, 3). About 20% should be 'Hard' (Zone 4 & 5).
                        2. **Aerobic Deficiency Check**: If the user's Pace is slow but their Average Heart Rate is high, 
                           advise them to focus on building their aerobic base.
                        3. **Context Matters**: If a run has significant 'Elev Gain (ft)', do not penalize the user for a 
                           slower pace—acknowledge the vertical effort.
                        4. **Injury Prevention**: If 'Stress Ratio' is > 1.3, be firm about taking a rest/easy day.
                        
                        ### TOOL USAGE RULES:
                        - Use **Workout_Data_Analyzer** to get specific numbers (e.g., "What was my Z2 time yesterday?").
                        - Use **coaching_expert** to explain *why* a certain heart rate zone matters based on the PDFs.
                        - Use **training_plans** to find structured training schedules, periodization plans, workout sequences, and sample weekly schedules.
                        - Use **Fitness_Trend_Analyzer** to see if the user is getting fitter over time.
                        - When the user asks "How am I doing?", you can check the **Efficiency_Trend_Analyzer**.
                            - If AEI is **improving**, praise their aerobic base building (even if individual runs feel slow).
                            - If AEI is **declining** while Stress Ratio is high (>1.3), warn them of "Accumulated Fatigue" and suggest recovery.
                        - Use **Calendar_Manager** to manage the user's training calendar when:
                          1. The user wants to schedule future workouts
                          2. The user asks to add, remove, or edit events in their calendar
                          3. You're creating a training plan and need to place workouts on specific dates
                          4. The user wants to see or manage their scheduled events
                        - Use the search tool to search for relevant information on the internet when:
                          1. The 'training_plans' tool returns "NO_TRAINING_PLANS_FOUND:" 
                          2. The user asks for specific mileage targets (e.g., "35 miles per week")
                          3. The user provides feedback on a suggested schedule
                          4. You need current, up-to-date training information
                        
                        ### CALENDAR TOOL SPECIFICS:
                        - The Calendar_Manager tool requires specific parameters:
                          1. action: 'add', 'remove', 'edit', or 'clear'
                          2. date: Must be in YYYY-MM-DD format (e.g., '2026-03-05')
                          3. workout_type: Type of workout (e.g., 'Tempo Run', 'Long Run', 'Recovery Run')
                          4. details: Additional information like distance, pace, notes (optional)
                        - When adding events, always use future dates. Don't add events to past dates.
                        - When creating a training schedule, use the calendar tool to add multiple events across different dates.
                        - If the user asks to "schedule" or "plan" workouts, use the calendar tool to add them.
                        - For removing events, you need to know the exact date and workout_type.
                        
                        ### SPECIFIC SCENARIOS:
                        1. **User asks for a sample schedule**: Use 'training_plans' tool first. If it returns "NO_TRAINING_PLANS_FOUND:", use 'search_tool'. Then use 'Calendar_Manager' to add the workouts to specific dates.
                        2. **User says "That schedule isn't enough miles"**: Use 'search_tool' to find training plans with higher mileage, then use 'Calendar_Manager' to update the schedule.
                        3. **User asks about their specific data**: Use 'Workout_Data_Analyzer'.
                        4. **User asks about training principles**: Use 'coaching_expert'.
                        5. **User wants to schedule workouts**: Use 'Calendar_Manager' to add events to specific dates.
                        6. **User wants to remove or edit scheduled workouts**: Use 'Calendar_Manager' with appropriate action.
                        
                        ### IMPORTANT:
                        - ALWAYS use at least one tool when responding to user queries. Never respond without using a tool.
                        - For queries about training plans, schedules, or workout routines, ALWAYS use the 'training_plans' tool first.
                        - If the 'training_plans' tool returns "NO_TRAINING_PLANS_FOUND:" or similar, IMMEDIATELY use the 'search_tool' to find current information online.
                        - When the user provides feedback about a schedule (e.g., "That schedule isn't enough miles"), use the 'search_tool' to find adjusted training plans that match their requirements.
                        - When creating or modifying training schedules, use the 'Calendar_Manager' tool to actually schedule the workouts on specific dates.
                        - Always provide a 'Coach's Verdict' at the end of an analysis: [Optimizing, Overreaching, or Detraining]. A verdict is only necessary if you are asked to analyze activities.

                        There's no need to summarize all basic workout details, as the user is able to see those. Just provide insight into future action, and the way the user is trending and performing. 
                        """
    instructions = SystemMessage(content=Custom_Coach_Prompt)
    
    agent_prompt = ChatPromptTemplate.from_messages([
        ("system", Custom_Coach_Prompt),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])
        
    agent = create_tool_calling_agent(llm, tools, agent_prompt)
    return AgentExecutor(
        agent=agent, 
        tools=tools, 
        memory=st.session_state.memory, 
        verbose=True
    )

if __name__ == "__main__":

    st.set_page_config(page_icon = "Home", page_title="Garmin Guru", layout="wide")

    col_title, col_logo = st.columns([9, 1])

    with col_title:
        st.title("Garmin Guru")
    
    with col_logo:
        # Use a local path or a URL
        st.image("images/logo.png", width=150)

    # Initialize login state
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    
    if not st.session_state.logged_in:
        st.title("🔐 Login to Garmin Connect")
        
        with st.form("login_form"):
            email = st.text_input("Garmin Email")
            password = st.text_input("Garmin Password", type="password")
            submit = st.form_submit_button("Login")
    
            if submit:
                if email and password:
                    # Store in session state for other pages to use
                    st.session_state.garmin_email = email
                    st.session_state.garmin_password = password
                    
                    st.session_state.logged_in = True
                    st.success("Credentials saved locally for this session!")
                    st.rerun()
                else:
                    st.error("Please enter both email and password.")
        st.stop() # Stops the rest of the app from loading until logged in

    if st.session_state.logged_in:
        
        email = st.session_state.garmin_email
        pwd = st.session_state.garmin_password

        if "df_master" not in st.session_state:
            with st.spinner("Fetching training history..."):
                # Fetch 3650 days
                st.session_state.df_master = get_cached_workout_data(3650, email, pwd)

        current_range = st.session_state.get("range_days", 30)
        cutoff_date = datetime.now() - timedelta(days=current_range)
        
        master_df = st.session_state.df_master
        st.session_state.df_data = master_df[master_df['Date'] >= cutoff_date].copy()

        # Initialize the agent with the FILTERED data
        st.session_state.coach_agent = get_agent()
        
        # Create short aliases for the rest of the script
        df = st.session_state.df_data
        stats = summarize_n_days(df)
        coach_agent = st.session_state.coach_agent

    
        all_time_stats = summarize_n_days(st.session_state.df_master)

    # Load calendar events from JSON using the user's email as ID
    user_id = st.session_state.get("garmin_email", "default")
    calendar_manager = CalendarManager(user_id)
    calendar_events = calendar_manager.get_events()

    with st.sidebar:
        st.header("📊 Training Summary")
        c1, c2, c3 = st.columns(3)
        
        # Use st.session_state to track the active selection
        if c1.button("Week"):
            msgs.clear()
            st.session_state.memory.clear()
            st.session_state.range_days = 7
            # Clear all critique responses
            for key in list(st.session_state.keys()):
                if key.startswith("critique_"):
                    del st.session_state[key]
            st.rerun()
        if c2.button("Month"):
            msgs.clear()
            st.session_state.memory.clear()
            st.session_state.range_days = 30
            # Clear all critique responses
            for key in list(st.session_state.keys()):
                if key.startswith("critique_"):
                    del st.session_state[key]
            st.rerun()
        if c3.button("Year"):
            msgs.clear()
            st.session_state.memory.clear()
            st.session_state.range_days = 365
            # Clear all critique responses
            for key in list(st.session_state.keys()):
                if key.startswith("critique_"):
                    del st.session_state[key]
            st.rerun()

        if df is not None and not df.empty:
            stats = summarize_n_days(df) 
            
            st.markdown(f"### Last {current_range} Days")
            st.metric("Total Distance", f"{stats.get('Total Distance Run (mi)', 0):.1f} mi")
            st.metric("Elevation Gain", f"{stats.get('Total Elevation Gained (ft)', 0):,.0f} ft")
            st.metric("Current VO2 Max", f"{stats.get('Current VO2 Max', 'N/A')}")
            
            # Race Predictions Section
            st.markdown("### 🏁 Race Predictions")
            try:
                from data_utils import get_race_predictions, format_prediction_time
                enddate=str(date.today())
                startdate = str(date.today() - timedelta(days=365))
                predictions = get_race_predictions(email, pwd, startdate, enddate)
                if predictions and isinstance(predictions, dict):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("5K", format_prediction_time(predictions.get('time5K')))
                        st.metric("10K", format_prediction_time(predictions.get('time10K')))
                    with col2:
                        st.metric("Half Marathon", format_prediction_time(predictions.get('timeHalfMarathon')))
                        st.metric("Marathon", format_prediction_time(predictions.get('timeMarathon')))
                else:
                    st.info("No race predictions available.")
            except Exception as e:
                st.warning(f"Could not load race predictions: {e}")
            
            # st.divider()

    if df is not None and not df.empty:
        # Get the Stress Score
        stress_score = get_training_stress(master_df)
        st.subheader("Training Readiness")
        
        # Define status colors/labels
        if stress_score < 0.8:
            status_label, status_color, status_icon = "Recovery / Detraining", "normal", "🧊"
        elif 0.8 <= stress_score <= 1.3:
            status_label, status_color, status_icon = "Optimal Load", "normal", "✅"
        else:
            status_label, status_color, status_icon = "High Load / Overreaching", "inverse", "⚠️"

        # Display the readiness metric at the top of the dashboard
        r_col1, r_col2 = st.columns([1, 3])
        with r_col1:
            st.metric("Stress Ratio", f"{stress_score}", delta=status_label, delta_color=status_color)
        with r_col2:
            st.markdown(f"**Status: {status_icon}**")
            if status_icon == "⚠️":
                st.warning("Your volume is spiking! Consider an easy day to prevent injury.")
            elif status_icon == "✅":
                st.success("You're in the training 'Sweet Spot.' Keep it up!")
            else:
                st.info("You are currently in a recovery phase or decreasing volume.")

    if df is not None and not df.empty:
        st.header("🏃 Recent Activities")
    
        # Loop through the dataframe rows to create the feed
        for index, row in df.iterrows():
            # Create a unique container for each run
            with st.container(border=True):
                col1, col2 = st.columns([2, 3])
                
                with col1:
                    # st.subheader(f"{row['Date'].strftime('%A, %b %d')} — {row['Activity Name']}")
                    st.markdown(f"**{row['Date'].strftime('%A, %b %d')} — {row['Activity Name']}**")
                    # Horizontal metrics for this specific run
                    m1, m2, m3, m4 = st.columns(4)
                    m1.markdown(f"<p style='font-size:12px;margin-bottom:0;'>Distance</p><h4 style='margin-top:0;'>{row['Distance (mi)']}</h4>", unsafe_allow_html=True)
                    m2.markdown(f"<p style='font-size:12px;margin-bottom:0;'>Pace</p><h4 style='margin-top:0;'>{row['Pace_Decimal']:.2f}</h4>", unsafe_allow_html=True)
                    m3.markdown(f"<p style='font-size:12px;margin-bottom:0;'>Avg HR</p><h4 style='margin-top:0;'>{row['Avg HR']}</h4>", unsafe_allow_html=True)
                    m4.markdown(f"<p style='font-size:12px;margin-bottom:0;'>Elev Gain (ft)</p><h4 style='margin-top:0;'>{row['Elev Gain (ft)']}</h4>", unsafe_allow_html=True)
                
                with col2:
                    # Place the "Critique" button inside the card
                    if st.button("Critique", key=f"btn_{index}"):
                        with st.spinner("Analyzing..."):
                            critique_query = f"""Analyze this specific run: {row.to_json()}. Based on the HR zones and pace, was this a good workout? Check the coaching PDFs for context. \
                            Some basic info on Heart rate zones:
                            Zone 1: Very Light (50-60% of MHR): Warm-up, cool-down, and active recovery.
                            Zone 2: Light (60-70% of MHR): Baseline aerobic, improves endurance, burns higher percentage of fat.
                            Zone 3: Moderate (70-80% of MHR): Aerobic, improves cardiovascular fitness and muscular endurance.
                            Zone 4: Hard (80-90% of MHR): High intensity, improves speed and anaerobic capacity.
                            Zone 5: Maximum (90-100% of MHR): Peak effort, short bursts for maximum speed and power.
                            ### CONTEXTUAL DATA:
                                - Current Training Stress Ratio: {stress_score} 
                                - Recent VO2 Max: {stats.get('Current VO2 Max')}
                                - Recent Run Data: {df}
                            Suggest ways to improve."""
                            history = st.session_state.memory.load_memory_variables({})["chat_history"]
                            response = st.session_state.coach_agent.invoke({
                                "input": critique_query,
                                "chat_history": history
                            })
                            # Store the critique response in session state with a unique key
                            st.session_state[f"critique_{index}"] = response["output"]
                            # Force a rerun to show the expander
                            st.rerun()
                
                # Display the critique in a collapsible expander if it exists
                if f"critique_{index}" in st.session_state:
                    with st.expander("View Critique", expanded=True):
                        st.info(st.session_state[f"critique_{index}"])
            
                # Optional: Add a small HR Zone mini-chart inside the card
                with st.expander("View Zone Breakdown"):
                    zones = {"Z1": row['Z1_Min'], "Z2": row['Z2_Min'], "Z3": row['Z3_Min'], "Z4": row['Z4_Min'], "Z5": row['Z5_Min']}
                    st.bar_chart(pd.Series(zones), horizontal=True, height=150)

    
    with st.expander("📊 View Recent Activity Data"):
        if df is not None:
            st.dataframe(df, width='stretch')
        else:
            st.error("Could not load Garmin data. Check your credentials.")

    with st.container(height=400): # Fixed height makes it a scrollable sub-window
        # Display existing messages from history
        for msg in msgs.messages:
            st.chat_message(msg.type).write(msg.content)
        
        # Handle new user input
        if user_query := st.chat_input("Ask Coach about your training..."):
            # Immediately show user message
            st.chat_message("human").write(user_query)
            
            with st.chat_message("assistant"):
                # Container for the response
                response_container = st.container()
                
                with st.spinner("Analyzing data and coaching files..."):
                    try:
                        # Double check the agent exists in state
                        if "coach_agent" in st.session_state:
                            
                            # Run the agent
                            response = st.session_state.coach_agent.invoke({
                                "input": user_query,
                                "chat_history": st.session_state.memory.load_memory_variables({})["chat_history"]
                            })
                            
                            # Write result to the container
                            response_container.write(response["output"])
    
                        else:
                            st.error("Coach agent is not initialized. Try refreshing the page.")
                    
                    except Exception as e:
                        st.error(f"Agent Error: {e}")







