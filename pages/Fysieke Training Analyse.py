import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import json
from plotly.subplots import make_subplots

# Supabase helpers (primary)
try:
    from supabase_helpers import (
        get_table_data, 
        get_training_data,
        get_cached_player_list,
        test_supabase_connection,
        safe_fetchdf
    )
    SUPABASE_MODE = True
except ImportError:
    # Fallback to legacy
    from db_config import get_database_connection
    SUPABASE_MODE = False
st.set_page_config(page_title="SPK Dashboard - Fysieke Training Analyse", layout="wide")

st.subheader("⚽ Fysieke Training Analyse")

# Database setup
if SUPABASE_MODE:
    st.info("🌐 Using Supabase database")
    if not test_supabase_connection():
        st.error("❌ Cannot connect to Supabase")
        st.stop()
    con = None  # Will use Supabase helpers instead
else:
    # Legacy mode
    # Legacy mode fallback
    try:
        con = get_database_connection()
    except NameError:
        st.error("❌ Database connection not available")
        st.stop()
# Database compatibility functions
def execute_db_query(query, params=None):
    """Execute query and return results compatible with both databases"""
    if SUPABASE_MODE:
        try:
            # Use Supabase helpers for simple queries
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

def execute_db_query_single(query, params=None):
    """Execute query and return single result"""
    results = execute_db_query(query, params)
    return results[0] if results else None

# Helper functions
def execute_query(query, params=None):
    """Execute query with proper database handling"""
    if SUPABASE_MODE:
        # For Supabase, use safe_fetchdf which handles simple queries
        return safe_fetchdf(query, params or {})
    else:
        # Legacy mode
        if params:
            return execute_db_query(query, params)
        else:
            return execute_db_query(query)

def convert_numeric_columns(df, columns):
    """Convert specified columns to numeric, handling string values from Supabase"""
    df_copy = df.copy()
    for col in columns:
        if col in df_copy.columns:
            df_copy[col] = pd.to_numeric(df_copy[col], errors='coerce')
    return df_copy

def calculate_acwr(player_data, metric_column, current_date, acute_days=7, chronic_days=28):
    """
    Bereken Acute:Chronic Workload Ratio (ACWR) voor een specifieke metric
    - Acute: gemiddelde van laatste 7 dagen
    - Chronic: gemiddelde van laatste 28 dagen
    - ACWR = Acute / Chronic
    """
    try:
        # Filter data voor de periode
        end_date = pd.to_datetime(current_date)
        chronic_start = end_date - timedelta(days=chronic_days)
        acute_start = end_date - timedelta(days=acute_days)
        
        # Data filteren
        chronic_data = player_data[
            (player_data['datum'] >= chronic_start) & 
            (player_data['datum'] <= end_date)
        ][metric_column].dropna()
        
        acute_data = player_data[
            (player_data['datum'] >= acute_start) & 
            (player_data['datum'] <= end_date)
        ][metric_column].dropna()
        
        # Bereken gemiddeldes
        if len(chronic_data) == 0 or len(acute_data) == 0:
            return None, None, None
            
        acute_avg = acute_data.mean()
        chronic_avg = chronic_data.mean()
        
        if chronic_avg == 0:
            return acute_avg, chronic_avg, None
            
        acwr = acute_avg / chronic_avg
        return acute_avg, chronic_avg, acwr
        
    except Exception as e:
        return None, None, None

def get_acwr_risk_category(acwr_value):
    """Categoriseer ACWR risico"""
    if acwr_value is None:
        return "Geen Data", "#BDC3C7"
    elif acwr_value < 0.8:
        return "Te Laag", "#3498DB"  # Blauw - mogelijk undertraining
    elif 0.8 <= acwr_value <= 1.3:
        return "Optimaal", "#2ECC71"  # Groen - sweet spot
    elif 1.3 < acwr_value <= 1.5:
        return "Verhoogd", "#F39C12"  # Oranje - verhoogd risico
    else:
        return "Hoog Risico", "#E74C3C"  # Rood - hoog blessure risico

def calculate_training_load_category(row):
    """Categoriseer trainingsbelasting op basis van GPS metrics"""
    score = 0
    
    # Afstand component (30%)
    if row['totale_afstand'] > 9000:
        score += 3
    elif row['totale_afstand'] > 8000:
        score += 2
    elif row['totale_afstand'] > 7000:
        score += 1
    
    # Hoge intensiteit component (25%)
    if row['hoge_intensiteit_afstand'] > 2000:
        score += 3
    elif row['hoge_intensiteit_afstand'] > 1500:
        score += 2
    elif row['hoge_intensiteit_afstand'] > 1000:
        score += 1
    
    # Sprint component (25%) 
    if row['aantal_sprints'] > 40:
        score += 3
    elif row['aantal_sprints'] > 25:
        score += 2
    elif row['aantal_sprints'] > 15:
        score += 1
    
    # Snelheid component (20%)
    if row['max_snelheid'] > 30:
        score += 2
    elif row['max_snelheid'] > 28:
        score += 1
    
    # Categoriseer
    if score >= 9:
        return "Zeer Hoog", "#E74C3C"
    elif score >= 6:
        return "Hoog", "#E67E22"
    elif score >= 3:
        return "Gemiddeld", "#F39C12"
    else:
        return "Laag", "#2ECC71"

def get_team_based_benchmarks(con):
    """Bereken benchmarks gebaseerd op eigen team data"""
    
    # Haal alle GPS data op - Supabase compatible
    try:
        df_team = safe_fetchdf("""
            SELECT 
                positie,
                totale_afstand,
                hoge_intensiteit_afstand,
                max_snelheid,
                aantal_sprints
            FROM gps_data 
            WHERE positie IS NOT NULL 
            AND totale_afstand IS NOT NULL
        """)
    except:
        # Fallback naar basis benchmarks als geen data
        return get_fallback_benchmarks()
    
    if df_team.empty:
        # Fallback naar basis benchmarks als geen data
        return get_fallback_benchmarks()
    
    # Convert numeric columns
    numeric_cols = ['totale_afstand', 'hoge_intensiteit_afstand', 'max_snelheid', 'aantal_sprints']
    for col in numeric_cols:
        if col in df_team.columns:
            df_team[col] = pd.to_numeric(df_team[col], errors='coerce')
    
    # Filter unrealistic values after conversion
    df_team = df_team[df_team['totale_afstand'] > 1000]
    
    benchmarks = {}
    
    # Bereken per positie de 25e en 75e percentiel als benchmark range
    for positie in df_team['positie'].unique():
        if positie and str(positie).strip():  # Skip empty/null positions
            positie_data = df_team[df_team['positie'] == positie]
            
            if len(positie_data) >= 3:  # Minimaal 3 datapunten voor betrouwbare benchmark
                benchmarks[positie] = {
                    'totale_afstand': (
                        positie_data['totale_afstand'].quantile(0.25),
                        positie_data['totale_afstand'].quantile(0.75)
                    ),
                    'hoge_intensiteit_afstand': (
                        positie_data['hoge_intensiteit_afstand'].quantile(0.25),
                        positie_data['hoge_intensiteit_afstand'].quantile(0.75)
                    ),
                    'max_snelheid': (
                        positie_data['max_snelheid'].quantile(0.25),
                        positie_data['max_snelheid'].quantile(0.75)
                    ),
                    'aantal_sprints': (
                        positie_data['aantal_sprints'].quantile(0.25),
                        positie_data['aantal_sprints'].quantile(0.75)
                    )
                }
    
    # Als geen positionele data beschikbaar, gebruik team gemiddelden
    if not benchmarks:
        team_benchmarks = {
            'totale_afstand': (
                df_team['totale_afstand'].quantile(0.25),
                df_team['totale_afstand'].quantile(0.75)
            ),
            'hoge_intensiteit_afstand': (
                df_team['hoge_intensiteit_afstand'].quantile(0.25),
                df_team['hoge_intensiteit_afstand'].quantile(0.75)
            ),
            'max_snelheid': (
                df_team['max_snelheid'].quantile(0.25),
                df_team['max_snelheid'].quantile(0.75)
            ),
            'aantal_sprints': (
                df_team['aantal_sprints'].quantile(0.25),
                df_team['aantal_sprints'].quantile(0.75)
            )
        }
        
        # Apply team benchmarks to all positions found in data
        for positie in df_team['positie'].unique():
            if positie and str(positie).strip():
                benchmarks[positie] = team_benchmarks
    
    return benchmarks

def get_fallback_benchmarks():
    """Fallback benchmarks als geen team data beschikbaar"""
    return {
        'Goalkeeper': {
            'totale_afstand': (3000, 5000),
            'hoge_intensiteit_afstand': (200, 600),
            'max_snelheid': (18, 23),
            'aantal_sprints': (3, 12)
        },
        'Center Back': {
            'totale_afstand': (5000, 7000),
            'hoge_intensiteit_afstand': (800, 1400),
            'max_snelheid': (22, 28),
            'aantal_sprints': (10, 25)
        },
        'Fullback': {
            'totale_afstand': (6000, 8000),
            'hoge_intensiteit_afstand': (1000, 1800),
            'max_snelheid': (24, 29),
            'aantal_sprints': (15, 35)
        },
        'Central Midfielder': {
            'totale_afstand': (6000, 7500),
            'hoge_intensiteit_afstand': (900, 1600),
            'max_snelheid': (22, 27),
            'aantal_sprints': (12, 30)
        },
        'Winger': {
            'totale_afstand': (6500, 8500),
            'hoge_intensiteit_afstand': (1200, 2000),
            'max_snelheid': (25, 30),
            'aantal_sprints': (20, 40)
        },
        'Central Attacker': {
            'totale_afstand': (5500, 7500),
            'hoge_intensiteit_afstand': (1000, 1800),
            'max_snelheid': (24, 29),
            'aantal_sprints': (15, 35)
        }
    }

