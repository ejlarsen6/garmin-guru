import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

def create_themed_line_chart(df, x_col, y_col, title):
    fig = px.line(df, x=x_col, y=y_col, title=title, template="plotly_dark")
    
    # Match Streamlit background (usually #0e1117 or similar)
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font_color="#fafafa",
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)"),
        hovermode="x unified"
    )
    # Make the line smooth and "Neon"
    fig.update_traces(line=dict(width=3, color="#00d4ff"))
    
    return fig

def apply_custom_style():
    st.markdown("<div id='top'></div>", unsafe_allow_html=True)
    
    st.markdown("""
    <script>
        // Force the window to scroll to the top element on load
        var topElement = window.parent.document.getElementById('top');
        if (topElement) {
            topElement.scrollIntoView();
        }
    </script>
    
    <style>
    /* Global App Background */
    .stApp {
        background-color: #0e1117;
    }

    /* Universal Text & Header Visibility */
    html, body, [class*="css"], .stMarkdown, [data-testid="stMarkdownContainer"], 
    h1, h2, h3, h4, h5, h6, label, p, summary, [data-testid="stWidgetLabel"] p,
    [data-testid="stSidebarNav"] span, div[data-baseweb="select"] span {
        color: #ffffff !important;
        letter-spacing: -0.2px;
    }

    /* Specific Header Weight & Metric Labels */
    h1, h2, h3 { font-weight: 700 !important; }
    [data-testid="stMetricLabel"] { color: #8899a6 !important; }
    [data-testid="stMetricValue"] { font-size: 2rem; color: #0078ff; }

    /* Glassmorphism Containers: Chat Bubbles, Expanders, and Sidebar */
    [data-testid="stChatMessage"], 
    .st-expanderHeader, 
    [data-testid="stSidebar"] > div:first-child {
        background-color: rgba(255, 255, 255, 0.05) !important;
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 15px;
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1);
    }
    
    /* Style for expander headers to ensure text is visible */
    .st-expanderHeader p,
    .st-expanderHeader span,
    .st-expanderHeader div,
    .st-expanderHeader label {
        color: #ffffff !important;
    }
    
    /* Make sure the expander header button is styled correctly */
    .st-expanderHeader button {
        background-color: transparent !important;
        color: #ffffff !important;
        border: none !important;
        box-shadow: none !important;
        outline: none !important;
    }
    
    .st-expanderHeader button:hover {
        background-color: rgba(255, 255, 255, 0.1) !important;
        color: #ffffff !important;
    }

    /* Sidebar Specific Styling */
    [data-testid="stSidebar"] {
        background-color: #161b22;
        border-right: 1px solid #30363d;
    }
    
    /* Coach Message Accent */
    [data-testid="stChatMessageContent"]:has(div[aria-label="assistant"]) {
        border-left: 3px solid #0078ff !important;
    }

    /* Specific styling for Buttons (Login, etc.) */
    .stButton>button {
        background-color: #1a1c23 !important; /* Dark charcoal */
        color: #ffffff !important;           /* Pure white text */
        border: 1px solid #0078ff !important; /* Garmin Blue border */
        border-radius: 8px;
        padding: 0.5rem 1rem;
        transition: all 0.3s ease;
        font-weight: 500 !important;
        box-shadow: none !important;
        outline: none !important;
    }

    /* Ensure all button text is always visible */
    button, .stButton>button, .stButton>button:link, .stButton>button:visited,
    .stButton>button:hover, .stButton>button:active, .stButton>button:focus {
        color: #ffffff !important;
    }

    /* Hover state to make it feel interactive */
    .stButton>button:hover {
        background-color: #0078ff !important; /* Blue background on hover */
        color: #ffffff !important;
        box-shadow: 0 0 15px rgba(0, 120, 255, 0.4);
    }

    /* Active/Click state */
    .stButton>button:active {
        transform: scale(0.98);
        background-color: #0056cc !important;
        color: #ffffff !important;
    }

    /* Make sure form submit buttons are also styled */
    div[data-testid="stForm"] button {
        background-color: #1a1c23 !important;
        color: #ffffff !important;
        border: 1px solid #0078ff !important;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: 500 !important;
        box-shadow: none !important;
        outline: none !important;
    }

    div[data-testid="stForm"] button:hover {
        background-color: #0078ff !important;
        color: #ffffff !important;
        border: 1px solid #0078ff !important;
    }

    /* Style for critique buttons specifically */
    button[kind="secondary"], button[kind="primary"] {
        background-color: #1a1c23 !important;
        color: #ffffff !important;
        border: 1px solid #0078ff !important;
    }

    button[kind="secondary"]:hover, button[kind="primary"]:hover {
        background-color: #0078ff !important;
        color: #ffffff !important;
    }

    /* Chat Input & Bottom UI */
    [data-testid="stChatInput"] {
        background-color: #1a1c23 !important;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 20px;
    }
    
    [data-testid="stChatInputTextArea"] {
        color: #ffffff !important;
    }

    [data-testid="stChatInputButton"] {
        color: #0078ff !important;
        background-color: transparent !important;
    }

    /* Hidden Header Elements */
    [data-testid="stHeader"] {
        visibility: hidden;
        height: 0%;
    }
    
    /* Ensure all buttons have visible text */
    button, .stButton button, .stButton button p, .stButton button span,
    .stButton button div, .stButton button label {
        color: #ffffff !important;
    }
    
    /* Make sure button text is always white */
    .stButton button {
        color: #ffffff !important;
    }
    
    /* Style for week/month/year buttons in sidebar */
    .stButton button[kind="secondary"] {
        background-color: #1a1c23 !important;
        color: #ffffff !important;
        border: 1px solid #0078ff !important;
    }
    
    .stButton button[kind="secondary"]:hover {
        background-color: #0078ff !important;
        color: #ffffff !important;
    }
    
    /* Dark Chat Input Styling - Target the entire container */
    [data-testid="stChatInput"] {
        background-color: #374151 !important; /* Dark gray background */
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
        border-radius: 12px;
        padding: 8px;
    }

    /* Target the text area inside */
    [data-testid="stChatInput"] textarea {
        background-color: #374151 !important;
        color: #ffffff !important;
        border: none !important;
        box-shadow: none !important;
    }

    /* Target the container that holds the text area */
    [data-testid="stChatInput"] > div {
        background-color: #374151 !important;
    }

    /* Placeholder text */
    [data-testid="stChatInput"] textarea::placeholder {
        color: #a0aec0 !important;
    }

    /* Focus state for the entire container */
    [data-testid="stChatInput"]:focus-within {
        border: 1px solid #0078ff !important;
        box-shadow: 0 0 10px rgba(0, 120, 255, 0.4);
        background-color: #4b5563 !important;
    }

    /* Ensure all child elements have appropriate background on focus */
    [data-testid="stChatInput"]:focus-within textarea,
    [data-testid="stChatInput"]:focus-within > div {
        background-color: #4b5563 !important;
    }

    /* Style the send button */
    [data-testid="stChatInput"] button {
        background-color: #0078ff !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
    }

    [data-testid="stChatInput"] button:hover {
        background-color: #0056cc !important;
    }

    /* Style for form submit buttons (like login) */
    div[data-testid="stFormSubmitButton"] button,
    div[data-testid="stFormSubmitButton"] button p,
    div[data-testid="stFormSubmitButton"] button span {
        background-color: #1a1c23 !important;
        color: #ffffff !important;
        border: 1px solid #0078ff !important;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: 500 !important;
        box-shadow: none !important;
        outline: none !important;
    }
    
    div[data-testid="stFormSubmitButton"] button:hover {
        background-color: #0078ff !important;
        color: #ffffff !important;
        border: 1px solid #0078ff !important;
    }
    
    [class="st-emotion-cache-128upt6 e1td4qo63"] {
        background-color: transparent;
    }
    
    </style>
    """, unsafe_allow_html=True)
