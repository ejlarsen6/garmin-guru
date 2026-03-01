import streamlit as st
from langchain_community.chat_message_histories import StreamlitChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import os
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
from langchain_community.vectorstores import FAISS
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
from data_utils import get_cached_workout_data, summarize_n_days, get_training_stress, get_workout_dataframe_n_days, check_fitness_trend
from style_utils import apply_custom_style
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

    # Vector Stores
    # Coaching store
    if os.path.exists("docs/coaching-store"):
        coaching_store = FAISS.load_local("docs/coaching-store", embeddings, allow_dangerous_deserialization=True)
        coaching_retriever = coaching_store.as_retriever()
    else:
        all_docs = []
        for file in os.listdir("./docs/"):
            if file.endswith(".pdf"):
                loader = PyPDFLoader(f"./docs/{file}")
                all_docs.extend(loader.load())
        
        coaching_chunks = splitter.split_documents(all_docs)
        coaching_store = FAISS.from_documents(coaching_chunks, embeddings)
        coaching_retriever = coaching_store.as_retriever()
        coaching_store.save_local("docs/coaching-store")
    
    # Training plans store
    training_plans_path = "docs/training_plans"
    if os.path.exists("docs/plan-store"):
        plan_store = FAISS.load_local("docs/plan-store", embeddings, allow_dangerous_deserialization=True)
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
            plan_store = FAISS.from_documents(plan_chunks, embeddings)
            plan_retriever = plan_store.as_retriever()
            plan_store.save_local("docs/plan-store")
        else:
            # Create an empty vector store if no documents
            plan_store = FAISS.from_documents([], embeddings)
            plan_retriever = plan_store.as_retriever()
            plan_store.save_local("docs/plan-store")

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

    def plan_retrieval(q):
        docs = plan_retriever.invoke(q)
        return "\n\n".join([d.page_content for d in docs])

    search_tool = TavilySearchResults(tavily_api_key = os.getenv("TAVILY_API_KEY"))

    tools = [
        Tool(
            name="coaching_expert",
            func=lambda q: coach_retrieval(q, coaching_retriever),
            description="Search this for analytical running principles and workout definitions."
        ), 
        Tool(
            name="training_plans",
            func=plan_retrieval,
            description="Search this for structured training plans, workout schedules, and periodization strategies."
        ),
        Tool(
        name="Workout_Data_Analyzer",
        func=workout_data_query,
        description="Query this to get stats on the user's recent running activities, pace, and heart rate."
        ),
        Tool(
            name="Fitness_Trend_Analyzer", 
            func=check_fitness_trend, 
            description="Use this to see if the user is actually getting fitter over time."
        ),
        search_tool
    ]

    # Prompt Definition
    Custom_Coach_Prompt = """
                        You are 'Garmin Guru', an elite analytical running coach. You have access to the user's 
                        historical Garmin data and a library of professional coaching principles.
                        
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
                        - Use **training_plans** to find structured training schedules, periodization plans, and workout sequences.
                        - Use **Fitness_Trend_Analyzer** to see if the user is  getting fitter over time.
                        - Use the search tool to search for relevant information on the internet.
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

    with st.sidebar:
        st.header("📊 Training Summary")
        c1, c2, c3 = st.columns(3)
        
        # Use st.session_state to track the active selection
        if c1.button("Week"):
            msgs.clear()
            st.session_state.memory.clear()
            st.session_state.range_days = 7
            st.rerun()
        if c2.button("Month"):
            msgs.clear()
            st.session_state.memory.clear()
            st.session_state.range_days = 30
            st.rerun()
        if c3.button("Year"):
            msgs.clear()
            st.session_state.memory.clear()
            st.session_state.range_days = 365
            st.rerun()

        if df is not None and not df.empty:
            stats = summarize_n_days(df) 
            
            st.markdown(f"### Last {current_range} Days")
            st.metric("Total Distance", f"{stats.get('Total Distance Run (mi)', 0):.1f} mi")
            st.metric("Elevation Gain", f"{stats.get('Total Elevation Gained (ft)', 0):,.0f} ft")
            st.metric("Current VO2 Max", f"{stats.get('Current VO2 Max', 'N/A')}")
    
            st.divider()
            
            # Race Predictions Section
            st.markdown("### 🏁 Race Predictions")
            try:
                from data_utils import get_race_predictions, format_prediction_time
                enddate=str(date.today())
                startdate = str(date.today() - timedelta(days=365))
                predictions = get_race_predictions(email, pwd, startdate, enddate)
                if predictions:
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
            
            st.divider()

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
        st.divider()
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
                            st.info(response["output"])
            
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