# Global date filters for all analysis tabs
st.markdown("### 📅 Datum Filters (geldt voor alle analyses)")
col_global1, col_global2 = st.columns(2)

with col_global1:
    global_start_datum = st.date_input("📅 Start Datum", 
                                     value=datetime.now().date() - timedelta(days=60),
                                     key="global_start")
with col_global2:
    global_eind_datum = st.date_input("📅 Eind Datum", 
                                    value=datetime.now().date(),
                                    key="global_end")

st.markdown("---")

# Tabs voor verschillende analyses
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "👤 Individuele Analyse", 
    "👥 Team Analyse", 
    "📊 Positionele Analyse",
    "📈 Trend Analyse",
    "⚖️ ACWR Analyse"
])

with tab1:
    st.markdown("### 👤 Individuele Speler Analyse")
    
    # Haal ALLE actieve spelers op - Supabase compatible
    all_players = pd.DataFrame()  # Initialize empty DataFrame
    
    try:
        # Simple approach - get players directly from GPS data first since that's what we need
        all_players_raw = safe_fetchdf("SELECT speler FROM gps_data ORDER BY speler")
        if not all_players_raw.empty:
            # Get unique players using pandas
            unique_players = all_players_raw['speler'].unique()
            all_players = pd.DataFrame({'naam': sorted(unique_players)})
            
        if all_players.empty:
            # Fallback to thirty_fifteen_results
            fitness_players_raw = safe_fetchdf("SELECT Speler FROM thirty_fifteen_results ORDER BY Speler") 
            if not fitness_players_raw.empty:
                unique_fitness_players = fitness_players_raw['Speler'].unique()
                all_players = pd.DataFrame({'naam': sorted(unique_fitness_players)})
                
        if all_players.empty:
            # Final fallback - try spelers_profiel 
            profile_players = safe_fetchdf("SELECT naam FROM spelers_profiel WHERE status = 'Actief' ORDER BY naam")
            if not profile_players.empty:
                all_players = profile_players
            
    except Exception as e:
        st.error(f"Kon spelers niet ophalen uit database: {e}")
        st.stop()
    
    if not all_players.empty:
        spelers = all_players['naam'].tolist()
        selected_speler = st.selectbox("🎯 Selecteer Speler", spelers)
        
        # Use global date filters
        start_datum = global_start_datum
        eind_datum = global_eind_datum
        
        st.info(f"📅 Analyzing data from {start_datum} to {eind_datum}")
        
        if selected_speler:
            # Start with simple GPS query first, then try to add RPE data
            speler_stats_df = pd.DataFrame()
            
            # First attempt: Simple GPS query
            try:
                speler_stats_df = safe_fetchdf("""
                    SELECT datum, totale_afstand, hoge_intensiteit_afstand, zeer_hoge_intensiteit_afstand,
                           sprint_afstand, max_snelheid, aantal_sprints, aantal_acceleraties, 
                           aantal_deceleraties, impacts, player_load, positie
                    FROM gps_data
                    WHERE speler = ? AND datum >= ? AND datum <= ?
                    ORDER BY datum DESC
                """, [selected_speler, start_datum.strftime('%Y-%m-%d'), eind_datum.strftime('%Y-%m-%d')])
                
                if not speler_stats_df.empty:
                    st.success(f"✅ {len(speler_stats_df)} GPS records gevonden voor {selected_speler} in periode {start_datum} - {eind_datum}")
                
            except Exception as e:
                st.error(f"GPS query failed: {e}")
            
            # If no data in selected period, show available data with date info
            if speler_stats_df.empty:
                st.warning(f"⚠️ Geen GPS data voor {selected_speler} in periode {start_datum} - {eind_datum}")
                st.info("🔍 Alle beschikbare data voor deze speler tonen...")
                
                try:
                    speler_stats_df = safe_fetchdf("""
                        SELECT datum, totale_afstand, hoge_intensiteit_afstand, zeer_hoge_intensiteit_afstand,
                               sprint_afstand, max_snelheid, aantal_sprints, aantal_acceleraties, 
                               aantal_deceleraties, impacts, player_load, positie
                        FROM gps_data
                        WHERE speler = ?
                        ORDER BY datum DESC
                        LIMIT 20
                    """, [selected_speler])
                    
                    if not speler_stats_df.empty:
                        # Show the actual date range of available data
                        min_date = speler_stats_df['datum'].min()
                        max_date = speler_stats_df['datum'].max()
                        st.success(f"✅ {len(speler_stats_df)} GPS records gevonden voor {selected_speler}")
                        st.info(f"📅 Beschikbare data: {min_date} tot {max_date}")
                except Exception as e:
                    st.error(f"Fallback GPS query failed: {e}")
            
            # Try to add RPE data if GPS data was found
            if not speler_stats_df.empty:
                st.info("🔍 Proberen RPE data toe te voegen...")
                try:
                    # Get matching RPE data for the same dates/player with date filter
                    rpe_data = safe_fetchdf("""
                        SELECT datum, rpe_score, rpe_categorie, session_load, algemeen_welzijn
                        FROM rpe_data
                        WHERE speler = ? AND datum >= ? AND datum <= ?
                    """, [selected_speler, start_datum.strftime('%Y-%m-%d'), eind_datum.strftime('%Y-%m-%d')])
                    
                    if not rpe_data.empty:
                        # Merge RPE data with GPS data on date
                        speler_stats_df = speler_stats_df.merge(rpe_data, on='datum', how='left')
                        rpe_count = speler_stats_df['rpe_score'].notna().sum()
                        st.success(f"✅ {rpe_count} RPE records toegevoegd")
                    else:
                        st.info("📭 Geen RPE data gevonden voor deze speler")
                        
                except Exception as e:
                    st.info(f"RPE data toevoegen gefaald: {e}")
            
            if not speler_stats_df.empty:
                df_speler = speler_stats_df.copy()
                df_speler['datum'] = pd.to_datetime(df_speler['datum'])
                
                # Convert numeric columns - GPS metrics filled with 0, RPE columns keep NULL
                gps_cols = ['totale_afstand', 'hoge_intensiteit_afstand', 'zeer_hoge_intensiteit_afstand',
                           'sprint_afstand', 'max_snelheid', 'aantal_sprints', 'aantal_acceleraties',
                           'aantal_deceleraties', 'impacts', 'player_load']
                rpe_cols = ['rpe_score', 'session_load', 'algemeen_welzijn']
                
                # Fill GPS columns with 0 for missing values
                for col in gps_cols:
                    if col in df_speler.columns:
                        df_speler[col] = pd.to_numeric(df_speler[col], errors='coerce').fillna(0)
                
                # Convert RPE columns to numeric but keep NULL values
                for col in rpe_cols:
                    if col in df_speler.columns:
                        df_speler[col] = pd.to_numeric(df_speler[col], errors='coerce')
                
                # Training load categorisatie
                df_speler[['training_load', 'load_color']] = df_speler.apply(
                    lambda row: pd.Series(calculate_training_load_category(row)), axis=1
                )
                
                # Speler info
                laatste_positie = df_speler['positie'].iloc[0] if not df_speler.empty else 'Onbekend'
                st.markdown(f"**📍 Positie:** {laatste_positie}")
                
                # Count trainings within the selected date range only
                if not df_speler.empty:
                    # Filter data to only count sessions within selected period
                    df_speler['datum_dt'] = pd.to_datetime(df_speler['datum']).dt.date
                    filtered_trainings = df_speler[
                        (df_speler['datum_dt'] >= start_datum) & 
                        (df_speler['datum_dt'] <= eind_datum)
                    ]
                    
                    if len(filtered_trainings) > 0:
                        st.markdown(f"**📊 Trainingen in periode:** {len(filtered_trainings)}")
                        st.markdown(f"**📊 Totaal beschikbaar:** {len(df_speler)}")
                    else:
                        st.markdown(f"**📊 Trainingen in periode:** 0")
                        st.markdown(f"**📊 Totaal beschikbaar:** {len(df_speler)}")
                else:
                    st.markdown(f"**📊 Aantal trainingen:** 0")
                
                # Key metrics - Focus op jouw specifieke GPS componenten
                st.markdown("#### 📊 Key Performance Metrics")
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    avg_distance = df_speler['totale_afstand'].mean()
                    st.metric("Total Distance", f"{avg_distance:.0f}m")
                
                with col2:
                    avg_hsr = df_speler['hoge_intensiteit_afstand'].mean()
                    st.metric("High Speed Running", f"{avg_hsr:.0f}m")
                
                with col3:
                    avg_sprint_meters = df_speler['sprint_afstand'].mean()
                    st.metric("Sprint Meters", f"{avg_sprint_meters:.0f}m")
                
                with col4:
                    max_speed = df_speler['max_snelheid'].max()
                    st.metric("Max Speed", f"{max_speed:.1f} km/h")
                
                col5, col6, col7, col8 = st.columns(4)
                
                with col5:
                    avg_acceleraties = df_speler['aantal_acceleraties'].mean()
                    st.metric("Acceleraties", f"{avg_acceleraties:.0f}")
                
                with col6:
                    avg_deceleraties = df_speler['aantal_deceleraties'].mean()
                    st.metric("Deceleraties", f"{avg_deceleraties:.0f}")
                
                with col7:
                    avg_sprints = df_speler['aantal_sprints'].mean()
                    st.metric("Sprints", f"{avg_sprints:.0f}")
                
                with col8:
                    # RPE metrics - check if column exists
                    if 'rpe_score' in df_speler.columns:
                        rpe_data = df_speler.dropna(subset=['rpe_score'])
                        if not rpe_data.empty:
                            avg_rpe = rpe_data['rpe_score'].mean()
                            st.metric("Gem. RPE", f"{avg_rpe:.1f}/10")
                        else:
                            st.metric("Gem. RPE", "Geen data")
                    else:
                        st.metric("Gem. RPE", "Geen data")
                
                # Benchmark vergelijking (nu gebaseerd op team data)
                benchmarks = get_team_based_benchmarks(con)
                if laatste_positie in benchmarks:
                    st.markdown("#### 📊 Prestatie vs Team Benchmarks")
                    st.info(f"💡 **Team-gebaseerde benchmarks** voor {laatste_positie} (25e-75e percentiel van alle {laatste_positie} prestaties)")
                    
                    benchmark_data = benchmarks[laatste_positie]
                    speler_avg = {
                        'totale_afstand': df_speler['totale_afstand'].mean(),
                        'hoge_intensiteit_afstand': df_speler['hoge_intensiteit_afstand'].mean(),
                        'max_snelheid': df_speler['max_snelheid'].max(),
                        'aantal_sprints': df_speler['aantal_sprints'].mean()
                    }
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # Radar chart voor benchmark vergelijking
                        categories = ['Totale Afstand', 'Hoge Intensiteit', 'Max Snelheid', 'Sprints']
                        
                        # Normaliseer waarden naar percentages van benchmark max
                        speler_norm = []
                        benchmark_min = []
                        benchmark_max = []
                        
                        for key in ['totale_afstand', 'hoge_intensiteit_afstand', 'max_snelheid', 'aantal_sprints']:
                            min_val, max_val = benchmark_data[key]
                            speler_val = speler_avg[key]
                            
                            # Normaliseer naar 0-100 scale waar max benchmark = 100
                            speler_norm.append(min(100, max(0, (speler_val / max_val) * 100)))
                            benchmark_min.append((min_val / max_val) * 100)
                            benchmark_max.append(100)
                        
                        fig_radar = go.Figure()
                        
                        # Speler prestatie
                        fig_radar.add_trace(go.Scatterpolar(
                            r=speler_norm + [speler_norm[0]],
                            theta=categories + [categories[0]],
                            fill='toself',
                            name=selected_speler,
                            fillcolor='rgba(26, 118, 255, 0.5)',
                            line=dict(color='rgba(26, 118, 255, 1)')
                        ))
                        
                        # Benchmark max
                        fig_radar.add_trace(go.Scatterpolar(
                            r=benchmark_max + [benchmark_max[0]],
                            theta=categories + [categories[0]],
                            fill='none',
                            name='Benchmark Max',
                            line=dict(color='rgba(46, 204, 113, 1)', dash='dash')
                        ))
                        
                        # Benchmark min
                        fig_radar.add_trace(go.Scatterpolar(
                            r=benchmark_min + [benchmark_min[0]],
                            theta=categories + [categories[0]],
                            fill='none',
                            name='Benchmark Min',
                            line=dict(color='rgba(231, 76, 60, 1)', dash='dot')
                        ))
                        
                        fig_radar.update_layout(
                            polar=dict(
                                radialaxis=dict(
                                    visible=True,
                                    range=[0, 120]
                                )),
                            showlegend=True,
                            title="Prestatie vs Benchmark"
                        )
                        
                        st.plotly_chart(fig_radar, use_container_width=True)
                    
                    with col2:
                        # Benchmark tabel
                        benchmark_comparison = []
                        for key, label in [
                            ('totale_afstand', 'Totale Afstand'),
                            ('hoge_intensiteit_afstand', 'Hoge Intensiteit'),
                            ('max_snelheid', 'Max Snelheid'),
                            ('aantal_sprints', 'Aantal Sprints')
                        ]:
                            min_val, max_val = benchmark_data[key]
                            speler_val = speler_avg[key]
                            
                            if speler_val >= max_val:
                                status = "🟢 Uitstekend"
                            elif speler_val >= min_val:
                                status = "🟡 Goed"
                            else:
                                status = "🔴 Onder gemiddeld"
                            
                            benchmark_comparison.append({
                                'Metric': label,
                                'Speler': f"{speler_val:.1f}",
                                'Benchmark Range': f"{min_val:.0f} - {max_val:.0f}",
                                'Status': status
                            })
                        
                        df_benchmark = pd.DataFrame(benchmark_comparison)
                        st.dataframe(df_benchmark, use_container_width=True, hide_index=True)
                
                # Prestatie trends
                col1, col2 = st.columns(2)
                
                with col1:
                    # Afstand trend
                    fig_distance = px.line(df_speler, x='datum', y='totale_afstand',
                                         title="Totale Afstand per Training",
                                         color_discrete_sequence=['#1f77b4'])
                    fig_distance.add_hline(y=df_speler['totale_afstand'].mean(), 
                                         line_dash="dash", line_color="red",
                                         annotation_text="Gemiddelde")
                    st.plotly_chart(fig_distance, use_container_width=True)
                
                with col2:
                    # RPE vs GPS Load correlatie - check if columns exist
                    if 'rpe_score' in df_speler.columns and 'player_load' in df_speler.columns:
                        rpe_data_viz = df_speler.dropna(subset=['rpe_score', 'player_load'])
                        if not rpe_data_viz.empty:
                            fig_rpe_gps = px.scatter(rpe_data_viz, x='player_load', y='rpe_score',
                                                   title="GPS Load vs RPE Score",
                                                   hover_data=['datum', 'training_type'] if 'training_type' in rpe_data_viz.columns else ['datum'],
                                                   color='rpe_score',
                                                   color_continuous_scale='RdYlGn_r')
                            fig_rpe_gps.update_layout(yaxis=dict(range=[0, 11]))
                            st.plotly_chart(fig_rpe_gps, use_container_width=True)
                        else:
                            # Fallback naar training load distributie
                            if 'training_load' in df_speler.columns:
                                load_counts = df_speler['training_load'].value_counts()
                                fig_load = px.pie(values=load_counts.values, names=load_counts.index,
                                                title="Training Load Verdeling")
                                st.plotly_chart(fig_load, use_container_width=True)
                            else:
                                st.info("Geen load data beschikbaar voor visualisatie")
                    else:
                        # Fallback naar training load distributie  
                        if 'training_load' in df_speler.columns:
                            load_counts = df_speler['training_load'].value_counts()
                            fig_load = px.pie(values=load_counts.values, names=load_counts.index,
                                            title="Training Load Verdeling")
                            st.plotly_chart(fig_load, use_container_width=True)
                        else:
                            st.info("Geen load data beschikbaar voor visualisatie")
                
                # RPE trend als er data is - check if columns exist first
                has_rpe_data = ('rpe_score' in df_speler.columns and 
                               not df_speler.dropna(subset=['rpe_score']).empty)
                
                if has_rpe_data:
                    rpe_data = df_speler.dropna(subset=['rpe_score'])
                    st.markdown("#### 🎯 RPE & Welzijn Trends")
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        fig_rpe_trend = px.line(rpe_data, x='datum', y='rpe_score',
                                              title="RPE Score Trend",
                                              color_discrete_sequence=['#e74c3c'])
                        fig_rpe_trend.update_layout(yaxis=dict(range=[0, 11]))
                        st.plotly_chart(fig_rpe_trend, use_container_width=True)
                    
                    with col2:
                        fig_welzijn = px.line(rpe_data, x='datum', y='algemeen_welzijn',
                                            title="Algemeen Welzijn Trend",
                                            color_discrete_sequence=['#2ecc71'])
                        fig_welzijn.update_layout(yaxis=dict(range=[0, 11]))
                        st.plotly_chart(fig_welzijn, use_container_width=True)
                
                # Detaildata
                st.markdown("#### 📋 Training Details")
                display_df = df_speler.copy()
                display_df['datum'] = display_df['datum'].dt.strftime('%d-%m-%Y')
                
                # Selecteer kolommen op basis van beschikbare data
                base_columns = ['datum', 'totale_afstand', 'hoge_intensiteit_afstand', 
                              'max_snelheid', 'aantal_sprints']
                
                # Only add training_type if it exists
                if 'training_type' in df_speler.columns:
                    base_columns.append('training_type')
                
                if has_rpe_data:
                    # Met RPE data - only add columns that exist
                    rpe_columns = []
                    if 'rpe_score' in df_speler.columns:
                        rpe_columns.append('rpe_score')
                    if 'rpe_categorie' in df_speler.columns:
                        rpe_columns.append('rpe_categorie')
                    if 'algemeen_welzijn' in df_speler.columns:
                        rpe_columns.append('algemeen_welzijn')
                    
                    display_columns = base_columns + rpe_columns
                    
                    # Filter columns that actually exist
                    display_columns = [col for col in display_columns if col in display_df.columns]
                    display_df = display_df[display_columns]
                    
                    # Create rename mapping only for existing columns
                    rename_mapping = {
                        'datum': 'Datum',
                        'totale_afstand': 'Afstand (m)',
                        'hoge_intensiteit_afstand': 'Hoge Int. (m)',
                        'max_snelheid': 'Max Speed (km/h)',
                        'aantal_sprints': 'Sprints'
                    }
                    
                    if 'training_type' in display_df.columns:
                        rename_mapping['training_type'] = 'Training Type'
                    if 'rpe_score' in display_df.columns:
                        rename_mapping['rpe_score'] = 'RPE'
                    if 'rpe_categorie' in display_df.columns:
                        rename_mapping['rpe_categorie'] = 'RPE Categorie'
                    if 'algemeen_welzijn' in display_df.columns:
                        rename_mapping['algemeen_welzijn'] = 'Welzijn'
                    
                    display_df = display_df.rename(columns=rename_mapping)
                else:
                    # Zonder RPE data - only add columns that exist
                    extra_columns = []
                    if 'impacts' in df_speler.columns:
                        extra_columns.append('impacts')
                    if 'training_load' in df_speler.columns:
                        extra_columns.append('training_load')
                    
                    display_columns = base_columns + extra_columns
                    
                    # Filter columns that actually exist
                    display_columns = [col for col in display_columns if col in display_df.columns]
                    display_df = display_df[display_columns]
                    
                    # Create rename mapping only for existing columns
                    rename_mapping = {
                        'datum': 'Datum',
                        'totale_afstand': 'Afstand (m)',
                        'hoge_intensiteit_afstand': 'Hoge Int. (m)',
                        'max_snelheid': 'Max Speed (km/h)',
                        'aantal_sprints': 'Sprints'
                    }
                    
                    if 'training_type' in display_df.columns:
                        rename_mapping['training_type'] = 'Training Type'
                    if 'impacts' in display_df.columns:
                        rename_mapping['impacts'] = 'Impacts'
                    if 'training_load' in display_df.columns:
                        rename_mapping['training_load'] = 'Training Load'
                    
                    display_df = display_df.rename(columns=rename_mapping)
                
                st.dataframe(display_df, use_container_width=True, hide_index=True)
                
            else:
                # Toon speler info ook als er geen GPS data is
                st.info(f"📊 **{selected_speler}** - Geen GPS data beschikbaar voor de geselecteerde periode")
                
                # Probeer andere beschikbare data te tonen
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("#### 🏃‍♂️ Fitness Test Data")
                    # Check voor 30-15 test resultaten - Supabase compatible
                    try:
                        fitness_df = safe_fetchdf(f"""
                            SELECT MAS, VO2MAX, PeakVelocity, Maand 
                            FROM thirty_fifteen_results 
                            WHERE Speler = '{selected_speler}'
                            ORDER BY Maand DESC
                            LIMIT 1
                        """)
                        fitness_data = not fitness_df.empty
                    except:
                        fitness_data = False
                        fitness_df = pd.DataFrame()
                    
                    if fitness_data and not fitness_df.empty:
                        fitness_row = fitness_df.iloc[0]
                        
                        # Safely format numeric values
                        mas_val = fitness_row['MAS']
                        vo2_val = fitness_row['VO2MAX'] 
                        pv_val = fitness_row['PeakVelocity']
                        
                        try:
                            mas_formatted = f"{float(mas_val):.1f} km/u" if pd.notna(mas_val) and mas_val != '' else "N/A"
                        except (ValueError, TypeError):
                            mas_formatted = "N/A"
                            
                        try:
                            vo2_formatted = f"{float(vo2_val):.0f} ml/kg/min" if pd.notna(vo2_val) and vo2_val != '' else "N/A"
                        except (ValueError, TypeError):
                            vo2_formatted = "N/A"
                            
                        try:
                            pv_formatted = f"{float(pv_val):.1f} km/u" if pd.notna(pv_val) and pv_val != '' else "N/A"
                        except (ValueError, TypeError):
                            pv_formatted = "N/A"
                        
                        st.metric("MAS", mas_formatted)
                        st.metric("VO2Max", vo2_formatted)
                        st.metric("Peak Velocity", pv_formatted)
                        st.caption(f"Laatste test: {fitness_row['Maand']}")
                    else:
                        st.write("Geen fitness test data beschikbaar")
                
                with col2:
                    st.markdown("#### ⚡ RPE Data")
                    # Check voor RPE data - Supabase compatible
                    try:
                        rpe_summary_df = safe_fetchdf("""
                            SELECT AVG(CAST(rpe_score AS FLOAT)) as avg_rpe, COUNT(*) as sessions
                            FROM rpe_data 
                            WHERE speler = ? AND datum >= ? AND datum <= ?
                        """, [selected_speler, start_datum.strftime('%Y-%m-%d'), eind_datum.strftime('%Y-%m-%d')])
                        
                        if not rpe_summary_df.empty and pd.notna(rpe_summary_df['avg_rpe'].iloc[0]):
                            avg_rpe = rpe_summary_df['avg_rpe'].iloc[0]
                            sessions = rpe_summary_df['sessions'].iloc[0]
                            st.metric("Gemiddelde RPE", f"{avg_rpe:.1f}")
                            st.metric("RPE Sessies", f"{sessions}")
                        else:
                            st.write("Geen RPE data beschikbaar")
                    except:
                        st.write("Geen RPE data beschikbaar")
                
                # Suggesties
                st.markdown("#### 💡 Suggesties")
                st.write("• Zorg ervoor dat de speler een GPS tracker draagt tijdens trainingen")
                st.write("• Import GPS data via de 'Fysieke Data Import' pagina")
                st.write("• Controleer of de speler correct gespeld staat in de data")
    
    else:
        st.warning("⚠️ Geen spelers gevonden in de database.")
        st.info("💡 Controleer of er spelers zijn toegevoegd via de Fysieke Data Import pagina.")

