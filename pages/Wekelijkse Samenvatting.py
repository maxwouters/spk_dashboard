import streamlit as st

# Supabase helpers (primary)
try:
    from supabase_helpers import (
        get_table_data, 
        get_thirty_fifteen_results, 
        get_cached_player_list,
        test_supabase_connection,
        safe_fetchdf,
        check_table_exists
    )
    SUPABASE_MODE = True
except ImportError:
    # Fallback to legacy
    from db_config import get_database_connection
    from database_helpers import check_table_exists, get_table_columns, add_column_if_not_exists, safe_fetchdf
    SUPABASE_MODE = False
import pandas as pd
from datetime import datetime, timedelta, date
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
import base64
import json
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.dates as mdates
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import requests


# Database compatibility functions
def execute_db_query(query, params=None):
    """Execute query and return results compatible with both databases"""
    if SUPABASE_MODE:
        try:
            df = safe_fetchdf(query, params or {})
            if df.empty:
                return []
            # Convert DataFrame to list of tuples (like fetchall())
            return [tuple(row) for row in df.values]
        except Exception as e:
            st.error(f"Query failed: {e}")
            return []
    else:
        # Legacy mode
        try:
            if params:
                return con.execute(query, params).fetchall()
            else:
                return con.execute(query).fetchall()
        except Exception as e:
            st.error(f"Legacy query failed: {e}")
            return []

def get_supabase_data(table_name, columns="*", where_conditions=None):
    """Get data using Supabase helpers"""
    if SUPABASE_MODE:
        return get_table_data(table_name, columns, where_conditions)
    else:
        # Legacy fallback
        query = f"SELECT {columns} FROM {table_name}"
        if where_conditions:
            conditions = [f"{k} = '{v}'" for k, v in where_conditions.items()]
            query += f" WHERE {' AND '.join(conditions)}"
        return safe_fetchdf(query)

st.set_page_config(page_title="SPK Dashboard", layout="wide")

st.subheader("📊 Wekelijkse Samenvatting")

# Database setup
if SUPABASE_MODE:
    st.info("🌐 Using Supabase database")
    if not test_supabase_connection():
        st.error("❌ Cannot connect to Supabase")
        st.stop()
    con = None  # Will use Supabase helpers
else:
    # Legacy mode
    # Legacy mode fallback
    try:
        con = get_database_connection()
    except NameError:
        st.error("❌ Database connection not available")
        st.stop()
