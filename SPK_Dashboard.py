import streamlit as st

st.set_page_config(
    page_title="SPK Dashboard", 
    page_icon="⚽", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Test Supabase connection on startup
try:
    from supabase_helpers import test_supabase_connection
    if test_supabase_connection():
        st.success("🌐 Supabase connected successfully!")
    else:
        st.warning("⚠️ Supabase connection issue - some features may not work")
except ImportError:
    st.info("📍 Using legacy database mode")

# Home pagina
def show_home():
    st.title("🏠 SPK Dashboard")
    st.markdown("### Welkom bij het SPK Professional Football Analytics Dashboard")
    
    st.markdown("""
    Dit dashboard biedt een complete toolkit voor moderne voetbalanalyse en coaching:
    
    **📊 Analyse & Overzichten**
    - Real-time team en speler statistieken
    - Uitgebreide performance metrics
    - Wekelijkse samenvattingen
    
    **🏃‍♂️ Fysieke Training**
    - GPS data analyse
    - Trainingsbelasting monitoring
    - Fysieke prestatie tracking
    
    **⚽ Tactiek & Coaching** 
    - Coaching principes library
    - Training planning tools
    - Tactische analyse
    
    **👥 Spelersbeheer**
    - Speler administratie
    - Progressie tracking
    - Player engagement
    
    **🏥 Medisch & Welzijn**
    - Blessure rapportage
    - Medische tracking
    """)

# Hoofdnavigatie setup met gecategoriseerde structuur
if __name__ == "__main__":
    # CSS voor professionele styling
    st.markdown("""
    <style>
    .main-header {
        background: linear-gradient(90deg, #1f4e79 0%, #2e86ab 100%);
        padding: 15px 20px;
        margin: -1rem -1rem 2rem -1rem;
        color: white;
        text-align: center;
        font-size: 1.8rem;
        font-weight: bold;
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Header
    st.markdown('<div class="main-header">⚽ SPK Dashboard - Professional Football Analytics</div>', unsafe_allow_html=True)
    
    # Gecategoriseerde navigatie structuur volgens correcte Streamlit API
    pages = {
        "🏠 Dashboard": [
            st.Page(show_home, title="Home", icon="🏠"),
            st.Page("pages/Wekelijkse Samenvatting.py", title="Wekelijkse Samenvatting", icon="📋")
        ],
        
        "📊 Analyse & Overzichten": [
            st.Page("pages/03_Team_Overzicht.py", title="Team Overzicht", icon="👥"),
            st.Page("pages/Team_Overzicht_Compleet.py", title="Team Compleet", icon="🏆"),
            st.Page("pages/02_Individueel_Overzicht.py", title="Individueel Overzicht", icon="📈"),
            st.Page("pages/Spelersoverzicht.py", title="Spelersoverzicht", icon="👤")
        ],
        
        "🏃‍♂️ Fysieke Training": [
            st.Page("pages/Fysieke Training Analyse.py", title="Fysieke Analyse", icon="🔬"),
            st.Page("pages/Fysieke Data Import.py", title="Data Import", icon="📊"),
            st.Page("pages/01_Training_Planning.py", title="Loopvorm Planner", icon="🎯")
        ],
        
        "⚽ Tactiek & Coaching": [
            st.Page("pages/05_Match_Analysis.py", title="Match Analysis", icon="⚽"),
            st.Page("pages/Coaching Principes.py", title="Coaching Principes", icon="🎯"),
            st.Page("pages/Coaching Tools.py", title="Coaching Tools", icon="🧰"),
            st.Page("pages/SSG_Calculator.py", title="SSG Calculator",) 
        ],
        
        "📅 Planning & Organisatie": [
            st.Page("pages/04_Trainingskalender.py", title="Trainingskalender", icon="📅"),
            st.Page("pages/Training Planner.py", title="Training Planner", icon="📝"),
            st.Page("pages/Periodisering Tool.py", title="Periodisering", icon="🗓️")
        ],
        
        "👥 Spelersbeheer": [
            st.Page("pages/Spelersbeheer.py", title="Spelersbeheer", icon="⚽"),
            st.Page("pages/Speler Progressie.py", title="Speler Progressie", icon="📈")
        ],
        
        "🏥 Medisch & Welzijn": [
            st.Page("pages/Blessure_Rapportage.py", title="Blessure Rapportage", icon="🩹")
        ]
    }
    
    # Initialiseer navigation met correcte API
    pg = st.navigation(pages, position="top")
    pg.run()