with tab2:
    st.markdown("### 👥 Team Analyse")
    
    # Use global date filters
    start_date = global_start_datum
    end_date = global_eind_datum
    
    st.info(f"📅 Team analysis from {start_date} to {end_date}")
    try:
        team_data_df = safe_fetchdf(f"""
            SELECT g.speler, g.datum, g.totale_afstand, g.hoge_intensiteit_afstand, g.max_snelheid,
                   g.aantal_sprints, g.aantal_acceleraties, g.impacts, g.player_load, g.positie,
                   r.rpe_score, r.rpe_categorie, r.session_load, r.algemeen_welzijn
            FROM gps_data g
            LEFT JOIN rpe_data r ON g.speler = r.speler AND g.datum = r.datum
            WHERE g.datum >= '{start_date}' AND g.datum <= '{end_date}'
            ORDER BY g.datum DESC
        """)
    except:
        # Fallback to simpler query if JOIN fails with Supabase
        try:
            team_data_df = safe_fetchdf(f"""
                SELECT speler, datum, totale_afstand, hoge_intensiteit_afstand, max_snelheid,
                       aantal_sprints, aantal_acceleraties, impacts, player_load, positie
                FROM gps_data
                WHERE datum >= '{start_date}' AND datum <= '{end_date}'
                ORDER BY datum DESC
            """)
        except:
            # Final fallback - get all recent data
            team_data_df = safe_fetchdf("""
                SELECT speler, datum, totale_afstand, hoge_intensiteit_afstand, max_snelheid,
                       aantal_sprints, aantal_acceleraties, impacts, player_load, positie
                FROM gps_data
                ORDER BY datum DESC
                LIMIT 100
            """)
    
    # If still empty, show informative message
    if team_data_df.empty:
        st.info(f"🔍 Proberen zonder datumfilter...")
        try:
            team_data_df = safe_fetchdf("""
                SELECT speler, datum, totale_afstand, hoge_intensiteit_afstand, max_snelheid,
                       aantal_sprints, aantal_acceleraties, impacts, player_load, positie
                FROM gps_data
                ORDER BY datum DESC
                LIMIT 50
            """)
            if not team_data_df.empty:
                st.success(f"✅ {len(team_data_df)} team GPS records gevonden (alle datums)")
        except:
            pass
    
    if not team_data_df.empty:
        df_team = team_data_df.copy()
        df_team['datum'] = pd.to_datetime(df_team['datum'])
        
        # Convert numeric columns - GPS metrics filled with 0, RPE columns keep NULL
        gps_cols = ['totale_afstand', 'hoge_intensiteit_afstand', 'max_snelheid', 
                   'aantal_sprints', 'aantal_acceleraties', 'impacts', 'player_load']
        rpe_cols = ['rpe_score', 'session_load', 'algemeen_welzijn']
        
        # Fill GPS columns with 0 for missing values
        for col in gps_cols:
            if col in df_team.columns:
                df_team[col] = pd.to_numeric(df_team[col], errors='coerce').fillna(0)
        
        # Convert RPE columns to numeric but keep NULL values
        for col in rpe_cols:
            if col in df_team.columns:
                df_team[col] = pd.to_numeric(df_team[col], errors='coerce')
        
        # Team statistieken
        st.markdown("#### 📊 Team Overzicht")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            unique_spelers = df_team['speler'].nunique()
            st.metric("Actieve Spelers", unique_spelers)
        
        with col2:
            total_trainingen = len(df_team)
            st.metric("Totaal Trainingen", total_trainingen)
        
        with col3:
            avg_team_distance = df_team['totale_afstand'].mean()
            st.metric("Gem. Team Afstand", f"{avg_team_distance:.0f}m")
        
        with col4:
            avg_team_load = df_team['player_load'].mean()
            st.metric("Gem. Team Load", f"{avg_team_load:.0f}")
        
        # Team prestatie vergelijking
        col1, col2 = st.columns(2)
        
        with col1:
            # Speler vergelijking - totale afstand
            speler_avg = df_team.groupby('speler')['totale_afstand'].mean().sort_values(ascending=True)
            fig_distance_comp = px.bar(x=speler_avg.values, y=speler_avg.index,
                                     orientation='h',
                                     title="Gemiddelde Totale Afstand per Speler",
                                     color=speler_avg.values,
                                     color_continuous_scale='viridis')
            fig_distance_comp.update_layout(height=600)
            st.plotly_chart(fig_distance_comp, use_container_width=True)
        
        with col2:
            # Speler vergelijking - hoge intensiteit
            speler_hi = df_team.groupby('speler')['hoge_intensiteit_afstand'].mean().sort_values(ascending=True)
            fig_hi_comp = px.bar(x=speler_hi.values, y=speler_hi.index,
                               orientation='h',
                               title="Gemiddelde Hoge Intensiteit per Speler",
                               color=speler_hi.values,
                               color_continuous_scale='plasma')
            fig_hi_comp.update_layout(height=600)
            st.plotly_chart(fig_hi_comp, use_container_width=True)
        
        # Team heatmap
        st.markdown("#### 🔥 Team Prestatie Heatmap")
        
        # Correlatie matrix van belangrijke metrics - only use available columns
        base_metrics = ['totale_afstand', 'hoge_intensiteit_afstand', 'max_snelheid', 
                       'aantal_sprints', 'aantal_acceleraties', 'impacts']
        
        # Only add columns that exist in the DataFrame
        metrics_cols = [col for col in base_metrics if col in df_team.columns]
        
        # Add RPE if available
        if 'rpe_score' in df_team.columns:
            metrics_cols.append('rpe_score')
        
        if len(metrics_cols) >= 2:  # Need at least 2 columns for correlation
            correlation_matrix = df_team[metrics_cols].corr()
            
            fig_heatmap = px.imshow(correlation_matrix, 
                                  text_auto=True,
                                  aspect="auto",
                                  title="Correlatie Matrix - Fysieke Metrics",
                                  color_continuous_scale='RdBu_r')
            st.plotly_chart(fig_heatmap, use_container_width=True)
        else:
            st.info("📊 Niet genoeg metrics beschikbaar voor correlatie matrix")
        
        # Top performers
        st.markdown("#### 🏆 Top Performers (Laatste 30 Dagen)")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("**💨 Snelste Spelers**")
            top_speed = df_team.groupby('speler')['max_snelheid'].max().sort_values(ascending=False).head(5)
            for i, (speler, speed) in enumerate(top_speed.items(), 1):
                st.write(f"{i}. {speler}: {speed:.1f} km/h")
        
        with col2:
            st.markdown("**🏃 Meeste Afstand**")
            top_distance = df_team.groupby('speler')['totale_afstand'].mean().sort_values(ascending=False).head(5)
            for i, (speler, distance) in enumerate(top_distance.items(), 1):
                st.write(f"{i}. {speler}: {distance:.0f}m")
        
        with col3:
            st.markdown("**⚡ Meeste Sprints**")
            top_sprints = df_team.groupby('speler')['aantal_sprints'].mean().sort_values(ascending=False).head(5)
            for i, (speler, sprints) in enumerate(top_sprints.items(), 1):
                st.write(f"{i}. {speler}: {sprints:.0f}")
        
        # RPE Analyse sectie - check if columns exist
        if 'rpe_score' in df_team.columns:
            rpe_team_data = df_team.dropna(subset=['rpe_score'])
            if not rpe_team_data.empty:
                st.markdown("#### 🎯 Team RPE Analyse")
                
                col1, col2 = st.columns(2)
            
                with col1:
                    # RPE distributie
                    fig_rpe_dist = px.histogram(rpe_team_data, x='rpe_score', 
                                              title="RPE Distributie (Team)",
                                              nbins=10)
                    fig_rpe_dist.update_layout(xaxis=dict(range=[0, 11]))
                    st.plotly_chart(fig_rpe_dist, use_container_width=True)
                
                with col2:
                    # RPE per speler (gemiddelde)
                    rpe_per_speler = rpe_team_data.groupby('speler')['rpe_score'].mean().sort_values(ascending=False)
                    fig_rpe_speler = px.bar(x=rpe_per_speler.values, y=rpe_per_speler.index,
                                          orientation='h',
                                          title="Gemiddelde RPE per Speler",
                                          color=rpe_per_speler.values,
                                          color_continuous_scale='Reds')
                    fig_rpe_speler.update_layout(xaxis=dict(range=[0, 11]))
                    st.plotly_chart(fig_rpe_speler, use_container_width=True)
                
                # RPE vs Load correlatie voor team
                st.markdown("#### 🔗 RPE vs GPS Load Correlatie (Team)")
                if 'player_load' in rpe_team_data.columns:
                    rpe_gps_data = rpe_team_data.dropna(subset=['player_load'])
                    if not rpe_gps_data.empty:
                        fig_rpe_team_corr = px.scatter(rpe_gps_data, x='player_load', y='rpe_score',
                                                     title="Team: GPS Load vs RPE Score",
                                                     color='speler',
                                                     hover_data=['datum'])
                        fig_rpe_team_corr.update_layout(yaxis=dict(range=[0, 11]))
                        st.plotly_chart(fig_rpe_team_corr, use_container_width=True)
                    else:
                        st.info("📭 Geen GPS Load data beschikbaar voor correlatie")
                else:
                    st.info("📭 Geen GPS Load data beschikbaar voor correlatie")
            else:
                st.info("📭 Geen RPE data beschikbaar voor team analyse")
        else:
            st.info("📭 Geen RPE data beschikbaar voor team analyse")    
    else:
        st.warning("⚠️ Geen GPS data gevonden voor team analyse.")
        st.info("💡 Import eerst GPS data via de Fysieke Data Import pagina.")