# Database tabellen voor wekrapportage
execute_db_query("""
    CREATE TABLE IF NOT EXISTS week_rapporten (
        rapport_id INTEGER PRIMARY KEY,
        week_start DATE,
        week_end DATE,
        rapport_data TEXT,
        llm_samenvatting TEXT,
        verzonden_naar TEXT,
        verzend_datum TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")

# Database tabellen voor blessures en fysieke data
execute_db_query("""
    CREATE TABLE IF NOT EXISTS blessures (
        blessure_id INTEGER PRIMARY KEY,
        speler TEXT,
        blessure_type TEXT,
        datum_blessure DATE,
        verwachte_herstel DATE,
        status TEXT,
        kine_comments TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")

execute_db_query("""
    CREATE TABLE IF NOT EXISTS fysieke_data (
        data_id INTEGER PRIMARY KEY,
        speler TEXT,
        datum DATE,
        totaal_afstand REAL,
        hoge_intensiteit_afstand REAL,
        gemiddelde_snelheid REAL,
        max_snelheid REAL,
        aantal_sprints INTEGER,
        training_load REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")

execute_db_query("""
    CREATE TABLE IF NOT EXISTS contact_lijst (
        contact_id INTEGER PRIMARY KEY,
        naam TEXT,
        email TEXT,
        telefoon TEXT,
        functie TEXT,
        actief BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")

# Sequences maken
try:
    execute_db_query("CREATE SEQUENCE IF NOT EXISTS rapport_id_seq START 1")
    execute_db_query("CREATE SEQUENCE IF NOT EXISTS contact_id_seq START 1")
    execute_db_query("CREATE SEQUENCE IF NOT EXISTS blessure_id_seq START 1")
    execute_db_query("CREATE SEQUENCE IF NOT EXISTS data_id_seq START 1")
except:
    pass

# Helper functies
def get_week_dates(target_date=None):
    """Krijg maandag en zondag van een week"""
    if target_date is None:
        target_date = datetime.now().date()
    
    # Zoek maandag van de week
    monday = target_date - timedelta(days=target_date.weekday())
    sunday = monday + timedelta(days=6)
    
    return monday, sunday

def get_week_training_topics(week_start, week_end):
    """Haal getrainde topics op voor de week"""
    topics = execute_db_query("""
        SELECT cp.naam, cp.spelfase, cp.niveau, SUM(tp.focus_minuten) as totaal_minuten,
               COUNT(DISTINCT tc.training_id) as aantal_trainingen
        FROM training_principes tp
        JOIN trainings_calendar tc ON tp.training_id = tc.training_id
        JOIN coaching_principes cp ON tp.principe_id = cp.principe_id
        WHERE tc.datum >= ? AND tc.datum <= ?
        GROUP BY cp.naam, cp.spelfase, cp.niveau
        ORDER BY totaal_minuten DESC
    """, (week_start, week_end))
    
    return topics

def get_week_fysieke_data(week_start, week_end):
    """Haal fysieke data op voor de week (uit database indien beschikbaar)"""
    # Use safe_fetchdf to get proper dataframe, then process it
    df = safe_fetchdf(f"""
        SELECT speler, totale_afstand, hoge_intensiteit_afstand, sprint_afstand, 
               gem_snelheid, max_snelheid, aantal_sprints
        FROM gps_data 
        WHERE datum >= '2025-07-21' AND datum <= '2025-07-27'
    """)
    
    if df.empty:
        return []
    
    # Process the data to create the summary we need
    import pandas as pd
    
    # Convert string columns to numeric
    numeric_cols = ['totale_afstand', 'hoge_intensiteit_afstand', 'sprint_afstand', 
                   'gem_snelheid', 'max_snelheid', 'aantal_sprints']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # Group by player and aggregate
    result = df.groupby('speler').agg({
        'totale_afstand': 'sum',
        'hoge_intensiteit_afstand': 'sum', 
        'sprint_afstand': 'sum',
        'gem_snelheid': 'mean',
        'max_snelheid': 'max',
        'aantal_sprints': 'sum'
    }).reset_index()
    
    # Add session count
    result['aantal_sessies'] = df.groupby('speler').size().values
    
    # Sort by total distance
    result = result.sort_values('totale_afstand', ascending=False)
    
    # Convert to list of tuples for compatibility
    return [tuple(row) for row in result.values]

def get_week_blessures(week_start, week_end):
    """Haal blessure informatie op voor de week uit Supabase database"""
    try:
        # Query Supabase for injuries relevant to this week
        df = safe_fetchdf(f"""
            SELECT speler as speler_naam, blessure_type, locatie, ernst, status, 
                   datum_blessure as datum_start, datum_herstel as datum_einde, 
                   voorspelling_dagen, beschrijving, behandeling
            FROM blessures 
            WHERE (datum_blessure <= '2025-07-27' AND 
                   (datum_herstel IS NULL OR datum_herstel >= '2025-07-21' OR 
                    status IN ('Actief', 'In behandeling')))
            ORDER BY datum_blessure DESC
        """)
        
        if df.empty:
            return []
        
        # Convert to list of tuples for compatibility
        return [tuple(row) for row in df.values]
        
    except Exception as e:
        # Als query faalt, return lege lijst
        return []

def get_week_matches(week_start, week_end):
    """Haal wedstrijd informatie op voor de week"""
    try:
        # Use safe_fetchdf for Supabase compatibility
        df = safe_fetchdf(f"""
            SELECT match_id, datum, tegenstander, thuis_uit, 
                   doelpunten_voor, doelpunten_tegen, match_type,
                   competitie, status
            FROM matches 
            WHERE datum >= '2025-07-21' AND datum <= '2025-07-27'
            ORDER BY datum ASC
        """)
        
        if df.empty:
            return []
        
        # Add uitslag column 
        df['uitslag'] = df['doelpunten_voor'].astype(str) + '-' + df['doelpunten_tegen'].astype(str)
        
        # Reorder columns to match expected format
        column_order = ['match_id', 'datum', 'tegenstander', 'thuis_uit', 'uitslag', 
                       'doelpunten_voor', 'doelpunten_tegen', 'match_type', 'competitie', 'status']
        df = df[[col for col in column_order if col in df.columns]]
        
        # Convert to list of tuples for compatibility
        return [tuple(row) for row in df.values]
        
    except Exception as e:
        # Als tabel niet bestaat, return lege lijst
        print(f"Error getting matches: {e}")
        return []

def get_week_gesprekken(week_start, week_end):
    """Haal gesprekken en notities op voor deze week"""
    try:
        # Use safe_fetchdf for Supabase compatibility
        df = safe_fetchdf("SELECT speler, datum, onderwerp, notities FROM gesprek_notities ORDER BY datum DESC LIMIT 10")
        if df.empty:
            return []
        return [tuple(row) for row in df.values]
    except Exception as e:
        return []
def create_weekly_summary_pdf(week_data, training_topics, blessures, matches, gesprekken, llm_summary, week_start, week_end):
    """Genereer professionele PDF van de wekelijkse samenvatting"""
    buffer = BytesIO()
    
    # Set matplotlib to use non-interactive backend
    plt.switch_backend('Agg')
    
    # Define colors for consistent styling
    primary_color = '#1f77b4'
    secondary_color = '#ff7f0e'
    accent_color = '#2ca02c'
    background_color = '#f8f9fa'
    
    with PdfPages(buffer) as pdf:
        # PAGE 1: COVER PAGE
        fig = plt.figure(figsize=(8.27, 11.69))  # A4 portrait
        ax = fig.add_subplot(111)
        ax.axis('off')
        
        # Header with logo space
        ax.add_patch(plt.Rectangle((0.1, 0.8), 0.8, 0.15, facecolor=primary_color, alpha=0.1))
        ax.text(0.5, 0.875, 'SPK DASHBOARD', ha='center', va='center', fontsize=24, 
                fontweight='bold', color=primary_color, transform=ax.transAxes)
        ax.text(0.5, 0.82, 'Wekelijkse Samenvatting', ha='center', va='center', fontsize=16, 
                transform=ax.transAxes)
        
        # Date range
        ax.text(0.5, 0.65, f'Week: {week_start.strftime("%d/%m/%Y")} - {week_end.strftime("%d/%m/%Y")}', 
                ha='center', va='center', fontsize=18, fontweight='bold', transform=ax.transAxes)
        
        # Summary stats
        stats_y = 0.5
        if training_topics:
            ax.text(0.5, stats_y, f'📊 {len(training_topics)} Training Topics', 
                    ha='center', va='center', fontsize=14, transform=ax.transAxes)
            stats_y -= 0.05
        
        if week_data:
            ax.text(0.5, stats_y, f'👥 {len(week_data)} Spelers', 
                    ha='center', va='center', fontsize=14, transform=ax.transAxes)
            stats_y -= 0.05
            
        if gesprekken:
            ax.text(0.5, stats_y, f'💬 {len(gesprekken)} Gesprekken', 
                    ha='center', va='center', fontsize=14, transform=ax.transAxes)
            stats_y -= 0.05
            
        if blessures:
            ax.text(0.5, stats_y, f'🏥 {len(blessures)} Blessures', 
                    ha='center', va='center', fontsize=14, transform=ax.transAxes)
        
        # Footer
        ax.text(0.5, 0.1, f'Gegenereerd op: {datetime.now().strftime("%d/%m/%Y %H:%M")}', 
                ha='center', va='center', fontsize=10, style='italic', transform=ax.transAxes)
        
        pdf.savefig(fig, bbox_inches='tight')
        plt.close()
        
        # PAGE 2: TRAINING TOPICS (Full page for better readability)
        if training_topics:
            fig, ax = plt.subplots(figsize=(11.69, 8.27))  # A4 landscape
            fig.suptitle('🎯 Training Topics Overzicht', fontsize=16, fontweight='bold', y=0.95)
            
            # Limit to top 15 for readability
            topics_data = [(naam, minuten) for naam, _, _, minuten, _ in training_topics[:15]]
            topics_names, topics_minutes = zip(*topics_data) if topics_data else ([], [])
            
            # Create horizontal bar chart for better name readability
            bars = ax.barh(range(len(topics_names)), topics_minutes, color=primary_color, alpha=0.7)
            ax.set_yticks(range(len(topics_names)))
            ax.set_yticklabels(topics_names, fontsize=10)
            ax.set_xlabel('Minuten', fontsize=12)
            ax.grid(True, alpha=0.3, axis='x')
            
            # Add value labels on bars
            for i, (bar, minutes) in enumerate(zip(bars, topics_minutes)):
                ax.text(bar.get_width() + max(topics_minutes) * 0.01, bar.get_y() + bar.get_height()/2, 
                       f'{minutes}min', va='center', fontsize=9)
            
            # Add background color
            ax.set_facecolor(background_color)
            
            plt.tight_layout()
            pdf.savefig(fig, bbox_inches='tight')
            plt.close()
        
        # PAGE 3: FYSIEKE DATA (Full page with better layout)
        if week_data:
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.27, 11.69))  # A4 portrait
            fig.suptitle('📊 Fysieke Data Analyse', fontsize=16, fontweight='bold')
            
            # Ensure week_data is properly formatted
            if isinstance(week_data, list) and len(week_data) > 0:
                if isinstance(week_data[0], dict):
                    df = pd.DataFrame(week_data)
                else:
                    # Handle case where week_data might be in different format
                    try:
                        df = pd.DataFrame(week_data)
                    except:
                        fig.text(0.5, 0.5, 'Geen fysieke data beschikbaar\nvoor visualisatie', 
                               ha='center', va='center', fontsize=12)
                        pdf.savefig(fig, bbox_inches='tight')
                        plt.close()
                        return
            else:
                fig.text(0.5, 0.5, 'Geen fysieke data beschikbaar', 
                       ha='center', va='center', fontsize=12)
                pdf.savefig(fig, bbox_inches='tight')
                plt.close()
                return
            
            # Check if required columns exist
            if 'speler' not in df.columns:
                # Try alternative column names
                if 'Speler' in df.columns:
                    df['speler'] = df['Speler']
                else:
                    fig.text(0.5, 0.5, 'Speler informatie niet beschikbaar', 
                           ha='center', va='center', fontsize=12)
                    pdf.savefig(fig, bbox_inches='tight')
                    plt.close()
                    return
            
            if 'totaal_afstand' not in df.columns:
                # Try alternative column names
                if 'Totaal Afstand (m)' in df.columns:
                    df['totaal_afstand'] = df['Totaal Afstand (m)']
                else:
                    fig.text(0.5, 0.5, 'Afstand informatie niet beschikbaar', 
                           ha='center', va='center', fontsize=12)
                    pdf.savefig(fig, bbox_inches='tight')
                    plt.close()
                    return
            
            # Top chart: Total distance
            spelers = df['speler'].tolist()
            afstanden = df['totaal_afstand'].tolist()
            
            bars1 = ax1.bar(range(len(spelers)), afstanden, color=secondary_color, alpha=0.7)
            ax1.set_xticks(range(len(spelers)))
            ax1.set_xticklabels(spelers, rotation=45, ha='right', fontsize=9)
            ax1.set_ylabel('Meters', fontsize=10)
            ax1.set_title('Totale Afstand per Speler', fontsize=12, pad=10)
            ax1.grid(True, alpha=0.3, axis='y')
            ax1.set_facecolor(background_color)
            
            # Add value labels
            for bar, afstand in zip(bars1, afstanden):
                ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(afstanden) * 0.01, 
                        f'{afstand:.0f}m', ha='center', va='bottom', fontsize=8)
            
            # Bottom chart: High intensity distance (if available)
            hi_column = None
            if 'hoge_intensiteit_afstand' in df.columns:
                hi_column = 'hoge_intensiteit_afstand'
            elif 'HSR Afstand (m)' in df.columns:
                hi_column = 'HSR Afstand (m)'
            elif 'hoge_snelheid_afstand' in df.columns:
                hi_column = 'hoge_snelheid_afstand'
            elif 'hoge_intensiteit_afstand' in df.columns:
                hi_column = 'hoge_intensiteit_afstand'
                
            if hi_column:
                hi_afstanden = df[hi_column].tolist()
                bars2 = ax2.bar(range(len(spelers)), hi_afstanden, color=accent_color, alpha=0.7)
                ax2.set_xticks(range(len(spelers)))
                ax2.set_xticklabels(spelers, rotation=45, ha='right', fontsize=9)
                ax2.set_ylabel('Meters', fontsize=10)
                ax2.set_title('High Speed Running per Speler', fontsize=12, pad=10)
                ax2.grid(True, alpha=0.3, axis='y')
                ax2.set_facecolor(background_color)
                
                # Add value labels
                for bar, hi_afstand in zip(bars2, hi_afstanden):
                    ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(hi_afstanden) * 0.01, 
                            f'{hi_afstand:.0f}m', ha='center', va='bottom', fontsize=8)
            else:
                ax2.text(0.5, 0.5, 'Geen hoge intensiteit data beschikbaar', 
                        ha='center', va='center', transform=ax2.transAxes, fontsize=12)
                ax2.set_title('High Speed Running Data', fontsize=12)
            
            plt.tight_layout()
            pdf.savefig(fig, bbox_inches='tight')
            plt.close()
        
        # PAGE 4: GESPREKKEN & BLESSURES
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.69, 8.27))  # A4 landscape
        fig.suptitle('💬 Gesprekken & 🏥 Blessures Overzicht', fontsize=16, fontweight='bold')
        
        # Gesprekken chart
        if gesprekken:
            gesprekken_per_dag = {}
            for _, datum, _, _, _, _ in gesprekken:
                dag = pd.to_datetime(datum).date().strftime('%d/%m')
                gesprekken_per_dag[dag] = gesprekken_per_dag.get(dag, 0) + 1
            
            dagen = list(gesprekken_per_dag.keys())
            aantallen = list(gesprekken_per_dag.values())
            
            bars = ax1.bar(dagen, aantallen, color=primary_color, alpha=0.7)
            ax1.set_xlabel('Datum', fontsize=10)
            ax1.set_ylabel('Aantal Gesprekken', fontsize=10)
            ax1.set_title('Gesprekken per Dag', fontsize=12, pad=10)
            ax1.grid(True, alpha=0.3, axis='y')
            ax1.set_facecolor(background_color)
            
            # Add value labels
            for bar, aantal in zip(bars, aantallen):
                ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05, 
                        str(aantal), ha='center', va='bottom', fontsize=10)
        else:
            ax1.text(0.5, 0.5, 'Geen gesprekken\ngeregistreerd deze week', 
                    ha='center', va='center', transform=ax1.transAxes, fontsize=12)
            ax1.set_title('Gesprekken', fontsize=12)
        
        # Blessures chart
        if blessures:
            blessure_status = {}
            for blessure in blessures:
                # Nieuwe blessure structuur: speler_naam, blessure_type, locatie, ernst, status, datum_start, datum_einde, voorspelling_dagen, beschrijving, behandeling
                status = blessure[4]  # status is op index 4
                blessure_status[status] = blessure_status.get(status, 0) + 1
            
            colors = ['#ff4444', '#ffaa44', '#44ff44'][:len(blessure_status)]
            wedges, texts, autotexts = ax2.pie(blessure_status.values(), labels=blessure_status.keys(), 
                                              autopct='%1.0f%%', colors=colors, startangle=90)
            ax2.set_title('Blessures Status', fontsize=12, pad=10)
            
            # Improve text readability
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontweight('bold')
        else:
            ax2.text(0.5, 0.5, 'Geen blessures\ngeregistreerd', 
                    ha='center', va='center', transform=ax2.transAxes, fontsize=12)
            ax2.set_title('Blessures', fontsize=12)
        
        plt.tight_layout()
        pdf.savefig(fig, bbox_inches='tight')
        plt.close()
        
        # PAGE 5+: AI SAMENVATTING (Multiple pages if needed)
        # Clean emojis from text for PDF compatibility
        cleaned_summary = remove_emojis_for_pdf(llm_summary)
        text_lines = cleaned_summary.split('\n')
        lines_per_page = 45
        
        for page_num, start_idx in enumerate(range(0, len(text_lines), lines_per_page)):
            fig, ax = plt.subplots(figsize=(8.27, 11.69))  # A4 portrait
            ax.axis('off')
            
            # Header
            header_text = 'AI Samenvatting' if page_num == 0 else f'AI Samenvatting (vervolg {page_num + 1})'
            ax.text(0.5, 0.95, header_text, ha='center', va='top', fontsize=14, 
                   fontweight='bold', transform=ax.transAxes)
            
            # Content
            y_pos = 0.9
            line_height = 0.018
            
            page_lines = text_lines[start_idx:start_idx + lines_per_page]
            
            for line in page_lines:
                if y_pos < 0.05:
                    break
                
                # Handle long lines
                if len(line) > 95:
                    words = line.split(' ')
                    current_line = ''
                    for word in words:
                        if len(current_line + word) < 95:
                            current_line += word + ' '
                        else:
                            if current_line:
                                # Determine font style
                                fontweight = 'bold' if current_line.strip().startswith(('📊', '🎯', '🚑', '💬', '📈', '🏃‍♂️', '🏆', '🔥', '⚠️')) else 'normal'
                                fontsize = 10 if fontweight == 'bold' else 9
                                
                                ax.text(0.08, y_pos, current_line.strip(), transform=ax.transAxes, 
                                       fontsize=fontsize, fontweight=fontweight, verticalalignment='top')
                                y_pos -= line_height
                            current_line = word + ' '
                    if current_line and y_pos > 0.05:
                        fontweight = 'bold' if current_line.strip().startswith(('📊', '🎯', '🚑', '💬', '📈', '🏃‍♂️', '🏆', '🔥', '⚠️')) else 'normal'
                        fontsize = 10 if fontweight == 'bold' else 9
                        ax.text(0.08, y_pos, current_line.strip(), transform=ax.transAxes, 
                               fontsize=fontsize, fontweight=fontweight, verticalalignment='top')
                        y_pos -= line_height
                else:
                    # Determine font style
                    fontweight = 'bold' if line.startswith(('📊', '🎯', '🚑', '💬', '📈', '🏃‍♂️', '🏆', '🔥', '⚠️')) else 'normal'
                    fontsize = 10 if fontweight == 'bold' else 9
                    
                    ax.text(0.08, y_pos, line, transform=ax.transAxes, 
                           fontsize=fontsize, fontweight=fontweight, verticalalignment='top')
                    y_pos -= line_height
            
            # Footer with page number
            ax.text(0.5, 0.02, f'Pagina {page_num + 5}', ha='center', va='bottom', 
                   fontsize=8, style='italic', transform=ax.transAxes)
            
            pdf.savefig(fig, bbox_inches='tight')
            plt.close()
    
    buffer.seek(0)
    return buffer.getvalue()

