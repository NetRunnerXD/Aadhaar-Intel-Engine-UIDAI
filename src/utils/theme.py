import streamlit as st

def setup_page():
    st.set_page_config(page_title="UIDAI Insight Engine", page_icon="🇮🇳", layout="wide")
    
    st.markdown("""
    <style>
        /* --- GLOBAL DARK THEME --- */
        .stApp { 
            background-color: #0b0f19; /* Deep Slate */
            color: #e2e8f0; /* Light Grey Text */
            font-family: 'Segoe UI', sans-serif; 
        }
        
        /* HEADINGS */
        h1, h2, h3 { color: #ffffff !important; font-weight: 600; }
        h4, h5, h6 { color: #cbd5e1 !important; }

        /* SIDEBAR: Darker Navy */
        section[data-testid="stSidebar"] { 
            background-color: #080c14; 
            border-right: 1px solid #1e293b; 
        }
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] label {
            color: #e2e8f0 !important;
        }
        
        /* METRICS CARDS: Dark Cards with Neon Accent */
        div[data-testid="metric-container"] { 
            background-color: #151b2b; 
            border: 1px solid #2d3748; 
            border-left: 4px solid #00f2ff; /* Neon Cyan */
            padding: 15px; 
            border-radius: 8px; 
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }
        
        /* Metric Numbers */
        div[data-testid="stMetricValue"] { 
            color: #00f2ff !important; /* Neon Cyan */
            font-size: 26px !important; 
            font-family: 'Courier New', monospace;
            font-weight: 700;
        }
        
        /* Metric Labels */
        div[data-testid="stMetricLabel"] { 
            color: #94a3b8 !important; /* Muted Blue-Grey */
            text-transform: uppercase; 
            letter-spacing: 1px;
            font-size: 13px;
        }

        /* TABS: Cyber Style */
        .stTabs [data-baseweb="tab-list"] {
            gap: 4px;
            background-color: transparent;
        }
        .stTabs [data-baseweb="tab"] {
            height: 50px;
            background-color: #1e293b;
            border-radius: 4px 4px 0 0;
            color: #94a3b8;
            border: 1px solid #334155;
            border-bottom: none;
        }
        .stTabs [aria-selected="true"] {
            background-color: #0b0f19;
            color: #00f2ff; /* Active Tab Neon */
            border-top: 2px solid #00f2ff;
        }

        /* DATA TABLES */
        div[data-testid="stDataFrame"] {
            background-color: #151b2b;
            border: 1px solid #2d3748;
        }
        div[data-testid="stDataFrame"] thead th {
            background-color: #1e293b !important;
            color: #e2e8f0 !important;
        }

        /* BUTTONS */
        button[kind="primary"] {
            background-color: #00f2ff !important;
            color: #000000 !important;
            border: none;
            font-weight: 600;
        }
        button[kind="secondary"] {
            background-color: transparent !important;
            color: #00f2ff !important;
            border: 1px solid #00f2ff;
        }
        
        /* SCROLLBARS */
        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        ::-webkit-scrollbar-track {
            background: #0b0f19; 
        }
        ::-webkit-scrollbar-thumb {
            background: #1e293b; 
            border-radius: 4px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: #00f2ff; 
        }
    </style>
    """, unsafe_allow_html=True)