with tab3:
    st.markdown("### 📊 Positionele Analyse")
    
    # Use global date filters
    pos_start_date = global_start_datum
    pos_end_date = global_eind_datum
    
    st.info(f"📅 Positional analysis from {pos_start_date} to {pos_end_date}")
    try:
        df_pos = safe_fetchdf(f"""
            SELECT positie, speler, totale_afstand, hoge_intensiteit_afstand, 
                   max_snelheid, aantal_sprints, aantal_acceleraties, impacts
            FROM gps_data 
            WHERE datum >= '{pos_start_date}' AND datum <= '{pos_end_date}'
        """)
    except:
        # Fallback without date filter
        df_pos = safe_fetchdf("""
            SELECT positie, speler, totale_afstand, hoge_intensiteit_afstand, 
                   max_snelheid, aantal_sprints, aantal_acceleraties, impacts
            FROM gps_data 
            LIMIT 200
        """)
    
    if not df_pos.empty:
        
        # Convert numerieke kolommen van string naar numeric
        numeric_columns = ['totale_afstand', 'hoge_intensiteit_afstand', 'max_snelheid', 
                          'aantal_sprints', 'aantal_acceleraties', 'impacts']
        for col in numeric_columns:
            df_pos[col] = pd.to_numeric(df_pos[col], errors='coerce')
        
        # Positionele gemiddeldes
        pos_stats = df_pos.groupby('positie').agg({
            'totale_afstand': 'mean',
            'hoge_intensiteit_afstand': 'mean', 
            'max_snelheid': 'mean',
            'aantal_sprints': 'mean',
            'aantal_acceleraties': 'mean',
            'impacts': 'mean'
        }).round(1)
        
        st.markdown("#### 📊 Gemiddelde Prestaties per Positie")
        st.dataframe(pos_stats, use_container_width=True)
        
        # Positionele vergelijkingen
        col1, col2 = st.columns(2)
        
        with col1:
            # Box plot voor afstand per positie
            fig_box_distance = px.box(df_pos, x='positie', y='totale_afstand',
                                    title="Totale Afstand Verdeling per Positie")
            fig_box_distance.update_xaxes(tickangle=45)
            st.plotly_chart(fig_box_distance, use_container_width=True)
        
        with col2:
            # Box plot voor hoge intensiteit per positie
            fig_box_hi = px.box(df_pos, x='positie', y='hoge_intensiteit_afstand',
                              title="Hoge Intensiteit Verdeling per Positie")
            fig_box_hi.update_xaxes(tickangle=45)
            st.plotly_chart(fig_box_hi, use_container_width=True)
        
        # Positionele radar charts
        st.markdown("#### 🎯 Positionele Profielen")
        
        posities = df_pos['positie'].unique()
        selected_posities = st.multiselect(
            "Selecteer posities om te vergelijken:", 
            posities, 
            default=posities[:3] if len(posities) >= 3 else posities
        )
        
        if selected_posities:
            fig_radar_pos = go.Figure()
            
            categories = ['Totale Afstand', 'Hoge Intensiteit', 'Max Snelheid', 'Sprints', 'Acceleraties']
            
            colors = ['rgba(26, 118, 255, 0.6)', 'rgba(255, 99, 132, 0.6)', 'rgba(54, 162, 235, 0.6)',
                     'rgba(255, 205, 86, 0.6)', 'rgba(75, 192, 192, 0.6)', 'rgba(153, 102, 255, 0.6)']
            
            for i, pos in enumerate(selected_posities):
                pos_data = df_pos[df_pos['positie'] == pos]
                
                # Normaliseer naar percentage van max waarde
                values = [
                    (pos_data['totale_afstand'].mean() / df_pos['totale_afstand'].max()) * 100,
                    (pos_data['hoge_intensiteit_afstand'].mean() / df_pos['hoge_intensiteit_afstand'].max()) * 100,
                    (pos_data['max_snelheid'].mean() / df_pos['max_snelheid'].max()) * 100,
                    (pos_data['aantal_sprints'].mean() / df_pos['aantal_sprints'].max()) * 100,
                    (pos_data['aantal_acceleraties'].mean() / df_pos['aantal_acceleraties'].max()) * 100
                ]
                
                fig_radar_pos.add_trace(go.Scatterpolar(
                    r=values + [values[0]],
                    theta=categories + [categories[0]],
                    fill='toself',
                    name=pos,
                    fillcolor=colors[i % len(colors)],
                    line=dict(color=colors[i % len(colors)].replace('0.6', '1'))
                ))
            
            fig_radar_pos.update_layout(
                polar=dict(
                    radialaxis=dict(
                        visible=True,
                        range=[0, 100]
                    )),
                showlegend=True,
                title="Positionele Vergelijking (% van Team Max)"
            )
            
            st.plotly_chart(fig_radar_pos, use_container_width=True)
    
    else:
        st.warning("⚠️ Geen GPS data gevonden voor positionele analyse.")
        st.info("💡 Import eerst GPS data via de Fysieke Data Import pagina.")