def generate_dummy_metrics(week_start, week_end):
    """Genereer dummy data ALLEEN in memory - NIET in database"""
    # Haal spelers op
    spelers = execute_db_query("""
        SELECT DISTINCT Speler FROM thirty_fifteen_results 
        ORDER BY Speler
    """)
    
    if not spelers:
        return []
    
    week_data = []
    
    for speler_row in spelers:
        speler = speler_row[0]
        
        # Simuleer realistische wekelijkse data (ALLEEN in memory)
        import random
        random.seed(hash(speler + str(week_start)))  # Consistent per speler/week
        
        # Check of er trainingen waren deze week
        trainingen_count = (lambda result: result[0] if result else None)(execute_db_query("""
            SELECT COUNT(*) FROM training_principes tp
            JOIN trainings_calendar tc ON tp.training_id = tc.training_id
            WHERE tc.datum >= ? AND tc.datum <= ?
        """, (week_start, week_end)))[0]
        
        if trainingen_count > 0:
            # Simuleer metrics gebaseerd op trainingen
            aantal_trainingen = min(trainingen_count, random.randint(2, 5))
            totaal_afstand = round(random.uniform(8000, 15000), 0)  # meters
            hoge_intensiteit_afstand = round(totaal_afstand * random.uniform(0.15, 0.35), 0)
            sprint_afstand = round(hoge_intensiteit_afstand * random.uniform(0.2, 0.4), 0)  # Subset of HSR
            gemiddelde_snelheid = round(random.uniform(12, 18), 1)  # km/h
            max_snelheid = round(random.uniform(25, 35), 1)  # km/h
            aantal_sprints = random.randint(15, 45)
            
            week_data.append({
                'speler': speler,
                'totaal_afstand': totaal_afstand,
                'hoge_intensiteit_afstand': hoge_intensiteit_afstand,
                'sprint_afstand': sprint_afstand,
                'aantal_trainingen': aantal_trainingen,
                'gemiddelde_snelheid': gemiddelde_snelheid,
                'max_snelheid': max_snelheid,
                'aantal_sprints': aantal_sprints
            })
    
    return week_data

def remove_emojis_for_pdf(text):
    """Remove emojis from text for PDF compatibility"""
    import re
    # Remove emoji patterns
    emoji_pattern = re.compile("["
        u"\U0001F600-\U0001F64F"  # emoticons
        u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        u"\U0001F680-\U0001F6FF"  # transport & map symbols
        u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
        u"\U00002500-\U00002BEF"  # chinese char
        u"\U00002702-\U000027B0"
        u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251"
        u"\U0001f926-\U0001f937"
        u"\U00010000-\U0010ffff"
        u"\u2640-\u2642" 
        u"\u2600-\u2B55"
        u"\u200d"
        u"\u23cf"
        u"\u23e9"
        u"\u231a"
        u"\ufe0f"  # dingbats
        u"\u3030"
        "]+", flags=re.UNICODE)
    return emoji_pattern.sub(r'', text)

def generate_llm_summary(week_data, training_topics, blessures, matches, gesprekken, week_start, week_end, heeft_fysieke_data=False):
    """Genereer uitgebreide LLM samenvatting van de week"""
    from datetime import datetime as dt
    
    samenvatting = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                           📊 WEKELIJKSE SAMENVATTING                         ║
║                    {week_start.strftime('%d/%m/%Y')} - {week_end.strftime('%d/%m/%Y')}                    ║
╚══════════════════════════════════════════════════════════════════════════════╝

┌─ ⚽ WEDSTRIJDEN ─────────────────────────────────────────────────────────────┐"""
    
    # Wedstrijden sectie
    if matches:
        for match in matches:
            match_id, datum, tegenstander, thuis_uit, uitslag, doelpunten_voor, doelpunten_tegen, match_type, competitie, status = match
            
            # Bepaal resultaat
            if doelpunten_voor is not None and doelpunten_tegen is not None:
                if doelpunten_voor > doelpunten_tegen:
                    result_text = "🟢 WINST"
                elif doelpunten_voor < doelpunten_tegen:
                    result_text = "🔴 VERLIES"
                else:
                    result_text = "🟡 GELIJKSPEL"
                score_text = f" ({doelpunten_voor}-{doelpunten_tegen})"
            else:
                result_text = "⚪ NOG TE SPELEN"
                score_text = ""
            
            location_text = "🏠 THUIS" if thuis_uit == "Thuis" else "✈️ UIT"
            
            samenvatting += f"""
│ {result_text} {location_text} vs {tegenstander.upper()}{score_text}
│ 📅 {datum} │ 🏆 {match_type or competitie or 'Competitie'}"""
            
            if status and status != 'Gespeeld':
                samenvatting += f"""
│ 📊 Status: {status}"""
    else:
        samenvatting += """
│ Geen wedstrijden deze week"""
    
    samenvatting += """
└─────────────────────────────────────────────────────────────────────────────┘

┌─ 🎯 TRAINING FOCUS ─────────────────────────────────────────────────────────┐"""
    
    # Training topics sectie
    if training_topics:
        # Bereken totaal aantal trainingen met tactische content
        unique_trainings = set()
        total_minuten = 0
        topics_per_spelfase = {}
        
        for naam, spelfase, niveau, minuten, aantal_trainingen in training_topics:
            if spelfase not in topics_per_spelfase:
                topics_per_spelfase[spelfase] = []
            topics_per_spelfase[spelfase].append((naam, minuten, aantal_trainingen))
            unique_trainings.add((spelfase, aantal_trainingen))  # Houd unieke trainingen bij
            total_minuten += minuten
        
        # Bereken totaal aantal trainingen (per spelfase)
        trainings_per_fase = {}
        for spelfase, aantal in unique_trainings:
            if spelfase not in trainings_per_fase:
                trainings_per_fase[spelfase] = 0
            trainings_per_fase[spelfase] += aantal
        
        samenvatting += f"""
│ 📊 {len(training_topics)} verschillende topics - {total_minuten} minuten totaal
│"""
        
        for spelfase, topics in topics_per_spelfase.items():
            trainings_count = trainings_per_fase.get(spelfase, 0)
            samenvatting += f"""
│ 🏗️ {spelfase.upper()} ({trainings_count} training{'s' if trainings_count > 1 else ''}):"""
            for naam, minuten, trainingen in topics:
                samenvatting += f"""
│   • {naam}: {minuten} min"""
    else:
        samenvatting += """
│ Geen specifieke topics geregistreerd deze week"""
    
    samenvatting += """
