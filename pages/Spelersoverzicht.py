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
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import plotly.express as px
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.backends.backend_pdf import PdfPages
from io import BytesIO
import numpy as np


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
                return execute_db_query(query, params)
            else:
                return execute_db_query(query)
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

st.set_page_config(page_title="Spelersoverzicht - SPK Dashboard", layout="wide")

# Custom CSS styling consistent with home page
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #2E86AB 0%, #A23B72 100%);
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 2rem;
        color: white;
        text-align: center;
    }
    
    .info-card {
        background: linear-gradient(135deg, #FAFCFF 0%, #E8F4FD 100%);
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 4px solid #2E86AB;
        margin: 1rem 0;
        box-shadow: 0 2px 4px rgba(46, 134, 171, 0.1);
    }
    
    .section-card {
        background: white;
        padding: 1.2rem;
        border-radius: 8px;
        border: 1px solid #E8F4FD;
        margin: 0.8rem 0;
        box-shadow: 0 2px 4px rgba(46, 134, 171, 0.05);
    }
    
    .accent-blue { color: #2E86AB; font-weight: bold; }
    .accent-purple { color: #A23B72; font-weight: bold; }
    .accent-orange { color: #F18F01; font-weight: bold; }
    .accent-green { color: #2E8B57; font-weight: bold; }
    
    .metric-box {
        background: linear-gradient(135deg, #F0F8FF 0%, #E8F4FD 100%);
        padding: 1rem;
        border-radius: 8px;
        text-align: center;
        margin: 0.5rem 0;
        border: 1px solid #E8F4FD;
    }
    
    .goal-item {
        background: #F8FFFA;
        border-left: 4px solid #2E8B57;
        padding: 0.8rem;
        margin: 0.5rem 0;
        border-radius: 0 8px 8px 0;
    }
    
    .conversation-item {
        background: #FFF8F0;
        border-left: 4px solid #F18F01;
        padding: 0.8rem;
        margin: 0.5rem 0;
        border-radius: 0 8px 8px 0;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header"><h1>👤 Spelersoverzicht</h1></div>', unsafe_allow_html=True)

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
# Zorg ervoor dat de benodigde tabellen bestaan
execute_db_query("""
    CREATE TABLE IF NOT EXISTS speler_doelen (
        doel_id INTEGER PRIMARY KEY,
        speler TEXT,
        doeltype TEXT,
        titel TEXT,
        beschrijving TEXT,
        target_datum DATE,
        status TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")

execute_db_query("""
    CREATE TABLE IF NOT EXISTS gesprek_notities (
        notitie_id INTEGER PRIMARY KEY,
        speler TEXT,
        datum DATE,
        onderwerp TEXT,
        notities TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")

# Sequences maken indien nodig
try:
    execute_db_query("CREATE SEQUENCE IF NOT EXISTS doel_id_seq START 1")
    execute_db_query("CREATE SEQUENCE IF NOT EXISTS notitie_id_seq START 1")
except:
    pass

# Check database migratie voor MAS kolom
try:
    existing_columns = get_table_columns(con, "thirty_fifteen_results")
    
    if add_column_if_not_exists(con, "thirty_fifteen_results", "MAS", "MAS DOUBLE"):
        execute_db_query("UPDATE thirty_fifteen_results SET MAS = TrueVIFT * 0.95 WHERE MAS IS NULL")
except:
    pass

# Check of er data is
table_exists = check_table_exists("thirty_fifteen_results")

if not table_exists:
    st.warning("📭 Er zijn nog geen testresultaten beschikbaar.")
else:
    # Haal alle data op
    all_data = safe_fetchdf("SELECT * FROM thirty_fifteen_results ORDER BY Maand DESC, Speler")
    
    # Ensure numeric columns are properly typed for calculations and formatting
    if not all_data.empty:
        numeric_columns = ['MAS', 'TrueVIFT', 'VO2MAX', 'PeakVelocity', 'Gewicht', 'Lengte']
        for col in numeric_columns:
            if col in all_data.columns:
                all_data[col] = pd.to_numeric(all_data[col], errors='coerce')
    
    # Check en bereken MAS als deze niet bestaat
    if 'MAS' not in all_data.columns:
        all_data['MAS'] = all_data['TrueVIFT'] * 0.95
    elif not all_data.empty:
        # Ensure MAS is numeric even if it exists
        all_data['MAS'] = pd.to_numeric(all_data['MAS'], errors='coerce')
    
    if len(all_data) == 0:
        st.warning("📭 Er zijn nog geen testresultaten beschikbaar.")
    else:
        # Speler selectie
        spelers = sorted(all_data["Speler"].unique())
        selected_speler = st.selectbox("👤 Selecteer speler", spelers)
        
        # Filter data voor geselecteerde speler
        speler_data = all_data[all_data["Speler"] == selected_speler].sort_values("Maand")
        
        if len(speler_data) == 0:
            st.warning(f"Geen data gevonden voor {selected_speler}")
        else:
            # Hoofdlayout in drie kolommen
            col1, col2, col3 = st.columns([2, 1, 1])
            
            # ==================== FYSIEKE TESTING (30-15) ====================
            with col1:
                st.markdown('<div class="info-card">', unsafe_allow_html=True)
                st.markdown("### <span class='accent-blue'>🧪 Fysieke Testing (30-15)</span>", unsafe_allow_html=True)
                
                # Laatste testresultaten
                laatste_test = speler_data.iloc[-1]
                
                # Prestatie metrics in 2x2 grid
                met_col1, met_col2 = st.columns(2)
                
                with met_col1:
                    st.markdown('<div class="metric-box">', unsafe_allow_html=True)
                    st.metric("🏃‍♂️ MAS", f"{laatste_test['MAS']:.1f} km/u", 
                             delta=f"{(laatste_test['MAS'] - speler_data.iloc[0]['MAS']):.1f}" if len(speler_data) > 1 else None)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    st.markdown('<div class="metric-box">', unsafe_allow_html=True)
                    st.metric("⚡ Peak Velocity", f"{laatste_test['PeakVelocity']:.1f} km/u")
                    st.markdown('</div>', unsafe_allow_html=True)
                
                with met_col2:
                    st.markdown('<div class="metric-box">', unsafe_allow_html=True)
                    st.metric("🫁 VO2Max", f"{laatste_test['VO2MAX']:.1f} ml/kg/min",
                             delta=f"{(laatste_test['VO2MAX'] - speler_data.iloc[0]['VO2MAX']):.1f}" if len(speler_data) > 1 else None)
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    st.markdown('<div class="metric-box">', unsafe_allow_html=True)
                    # Handle potential string/float conversion for FinishingTime
                    try:
                        finish_time = float(laatste_test['FinishingTime'])
                        st.metric("⏱️ Finish Time", f"{finish_time:.1f} s")
                    except (ValueError, TypeError):
                        st.metric("⏱️ Finish Time", f"{laatste_test['FinishingTime']} s")
                    st.markdown('</div>', unsafe_allow_html=True)
                
                # Progressie grafiek
                if len(speler_data) > 1:
                    fig = make_subplots(
                        rows=2, cols=1,
                        subplot_titles=('MAS Ontwikkeling', 'VO2Max Ontwikkeling'),
                        vertical_spacing=0.1
                    )
                    
                    # MAS grafiek
                    fig.add_trace(
                        go.Scatter(
                            x=speler_data["Maand"],
                            y=speler_data["MAS"],
                            mode='lines+markers',
                            name='MAS',
                            line=dict(color='#2E86AB', width=3),
                            marker=dict(size=8)
                        ),
                        row=1, col=1
                    )
                    
                    # VO2Max grafiek  
                    fig.add_trace(
                        go.Scatter(
                            x=speler_data["Maand"],
                            y=speler_data["VO2MAX"],
                            mode='lines+markers',
                            name='VO2Max',
                            line=dict(color='#A23B72', width=3),
                            marker=dict(size=8)
                        ),
                        row=2, col=1
                    )
                    
                    fig.update_layout(
                        height=500,
                        showlegend=False,
                        title_text=f"Prestatie Ontwikkeling - {selected_speler}"
                    )
                    
                    fig.update_xaxes(title_text="Test Maand", row=2, col=1)
                    fig.update_yaxes(title_text="MAS (km/u)", row=1, col=1)
                    fig.update_yaxes(title_text="VO2Max (ml/kg/min)", row=2, col=1)
                    
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("📊 Minimaal 2 testresultaten nodig voor progressiegrafiek")
                
                st.markdown('</div>', unsafe_allow_html=True)
                
                # GPS Prestatie Data ophalen
                gps_data = execute_db_query("""
                    SELECT datum, totale_afstand, hoge_intensiteit_afstand, zeer_hoge_intensiteit_afstand,
                           sprint_afstand, max_snelheid, aantal_sprints, aantal_acceleraties, 
                           aantal_deceleraties, impacts, player_load
                    FROM gps_data 
                    WHERE speler = ?
                    ORDER BY datum DESC
                    LIMIT 30
                """, (selected_speler,))
                
                # GPS Prestaties sectie
                st.markdown('<div class="section-card">', unsafe_allow_html=True)
                st.markdown("### <span class='accent-purple'>📊 GPS Prestaties (Training Data)</span>", unsafe_allow_html=True)
                
                if gps_data:
                    df_gps = pd.DataFrame(gps_data, columns=[
                        'datum', 'totale_afstand', 'hoge_intensiteit_afstand', 'zeer_hoge_intensiteit_afstand',
                        'sprint_afstand', 'max_snelheid', 'aantal_sprints', 'aantal_acceleraties',
                        'aantal_deceleraties', 'impacts', 'player_load'
                    ])
                    df_gps['datum'] = pd.to_datetime(df_gps['datum'])
                    
                    # GPS metrics in 3x2 grid
                    gps_col1, gps_col2, gps_col3 = st.columns(3)
                    
                    # Bereken gemiddeldes voor laatste 30 dagen
                    with gps_col1:
                        avg_distance = df_gps['totale_afstand'].mean()
                        max_distance = df_gps['totale_afstand'].max()
                        st.metric("🏃‍♂️ Total Distance", f"{avg_distance:.0f}m avg", 
                                 help=f"Max: {max_distance:.0f}m")
                        
                        avg_hsr = df_gps['hoge_intensiteit_afstand'].mean()
                        max_hsr = df_gps['hoge_intensiteit_afstand'].max()
                        st.metric("⚡ High Speed Running", f"{avg_hsr:.0f}m avg", 
                                 help=f"Max: {max_hsr:.0f}m")
                    
                    with gps_col2:
                        avg_sprint = df_gps['sprint_afstand'].mean() if 'sprint_afstand' in df_gps.columns else 0
                        max_sprint = df_gps['sprint_afstand'].max() if 'sprint_afstand' in df_gps.columns else 0
                        st.metric("💨 Sprint Distance", f"{avg_sprint:.0f}m avg", 
                                 help=f"Max: {max_sprint:.0f}m")
                        
                        avg_max_speed = df_gps['max_snelheid'].mean()
                        max_max_speed = df_gps['max_snelheid'].max()
                        st.metric("🚀 Max Speed", f"{avg_max_speed:.1f} km/u avg", 
                                 help=f"Peak: {max_max_speed:.1f} km/u")
                    
                    with gps_col3:
                        avg_accelerations = df_gps['aantal_acceleraties'].mean()
                        max_accelerations = df_gps['aantal_acceleraties'].max()
                        st.metric("🔺 Acceleraties", f"{avg_accelerations:.1f} avg", 
                                 help=f"Max: {max_accelerations:.0f}")
                        
                        avg_player_load = df_gps['player_load'].mean() if 'player_load' in df_gps.columns else 0
                        max_player_load = df_gps['player_load'].max() if 'player_load' in df_gps.columns else 0
                        st.metric("🎯 Player Load", f"{avg_player_load:.1f} avg", 
                                 help=f"Max: {max_player_load:.1f}")
                    
                    # GPS Trend grafiek (laatste 10 sessies)
                    st.markdown("#### 📈 GPS Prestatie Trends")
                    
                    recent_gps = df_gps.head(10).sort_values('datum')
                    if len(recent_gps) > 1:
                        fig_gps = make_subplots(
                            rows=2, cols=2,
                            subplot_titles=('Total Distance', 'High Speed Running', 'Max Speed', 'Acceleraties'),
                            vertical_spacing=0.12,
                            horizontal_spacing=0.1
                        )
                        
                        # Total Distance
                        fig_gps.add_trace(
                            go.Scatter(
                                x=recent_gps['datum'],
                                y=recent_gps['totale_afstand'],
                                mode='lines+markers',
                                name='Total Distance',
                                line=dict(color='#2E86AB', width=2),
                                marker=dict(size=6)
                            ),
                            row=1, col=1
                        )
                        
                        # High Speed Running
                        fig_gps.add_trace(
                            go.Scatter(
                                x=recent_gps['datum'],
                                y=recent_gps['hoge_intensiteit_afstand'],
                                mode='lines+markers',
                                name='HSR',
                                line=dict(color='#A23B72', width=2),
                                marker=dict(size=6)
                            ),
                            row=1, col=2
                        )
                        
                        # Max Speed
                        fig_gps.add_trace(
                            go.Scatter(
                                x=recent_gps['datum'],
                                y=recent_gps['max_snelheid'],
                                mode='lines+markers',
                                name='Max Speed',
                                line=dict(color='#F18F01', width=2),
                                marker=dict(size=6)
                            ),
                            row=2, col=1
                        )
                        
                        # Acceleraties
                        fig_gps.add_trace(
                            go.Scatter(
                                x=recent_gps['datum'],
                                y=recent_gps['aantal_acceleraties'],
                                mode='lines+markers',
                                name='Acceleraties',
                                line=dict(color='#2E8B57', width=2),
                                marker=dict(size=6)
                            ),
                            row=2, col=2
                        )
                        
                        fig_gps.update_layout(
                            height=500,
                            showlegend=False,
                            title_text=f"GPS Prestaties - Laatste 10 Sessies ({selected_speler})"
                        )
                        
                        # Update axes labels
                        fig_gps.update_xaxes(title_text="Datum", row=2, col=1)
                        fig_gps.update_xaxes(title_text="Datum", row=2, col=2)
                        fig_gps.update_yaxes(title_text="Meters", row=1, col=1)
                        fig_gps.update_yaxes(title_text="Meters", row=1, col=2)
                        fig_gps.update_yaxes(title_text="km/u", row=2, col=1)
                        fig_gps.update_yaxes(title_text="Aantal", row=2, col=2)
                        
                        st.plotly_chart(fig_gps, use_container_width=True)
                    
                else:
                    st.info("📈 Nog geen GPS training data beschikbaar voor deze speler")
                
                st.markdown('</div>', unsafe_allow_html=True)
            
            # ==================== ONTWIKKELINGSDOELEN ====================
            with col2:
                st.markdown('<div class="info-card">', unsafe_allow_html=True)
                st.markdown("### <span class='accent-green'>🎯 Ontwikkelingsdoelen</span>", unsafe_allow_html=True)
                
                # Haal doelen op uit database
                doelen = execute_db_query("""
                    SELECT doel_id, doeltype, titel, beschrijving, target_datum, status, created_at
                    FROM speler_doelen 
                    WHERE speler = ?
                    ORDER BY created_at DESC
                    LIMIT 5
                """, (selected_speler,))
                
                if doelen:
                    # Toon eerste paar doelen
                    for doel in doelen[:3]:  # Toon max 3 doelen in overzicht
                        doel_id, doeltype, titel, beschrijving, target_datum, status, created_at = doel
                        
                        # Status icoon
                        status_icons = {
                            "Actief": "🟢",
                            "Behaald": "✅", 
                            "Uitgesteld": "🟡",
                            "Geannuleerd": "🔴"
                        }
                        
                        target_str = pd.to_datetime(target_datum).date().strftime('%d/%m/%Y')
                        
                        st.markdown(f"""
                        <div class="goal-item">
                            <strong>{status_icons.get(status, '⚪')} [{doeltype}] {titel}</strong><br>
                            <small>Doel datum: {target_str} | Status: {status}</small><br>
                            {beschrijving[:100]}{'...' if len(beschrijving) > 100 else ''}
                        </div>
                        """, unsafe_allow_html=True)
                    
                    if len(doelen) > 3:
                        st.caption(f"En {len(doelen) - 3} andere doelen...")
                    
                    # Link naar Speler Progressie pagina
                    st.info("🔗 Voor volledig doelen beheer, ga naar de 'Speler Progressie' pagina.")
                    
                else:
                    st.markdown("""
                    <div class="goal-item">
                        <strong>📝 Geen doelen ingesteld</strong><br>
                        Voeg doelen toe via de 'Speler Progressie' pagina.
                    </div>
                    """, unsafe_allow_html=True)
                    
                    st.info("🏁 **Ontwikkelingsdoelen** kunnen worden toegevoegd via de 'Speler Progressie' pagina.")
                
                st.markdown('</div>', unsafe_allow_html=True)
            
            # ==================== GESPREKKEN & NOTITIES ====================
            with col3:
                st.markdown('<div class="info-card">', unsafe_allow_html=True)
                st.markdown("### <span class='accent-orange'>💬 Gesprekken & Notities</span>", unsafe_allow_html=True)
                
                # Haal gesprekken op uit database
                gesprekken = execute_db_query("""
                    SELECT notitie_id, datum, onderwerp, notities, created_at
                    FROM gesprek_notities 
                    WHERE speler = ?
                    ORDER BY datum DESC
                    LIMIT 5
                """, (selected_speler,))
                
                if gesprekken:
                    # Toon eerste paar gesprekken
                    for gesprek in gesprekken[:3]:  # Toon max 3 gesprekken in overzicht
                        notitie_id, datum, onderwerp, notities, created_at = gesprek
                        datum_str = pd.to_datetime(datum).date().strftime('%d/%m/%Y')
                        
                        # Kort notitie preview (eerste 80 karakters)
                        notitie_preview = notities[:80] + '...' if len(notities) > 80 else notities
                        
                        st.markdown(f"""
                        <div class="conversation-item">
                            <strong>💬 {onderwerp}</strong><br>
                            <small>{datum_str}</small><br>
                            {notitie_preview}
                        </div>
                        """, unsafe_allow_html=True)
                    
                    if len(gesprekken) > 3:
                        st.caption(f"En {len(gesprekken) - 3} andere gesprekken...")
                    
                    # Link naar Speler Progressie pagina
                    st.info("🔗 Voor volledig gesprekken beheer, ga naar de 'Speler Progressie' pagina.")
                    
                else:
                    st.markdown("""
                    <div class="conversation-item">
                        <strong>📝 Geen gesprekken</strong><br>
                        Voeg gesprekken toe via de 'Speler Progressie' pagina.
                    </div>
                    """, unsafe_allow_html=True)
                    
                    st.info("💬 **Gesprekken en notities** kunnen worden toegevoegd via de 'Speler Progressie' pagina.")
                
                st.markdown('</div>', unsafe_allow_html=True)
                
            st.markdown('</div>', unsafe_allow_html=True)
            
            # ==================== WEDSTRIJD PRESTATIES ====================
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown("### <span class='accent-green'>⚽ Wedstrijd Prestaties</span>", unsafe_allow_html=True)
            
            # Haal wedstrijd data op
            try:
                # Match lineups (minutes played, positions) - get separately then merge
                lineups_df = safe_fetchdf(f"SELECT * FROM match_lineups WHERE speler = '{selected_speler}'")
                matches_df = safe_fetchdf("SELECT match_id, datum, tegenstander, doelpunten_voor, doelpunten_tegen FROM matches")
                
                # Merge lineups with match details
                if not lineups_df.empty and not matches_df.empty:
                    lineups_df = lineups_df.merge(matches_df, on='match_id', how='left').sort_values('datum', ascending=False)
                
                # Match ratings
                ratings_df = safe_fetchdf(f"SELECT * FROM match_ratings WHERE speler = '{selected_speler}'")
                
                # Match events - get separately then merge
                events_df = safe_fetchdf(f"SELECT * FROM match_events WHERE speler = '{selected_speler}'")
                if not events_df.empty and not matches_df.empty:
                    events_df = events_df.merge(matches_df[['match_id', 'datum']], on='match_id', how='left').sort_values(['datum', 'minuut'], ascending=[False, False])
                
                if not lineups_df.empty:
                    # Ensure numeric conversion for match data
                    numeric_cols = ['minuten_gespeeld', 'doelpunten_voor', 'doelpunten_tegen']
                    for col in numeric_cols:
                        if col in lineups_df.columns:
                            lineups_df[col] = pd.to_numeric(lineups_df[col], errors='coerce')
                    
                    if not ratings_df.empty:
                        ratings_df['rating'] = pd.to_numeric(ratings_df['rating'], errors='coerce')
                    
                    # Summary metrics
                    total_matches = len(lineups_df)
                    total_minutes = lineups_df['minuten_gespeeld'].sum()
                    avg_minutes = lineups_df['minuten_gespeeld'].mean()
                    starts = lineups_df['start_elf'].sum()
                    avg_rating = ratings_df['rating'].mean() if not ratings_df.empty else 0
                    goals = len(events_df[events_df['event_type'] == 'Goal']) if not events_df.empty else 0
                    
                    # Display metrics in columns
                    match_col1, match_col2, match_col3, match_col4 = st.columns(4)
                    
                    with match_col1:
                        st.markdown('<div class="metric-box">', unsafe_allow_html=True)
                        st.metric("🏟️ Wedstrijden", total_matches)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        st.markdown('<div class="metric-box">', unsafe_allow_html=True)
                        st.metric("⏱️ Gemiddeld Minuten", f"{avg_minutes:.0f}" if avg_minutes > 0 else "0")
                        st.markdown('</div>', unsafe_allow_html=True)
                    
                    with match_col2:
                        st.markdown('<div class="metric-box">', unsafe_allow_html=True)
                        st.metric("🚀 Basiself", f"{starts}/{total_matches}")
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        st.markdown('<div class="metric-box">', unsafe_allow_html=True)
                        st.metric("⏰ Totaal Minuten", f"{total_minutes:.0f}")
                        st.markdown('</div>', unsafe_allow_html=True)
                    
                    with match_col3:
                        st.markdown('<div class="metric-box">', unsafe_allow_html=True)
                        st.metric("⭐ Gemiddelde Rating", f"{avg_rating:.1f}/10" if avg_rating > 0 else "N/A")
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        st.markdown('<div class="metric-box">', unsafe_allow_html=True)
                        motm_count = len(ratings_df[ratings_df['man_of_the_match'] == True]) if not ratings_df.empty else 0
                        st.metric("🏆 Man of the Match", motm_count)
                        st.markdown('</div>', unsafe_allow_html=True)
                    
                    with match_col4:
                        st.markdown('<div class="metric-box">', unsafe_allow_html=True)
                        st.metric("⚽ Doelpunten", goals)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Most played position
                        if 'positie' in lineups_df.columns:
                            most_pos = lineups_df['positie'].mode().iloc[0] if not lineups_df['positie'].mode().empty else "N/A"
                            st.markdown('<div class="metric-box">', unsafe_allow_html=True)
                            st.metric("📍 Hoofdpositie", most_pos)
                            st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Recent matches table
                    st.markdown("#### 📅 Recente Wedstrijden")
                    
                    recent_matches = lineups_df.head(10).copy()
                    if not recent_matches.empty:
                        # Merge with ratings
                        if not ratings_df.empty:
                            recent_matches = recent_matches.merge(
                                ratings_df[['match_id', 'rating', 'man_of_the_match']], 
                                on='match_id', how='left'
                            )
                        
                        # Format for display
                        display_matches = recent_matches[[
                            'datum', 'tegenstander', 'doelpunten_voor', 'doelpunten_tegen', 
                            'positie', 'minuten_gespeeld', 'start_elf'
                        ]].copy()
                        
                        if 'rating' in recent_matches.columns:
                            display_matches['rating'] = recent_matches['rating']
                        
                        if 'man_of_the_match' in recent_matches.columns:
                            display_matches['MOTM'] = recent_matches['man_of_the_match'].apply(lambda x: '⭐' if x else '')
                        
                        # Rename columns for display
                        display_matches.columns = ['Datum', 'Tegenstander', 'Voor', 'Tegen', 'Positie', 'Min', 'Start'] + (['Rating'] if 'rating' in display_matches.columns else []) + (['MOTM'] if 'MOTM' in display_matches.columns else [])
                        
                        st.dataframe(display_matches, use_container_width=True, hide_index=True)
                    
                    # Events if any
                    if not events_df.empty:
                        st.markdown("#### 🎯 Wedstrijd Events")
                        events_display = events_df[['datum', 'event_type', 'minuut', 'omschrijving']].copy()
                        events_display.columns = ['Datum', 'Event', 'Minuut', 'Omschrijving']
                        st.dataframe(events_display, use_container_width=True, hide_index=True)
                        
                else:
                    st.info("📭 Geen wedstrijd data beschikbaar voor deze speler.")
                    
            except Exception as e:
                st.error(f"Error loading match data: {e}")
            
            st.markdown('</div>', unsafe_allow_html=True)
            
            # ==================== GEDETAILLEERDE TESTGEGEVENS ====================
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown("### <span class='accent-purple'>📋 Testgeschiedenis</span>", unsafe_allow_html=True)
            
            # Voeg progressie kolommen toe
            display_data = speler_data.copy().sort_values("Maand")
            display_data["MAS_Progressie"] = display_data["MAS"].diff().round(2)
            display_data["VO2_Progressie"] = display_data["VO2MAX"].diff().round(1)
            display_data["MAS_Progressie"] = display_data["MAS_Progressie"].apply(
                lambda x: f"{x:+.2f}" if pd.notna(x) else "-"
            )
            display_data["VO2_Progressie"] = display_data["VO2_Progressie"].apply(
                lambda x: f"{x:+.1f}" if pd.notna(x) else "-"
            )
            
            # Kolommen voor weergave
            display_cols = ["Maand", "MAS", "MAS_Progressie", "VO2MAX", "VO2_Progressie", "PeakVelocity", "FinishingTime"]
            col_names = {
                "Maand": "Test Datum",
                "MAS": "MAS (km/u)", 
                "MAS_Progressie": "MAS Δ",
                "VO2MAX": "VO2Max (ml/kg/min)",
                "VO2_Progressie": "VO2Max Δ",
                "PeakVelocity": "Peak Velocity (km/u)",
                "FinishingTime": "Finish Time (s)"
            }
            
            result_table = display_data[display_cols].copy()
            result_table.columns = [col_names[col] for col in display_cols]
            
            st.dataframe(
                result_table,
                use_container_width=True,
                hide_index=True
            )
            
            # Export opties
            col_exp1, col_exp2 = st.columns(2)
            
            with col_exp1:
                csv_data = speler_data.to_csv(index=False)
                st.download_button(
                    label=f"📥 Download testgegevens CSV",
                    data=csv_data,
                    file_name=f"{selected_speler}_spelersoverzicht.csv",
                    mime="text/csv"
                )
            
            with col_exp2:
                def create_player_profile_pdf():
                    """Generate custom player report with overview, GPS data, match stats, and goals/conversations"""
                    buffer = BytesIO()
                    
                    # Get GPS data for last 10 sessions
                    gps_data_recent = execute_db_query("""
                        SELECT datum, totale_afstand, hoge_intensiteit_afstand, zeer_hoge_intensiteit_afstand,
                               sprint_afstand, max_snelheid, aantal_sprints, aantal_acceleraties, 
                               aantal_deceleraties, impacts, player_load
                        FROM gps_data 
                        WHERE speler = ?
                        ORDER BY datum DESC
                        LIMIT 10
                    """, (selected_speler,))
                    
                    # Get match data for PDF using safe_fetchdf (same as main code)
                    try:
                        # Get lineups separately then merge (Supabase compatible)
                        pdf_lineups_df = safe_fetchdf(f"SELECT * FROM match_lineups WHERE speler = '{selected_speler}'")
                        pdf_matches_df = safe_fetchdf("SELECT match_id, datum, tegenstander, doelpunten_voor, doelpunten_tegen FROM matches")
                        
                        # Merge lineups with match details
                        if not pdf_lineups_df.empty and not pdf_matches_df.empty:
                            pdf_lineups_merged = pdf_lineups_df.merge(pdf_matches_df, on='match_id', how='left').sort_values('datum', ascending=False)
                        else:
                            pdf_lineups_merged = pd.DataFrame()
                        
                        # Get ratings separately
                        pdf_ratings_df = safe_fetchdf(f"SELECT * FROM match_ratings WHERE speler = '{selected_speler}'")
                        if not pdf_ratings_df.empty and not pdf_matches_df.empty:
                            pdf_ratings_merged = pdf_ratings_df.merge(pdf_matches_df[['match_id', 'datum']], on='match_id', how='left').sort_values('datum', ascending=False)
                        else:
                            pdf_ratings_merged = pd.DataFrame()
                        
                        # Get events separately  
                        pdf_events_df = safe_fetchdf(f"SELECT * FROM match_events WHERE speler = '{selected_speler}'")
                        if not pdf_events_df.empty and not pdf_matches_df.empty:
                            pdf_events_merged = pdf_events_df.merge(pdf_matches_df[['match_id', 'datum']], on='match_id', how='left').sort_values('datum', ascending=False)
                        else:
                            pdf_events_merged = pd.DataFrame()
                            
                    except Exception as e:
                        st.error(f"Error loading match data for PDF: {e}")
                        pdf_lineups_merged = pd.DataFrame()
                        pdf_ratings_merged = pd.DataFrame() 
                        pdf_events_merged = pd.DataFrame()
                    
                    # Get conversation notes
                    gesprek_notes = execute_db_query("""
                        SELECT datum, onderwerp, notities, coach
                        FROM gesprek_notities 
                        WHERE speler = ?
                        ORDER BY datum DESC
                        LIMIT 8
                    """, (selected_speler,))
                    
                    # Get player goals
                    speler_goals = execute_db_query("""
                        SELECT doeltype, titel, beschrijving, target_datum, status, created_at
                        FROM speler_doelen 
                        WHERE speler = ?
                        ORDER BY created_at DESC
                        LIMIT 6
                    """, (selected_speler,))
                    
                    with PdfPages(buffer) as pdf:
                        # Set up professional matplotlib style
                        plt.style.use('default')
                        plt.rcParams.update({
                            'font.size': 10,
                            'axes.titlesize': 12,
                            'axes.labelsize': 10,
                            'xtick.labelsize': 9,
                            'ytick.labelsize': 9,
                            'legend.fontsize': 9,
                            'figure.titlesize': 16
                        })
                        
                        # Helper function to create clean header
                        def add_header(fig, title, subtitle=None):
                            fig.patch.set_facecolor('white')
                            # Add colored header bar
                            header_ax = fig.add_axes([0, 0.93, 1, 0.06])
                            header_ax.set_xlim(0, 1)
                            header_ax.set_ylim(0, 1)
                            header_ax.add_patch(patches.Rectangle((0, 0), 1, 1, facecolor='#2E86AB', alpha=0.9))
                            header_ax.text(0.02, 0.5, 'SPK DASHBOARD', fontsize=12, fontweight='bold', 
                                         color='white', va='center')
                            header_ax.text(0.98, 0.5, f'{datetime.now().strftime("%d/%m/%Y")}', 
                                         fontsize=9, color='white', va='center', ha='right')
                            header_ax.axis('off')
                            
                            # Main title with proper spacing
                            fig.suptitle(title, fontsize=16, fontweight='bold', y=0.88)
                            if subtitle:
                                fig.text(0.5, 0.84, subtitle, fontsize=11, ha='center', style='italic', color='#666')
                        
                        # PAGE 1: OVERZICHT
                        fig1 = plt.figure(figsize=(11.7, 8.3))
                        add_header(fig1, f'SPELERSRAPPORT: {selected_speler.upper()}', f'Rapport datum: {datetime.now().strftime("%d/%m/%Y")}')
                        
                        # Simple overview section - full page
                        ax_overview = fig1.add_subplot(1, 1, 1)
                        ax_overview.axis('off')
                        
                        # Title section
                        ax_overview.text(0.5, 0.9, 'OVERZICHT', fontsize=18, fontweight='bold',
                                       ha='center', transform=ax_overview.transAxes, color='#2E86AB')
                        
                        # Player info in a clean layout
                        overview_text = f"""
SPELER INFORMATIE:
• Naam: {selected_speler}
• Rapport datum: {datetime.now().strftime('%d/%m/%Y')}
• Status: Actief

RAPPORT ONDERDELEN:
• GPS Data: Laatste 10 trainingssessies
• Wedstrijdstatistieken: Seizoen tot nu toe  
• Doelen & Progressie: Persoonlijke ontwikkeling
• Gesprekken: Coach evaluaties en feedback

Dit rapport geeft een volledig overzicht van de prestaties en ontwikkeling 
van {selected_speler} binnen het SPK Dashboard systeem."""
                        
                        ax_overview.text(0.1, 0.75, overview_text, fontsize=12, transform=ax_overview.transAxes,
                                       verticalalignment='top', linespacing=2.0)
                        
                        # Add decorative border
                        ax_overview.add_patch(patches.Rectangle((0.05, 0.05), 0.9, 0.8, fill=False, 
                                                              edgecolor='#2E86AB', linewidth=3))
                        
                        plt.subplots_adjust(left=0.1, right=0.95, top=0.8, bottom=0.1)
                        pdf.savefig(fig1, bbox_inches='tight', dpi=150)
                        plt.close(fig1)
                        
                        # PAGE 2: GPS DATA (LAATSTE 10 SESSIES)
                        fig2 = plt.figure(figsize=(11.7, 8.3))
                        add_header(fig2, 'GPS DATA', 'Laatste 10 Trainingssessies')
                        
                        if gps_data_recent:
                            # Convert to DataFrame for easier handling
                            df_gps = pd.DataFrame(gps_data_recent, columns=[
                                'datum', 'totale_afstand', 'hoge_intensiteit_afstand', 'zeer_hoge_intensiteit_afstand',
                                'sprint_afstand', 'max_snelheid', 'aantal_sprints', 'aantal_acceleraties',
                                'aantal_deceleraties', 'impacts', 'player_load'
                            ])
                            df_gps['datum'] = pd.to_datetime(df_gps['datum'])
                            
                            # Clean and convert numeric columns - handle problematic strings
                            numeric_columns = ['totale_afstand', 'hoge_intensiteit_afstand', 'zeer_hoge_intensiteit_afstand',
                                             'sprint_afstand', 'max_snelheid', 'aantal_sprints', 'aantal_acceleraties',
                                             'aantal_deceleraties', 'impacts', 'player_load']
                            
                            for col in numeric_columns:
                                if col in df_gps.columns:
                                    # Convert to string first, then numeric, handling errors
                                    df_gps[col] = pd.to_numeric(df_gps[col].astype(str), errors='coerce')
                                    # Fill NaN values with 0
                                    df_gps[col] = df_gps[col].fillna(0)
                            
                            df_gps = df_gps.sort_values('datum')
                            
                            # GPS Data in 3 separate tables for better analysis
                            
                            # TABLE 1: AFSTAND & INTENSITEIT (top left)
                            ax_distance = fig2.add_subplot(2, 3, 1)
                            ax_distance.axis('off')
                            ax_distance.text(0.5, 0.95, 'AFSTAND & INTENSITEIT', fontsize=11, fontweight='bold',
                                           ha='center', transform=ax_distance.transAxes, color='#2E86AB')
                            
                            distance_data = []
                            for _, session in df_gps.head(10).iterrows():
                                distance_data.append([
                                    session['datum'].strftime('%d/%m'),
                                    f"{session['totale_afstand']:.0f}",
                                    f"{session['hoge_intensiteit_afstand']:.0f}",
                                    f"{session['zeer_hoge_intensiteit_afstand']:.0f}" if pd.notna(session['zeer_hoge_intensiteit_afstand']) else '0'
                                ])
                            
                            if distance_data:
                                dist_table = ax_distance.table(cellText=distance_data,
                                                             colLabels=['Datum', 'Tot.Afst', 'HSR', 'VHSR'],
                                                             cellLoc='center', loc='center', 
                                                             bbox=[0.05, 0.1, 0.9, 0.8])
                                dist_table.auto_set_font_size(False)
                                dist_table.set_fontsize(7)
                                dist_table.scale(1, 1.2)
                                
                                for (i, j), cell in dist_table.get_celld().items():
                                    if i == 0:
                                        cell.set_facecolor('#2E86AB')
                                        cell.set_text_props(weight='bold', color='white')
                                    else:
                                        cell.set_facecolor('#f8f9fa' if i % 2 == 0 else 'white')
                            
                            # TABLE 2: SNELHEID & SPRINTS (top middle)
                            ax_speed = fig2.add_subplot(2, 3, 2)
                            ax_speed.axis('off')
                            ax_speed.text(0.5, 0.95, 'SNELHEID & SPRINTS', fontsize=11, fontweight='bold',
                                        ha='center', transform=ax_speed.transAxes, color='#28a745')
                            
                            speed_data = []
                            for _, session in df_gps.head(10).iterrows():
                                speed_data.append([
                                    session['datum'].strftime('%d/%m'),
                                    f"{session['max_snelheid']:.1f}",
                                    f"{session['sprint_afstand']:.0f}" if pd.notna(session['sprint_afstand']) else '0',
                                    f"{session['aantal_sprints']:.0f}" if pd.notna(session['aantal_sprints']) else '0'
                                ])
                            
                            if speed_data:
                                speed_table = ax_speed.table(cellText=speed_data,
                                                           colLabels=['Datum', 'Max Sn', 'Sprint m', 'Sprints'],
                                                           cellLoc='center', loc='center', 
                                                           bbox=[0.05, 0.1, 0.9, 0.8])
                                speed_table.auto_set_font_size(False)
                                speed_table.set_fontsize(7)
                                speed_table.scale(1, 1.2)
                                
                                for (i, j), cell in speed_table.get_celld().items():
                                    if i == 0:
                                        cell.set_facecolor('#28a745')
                                        cell.set_text_props(weight='bold', color='white')
                                    else:
                                        cell.set_facecolor('#f0f8f0' if i % 2 == 0 else 'white')
                            
                            # TABLE 3: BELASTING & BEWEGING (top right)
                            ax_load = fig2.add_subplot(2, 3, 3)
                            ax_load.axis('off')
                            ax_load.text(0.5, 0.95, 'BELASTING & BEWEGING', fontsize=11, fontweight='bold',
                                       ha='center', transform=ax_load.transAxes, color='#ffc107')
                            
                            load_data = []
                            for _, session in df_gps.head(10).iterrows():
                                load_data.append([
                                    session['datum'].strftime('%d/%m'),
                                    f"{session['player_load']:.1f}" if pd.notna(session['player_load']) else 'N/A',
                                    f"{session['aantal_acceleraties']:.0f}" if pd.notna(session['aantal_acceleraties']) else '0',
                                    f"{session['aantal_deceleraties']:.0f}" if pd.notna(session['aantal_deceleraties']) else '0'
                                ])
                            
                            if load_data:
                                load_table = ax_load.table(cellText=load_data,
                                                          colLabels=['Datum', 'P.Load', 'Accel', 'Decel'],
                                                          cellLoc='center', loc='center', 
                                                          bbox=[0.05, 0.1, 0.9, 0.8])
                                load_table.auto_set_font_size(False)
                                load_table.set_fontsize(7)
                                load_table.scale(1, 1.2)
                                
                                for (i, j), cell in load_table.get_celld().items():
                                    if i == 0:
                                        cell.set_facecolor('#ffc107')
                                        cell.set_text_props(weight='bold', color='black')
                                    else:
                                        cell.set_facecolor('#fffbf0' if i % 2 == 0 else 'white')
                            
                            # BOTTOM ROW: 3 single-metric charts for focused analysis
                            
                            # CHART 1: TOTAL DISTANCE TREND (bottom left)
                            ax_total_distance = fig2.add_subplot(2, 3, 4)
                            ax_total_distance.plot(df_gps['datum'], df_gps['totale_afstand'], 
                                                 marker='o', linewidth=3, markersize=6, color='#2E86AB')
                            ax_total_distance.fill_between(df_gps['datum'], df_gps['totale_afstand'], 
                                                         alpha=0.3, color='#2E86AB')
                            
                            ax_total_distance.set_title('TOTAL DISTANCE', fontsize=11, fontweight='bold', color='#2E86AB')
                            ax_total_distance.set_ylabel('Meters', fontsize=10)
                            ax_total_distance.grid(True, alpha=0.3)
                            ax_total_distance.tick_params(axis='x', rotation=45, labelsize=8)
                            ax_total_distance.tick_params(axis='y', labelsize=8)
                            
                            # Add average line
                            avg_distance = df_gps['totale_afstand'].mean()
                            ax_total_distance.axhline(y=avg_distance, color='red', linestyle='--', alpha=0.7, label=f'Gem: {avg_distance:.0f}m')
                            ax_total_distance.legend(fontsize=8)
                            
                            # CHART 2: HIGH SPEED RUNNING TREND (bottom middle)
                            ax_hsr = fig2.add_subplot(2, 3, 5)
                            ax_hsr.plot(df_gps['datum'], df_gps['hoge_intensiteit_afstand'], 
                                      marker='s', linewidth=3, markersize=6, color='#28a745')
                            ax_hsr.fill_between(df_gps['datum'], df_gps['hoge_intensiteit_afstand'], 
                                              alpha=0.3, color='#28a745')
                            
                            ax_hsr.set_title('HIGH SPEED RUNNING', fontsize=11, fontweight='bold', color='#28a745')
                            ax_hsr.set_ylabel('Meters', fontsize=10)
                            ax_hsr.grid(True, alpha=0.3)
                            ax_hsr.tick_params(axis='x', rotation=45, labelsize=8)
                            ax_hsr.tick_params(axis='y', labelsize=8)
                            
                            # Add average line
                            avg_hsr = df_gps['hoge_intensiteit_afstand'].mean()
                            ax_hsr.axhline(y=avg_hsr, color='red', linestyle='--', alpha=0.7, label=f'Gem: {avg_hsr:.0f}m')
                            ax_hsr.legend(fontsize=8)
                            
                            # CHART 3: SPRINT METERS TREND (bottom right)
                            ax_sprint = fig2.add_subplot(2, 3, 6)
                            if 'sprint_afstand' in df_gps.columns:
                                ax_sprint.plot(df_gps['datum'], df_gps['sprint_afstand'], 
                                             marker='^', linewidth=3, markersize=6, color='#ffc107')
                                ax_sprint.fill_between(df_gps['datum'], df_gps['sprint_afstand'], 
                                                     alpha=0.3, color='#ffc107')
                                
                                # Add average line
                                avg_sprint = df_gps['sprint_afstand'].mean()
                                ax_sprint.axhline(y=avg_sprint, color='red', linestyle='--', alpha=0.7, label=f'Gem: {avg_sprint:.0f}m')
                                ax_sprint.legend(fontsize=8)
                            else:
                                # If no sprint distance data, show message
                                ax_sprint.text(0.5, 0.5, 'Geen Sprint\nAfstand Data', 
                                             ha='center', va='center', transform=ax_sprint.transAxes, 
                                             fontsize=10, color='#666')
                            
                            ax_sprint.set_title('SPRINT METERS', fontsize=11, fontweight='bold', color='#ffc107')
                            ax_sprint.set_ylabel('Meters', fontsize=10)
                            ax_sprint.grid(True, alpha=0.3)
                            ax_sprint.tick_params(axis='x', rotation=45, labelsize=8)
                            ax_sprint.tick_params(axis='y', labelsize=8)
                        else:
                            # No GPS data message
                            ax_no_data = fig2.add_subplot(1, 1, 1)
                            ax_no_data.axis('off')
                            ax_no_data.text(0.5, 0.5, 'Geen GPS data beschikbaar voor de laatste 10 sessies', 
                                          fontsize=14, ha='center', transform=ax_no_data.transAxes, color='#666')
                        
                        plt.subplots_adjust(left=0.1, right=0.95, top=0.8, bottom=0.15, hspace=0.4)
                        pdf.savefig(fig2, bbox_inches='tight', dpi=150)
                        plt.close(fig2)
                        
                        # PAGE 3: WEDSTRIJDSTATISTIEKEN
                        fig3 = plt.figure(figsize=(11.7, 8.3))
                        add_header(fig3, 'WEDSTRIJDSTATISTIEKEN', 'Seizoen Tot Nu Toe')
                        
                        if not pdf_lineups_merged.empty:
                            # Use the merged DataFrames directly
                            df_lineups = pdf_lineups_merged.copy()
                            df_ratings = pdf_ratings_merged.copy() if not pdf_ratings_merged.empty else pd.DataFrame()
                            df_events = pdf_events_merged.copy() if not pdf_events_merged.empty else pd.DataFrame()
                            
                            # Clean numeric columns in lineups data
                            if not df_lineups.empty:
                                numeric_lineup_cols = ['minuten_gespeeld', 'start_elf', 'doelpunten_voor', 'doelpunten_tegen']
                                for col in numeric_lineup_cols:
                                    if col in df_lineups.columns:
                                        df_lineups[col] = pd.to_numeric(df_lineups[col], errors='coerce').fillna(0)
                            
                            # Clean ratings data
                            if not df_ratings.empty and 'rating' in df_ratings.columns:
                                df_ratings['rating'] = pd.to_numeric(df_ratings['rating'], errors='coerce').fillna(0)
                            
                            # Calculate statistics for WHOLE SEASON (all data)
                            total_matches = len(df_lineups)
                            total_minutes = df_lineups['minuten_gespeeld'].sum() if 'minuten_gespeeld' in df_lineups.columns else 0
                            starts = df_lineups['start_elf'].sum() if 'start_elf' in df_lineups.columns else 0
                            avg_rating = df_ratings['rating'].mean() if not df_ratings.empty and 'rating' in df_ratings.columns else 0
                            goals = len(df_events[df_events['event_type'] == 'Goal']) if not df_events.empty and 'event_type' in df_events.columns else 0
                            assists = len(df_events[df_events['event_type'] == 'Assist']) if not df_events.empty and 'event_type' in df_events.columns else 0
                            yellow_cards = len(df_events[df_events['event_type'] == 'Yellow Card']) if not df_events.empty and 'event_type' in df_events.columns else 0
                            
                            # TOP ROW: Statistics (left) and Rating trend (right) - each takes ~half page height
                            # Statistics overview - top left
                            ax_stats = fig3.add_subplot(2, 2, 1)
                            ax_stats.axis('off')
                            ax_stats.text(0.5, 0.95, 'SEIZOEN STATISTIEKEN', fontsize=12, fontweight='bold',
                                        ha='center', transform=ax_stats.transAxes, color='#2E86AB')
                            
                            stats_text = f"""Wedstrijden: {total_matches}
Totaal minuten: {total_minutes:.0f}
Basisplaatsen: {starts}
Gem. rating: {avg_rating:.1f}/10
Doelpunten: {goals}
Assists: {assists}
Gele kaarten: {yellow_cards}"""
                            ax_stats.text(0.1, 0.8, stats_text, fontsize=10, transform=ax_stats.transAxes,
                                        verticalalignment='top', linespacing=1.8)
                            ax_stats.add_patch(patches.Rectangle((0.05, 0.1), 0.9, 0.8, fill=False, 
                                                               edgecolor='#2E86AB', linewidth=2))
                            
                            # Ratings trend for WHOLE SEASON - top right
                            ratings_added = False
                            if not df_ratings.empty and len(df_ratings) > 1 and 'rating' in df_ratings.columns and 'datum' in df_ratings.columns:
                                try:
                                    ax_ratings = fig3.add_subplot(2, 2, 2)
                                    df_ratings['datum'] = pd.to_datetime(df_ratings['datum'], errors='coerce')
                                    # Remove rows where datum conversion failed
                                    df_ratings_clean = df_ratings.dropna(subset=['datum', 'rating'])
                                    df_ratings_sorted = df_ratings_clean.sort_values('datum')  # ALL ratings, not just last 10
                                    
                                    if len(df_ratings_sorted) > 0:
                                        ax_ratings.plot(range(len(df_ratings_sorted)), df_ratings_sorted['rating'], 
                                                      marker='o', linewidth=2, markersize=4, color='#2E86AB')
                                        ax_ratings.set_title('RATING SEIZOEN EVOLUTIE', fontsize=12, fontweight='bold')
                                        ax_ratings.set_ylabel('Rating', fontsize=10)
                                        ax_ratings.set_xlabel('Wedstrijden', fontsize=10)
                                        ax_ratings.grid(True, alpha=0.3)
                                        ax_ratings.set_ylim(0, 10)
                                        ax_ratings.tick_params(labelsize=8)
                                        ratings_added = True
                                except Exception as e:
                                    # Skip ratings chart if there's an error
                                    pass
                            
                            # If no ratings chart, add a placeholder
                            if not ratings_added:
                                ax_placeholder = fig3.add_subplot(2, 2, 2)
                                ax_placeholder.axis('off')
                                ax_placeholder.text(0.5, 0.5, 'Geen ratings\nbeschikbaar', 
                                                  fontsize=12, ha='center', va='center', 
                                                  transform=ax_placeholder.transAxes, color='#666')
                            
                            # BOTTOM ROW: Recent matches table - ONLY LAST 5 MATCHES
                            ax_matches = fig3.add_subplot(2, 1, 2)
                            ax_matches.axis('off')
                            ax_matches.text(0.5, 0.95, 'LAATSTE 5 WEDSTRIJDEN', fontsize=14, fontweight='bold',
                                          ha='center', transform=ax_matches.transAxes, color='#2E86AB')
                            
                            # Get only last 5 matches
                            df_recent = df_lineups.head(5).copy()  # Changed from 6 to 5
                            if not df_ratings.empty:
                                df_recent = df_recent.merge(df_ratings[['match_id', 'rating']], on='match_id', how='left')
                            
                            # Add events info with safe data handling
                            match_table_data = []
                            for _, match in df_recent.iterrows():
                                try:
                                    # Safe rating extraction
                                    rating_val = match.get('rating', 0) if 'rating' in match else 0
                                    rating = f"{float(rating_val):.1f}" if pd.notna(rating_val) and rating_val != 0 else 'N/A'
                                    
                                    # Get events for this match with safe access
                                    events_text = ""
                                    if not df_events.empty and 'match_id' in df_events.columns and 'event_type' in df_events.columns:
                                        match_id_val = match.get('match_id')
                                        if pd.notna(match_id_val):
                                            match_events = df_events[df_events['match_id'] == match_id_val]
                                            if not match_events.empty:
                                                event_counts = match_events['event_type'].value_counts()
                                                events_list = []
                                                for event_type, count in event_counts.items():
                                                    if event_type == 'Goal':
                                                        events_list.append(f"{count}G")
                                                    elif event_type == 'Assist':
                                                        events_list.append(f"{count}A")
                                                    elif event_type == 'Yellow Card':
                                                        events_list.append(f"{count}Y")
                                                    elif event_type == 'Red Card':
                                                        events_list.append(f"{count}R")
                                                events_text = ", ".join(events_list) if events_list else ""
                                    
                                    # Safe data extraction for table
                                    datum_str = str(match.get('datum', 'N/A'))[:10] if pd.notna(match.get('datum')) else 'N/A'
                                    tegenstander_str = str(match.get('tegenstander', 'N/A'))[:12] if pd.notna(match.get('tegenstander')) else 'N/A'
                                    positie_str = str(match.get('positie', 'N/A')) if pd.notna(match.get('positie')) else 'N/A'
                                    
                                    minuten_val = match.get('minuten_gespeeld', 0)
                                    minuten_str = f"{float(minuten_val):.0f}'" if pd.notna(minuten_val) else "0'"
                                    
                                    match_table_data.append([
                                        datum_str,
                                        tegenstander_str,
                                        positie_str,
                                        minuten_str,
                                        rating,
                                        events_text if events_text else '-'
                                    ])
                                except Exception as e:
                                    # Skip problematic rows
                                    continue
                            
                            if match_table_data:
                                table = ax_matches.table(cellText=match_table_data,
                                                       colLabels=['Datum', 'Tegenstander', 'Pos', 'Min', 'Rating', 'Events'],
                                                       cellLoc='center', loc='center',
                                                       bbox=[0.05, 0.1, 0.9, 0.8])
                                table.auto_set_font_size(False)
                                table.set_fontsize(8)
                                table.scale(1, 1.5)
                                
                                for (i, j), cell in table.get_celld().items():
                                    if i == 0:
                                        cell.set_facecolor('#2E86AB')
                                        cell.set_text_props(weight='bold', color='white')
                                    else:
                                        cell.set_facecolor('#f8f9fa' if i % 2 == 0 else 'white')
                        else:
                            # No match data
                            ax_no_matches = fig3.add_subplot(1, 1, 1)
                            ax_no_matches.axis('off')
                            ax_no_matches.text(0.5, 0.5, 'Geen wedstrijddata beschikbaar', 
                                             fontsize=14, ha='center', transform=ax_no_matches.transAxes, color='#666')
                        
                        plt.subplots_adjust(left=0.08, right=0.95, top=0.8, bottom=0.08, hspace=0.5, wspace=0.3)
                        pdf.savefig(fig3, bbox_inches='tight', dpi=150)
                        plt.close(fig3)
                        
                        # PAGE 4: DOELEN & PROGRESSIE GESPREKKEN
                        fig4 = plt.figure(figsize=(11.7, 8.3))
                        add_header(fig4, 'DOELEN & GESPREKKEN', 'Persoonlijke Ontwikkeling')
                        
                        # Goals section
                        ax_goals = fig4.add_subplot(2, 1, 1)
                        ax_goals.axis('off')
                        ax_goals.text(0.5, 0.95, 'PERSOONLIJKE DOELEN', fontsize=14, fontweight='bold',
                                    ha='center', transform=ax_goals.transAxes, color='#2E86AB')
                        
                        if speler_goals:
                            goals_table_data = []
                            for goal in speler_goals:
                                doeltype, titel, beschrijving, target_datum, status, created_at = goal
                                goals_table_data.append([
                                    str(doeltype) if doeltype else 'N/A',
                                    str(titel)[:25] if titel else 'N/A',
                                    str(beschrijving)[:30] + '...' if beschrijving and len(str(beschrijving)) > 30 else str(beschrijving) if beschrijving else 'N/A',
                                    str(target_datum)[:10] if target_datum else 'N/A',
                                    str(status) if status else 'N/A'
                                ])
                            
                            if goals_table_data:
                                goals_table = ax_goals.table(cellText=goals_table_data,
                                                           colLabels=['Type', 'Titel', 'Beschrijving', 'Doel Datum', 'Status'],
                                                           cellLoc='center', loc='center',
                                                           bbox=[0.05, 0.2, 0.9, 0.7])
                                goals_table.auto_set_font_size(False)
                                goals_table.set_fontsize(9)
                                goals_table.scale(1, 1.3)
                                
                                for (i, j), cell in goals_table.get_celld().items():
                                    if i == 0:
                                        cell.set_facecolor('#2E86AB')
                                        cell.set_text_props(weight='bold', color='white')
                                    else:
                                        cell.set_facecolor('#f8f9fa' if i % 2 == 0 else 'white')
                        else:
                            ax_goals.text(0.5, 0.5, 'Geen persoonlijke doelen gedefinieerd', 
                                        fontsize=12, ha='center', transform=ax_goals.transAxes, color='#666')
                        
                        # Conversations section
                        ax_conversations = fig4.add_subplot(2, 1, 2)
                        ax_conversations.axis('off')
                        ax_conversations.text(0.5, 0.95, 'GESPREKKEN & EVALUATIES', fontsize=14, fontweight='bold',
                                            ha='center', transform=ax_conversations.transAxes, color='#2E86AB')
                        
                        if gesprek_notes:
                            conv_table_data = []
                            for conv in gesprek_notes:
                                datum, onderwerp, notities, coach = conv
                                conv_table_data.append([
                                    str(datum)[:10] if datum else 'N/A',
                                    str(onderwerp)[:20] if onderwerp else 'N/A',
                                    str(notities)[:40] + '...' if notities and len(str(notities)) > 40 else str(notities) if notities else 'N/A',
                                    str(coach) if coach else 'N/A'
                                ])
                            
                            if conv_table_data:
                                conv_table = ax_conversations.table(cellText=conv_table_data,
                                                                   colLabels=['Datum', 'Onderwerp', 'Notities', 'Coach'],
                                                                   cellLoc='center', loc='center',
                                                                   bbox=[0.05, 0.2, 0.9, 0.7])
                                conv_table.auto_set_font_size(False)
                                conv_table.set_fontsize(9)
                                conv_table.scale(1, 1.3)
                                
                                for (i, j), cell in conv_table.get_celld().items():
                                    if i == 0:
                                        cell.set_facecolor('#2E86AB')
                                        cell.set_text_props(weight='bold', color='white')
                                    else:
                                        cell.set_facecolor('#f8f9fa' if i % 2 == 0 else 'white')
                        else:
                            ax_conversations.text(0.5, 0.5, 'Geen gesprekken geregistreerd', 
                                                fontsize=12, ha='center', transform=ax_conversations.transAxes, color='#666')
                        
                        plt.subplots_adjust(left=0.1, right=0.95, top=0.8, bottom=0.1, hspace=0.4)
                        pdf.savefig(fig4, bbox_inches='tight', dpi=150)
                        plt.close(fig4)
                    
                    buffer.seek(0)
                    return buffer.getvalue()
                
                # PDF download button
                if st.button("📄 Genereer PDF rapport"):
                    try:
                        pdf_data = create_player_profile_pdf()
                        st.download_button(
                            label="💾 Download PDF Rapport",
                            data=pdf_data,
                            file_name=f"{selected_speler}_spelersprofiel_{datetime.now().strftime('%Y%m%d')}.pdf",
                            mime="application/pdf"
                        )
                        st.success("✅ PDF rapport gegenereerd!")
                    except Exception as e:
                        st.error(f"❌ Fout bij genereren PDF: {e}")
                        st.info("💡 Zorg ervoor dat er voldoende data beschikbaar is voor het rapport.")
            
            st.markdown('</div>', unsafe_allow_html=True)

# Safe database connection cleanup

# Database cleanup handled by Supabase helpers