with tab4:
    st.markdown("### 📈 Trend Analyse")
    
    # Use global date filters
    trend_start_date = global_start_datum
    trend_end_date = global_eind_datum
    
    st.info(f"📅 Trend analysis from {trend_start_date} to {trend_end_date}")
    try:
        df_trend = safe_fetchdf(f"""
            SELECT datum, speler, totale_afstand, hoge_intensiteit_afstand, max_snelheid,
                   aantal_sprints, player_load
            FROM gps_data 
            WHERE datum >= '{trend_start_date}' AND datum <= '{trend_end_date}'
            ORDER BY datum
        """)
    except:
        # Fallback without date filter
        df_trend = safe_fetchdf("""
            SELECT datum, speler, totale_afstand, hoge_intensiteit_afstand, max_snelheid,
                   aantal_sprints, player_load
            FROM gps_data 
            ORDER BY datum DESC
            LIMIT 150
        """)
    
    if not df_trend.empty:
        df_trend['datum'] = pd.to_datetime(df_trend['datum'])
        
        # Convert numeric columns - ensure GPS metrics are numeric
        numeric_cols = ['totale_afstand', 'hoge_intensiteit_afstand', 'max_snelheid', 
                       'aantal_sprints', 'player_load']
        
        for col in numeric_cols:
            if col in df_trend.columns:
                df_trend[col] = pd.to_numeric(df_trend[col], errors='coerce').fillna(0)
        
        # Team gemiddelde trends
        daily_avg = df_trend.groupby('datum').agg({
            'totale_afstand': 'mean',
            'hoge_intensiteit_afstand': 'mean',
            'max_snelheid': 'mean',
            'aantal_sprints': 'mean',
            'player_load': 'mean'
        }).reset_index()
        
        # Trend visualisaties
        col1, col2 = st.columns(2)
        
        with col1:
            fig_trend_distance = px.line(daily_avg, x='datum', y='totale_afstand',
                                       title="Team Gemiddelde - Totale Afstand Trend")
            fig_trend_distance.add_scatter(x=daily_avg['datum'], y=daily_avg['totale_afstand'],
                                         mode='markers', name='Training Dagen')
            st.plotly_chart(fig_trend_distance, use_container_width=True)
        
        with col2:
            fig_trend_load = px.line(daily_avg, x='datum', y='player_load',
                                   title="Team Gemiddelde - Training Load Trend")
            fig_trend_load.add_scatter(x=daily_avg['datum'], y=daily_avg['player_load'],
                                     mode='markers', name='Training Dagen')
            st.plotly_chart(fig_trend_load, use_container_width=True)
        
        # Speler individuele trends
        st.markdown("#### 👤 Individuele Trends")
        
        speler_voor_trend = st.selectbox("Selecteer speler voor trend analyse:", 
                                       df_trend['speler'].unique())
        
        if speler_voor_trend:
            speler_trend_data = df_trend[df_trend['speler'] == speler_voor_trend]
            
            # Multi-metric trend
            fig_multi = make_subplots(rows=2, cols=2,
                                    subplot_titles=('Totale Afstand', 'Hoge Intensiteit', 
                                                  'Max Snelheid', 'Aantal Sprints'))
            
            fig_multi.add_trace(
                go.Scatter(x=speler_trend_data['datum'], y=speler_trend_data['totale_afstand'],
                         mode='lines+markers', name='Afstand'),
                row=1, col=1
            )
            
            fig_multi.add_trace(
                go.Scatter(x=speler_trend_data['datum'], y=speler_trend_data['hoge_intensiteit_afstand'],
                         mode='lines+markers', name='Hoge Int.'),
                row=1, col=2
            )
            
            fig_multi.add_trace(
                go.Scatter(x=speler_trend_data['datum'], y=speler_trend_data['max_snelheid'],
                         mode='lines+markers', name='Max Snelheid'),
                row=2, col=1
            )
            
            fig_multi.add_trace(
                go.Scatter(x=speler_trend_data['datum'], y=speler_trend_data['aantal_sprints'],
                         mode='lines+markers', name='Sprints'),
                row=2, col=2
            )
            
            fig_multi.update_layout(height=600, showlegend=False,
                                  title_text=f"Prestatie Trends - {speler_voor_trend}")
            
            st.plotly_chart(fig_multi, use_container_width=True)
            
            # Trend statistieken
            st.markdown(f"#### 📊 Trend Statistieken - {speler_voor_trend}")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                recent_avg = speler_trend_data.tail(5)['totale_afstand'].mean()
                overall_avg = speler_trend_data['totale_afstand'].mean()
                trend_pct = ((recent_avg - overall_avg) / overall_avg) * 100
                
                st.metric("Afstand Trend (Laatste 5)", 
                         f"{recent_avg:.0f}m",
                         f"{trend_pct:+.1f}%")
            
            with col2:
                recent_hi = speler_trend_data.tail(5)['hoge_intensiteit_afstand'].mean()
                overall_hi = speler_trend_data['hoge_intensiteit_afstand'].mean()
                hi_trend_pct = ((recent_hi - overall_hi) / overall_hi) * 100
                
                st.metric("HI Trend (Laatste 5)",
                         f"{recent_hi:.0f}m", 
                         f"{hi_trend_pct:+.1f}%")
            
            with col3:
                recent_speed = speler_trend_data.tail(5)['max_snelheid'].max()
                overall_speed = speler_trend_data['max_snelheid'].max()
                speed_diff = recent_speed - overall_speed
                
                st.metric("Max Snelheid",
                         f"{recent_speed:.1f} km/h",
                         f"{speed_diff:+.1f} km/h")
    
    else:
        st.warning("⚠️ Geen GPS data gevonden voor trend analyse.")
        st.info("💡 Import eerst GPS data via de Fysieke Data Import pagina.")