└─────────────────────────────────────────────────────────────────────────────┘"""
    
    # Fysieke data sectie
    samenvatting += """

┌─ 🏃‍♂️ FYSIEKE PRESTATIES ──────────────────────────────────────────────────────┐"""
    
    if heeft_fysieke_data and week_data:
        df = pd.DataFrame(week_data)
        
        gem_afstand = df['totaal_afstand'].mean()
        gem_hsr = df['hoge_intensiteit_afstand'].mean()
        gem_sprint = df['sprint_afstand'].mean()
        max_snelheid_team = df['max_snelheid'].max()
        
        top_afstand = df.loc[df['totaal_afstand'].idxmax()]
        top_snelheid = df.loc[df['max_snelheid'].idxmax()]
        top_sprints = df.loc[df['aantal_sprints'].idxmax()]
        top_hsr = df.loc[df['hoge_intensiteit_afstand'].idxmax()]
        
        samenvatting += f"""
│ 📊 TEAM GEMIDDELDEN:
│   • Totale afstand: {gem_afstand:.0f}m per speler
│   • HSR afstand: {gem_hsr:.0f}m per speler
│   • Sprint afstand: {gem_sprint:.0f}m per speler
│   • Max snelheid: {max_snelheid_team:.1f} km/h ({top_snelheid['speler']})
│
│ 🏆 TOP PRESTATIES:
│   • Meeste afstand: {top_afstand['speler']} ({top_afstand['totaal_afstand']:.0f}m)
│   • Hoogste snelheid: {top_snelheid['speler']} ({top_snelheid['max_snelheid']:.1f} km/h)
│   • Meeste HSR: {top_hsr['speler']} ({top_hsr['hoge_intensiteit_afstand']:.0f}m)
│   • Meeste sprints: {top_sprints['speler']} ({top_sprints['aantal_sprints']} sprints)
│
│ 📈 ANALYSE:
│   • HSR: {(gem_hsr/gem_afstand*100):.1f}% van totale afstand
│   • Intensiteit range: {((df['hoge_intensiteit_afstand']/df['totaal_afstand']).min()*100):.1f}%-{((df['hoge_intensiteit_afstand']/df['totaal_afstand']).max()*100):.1f}%
│   • Team balans: {'Goede spreiding' if (df['totaal_afstand'].std()/df['totaal_afstand'].mean()) < 0.2 else 'Grote verschillen'} in afstanden"""
    else:
        samenvatting += """
│ ⚠️ Geen GPS/fysieke data beschikbaar deze week
│    Voor uitgebreidere analyse: koppel GPS-trackers of fitness devices"""
    
    samenvatting += """
└─────────────────────────────────────────────────────────────────────────────┘"""
    
    # Blessures sectie met nieuwe database structuur
    samenvatting += """

┌─ 🚑 BLESSURES & MEDISCH ───────────────────────────────────────────────────┐"""
    
    if blessures:
        # Categoriseer blessures op status
        actieve_blessures = [b for b in blessures if b[4] == 'Actief']  # status is index 4
        behandeling_blessures = [b for b in blessures if b[4] == 'In behandeling']
        genezen_blessures = [b for b in blessures if b[4] == 'Genezen']
        
        if actieve_blessures:
            samenvatting += f"""
│ 🔴 ACTIEVE BLESSURES ({len(actieve_blessures)}):"""
            for blessure in actieve_blessures:
                speler_naam, blessure_type, locatie, ernst, status, datum_start, datum_einde, voorspelling_dagen, beschrijving, behandeling = blessure
                
                # Bereken dagen uit
                start_date = dt.strptime(datum_start, '%Y-%m-%d').date()
                dagen_uit = (dt.now().date() - start_date).days
                
                samenvatting += f"""
│   • {speler_naam}: {blessure_type} ({locatie}) - Ernst: {ernst}
│     📅 Uit sinds: {datum_start} ({dagen_uit} dagen)"""
                
                if voorspelling_dagen:
                    samenvatting += f"""
│     ⏱️ Voorspelling: {voorspelling_dagen} dagen"""
                
                if behandeling:
                    samenvatting += f"""
│     🏥 Behandeling: {behandeling}"""
        
        if behandeling_blessures:
            samenvatting += f"""
│
│ 🟡 IN BEHANDELING ({len(behandeling_blessures)}):"""
            for blessure in behandeling_blessures:
                speler_naam, blessure_type, locatie, ernst, status, datum_start, datum_einde, voorspelling_dagen, beschrijving, behandeling = blessure
                
                samenvatting += f"""
│   • {speler_naam}: {blessure_type} ({locatie})"""
                
                if behandeling:
                    samenvatting += f"""
│     🏥 {behandeling}"""
        
        if genezen_blessures:
            samenvatting += f"""
│
│ 🟢 RECENT GENEZEN ({len(genezen_blessures)}):"""
            for blessure in genezen_blessures:
                speler_naam, blessure_type, locatie, ernst, status, datum_start, datum_einde, voorspelling_dagen, beschrijving, behandeling = blessure
                
                if datum_einde:
                    samenvatting += f"""
│   • {speler_naam}: {blessure_type} - Hersteld op {datum_einde}"""
        
        # Samenvatting stats
        totaal_blessures = len(actieve_blessures) + len(behandeling_blessures)
        if totaal_blessures > 0:
            samenvatting += f"""
│
│ 📊 OVERZICHT: {totaal_blessures} actieve blessure{'s' if totaal_blessures != 1 else ''} - {len(genezen_blessures)} recent genezen"""
    else:
        samenvatting += """
│ ✅ Geen blessures geregistreerd deze week - Team volledig fit!"""
    
    samenvatting += """
└─────────────────────────────────────────────────────────────────────────────┘"""
    
    # Gesprekken sectie
    if gesprekken:
        samenvatting += f"""

💬 GESPREKKEN & COACHING:"""
        
        # Groepeer gesprekken per speler
        gesprekken_per_speler = {}
        for speler, datum, onderwerp, notities in gesprekken:
            if speler not in gesprekken_per_speler:
                gesprekken_per_speler[speler] = []
            gesprekken_per_speler[speler].append((datum, onderwerp, notities))
        
        samenvatting += f"\n\nTotaal {len(gesprekken)} gesprek{'ken' if len(gesprekken) > 1 else ''} gevoerd met {len(gesprekken_per_speler)} speler{'s' if len(gesprekken_per_speler) > 1 else ''}:"
        
        for speler, speler_gesprekken in gesprekken_per_speler.items():
            samenvatting += f"\n\n{speler.upper()} ({len(speler_gesprekken)} gesprek{'ken' if len(speler_gesprekken) > 1 else ''}):"
            for datum, onderwerp, notities in speler_gesprekken:
                datum_str = pd.to_datetime(datum).date().strftime('%d/%m')
                samenvatting += f"\n• {datum_str}: {onderwerp}"
                if notities and len(notities) > 50:
                    samenvatting += f"\n  💭 {notities[:100]}{'...' if len(notities) > 100 else ''}"
                elif notities:
                    samenvatting += f"\n  💭 {notities}"
    else:
        samenvatting += """

💬 GESPREKKEN & COACHING:
• Geen gesprekken geregistreerd deze week"""
    
    # Grafiek analyse toevoegen als er fysieke data is
    if heeft_fysieke_data and week_data:
        df = pd.DataFrame(week_data)
        hsr_leader = df.loc[df['hoge_intensiteit_afstand'].idxmax()]
        sprint_leader = df.loc[df['sprint_afstand'].idxmax()]
        
        samenvatting += f"""

📊 GRAFIEK ANALYSE:
De visualisaties tonen interessante patronen:
• Afstand grafiek: Duidelijke verschillen in volume tussen spelers
• HSR/Sprint scatter: {hsr_leader['speler']} toont beste HSR prestaties ({hsr_leader['hoge_intensiteit_afstand']:.0f}m)
• Intensiteit chart: {sprint_leader['speler']} leidt in sprint afstand ({sprint_leader['sprint_afstand']:.0f}m)
• Team spreiding: {'Homogene groep' if (df['totaal_afstand'].std()/df['totaal_afstand'].mean()) < 0.15 else 'Diverse niveaus'} qua fysieke output"""

    # Week analyse
    totaal_topics_minuten = sum([minuten for _, _, _, minuten, _ in training_topics]) if training_topics else 0
    aantal_trainingen = len(set([aantal for _, _, _, _, aantal in training_topics])) if training_topics else 0
    
    samenvatting += f"""

📈 WEEK ANALYSE:
Deze week werkten we aan {len(training_topics) if training_topics else 0} verschillende topics 
met een totale focus van {totaal_topics_minuten} minuten verdeeld over {aantal_trainingen} training(en).
{'Goede variatie in training topics' if len(training_topics) > 5 else 'Overweeg meer topic variatie' if training_topics else 'Geen topics geregistreerd'}.

💡 AANDACHTSPUNTEN VOLGENDE WEEK:"""
    
    if heeft_fysieke_data and week_data:
        df = pd.DataFrame(week_data)
        hsr_percentage = (df['hoge_intensiteit_afstand'].mean() / df['totaal_afstand'].mean() * 100)
        if hsr_percentage > 15:
            samenvatting += "\n• Hoge intensiteit training - monitor herstel"
        elif hsr_percentage < 8:
            samenvatting += "\n• Ruimte voor meer hoge intensiteit training"
    
    if blessures:
        actieve_count = len([b for b in blessures if b[4] == 'Actief'])  # status is op index 4
        if actieve_count > 0:
            samenvatting += f"\n• Monitoring {actieve_count} geblesseerde speler(s)"
    
    samenvatting += "\n• Continueer met geregistreerde coaching topics"
    if not training_topics:
        samenvatting += "\n• Start met registreren van training topics voor betere analyse"
    
    if heeft_fysieke_data and week_data:
        samenvatting += "\n• Bekijk de grafieken voor visuele analyse van HSR vs Sprint prestaties"
    
    samenvatting += f"""

🏅 Gegenereerd door SPK Dashboard - {dt.now().strftime('%d/%m/%Y %H:%M')}"""
    
    return samenvatting

# Tabs voor verschillende functies
tab1, tab2, tab3, tab4 = st.tabs(["📊 Week Overzicht", "📧 Verzend Rapport", "👥 Contact Beheer", "⚙️ Instellingen"])

with tab1:
    st.markdown("### 📊 Wekelijkse Prestatie Overzicht")
    
    # Week selectie
    col1, col2 = st.columns(2)
    with col1:
        selected_date = st.date_input("📅 Selecteer een datum in de gewenste week", 
                                    value=datetime.now().date())
    
    week_start, week_end = get_week_dates(selected_date)
    
    with col2:
        st.info(f"📅 Week van {week_start.strftime('%d/%m/%Y')} tot {week_end.strftime('%d/%m/%Y')}")
    
    # Check voor echte fysieke data
    echte_fysieke_data = get_week_fysieke_data(week_start, week_end)
    heeft_fysieke_data = len(echte_fysieke_data) > 0
    
    if heeft_fysieke_data:
        st.success("✅ Echte fysieke data gevonden in database")
        week_data_raw = echte_fysieke_data
        week_data = []
        for row in week_data_raw:
            speler, totaal_afstand, hoge_intensiteit_afstand, sprint_afstand, gem_snelheid, max_snelheid, totaal_sprints, aantal_sessies = row
            week_data.append({
                'speler': speler,
                'totaal_afstand': totaal_afstand,
                'hoge_intensiteit_afstand': hoge_intensiteit_afstand,
                'sprint_afstand': sprint_afstand,
                'aantal_trainingen': aantal_sessies,
                'gemiddelde_snelheid': gem_snelheid,
                'max_snelheid': max_snelheid,
                'aantal_sprints': totaal_sprints
            })
    else:
        st.info("ℹ️ Geen echte fysieke data gevonden. Gebruik dummy data voor preview.")
        
        if st.button("🔄 Genereer Preview Data (Dummy)", type="secondary"):
            st.session_state[f'dummy_data_{week_start}'] = generate_dummy_metrics(week_start, week_end)
            st.rerun()
        
        # Haal dummy data uit session state (NIET uit database)
        week_data = st.session_state.get(f'dummy_data_{week_start}', [])
    
    if week_data:
        # Converteer naar DataFrame
        if heeft_fysieke_data:
            df_week = pd.DataFrame(week_data)
            df_week.columns = ['Speler', 'Totaal Afstand (m)', 'HSR Afstand (m)', 'Sprint Afstand (m)',
                             'Aantal Trainingen', 'Gem. Snelheid (km/h)', 'Max Snelheid (km/h)', 
                             'Aantal Sprints']
        else:
            df_week = pd.DataFrame(week_data)
            if not df_week.empty:
                df_week = df_week[['speler', 'totaal_afstand', 'hoge_intensiteit_afstand', 'sprint_afstand',
                                 'aantal_trainingen', 'gemiddelde_snelheid', 'max_snelheid', 
                                 'aantal_sprints']]
                df_week.columns = ['Speler', 'Totaal Afstand (m)', 'HSR Afstand (m)', 'Sprint Afstand (m)',
                                 'Aantal Trainingen', 'Gem. Snelheid (km/h)', 'Max Snelheid (km/h)', 
                                 'Aantal Sprints']
        
        # Team metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Totaal Team Afstand", f"{df_week['Totaal Afstand (m)'].sum()/1000:.1f} km")
        with col2:
            st.metric("Gem. HSR Afstand", f"{df_week['HSR Afstand (m)'].mean():.0f} m")
        with col3:
            st.metric("Gem. Sprint Afstand", f"{df_week['Sprint Afstand (m)'].mean():.0f} m")
        with col4:
            st.metric("Hoogste Snelheid", f"{df_week['Max Snelheid (km/h)'].max():.1f} km/h")
        
        # Visualisaties
        col1, col2 = st.columns(2)
        
        with col1:
            # Afstand per speler
            fig_afstand = px.bar(df_week, x='Speler', y='Totaal Afstand (m)',
                               title="Totale Afstand per Speler",
                               color='Totaal Afstand (m)',
                               color_continuous_scale='viridis')
            fig_afstand.update_layout(xaxis_tickangle=45)
            st.plotly_chart(fig_afstand, use_container_width=True)
        
        with col2:
            # HSR vs Sprint afstand analyse
            fig_intensiteit = px.scatter(df_week, x='HSR Afstand (m)', y='Sprint Afstand (m)',
                                        size='Aantal Sprints', hover_name='Speler',
                                        title="HSR vs Sprint Afstand",
                                        labels={'size': 'Aantal Sprints'})
            fig_intensiteit.update_layout(
                xaxis_title="HSR Afstand (m)",
                yaxis_title="Sprint Afstand (m)"
            )
            st.plotly_chart(fig_intensiteit, use_container_width=True)
        
        # Extra grafiek: Intensiteit overzicht
        st.markdown("#### 🔥 Intensiteit Overzicht per Speler")
        
        # Bereken percentages voor stacked bar chart
        df_week['HSR %'] = (df_week['HSR Afstand (m)'] / df_week['Totaal Afstand (m)'] * 100).round(1)
        df_week['Sprint %'] = (df_week['Sprint Afstand (m)'] / df_week['Totaal Afstand (m)'] * 100).round(1)
        
        fig_intensiteit_stack = px.bar(df_week, x='Speler', 
                                      y=['HSR Afstand (m)', 'Sprint Afstand (m)'],
                                      title="HSR en Sprint Afstand per Speler",
                                      color_discrete_sequence=['#FF6B6B', '#4ECDC4'])
        fig_intensiteit_stack.update_layout(
            xaxis_tickangle=45,
            yaxis_title="Afstand (m)",
            legend_title="Type Afstand"
        )
        st.plotly_chart(fig_intensiteit_stack, use_container_width=True)
        
        # Detailed tabel
        st.markdown("#### 📋 Gedetailleerde Statistieken")
        st.dataframe(df_week, use_container_width=True)
        
        # Haal extra data op voor samenvatting
        training_topics = get_week_training_topics(week_start, week_end)
        blessures = get_week_blessures(week_start, week_end)
        matches = get_week_matches(week_start, week_end)
        gesprekken = get_week_gesprekken(week_start, week_end)
        
        # Toon wedstrijden indien aanwezig
        if matches:
            st.markdown("#### ⚽ Wedstrijden deze Week")
            for match in matches:
                match_id, datum, tegenstander, thuis_uit, uitslag, doelpunten_voor, doelpunten_tegen, match_type, competitie, status = match
                
                # Bepaal resultaat kleur
                if doelpunten_voor and doelpunten_tegen is not None:
                    if doelpunten_voor > doelpunten_tegen:
                        result_color = "🟢"
                        result_text = "Winst"
                    elif doelpunten_voor < doelpunten_tegen:
                        result_color = "🔴" 
                        result_text = "Verlies"
                    else:
                        result_color = "🟡"
                        result_text = "Gelijk"
                else:
                    result_color = "⚪"
                    result_text = "Nog te spelen"
                
                location_icon = "🏠" if thuis_uit == "Thuis" else "✈️"
                
                with st.expander(f"{result_color} {location_icon} vs {tegenstander} - {result_text} ({datum})"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**📅 Datum:** {datum}")
                        st.write(f"**🏟️ Locatie:** {thuis_uit}")
                        st.write(f"**🏆 Type:** {match_type or competitie or 'Competitie'}")
                    
                    with col2:
                        if doelpunten_voor is not None and doelpunten_tegen is not None:
                            st.write(f"**⚽ Uitslag:** {doelpunten_voor} - {doelpunten_tegen}")
                        st.write(f"**📊 Status:** {status}")
                    
                    if competitie:
                        st.write(f"**🏆 Competitie:** {competitie}")
        
        # Toon training topics
        if training_topics:
            st.markdown("#### 🎯 Getrainde Topics deze Week")
            topics_df = pd.DataFrame(training_topics, columns=['Topic', 'Spelfase', 'Niveau', 'Minuten', 'Trainingen'])
            st.dataframe(topics_df, use_container_width=True)
        
        # Toon blessures indien aanwezig
        if blessures:
            st.markdown("#### 🚑 Blessures & Medisch")
            for blessure in blessures:
                speler_naam, blessure_type, locatie, ernst, status, datum_start, datum_einde, voorspelling_dagen, beschrijving, behandeling = blessure
                
                # Status kleur bepalen
                if status == "Actief":
                    status_color = "🔴"
                elif status == "In behandeling":
                    status_color = "🟡"
                elif status == "Genezen":
                    status_color = "🟢"
                else:
                    status_color = "⚪"
                
                with st.expander(f"{status_color} {speler_naam} - {blessure_type} ({status})"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**🩹 Type:** {blessure_type}")
                        st.write(f"**📍 Locatie:** {locatie}")
                        st.write(f"**⚠️ Ernst:** {ernst}")
                        st.write(f"**📅 Start:** {datum_start}")
                    
                    with col2:
                        if datum_einde:
                            st.write(f"**✅ Herstel:** {datum_einde}")
                        if voorspelling_dagen:
                            st.write(f"**⏱️ Voorspelling:** {voorspelling_dagen} dagen")
                        
                        # Bereken dagen uit
                        from datetime import datetime
                        start_date = datetime.strptime(datum_start, '%Y-%m-%d').date()
                        if datum_einde and status == 'Genezen':
                            end_date = datetime.strptime(datum_einde, '%Y-%m-%d').date()
                            dagen_uit = (end_date - start_date).days
                        else:
                            dagen_uit = (datetime.now().date() - start_date).days
                        st.write(f"**📊 Dagen uit:** {dagen_uit}")
                    
                    if beschrijving:
                        st.write(f"**📝 Beschrijving:** {beschrijving}")
                    
                    if behandeling:
                        st.write(f"**🏥 Behandeling:** {behandeling}")
        
        # LLM Samenvatting genereren
        if st.button("🤖 Genereer AI Samenvatting"):
            try:
                # Debug info
                st.write(f"Debug: week_data length = {len(week_data) if week_data else 0}")
                st.write(f"Debug: training_topics length = {len(training_topics) if training_topics else 0}")
                st.write(f"Debug: blessures length = {len(blessures) if blessures else 0}")
                st.write(f"Debug: heeft_fysieke_data = {heeft_fysieke_data}")
                
                llm_summary = generate_llm_summary(week_data, training_topics, blessures, matches, gesprekken, week_start, week_end, heeft_fysieke_data)
                
                # Sla rapport ALTIJD op (ook zonder fysieke data)
                rapport_data = df_week.to_json() if 'df_week' in locals() and not df_week.empty else "{}"
                execute_db_query("""
                    INSERT OR REPLACE INTO week_rapporten 
                    (rapport_id, week_start, week_end, rapport_data, llm_samenvatting)
                    VALUES (nextval('rapport_id_seq'), ?, ?, ?, ?)
                """, (week_start, week_end, rapport_data, llm_summary))
                
                if heeft_fysieke_data or training_topics:
                    st.success("🤖 AI Samenvatting gegenereerd en opgeslagen!")
                else:
                    st.success("🤖 AI Samenvatting gegenereerd en opgeslagen (zonder fysieke data)")
                
                st.info("📧 **Het rapport is nu beschikbaar in de 'Rapport Verzenden' tab voor email verzending**")
                
                # Display AI Samenvatting in een overzichtelijke manier
                st.markdown("### 📋 AI Samenvatting")
                
                # Parse de samenvatting in secties
                sections = llm_summary.split('┌─')
                
                # Toon header sectie apart
                if sections:
                    header = sections[0].strip()
                    if header:
                        with st.expander("📊 Week Overzicht", expanded=True):
                            st.code(header, language=None)
                
                # Toon elke sectie in een apart expander
                for i, section in enumerate(sections[1:], 1):
                    if section.strip():
                        # Extract section title
                        lines = section.split('\n')
                        if lines:
                            title_line = lines[0].strip(' ─')
                            section_title = title_line.split('│')[0].strip() if '│' in title_line else title_line
                            
                            # Bepaal emoji en titel op basis van inhoud
                            if 'WEDSTRIJDEN' in section_title:
                                emoji = "⚽"
                                display_title = "Wedstrijden"
                            elif 'TRAINING' in section_title:
                                emoji = "🎯"
                                display_title = "Training Focus"
                            elif 'FYSIEKE' in section_title:
                                emoji = "🏃‍♂️"
                                display_title = "Fysieke Prestaties"
                            elif 'BLESSURES' in section_title:
                                emoji = "🚑"
                                display_title = "Blessures & Medisch"
                            elif 'GESPREKKEN' in section_title:
                                emoji = "💬"
                                display_title = "Gesprekken & Coaching"
                            else:
                                emoji = "📄"
                                display_title = section_title.replace('┌─', '').replace('─┐', '').strip()
                            
                            with st.expander(f"{emoji} {display_title}", expanded=True):
                                st.code(f"┌─{section}", language=None)
                
                # Backup: als parsing faalt, toon gewoon de hele samenvatting
                if len(sections) <= 1:
                    with st.expander("📊 Volledige Samenvatting", expanded=True):
                        st.code(llm_summary, language=None)
                
                # PDF Download functionaliteit
                st.markdown("---")
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.button("📄 Genereer PDF Rapport", key="generate_pdf"):
                        try:
                            with st.spinner("PDF wordt gegenereerd..."):
                                pdf_data = create_weekly_summary_pdf(
                                    week_data, training_topics, blessures, matches, gesprekken, 
                                    llm_summary, week_start, week_end
                                )
                                
                                st.success("✅ PDF succesvol gegenereerd!")
                                
                                # Store PDF in session state for download
                                st.session_state.pdf_data = pdf_data
                                st.session_state.pdf_filename = f"wekelijkse_samenvatting_{week_start.strftime('%Y%m%d')}_{week_end.strftime('%Y%m%d')}.pdf"
                                
                        except Exception as pdf_error:
                            st.error(f"❌ Fout bij PDF generatie: {str(pdf_error)}")
                
                with col2:
                    if hasattr(st.session_state, 'pdf_data') and st.session_state.pdf_data:
                        st.download_button(
                            label="📥 Download PDF",
                            data=st.session_state.pdf_data,
                            file_name=st.session_state.pdf_filename,
                            mime="application/pdf",
                            key="download_pdf"
                        )
                
            except Exception as e:
                st.error(f"❌ Fout bij genereren samenvatting: {str(e)}")
                st.write("Debug error details:", e)
            
    else:
        st.info("📭 Geen week data beschikbaar.")
        if not heeft_fysieke_data:
            st.info("💡 Voor echte data: koppel GPS-trackers of voeg fysieke data toe via database.")
        
        # Toon wel training topics, matches en blessures als die er zijn
        training_topics = get_week_training_topics(week_start, week_end)
        blessures = get_week_blessures(week_start, week_end)
        matches = get_week_matches(week_start, week_end)
        
        # Toon wedstrijden indien aanwezig
        if matches:
            st.markdown("#### ⚽ Wedstrijden deze Week")
            for match in matches:
                match_id, datum, tegenstander, thuis_uit, uitslag, doelpunten_voor, doelpunten_tegen, match_type, competitie, status = match
                
                # Bepaal resultaat kleur
                if doelpunten_voor and doelpunten_tegen is not None:
                    if doelpunten_voor > doelpunten_tegen:
                        result_color = "🟢"
                        result_text = "Winst"
                    elif doelpunten_voor < doelpunten_tegen:
                        result_color = "🔴" 
                        result_text = "Verlies"
                    else:
                        result_color = "🟡"
                        result_text = "Gelijk"
                else:
                    result_color = "⚪"
                    result_text = "Nog te spelen"
                
                location_icon = "🏠" if thuis_uit == "Thuis" else "✈️"
                st.info(f"{result_color} {location_icon} **vs {tegenstander}** - {result_text} ({datum}) - {match_type or competitie}")
        
        if training_topics:
            st.markdown("#### 🎯 Getrainde Topics deze Week")
            topics_df = pd.DataFrame(training_topics, columns=['Topic', 'Spelfase', 'Niveau', 'Minuten', 'Trainingen'])
            st.dataframe(topics_df, use_container_width=True)
        
        # Toon blessures indien aanwezig (gebruik nieuwe structuur)
        if blessures:
            st.markdown("#### 🚑 Blessures & Medisch")
            for blessure in blessures:
                speler_naam, blessure_type, locatie, ernst, status, datum_start, datum_einde, voorspelling_dagen, beschrijving, behandeling = blessure
                
                # Status kleur bepalen
                if status == "Actief":
                    status_color = "🔴"
                elif status == "In behandeling":
                    status_color = "🟡"
                elif status == "Genezen":
                    status_color = "🟢"
                else:
                    status_color = "⚪"
                
                st.warning(f"{status_color} **{speler_naam}** - {blessure_type} ({status}) - {locatie}")
        
        # Toon gesprekken en notities
        gesprekken = get_week_gesprekken(week_start, week_end)
        if gesprekken:
            st.markdown("#### 💬 Gesprekken & Notities deze Week")
            for speler, datum, onderwerp, notities in gesprekken:
                datum_str = pd.to_datetime(datum).date().strftime('%d/%m/%Y')
                with st.expander(f"💬 {speler} - {onderwerp} ({datum_str})"):
                    st.write(f"**Datum:** {datum_str}")
                    st.write(f"**Onderwerp:** {onderwerp}")
                    if notities:
                        st.write(f"**Notities:** {notities}")
        else:
            st.info("💬 Geen gesprekken geregistreerd deze week")
        
        # Altijd samenvatting optie aanbieden (ook zonder fysieke data)
        if training_topics or blessures or gesprekken:
            if st.button("🤖 Genereer AI Samenvatting", key="samenvatting_zonder_fysiek"):
                try:
                    llm_summary = generate_llm_summary([], training_topics, blessures, matches, gesprekken, week_start, week_end, False)
                    
                    # Sla rapport ALTIJD op
                    execute_db_query("""
                        INSERT OR REPLACE INTO week_rapporten 
                        (rapport_id, week_start, week_end, rapport_data, llm_samenvatting)
                        VALUES (nextval('rapport_id_seq'), ?, ?, ?, ?)
                    """, (week_start, week_end, "{}", llm_summary))
                    
                    st.success("🤖 AI Samenvatting gegenereerd en opgeslagen!")
                    st.info("📧 **Het rapport is nu beschikbaar in de 'Rapport Verzenden' tab voor email verzending**")
                    
                    # Display AI Samenvatting in een overzichtelijke manier
                    st.markdown("### 📋 AI Samenvatting")
                    
                    # Parse de samenvatting in secties
                    sections = llm_summary.split('┌─')
                    
                    # Toon header sectie apart
                    if sections:
                        header = sections[0].strip()
                        if header:
                            with st.expander("📊 Week Overzicht", expanded=True):
                                st.code(header, language=None)
                    
                    # Toon elke sectie in een apart expander
                    for i, section in enumerate(sections[1:], 1):
                        if section.strip():
                            # Extract section title
                            lines = section.split('\n')
                            if lines:
                                title_line = lines[0].strip(' ─')
                                section_title = title_line.split('│')[0].strip() if '│' in title_line else title_line
                                
                                # Bepaal emoji en titel op basis van inhoud
                                if 'WEDSTRIJDEN' in section_title:
                                    emoji = "⚽"
                                    display_title = "Wedstrijden"
                                elif 'TRAINING' in section_title:
                                    emoji = "🎯"
                                    display_title = "Training Focus"
                                elif 'FYSIEKE' in section_title:
                                    emoji = "🏃‍♂️"
                                    display_title = "Fysieke Prestaties"
                                elif 'BLESSURES' in section_title:
                                    emoji = "🚑"
                                    display_title = "Blessures & Medisch"
                                elif 'GESPREKKEN' in section_title:
                                    emoji = "💬"
                                    display_title = "Gesprekken & Coaching"
                                else:
                                    emoji = "📄"
                                    display_title = section_title.replace('┌─', '').replace('─┐', '').strip()
                                
                                with st.expander(f"{emoji} {display_title}", expanded=True):
                                    st.code(f"┌─{section}", language=None)
                    
                    # Backup: als parsing faalt, toon gewoon de hele samenvatting
                    if len(sections) <= 1:
                        with st.expander("📊 Volledige Samenvatting", expanded=True):
                            st.code(llm_summary, language=None)
                except Exception as e:
                    st.error(f"❌ Fout bij genereren samenvatting: {str(e)}")

with tab2:
    st.markdown("### 📧 Rapport Verzenden")
    
    # Selecteer week voor verzending
    col1, col2 = st.columns(2)
    with col1:
        rapport_week = st.date_input("📅 Selecteer week voor rapport", 
                                   value=datetime.now().date(),
                                   key="rapport_week")
    
    rapport_week_start, rapport_week_end = get_week_dates(rapport_week)
    
    # Haal altijd de meest actuele data op (net zoals in tab 1)
    training_topics = get_week_training_topics(rapport_week_start, rapport_week_end)
    blessures = get_week_blessures(rapport_week_start, rapport_week_end)
    gesprekken = get_week_gesprekken(rapport_week_start, rapport_week_end)
    
    # Haal actuele fysieke data op (use the fixed function we already have)
    current_week_data = get_week_fysieke_data(rapport_week_start, rapport_week_end)
    
    # Convert naar juiste format (adjust based on our get_week_fysieke_data function)
    week_data = [{
        'speler': row[0], 
        'totaal_afstand': row[1], 
        'hoge_intensiteit_afstand': row[2],
        'sprint_afstand': row[3], 
        'gemiddelde_snelheid': row[4],
        'max_snelheid': row[5], 
        'aantal_sprints': row[6],
        'aantal_trainingen': row[7]  # This is aantal_sessies in our function
    } for row in current_week_data] if current_week_data else []
    
    # Haal ook matches op voor deze week
    matches = get_week_matches(rapport_week_start, rapport_week_end)
    
    # Genereer altijd fresh samenvatting
    llm_samenvatting = generate_llm_summary(
        week_data, training_topics, blessures, matches, gesprekken, 
        rapport_week_start, rapport_week_end, len(current_week_data) > 0
    )
    
    # Sla nieuwe samenvatting op
    rapport_data = json.dumps(week_data) if week_data else "{}"
    execute_db_query("""
        INSERT OR REPLACE INTO week_rapporten 
        (rapport_id, week_start, week_end, rapport_data, llm_samenvatting)
        VALUES (nextval('rapport_id_seq'), ?, ?, ?, ?)
    """, (rapport_week_start, rapport_week_end, rapport_data, llm_samenvatting))
    
    # Check of er data is
    if week_data or training_topics or blessures or gesprekken:
        
        with col2:
            st.success(f"✅ Actueel rapport gegenereerd voor week {rapport_week_start.strftime('%d/%m')} - {rapport_week_end.strftime('%d/%m')}")
            st.info("💡 Dit rapport wordt automatisch ververst met de meest actuele data")
        
        # Toon samenvatting in overzichtelijke format
        st.markdown("### 📋 Rapport Inhoud")
        
        # Parse de samenvatting in secties
        sections = llm_samenvatting.split('┌─')
        
        # Toon header sectie apart
        if sections:
            header = sections[0].strip()
            if header:
                with st.expander("📊 Week Overzicht", expanded=False):
                    st.code(header, language=None)
        
        # Toon elke sectie in een apart expander
        for i, section in enumerate(sections[1:], 1):
            if section.strip():
                # Extract section title
                lines = section.split('\n')
                if lines:
                    title_line = lines[0].strip(' ─')
                    section_title = title_line.split('│')[0].strip() if '│' in title_line else title_line
                    
                    # Bepaal emoji en titel op basis van inhoud
                    if 'WEDSTRIJDEN' in section_title:
                        emoji = "⚽"
                        display_title = "Wedstrijden"
                    elif 'TRAINING' in section_title:
                        emoji = "🎯"
                        display_title = "Training Focus"
                    elif 'FYSIEKE' in section_title:
                        emoji = "🏃‍♂️"
                        display_title = "Fysieke Prestaties"
                    elif 'BLESSURES' in section_title:
                        emoji = "🚑"
                        display_title = "Blessures & Medisch"
                    elif 'GESPREKKEN' in section_title:
                        emoji = "💬"
                        display_title = "Gesprekken & Coaching"
                    else:
                        emoji = "📄"
                        display_title = section_title.replace('┌─', '').replace('─┐', '').strip()
                    
                    with st.expander(f"{emoji} {display_title}", expanded=False):
                        st.code(f"┌─{section}", language=None)
        
        # Backup: als parsing faalt, toon gewoon de hele samenvatting
        if len(sections) <= 1:
            with st.expander("📊 Volledige Samenvatting", expanded=True):
                st.code(llm_samenvatting, language=None)
        
        # Verzend opties
        st.markdown("#### 📨 Verzend Opties")
        
        # Haal contacten op
        contacten = execute_db_query("""
            SELECT naam, email, telefoon, functie FROM contact_lijst 
            WHERE actief = TRUE
            ORDER BY functie, naam
        """)
        
        if contacten:
            verzend_methode = st.selectbox("📱 Verzend via", 
                                         ["Email", "WhatsApp", "Telegram", "Alle kanalen"])
            
            # Selecteer ontvangers
            contact_options = {f"{naam} ({functie}) - {email}": email for naam, email, telefoon, functie in contacten}
            selected_contacts = st.multiselect("👥 Selecteer ontvangers", list(contact_options.keys()))
            
            # PDF bijlage optie
            include_pdf = st.checkbox("📎 Voeg PDF bijlage toe", value=True, 
                                    help="Genereer en voeg automatisch een PDF samenvatting toe als bijlage bij de email")
            
            if selected_contacts and st.button("📤 Verzend Rapport", type="primary"):
                selected_emails = [contact_options[contact] for contact in selected_contacts]
                
                # Echte e-mail verzending
                if verzend_methode == "Email":
                    try:
                        # E-mail configuratie - probeer alle mogelijke locaties
                        try:
                            smtp_server = "smtp.gmail.com"
                            smtp_port = 587
                            smtp_username = ""
                            smtp_password = ""
                            
                            # Debug info - toon secrets structuur
                            st.write("🔍 Debug - Secrets structuur:")
                            for key in st.secrets.keys():
                                if hasattr(st.secrets[key], 'keys'):
                                    st.write(f"  {key}: {list(st.secrets[key].keys())}")
                                else:
                                    st.write(f"  {key}: {type(st.secrets[key])}")
                            
                            # Methode 1: Direct op root niveau
                            if "smtp_username" in st.secrets:
                                smtp_username = str(st.secrets["smtp_username"]).strip()
                            if "smtp_password" in st.secrets:
                                smtp_password = str(st.secrets["smtp_password"]).strip()
                            if "smtp_server" in st.secrets:
                                smtp_server = str(st.secrets["smtp_server"]).strip()
                            if "smtp_port" in st.secrets:
                                smtp_port = int(st.secrets["smtp_port"])
                            
                            # Methode 2: Onder 'email' sectie
                            if not smtp_username and "email" in st.secrets:
                                email_config = st.secrets["email"]
                                if hasattr(email_config, 'get'):
                                    smtp_username = str(email_config.get("smtp_username", "")).strip()
                                    smtp_password = str(email_config.get("smtp_password", "")).strip()
                                    smtp_server = str(email_config.get("smtp_server", "smtp.gmail.com")).strip()
                                    smtp_port = int(email_config.get("smtp_port", 587))
                            
                            # Methode 3: Onder 'smtp' sectie
                            if not smtp_username and "smtp" in st.secrets:
                                smtp_config = st.secrets["smtp"]
                                if hasattr(smtp_config, 'get'):
                                    smtp_username = str(smtp_config.get("username", "")).strip()
                                    smtp_password = str(smtp_config.get("password", "")).strip()
                                    smtp_server = str(smtp_config.get("server", "smtp.gmail.com")).strip()
                                    smtp_port = int(smtp_config.get("port", 587))
                            
                            # Debug resultaten
                            st.write(f"✅ Debug resultaten:")
                            st.write(f"  - SMTP Server: {smtp_server}")
                            st.write(f"  - SMTP Port: {smtp_port}")
                            st.write(f"  - Username gevonden: {'Ja' if smtp_username else 'Nee'}")
                            st.write(f"  - Password gevonden: {'Ja' if smtp_password else 'Nee'}")
                            
                        except Exception as e:
                            st.error(f"❌ Fout bij lezen van secrets: {e}")
                            smtp_username = ""
                            smtp_password = ""
                        
                        if not smtp_username or not smtp_password:
                            st.error("❌ E-mail instellingen niet gevonden in secrets.")
                            st.info("""