with tab5:
    st.markdown("### ⚖️ ACWR (Acute:Chronic Workload Ratio) Analyse")
    
    st.info("💡 **ACWR** vergelijkt je **acute belasting** (laatste 7 dagen) met je **chronische belasting** (laatste 28 dagen). Optimaal: 0.8-1.3")
    
    # ACWR niveau selectie
    acwr_niveau = st.radio("📊 Selecteer analyse niveau", ["👤 Individueel", "👥 Team"], horizontal=True)
    
    # ACWR data ophalen - Use global date filters
    acwr_start_date = global_start_datum
    acwr_end_date = global_eind_datum
    
    st.info(f"📅 ACWR analysis from {acwr_start_date} to {acwr_end_date}") 
    try:
        df_acwr = safe_fetchdf(f"""
            SELECT speler, datum, totale_afstand, hoge_intensiteit_afstand, sprint_afstand,
                   aantal_acceleraties, aantal_deceleraties, max_snelheid, aantal_sprints
            FROM gps_data 
            WHERE datum >= '{acwr_start_date}' AND datum <= '{acwr_end_date}'
            ORDER BY speler, datum
        """)
    except:
        # Fallback without date filter
        df_acwr = safe_fetchdf("""
            SELECT speler, datum, totale_afstand, hoge_intensiteit_afstand, sprint_afstand,
                   aantal_acceleraties, aantal_deceleraties, max_snelheid, aantal_sprints
            FROM gps_data 
            ORDER BY speler, datum DESC
            LIMIT 200
        """)
    
    if not df_acwr.empty:
        df_acwr['datum'] = pd.to_datetime(df_acwr['datum'])
        
        # Convert numeric columns - ensure GPS metrics are numeric
        numeric_cols = ['totale_afstand', 'hoge_intensiteit_afstand', 'sprint_afstand',
                       'aantal_acceleraties', 'aantal_deceleraties', 'max_snelheid', 'aantal_sprints']
        
        for col in numeric_cols:
            if col in df_acwr.columns:
                df_acwr[col] = pd.to_numeric(df_acwr[col], errors='coerce').fillna(0)
        
        # GPS componenten voor ACWR
        gps_metrics = {
            'totale_afstand': 'Total Distance',
            'hoge_intensiteit_afstand': 'High Speed Running', 
            'sprint_afstand': 'Sprint Meters',
            'aantal_acceleraties': 'Acceleraties',
            'aantal_deceleraties': 'Deceleraties',
            'max_snelheid': 'Max Speed',
            'aantal_sprints': 'Sprints'
        }
        
        if acwr_niveau == "👤 Individueel":
            # Speler selectie
            acwr_spelers = df_acwr['speler'].unique()
            if len(acwr_spelers) > 0:
                selected_acwr_speler = st.selectbox("👤 Selecteer Speler voor ACWR Analyse", acwr_spelers)
                
                # Metric selectie voor individuele analyse
                selected_metric = st.selectbox("📊 Selecteer Metric voor Trend Analyse", 
                                             list(gps_metrics.values()), 
                                             index=0,
                                             help="Selecteer welke metric je wilt gebruiken voor de gedetailleerde trend analyse")
                selected_metric_col = [k for k, v in gps_metrics.items() if v == selected_metric][0]
            
                # Filter data voor geselecteerde speler
                speler_acwr_data = df_acwr[df_acwr['speler'] == selected_acwr_speler].sort_values('datum')
                
                if len(speler_acwr_data) >= 7:  # Minimaal 7 dagen data nodig
                    # Bereken ACWR voor laatste datum
                    laatste_datum = speler_acwr_data['datum'].max()
                    
                    st.markdown(f"#### 📊 ACWR Status voor {selected_acwr_speler} ({laatste_datum.strftime('%d-%m-%Y')})")
                    
                    # ACWR overzichtstabel
                    acwr_results = []
                    
                    for metric_col, display_name in gps_metrics.items():
                        acute, chronic, acwr = calculate_acwr(speler_acwr_data, metric_col, laatste_datum)
                        risk_cat, risk_color = get_acwr_risk_category(acwr)
                        
                        acwr_results.append({
                            'Component': display_name,
                            'Acute (7d)': f"{acute:.1f}" if acute is not None else "N/A",
                            'Chronic (28d)': f"{chronic:.1f}" if chronic is not None else "N/A", 
                            'ACWR': f"{acwr:.2f}" if acwr is not None else "N/A",
                            'Risico': risk_cat,
                            'acwr_value': acwr,
                            'risk_color': risk_color
                        })
                    
                    # ACWR Metrics display
                    col1, col2, col3, col4 = st.columns(4)
                    
                    optimal_count = sum(1 for r in acwr_results if r['Risico'] == 'Optimaal')
                    verhoogd_count = sum(1 for r in acwr_results if r['Risico'] in ['Verhoogd', 'Hoog Risico'])
                    te_laag_count = sum(1 for r in acwr_results if r['Risico'] == 'Te Laag')
                    
                    with col1:
                        st.metric("🟢 Optimaal", optimal_count)
                    
                    with col2:
                        st.metric("🟡 Verhoogd Risico", verhoogd_count)
                    
                    with col3:
                        st.metric("🔵 Te Laag", te_laag_count)
                    
                    with col4:
                        # Overall risk score
                        overall_risk = "Optimaal" if verhoogd_count == 0 else "Let Op!" if verhoogd_count <= 2 else "Hoog Risico"
                        st.metric("🎯 Overall Status", overall_risk)
                    
                    # ACWR Details tabel
                    st.markdown("#### 📋 ACWR Details per Component")
                    df_acwr_display = pd.DataFrame(acwr_results)
                    
                    # Color coding voor de tabel
                    def highlight_acwr_risk(row):
                        if row['Risico'] == 'Optimaal':
                            return ['background-color: #d5f4e6'] * len(row)
                        elif row['Risico'] in ['Verhoogd', 'Hoog Risico']:
                            return ['background-color: #ffeaa7'] * len(row)
                        elif row['Risico'] == 'Te Laag':
                            return ['background-color: #a8e6cf'] * len(row)
                        else:
                            return [''] * len(row)
                    
                    styled_df = df_acwr_display[['Component', 'Acute (7d)', 'Chronic (28d)', 'ACWR', 'Risico']].style.apply(highlight_acwr_risk, axis=1)
                    st.dataframe(styled_df, use_container_width=True, hide_index=True)
                    
                    # ACWR Visualisaties
                    st.markdown("#### 📈 ACWR Trends")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # ACWR bar chart
                        valid_acwr = [r for r in acwr_results if r['acwr_value'] is not None]
                        if valid_acwr:
                            fig_acwr_bar = go.Figure()
                        
                            colors = [r['risk_color'] for r in valid_acwr]
                            
                            fig_acwr_bar.add_trace(go.Bar(
                                x=[r['Component'] for r in valid_acwr],
                                y=[r['acwr_value'] for r in valid_acwr],
                                marker_color=colors,
                                text=[f"{r['acwr_value']:.2f}" for r in valid_acwr],
                                textposition='outside'
                            ))
                            
                            # Add optimal zone
                            fig_acwr_bar.add_hline(y=0.8, line_dash="dash", line_color="green", 
                                                 annotation_text="Optimaal Min (0.8)")
                            fig_acwr_bar.add_hline(y=1.3, line_dash="dash", line_color="green",
                                                 annotation_text="Optimaal Max (1.3)")
                            fig_acwr_bar.add_hline(y=1.5, line_dash="dash", line_color="red",
                                                 annotation_text="Hoog Risico (1.5)")
                            
                            fig_acwr_bar.update_layout(
                                title="ACWR per GPS Component",
                                xaxis_title="GPS Component",
                                yaxis_title="ACWR Ratio",
                                showlegend=False,
                                height=500
                            )
                            fig_acwr_bar.update_xaxis(tickangle=45)
                            
                            st.plotly_chart(fig_acwr_bar, use_container_width=True)
                    
                    with col2:
                        # ACWR trend over tijd voor geselecteerde metric
                        st.markdown(f"**{selected_metric} ACWR Trend (28 dagen)**")
                        
                        # Bereken ACWR voor elke dag in de laatste 28 dagen
                        acwr_trend_data = []
                        for i in range(28, 0, -1):
                            check_date = laatste_datum - timedelta(days=i)
                            acute, chronic, acwr = calculate_acwr(speler_acwr_data, selected_metric_col, check_date)
                            if acwr is not None:
                                risk_cat, risk_color = get_acwr_risk_category(acwr)
                                acwr_trend_data.append({
                                    'datum': check_date,
                                    'acwr': acwr,
                                    'risk_category': risk_cat,
                                    'risk_color': risk_color
                                })
                        
                        if acwr_trend_data:
                            df_trend = pd.DataFrame(acwr_trend_data)
                            
                            fig_trend = px.line(df_trend, x='datum', y='acwr',
                                              title=f"ACWR Trend - {selected_metric}",
                                              color_discrete_sequence=['#1f77b4'])
                            
                            # Add zones
                            fig_trend.add_hline(y=0.8, line_dash="dash", line_color="green")
                            fig_trend.add_hline(y=1.3, line_dash="dash", line_color="green") 
                            fig_trend.add_hline(y=1.5, line_dash="dash", line_color="red")
                            
                            # Color points by risk
                            for _, row in df_trend.iterrows():
                                fig_trend.add_scatter(x=[row['datum']], y=[row['acwr']],
                                                    mode='markers', marker_color=row['risk_color'],
                                                    marker_size=8, showlegend=False)
                            
                            fig_trend.update_layout(height=400)
                            st.plotly_chart(fig_trend, use_container_width=True)
                        else:
                            st.info("Niet genoeg data voor trend analyse")
                    
                    # ACWR Interpretatie
                    st.markdown("#### 💡 ACWR Interpretatie")
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("""
                        **🟢 Optimaal (0.8 - 1.3)**
                        - Goede balans tussen belasting en herstel
                        - Laag blessure risico
                        - Optimale adaptatie
                        
                        **🟡 Verhoogd (1.3 - 1.5)**
                        - Verhoogd blessure risico
                        - Overweeg belasting te verminderen
                        """)
                    
                    with col2:
                        st.markdown("""
                        **🔴 Hoog Risico (>1.5)**
                        - Zeer hoog blessure risico  
                        - Belasting direct verminderen
                        - Extra herstel nodig
                        
                        **🔵 Te Laag (<0.8)**
                        - Mogelijk ondertraining
                        - Geleidelijk belasting verhogen
                        """)
                    
                else:
                    st.warning(f"⚠️ Niet genoeg data voor ACWR analyse. Minimaal 7 dagen nodig, {len(speler_acwr_data)} beschikbaar.")
            
            else:
                st.warning("⚠️ Geen spelers gevonden met GPS data.")
        
        elif acwr_niveau == "👥 Team":
            st.markdown("### 👥 Team ACWR Analyse")
            
            # Metric selectie voor team analyse
            selected_team_metric = st.selectbox("📊 Selecteer Metric voor Team ACWR", 
                                               list(gps_metrics.values()), 
                                               index=0,
                                               help="Selecteer welke metric je wilt gebruiken voor de team ACWR analyse")
            selected_team_metric_col = [k for k, v in gps_metrics.items() if v == selected_team_metric][0]
            
            # Bereken ACWR voor alle spelers
            team_acwr_results = []
            laatste_datum = df_acwr['datum'].max()
            
            for speler in df_acwr['speler'].unique():
                speler_data = df_acwr[df_acwr['speler'] == speler].sort_values('datum')
                
                if len(speler_data) >= 7:  # Minimaal 7 dagen data nodig
                    acute, chronic, acwr = calculate_acwr(speler_data, selected_team_metric_col, laatste_datum)
                    risk_cat, risk_color = get_acwr_risk_category(acwr)
                    
                    team_acwr_results.append({
                        'speler': speler,
                        'acute': acute,
                        'chronic': chronic,
                        'acwr': acwr,
                        'risk_category': risk_cat,
                        'risk_color': risk_color
                    })
            
            if team_acwr_results:
                # Team ACWR overzicht
                col1, col2, col3, col4 = st.columns(4)
                
                valid_acwr = [r for r in team_acwr_results if r['acwr'] is not None]
                optimal_count = sum(1 for r in valid_acwr if r['risk_category'] == 'Optimaal')
                verhoogd_count = sum(1 for r in valid_acwr if r['risk_category'] in ['Verhoogd', 'Hoog Risico'])
                te_laag_count = sum(1 for r in valid_acwr if r['risk_category'] == 'Te Laag')
                
                with col1:
                    st.metric("🟫 Team Spelers", len(valid_acwr))
                    
                with col2:
                    st.metric("🟢 Optimaal", optimal_count)
                    
                with col3:
                    st.metric("🟡 Verhoogd Risico", verhoogd_count)
                    
                with col4:
                    st.metric("🔵 Te Laag", te_laag_count)
                
                # Team ACWR visualisaties
                col1, col2 = st.columns(2)
                
                with col1:
                    # Team ACWR bar chart
                    st.markdown(f"#### 📊 {selected_team_metric} - Team ACWR")
                    
                    if valid_acwr:
                        fig_team_acwr = go.Figure()
                        
                        fig_team_acwr.add_trace(go.Bar(
                            x=[r['speler'] for r in valid_acwr],
                            y=[r['acwr'] for r in valid_acwr],
                            marker_color=[r['risk_color'] for r in valid_acwr],
                            text=[f"{r['acwr']:.2f}" for r in valid_acwr],
                            textposition='outside',
                            hovertemplate='Speler: %{x}<br>ACWR: %{y:.2f}<br>Acute: %{customdata[0]:.1f}<br>Chronic: %{customdata[1]:.1f}<extra></extra>',
                            customdata=[[r['acute'], r['chronic']] for r in valid_acwr]
                        ))
                        
                        # Add optimal zone
                        fig_team_acwr.add_hline(y=0.8, line_dash="dash", line_color="green", 
                                              annotation_text="Optimaal Min (0.8)")
                        fig_team_acwr.add_hline(y=1.3, line_dash="dash", line_color="green",
                                              annotation_text="Optimaal Max (1.3)")
                        fig_team_acwr.add_hline(y=1.5, line_dash="dash", line_color="red",
                                              annotation_text="Hoog Risico (1.5)")
                        
                        fig_team_acwr.update_layout(
                            title=f"Team ACWR - {selected_team_metric}",
                            xaxis_title="Speler",
                            yaxis_title="ACWR Ratio",
                            showlegend=False,
                            height=500
                        )
                        fig_team_acwr.update_xaxis(tickangle=45)
                        
                        st.plotly_chart(fig_team_acwr, use_container_width=True)
                
                with col2:
                    # ACWR distributie
                    st.markdown("#### 📊 ACWR Distributie")
                    
                    acwr_values = [r['acwr'] for r in valid_acwr if r['acwr'] is not None]
                    if acwr_values:
                        fig_dist = go.Figure()
                        
                        fig_dist.add_trace(go.Histogram(
                            x=acwr_values,
                            nbinsx=15,
                            name="ACWR Distributie",
                            marker_color='rgba(46, 134, 171, 0.7)'
                        ))
                        
                        # Add optimal zone shading
                        fig_dist.add_vrect(
                            x0=0.8, x1=1.3,
                            fillcolor="green", opacity=0.2,
                            layer="below", line_width=0,
                            annotation_text="Optimaal", annotation_position="top left"
                        )
                        
                        fig_dist.update_layout(
                            title="ACWR Verdeling Team",
                            xaxis_title="ACWR Ratio",
                            yaxis_title="Aantal Spelers",
                            height=400
                        )
                        
                        st.plotly_chart(fig_dist, use_container_width=True)
                
                # Team ACWR tabel
                st.markdown("#### 📋 Team ACWR Details")
                
                df_team_acwr = pd.DataFrame(team_acwr_results)
                df_team_display = df_team_acwr[df_team_acwr['acwr'].notna()].copy()
                df_team_display['acute_formatted'] = df_team_display['acute'].apply(lambda x: f"{x:.1f}" if x is not None else "N/A")
                df_team_display['chronic_formatted'] = df_team_display['chronic'].apply(lambda x: f"{x:.1f}" if x is not None else "N/A")
                df_team_display['acwr_formatted'] = df_team_display['acwr'].apply(lambda x: f"{x:.2f}" if x is not None else "N/A")
                
                # Sorteer op risico en ACWR waarde
                risk_order = {'Hoog Risico': 0, 'Verhoogd': 1, 'Te Laag': 2, 'Optimaal': 3}
                df_team_display['risk_order'] = df_team_display['risk_category'].map(risk_order)
                df_team_display = df_team_display.sort_values(['risk_order', 'acwr'], ascending=[True, False])
                
                # Color coding voor de tabel
                def highlight_team_acwr_risk(row):
                    if row['risk_category'] == 'Optimaal':
                        return ['background-color: #d5f4e6'] * len(row)
                    elif row['risk_category'] in ['Verhoogd', 'Hoog Risico']:
                        return ['background-color: #ffeaa7'] * len(row)
                    elif row['risk_category'] == 'Te Laag':
                        return ['background-color: #a8e6cf'] * len(row)
                    else:
                        return [''] * len(row)
                
                display_cols = ['speler', 'acute_formatted', 'chronic_formatted', 'acwr_formatted', 'risk_category']
                col_names = ['Speler', f'Acute (7d) - {selected_team_metric}', f'Chronic (28d) - {selected_team_metric}', 'ACWR', 'Risico']
                
                styled_team_df = df_team_display[display_cols].copy()
                styled_team_df.columns = col_names
                styled_team_df = styled_team_df.style.apply(lambda row: highlight_team_acwr_risk(df_team_display.iloc[row.name]), axis=1)
                
                st.dataframe(styled_team_df, use_container_width=True, hide_index=True)
                
                # Team aanbevelingen
                st.markdown("#### 💡 Team Aanbevelingen")
                
                if verhoogd_count > 0:
                    st.warning(f"⚠️ {verhoogd_count} speler(s) met verhoogd blessurerisico. Overweeg belasting te verminderen.")
                
                if te_laag_count > len(valid_acwr) * 0.3:  # >30% te laag
                    st.info(f"📈 {te_laag_count} speler(s) mogelijk ondergetraind. Overweeg geleidelijke belasting verhoging.")
                
                if optimal_count == len(valid_acwr):
                    st.success("🎆 Hele team in optimale ACWR zone! Uitstekende belastingsbalans.")
                
                # Export optie
                if st.button("📄 Export Team ACWR Data"):
                    csv_data = df_team_display[['speler', 'acute', 'chronic', 'acwr', 'risk_category']].to_csv(index=False)
                    st.download_button(
                        label="Download CSV",
                        data=csv_data,
                        file_name=f"team_acwr_{selected_team_metric.lower().replace(' ', '_')}_{laatste_datum.strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
            
            else:
                st.warning("⚠️ Geen spelers met voldoende data gevonden voor team ACWR analyse.")
    
    else:
        st.warning("⚠️ Geen GPS data gevonden voor ACWR analyse.")
        st.info("💡 Import eerst GPS data via de Fysieke Data Import pagina.")

# Database cleanup
# Safe database connection cleanup
# Database cleanup handled by Supabase helpers