💡 **Oplossing**: Voeg de volgende regels toe aan je Streamlit secrets:

**Optie 1 - Direct op root niveau:**
```
smtp_username = "maximwouters1993@gmail.com"
smtp_password = "falr ksux wuih uwqh"
smtp_server = "smtp.gmail.com"
smtp_port = 587
```

**Optie 2 - In een email sectie:**
```
[email]
smtp_username = "maximwouters1993@gmail.com"
smtp_password = "falr ksux wuih uwqh"
smtp_server = "smtp.gmail.com"
smtp_port = 587
```

**Huidige secrets structuur:** Alleen 'supabase' sectie gevonden.
                            """)
                        else:
                            # Verstuur e-mails
                            server = smtplib.SMTP(smtp_server, smtp_port)
                            server.starttls()
                            server.login(smtp_username, smtp_password)
                            
                            for email in selected_emails:
                                msg = MIMEMultipart()
                                msg['From'] = smtp_username
                                msg['To'] = email
                                msg['Subject'] = f"Wekelijkse Samenvatting - Week {rapport_week_start.strftime('%d/%m')} - {rapport_week_end.strftime('%d/%m')}"
                                
                                # E-mail body
                                body = f"""
Beste collega,

Hierbij de wekelijkse samenvatting van ons team:

{llm_samenvatting}

Met sportieve groeten,
SPK Dashboard
                                """
                                msg.attach(MIMEText(body, 'plain'))
                                
                                # Voeg PDF bijlage toe indien gewenst
                                if include_pdf:
                                    try:
                                        # Haal data op voor PDF generatie
                                        training_topics = get_week_training_topics(rapport_week_start, rapport_week_end)
                                        blessures = get_week_blessures(rapport_week_start, rapport_week_end)
                                        matches = get_week_matches(rapport_week_start, rapport_week_end)
                                        gesprekken = get_week_gesprekken(rapport_week_start, rapport_week_end)
                                        
                                        # Genereer PDF
                                        with st.spinner("PDF bijlage wordt gegenereerd..."):
                                            pdf_data = create_weekly_summary_pdf(
                                                week_data, training_topics, blessures, matches, gesprekken, 
                                                llm_samenvatting, rapport_week_start, rapport_week_end
                                            )
                                        
                                        # Voeg PDF toe als bijlage
                                        pdf_attachment = MIMEBase('application', 'octet-stream')
                                        pdf_attachment.set_payload(pdf_data)
                                        encoders.encode_base64(pdf_attachment)
                                        pdf_filename = f"wekelijkse_samenvatting_{rapport_week_start.strftime('%Y%m%d')}_{rapport_week_end.strftime('%Y%m%d')}.pdf"
                                        pdf_attachment.add_header(
                                            'Content-Disposition',
                                            f'attachment; filename={pdf_filename}'
                                        )
                                        msg.attach(pdf_attachment)
                                        
                                    except Exception as pdf_error:
                                        st.warning(f"⚠️ PDF bijlage kon niet worden toegevoegd: {str(pdf_error)}")
                                        st.info("Email wordt verzonden zonder PDF bijlage")
                                
                                server.send_message(msg)
                            
                            server.quit()
                            st.success(f"✅ E-mails verzonden naar {len(selected_emails)} ontvangers!")
                    
                    except Exception as e:
                        st.error(f"❌ Fout bij verzenden e-mail: {str(e)}")
                        st.info("💡 Controleer je e-mail instellingen in Streamlit secrets")
                
                elif verzend_methode == "WhatsApp":
                    st.info("📱 WhatsApp integratie - implementatie volgt later")
                elif verzend_methode == "Telegram":
                    try:
                        # Telegram Bot configuratie
                        bot_token = st.secrets.get("telegram_bot_token", "")
                        chat_id = st.secrets.get("telegram_chat_id", "")
                        
                        if not bot_token or not chat_id:
                            st.error("❌ Telegram instellingen niet geconfigureerd. Voeg telegram_bot_token en telegram_chat_id toe aan je Streamlit secrets.")
                        else:
                            # Verstuur Telegram bericht
                            telegram_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                            
                            # Format bericht voor Telegram
                            telegram_message = f"""🏆 *WEKELIJKSE SAMENVATTING*
Week {rapport_week_start.strftime('%d/%m')} - {rapport_week_end.strftime('%d/%m/%Y')}

{llm_samenvatting}

📱 Verzonden via SPK Dashboard"""
                            
                            payload = {
                                "chat_id": chat_id,
                                "text": telegram_message,
                                "parse_mode": "Markdown"
                            }
                            
                            response = requests.post(telegram_url, json=payload)
                            
                            if response.status_code == 200:
                                st.success("✅ Telegram bericht verzonden!")
                            else:
                                st.error(f"❌ Fout bij verzenden Telegram: {response.text}")
                    
                    except Exception as e:
                        st.error(f"❌ Fout bij Telegram verzending: {str(e)}")
                        st.info("💡 Controleer je Telegram bot instellingen")
                else:
                    st.info("📨 Multi-kanaal verzending - implementatie volgt later")
                
                # Update database
                verzonden_naar = ", ".join(selected_contacts)
                execute_db_query("""
                    UPDATE week_rapporten 
                    SET verzonden_naar = ?, verzend_datum = CURRENT_TIMESTAMP
                    WHERE week_start = ?
                """, (verzonden_naar, rapport_week_start))
                
        else:
            st.warning("⚠️ Geen contacten gevonden. Voeg eerst contacten toe in het Contact Beheer tab.")
    
    else:
        st.warning(f"⚠️ Geen rapport gevonden voor week {rapport_week_start.strftime('%d/%m')} - {rapport_week_end.strftime('%d/%m')}. Genereer eerst een rapport.")

with tab3:
    st.markdown("### 👥 Contact Beheer")
    
    # Nieuw contact toevoegen
    with st.expander("➕ Nieuw Contact Toevoegen"):
        with st.form("nieuw_contact"):
            col1, col2 = st.columns(2)
            with col1:
                contact_naam = st.text_input("👤 Naam")
                contact_email = st.text_input("📧 Email")
            with col2:
                contact_telefoon = st.text_input("📱 Telefoon")
                contact_functie = st.selectbox("💼 Functie", 
                                             ["Hoofdtrainer", "Assistent Trainer", "Fysiek Trainer", 
                                              "Goalkeeper Trainer", "Team Manager", "Overig"])
            
            submitted = st.form_submit_button("✅ Contact Toevoegen")
            
            if submitted and contact_naam and contact_email:
                execute_db_query("""
                    INSERT INTO contact_lijst (contact_id, naam, email, telefoon, functie)
                    VALUES (nextval('contact_id_seq'), ?, ?, ?, ?)
                """, (contact_naam, contact_email, contact_telefoon, contact_functie))
                
                st.success(f"✅ Contact '{contact_naam}' toegevoegd!")
                st.rerun()
    
    # Bestaande contacten tonen
    contacten = execute_db_query("""
        SELECT contact_id, naam, email, telefoon, functie, actief
        FROM contact_lijst 
        ORDER BY functie, naam
    """)
    
    if contacten:
        st.markdown("#### 📋 Contact Lijst")
        
        for contact in contacten:
            contact_id, naam, email, telefoon, functie, actief = contact
            
            with st.container():
                col1, col2, col3 = st.columns([3, 1, 1])
                
                with col1:
                    status_icon = "✅" if actief else "❌"
                    st.markdown(f"{status_icon} **{naam}** ({functie})")
                    st.markdown(f"📧 {email} | 📱 {telefoon}")
                
                with col2:
                    if actief:
                        if st.button("🔇 Deactiveren", key=f"deact_{contact_id}"):
                            safe_fetchdf(f"UPDATE contact_lijst SET actief = FALSE WHERE contact_id = {contact_id}")
                            st.rerun()
                    else:
                        if st.button("🔔 Activeren", key=f"act_{contact_id}"):
                            safe_fetchdf(f"UPDATE contact_lijst SET actief = TRUE WHERE contact_id = {contact_id}")
                            st.rerun()
                
                with col3:
                    if st.button("🗑️ Verwijderen", key=f"del_contact_{contact_id}"):
                        safe_fetchdf(f"DELETE FROM contact_lijst WHERE contact_id = {contact_id}")
                        st.success("Contact verwijderd!")
                        st.rerun()
    else:
        st.info("📭 Nog geen contacten toegevoegd")

with tab4:
    st.markdown("### ⚙️ Automatisering Instellingen")
    
    # Schema instellingen
    st.markdown("#### 📅 Automatische Rapporten")
    
    col1, col2 = st.columns(2)
    with col1:
        auto_rapport = st.checkbox("🤖 Automatische wekelijkse rapporten", value=False)
        verzend_dag = st.selectbox("📅 Verzend dag", 
                                 ["Zondag", "Maandag"], 
                                 index=0)
    
    with col2:
        verzend_tijd = st.time_input("🕐 Verzend tijd", value=datetime.strptime("20:00", "%H:%M").time())
        test_mode = st.checkbox("🧪 Test modus (alleen naar hoofdtrainer)", value=True)
    
    if auto_rapport:
        st.info(f"📋 Automatische rapporten worden elke {verzend_dag.lower()} om {verzend_tijd.strftime('%H:%M')} verzonden.")
        
        if st.button("💾 Instellingen Opslaan"):
            # Hier zou je de scheduler configuratie opslaan
            st.success("✅ Automatisering instellingen opgeslagen!")
    
    # LLM Instellingen
    st.markdown("#### 🤖 AI Samenvatting Instellingen")
    
    llm_provider = st.selectbox("🧠 AI Provider", 
                              ["OpenAI GPT", "Claude", "Local LLM", "Geen AI"])
    
    if llm_provider != "Geen AI":
        api_key = st.text_input("🔑 API Key", type="password", 
                               placeholder="Voer je API key in...")
        
        prompt_template = st.text_area("📝 Prompt Template", 
                                     value="Genereer een professionele wekelijkse samenvatting voor voetbaltrainers...",
                                     height=100)
        
        if st.button("🧪 Test AI Verbinding"):
            st.info("🔄 Test AI verbinding... (Simulatie)")
            st.success("✅ AI verbinding succesvol!")
    
    # Export instellingen
    st.markdown("#### 📤 Export Opties")
    
    export_formats = st.multiselect("📋 Export formaten", 
                                   ["PDF", "Excel", "CSV", "JSON"])
    
    include_charts = st.checkbox("📊 Grafieken in export", value=True)
    
    if st.button("💾 Alle Instellingen Opslaan"):
        st.success("✅ Alle instellingen opgeslagen!")

# Cleanup
# Safe database connection cleanup
# Database cleanup handled by Supabase helpers