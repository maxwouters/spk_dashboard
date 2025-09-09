import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

from supabase_helpers import safe_fetchdf

st.set_page_config(page_title="Wedstrijdvoorbereiding Analyse", page_icon="⚽", layout="wide")

st.title("⚽ Wedstrijdvoorbereiding Analyse")
st.markdown("""
Deze pagina helpt bij het optimaliseren van de wedstrijdvoorbereiding door:
- **Volume en Intensiteit** van trainingsweken te vergelijken met wedstrijdvereisten
- **Evolutie** van trainingsbelasting doorheen de tijd te monitoren
- **Wedstrijdgereedheid** van spelers te beoordelen
""")

# Helper functions
def identify_session_type(training_id):
    """Identificeer of een sessie een wedstrijd of training is"""
    try:
        # Check training type
        training_info = safe_fetchdf("""
            SELECT type, omschrijving 
            FROM trainings_calendar 
            WHERE training_id = ?
        """, [training_id])
        
        if not training_info.empty:
            training_type = training_info['type'].iloc[0]
            if training_type in ['Wedstrijd', 'Vriendschappelijk']:
                return 'Wedstrijd'
            
            # Check for match link
            match_link = safe_fetchdf("""
                SELECT match_id FROM matches 
                WHERE training_calendar_id = ?
            """, [training_id])
            
            if not match_link.empty:
                return 'Wedstrijd'
        
        return 'Training'
    except:
        return 'Onbekend'

def calculate_weekly_load(df, week_start):
    """Bereken wekelijkse belasting voor een speler"""
    if df.empty:
        return {}
    
    # Filter data voor de week
    week_end = week_start + timedelta(days=7)
    # Convert week_start and week_end to datetime for comparison with pandas datetime64[ns]
    week_start_dt = pd.to_datetime(week_start)
    week_end_dt = pd.to_datetime(week_end)
    week_data = df[(df['datum'] >= week_start_dt) & (df['datum'] < week_end_dt)]
    
    if week_data.empty:
        return {}
    
    # Bereken totalen per week
    weekly_metrics = {
        'totale_afstand': week_data['totale_afstand'].sum() if 'totale_afstand' in week_data.columns else 0,
        'hoge_intensiteit_afstand': week_data['hoge_intensiteit_afstand'].sum() if 'hoge_intensiteit_afstand' in week_data.columns else 0,
        'sprint_afstand': week_data['sprint_afstand'].sum() if 'sprint_afstand' in week_data.columns else 0,
        'aantal_sprints': week_data['aantal_sprints'].sum() if 'aantal_sprints' in week_data.columns else 0,
        'player_load': week_data['player_load'].sum() if 'player_load' in week_data.columns else 0,
        'aantal_sessies': len(week_data),
        'gemiddelde_rpe': week_data['rpe_score'].mean() if 'rpe_score' in week_data.columns and not week_data['rpe_score'].isna().all() else None
    }
    
    return weekly_metrics

def get_match_benchmarks(position=None):
    """Krijg wedstrijd benchmarks gebaseerd op historische data"""
    try:
        # Query voor wedstrijddata
        query = """
            SELECT g.*, t.type
            FROM gps_data g
            JOIN trainings_calendar t ON g.training_id = t.training_id
            WHERE t.type IN ('Wedstrijd', 'Vriendschappelijk')
            AND g.session_duur_minuten >= 45
        """
        params = []
        
        if position:
            query += " AND g.positie = ?"
            params.append(position)
        
        match_data = safe_fetchdf(query, params)
        
        if match_data.empty:
            return get_fallback_benchmarks()
        
        # Bereken benchmarks
        benchmarks = {
            'totale_afstand': {
                '25th': match_data['totale_afstand'].quantile(0.25),
                '50th': match_data['totale_afstand'].quantile(0.50),
                '75th': match_data['totale_afstand'].quantile(0.75),
                '90th': match_data['totale_afstand'].quantile(0.90)
            },
            'hoge_intensiteit_afstand': {
                '25th': match_data['hoge_intensiteit_afstand'].quantile(0.25),
                '50th': match_data['hoge_intensiteit_afstand'].quantile(0.50),
                '75th': match_data['hoge_intensiteit_afstand'].quantile(0.75),
                '90th': match_data['hoge_intensiteit_afstand'].quantile(0.90)
            },
            'sprint_afstand': {
                '25th': match_data['sprint_afstand'].quantile(0.25),
                '50th': match_data['sprint_afstand'].quantile(0.50),
                '75th': match_data['sprint_afstand'].quantile(0.75),
                '90th': match_data['sprint_afstand'].quantile(0.90)
            },
            'aantal_sprints': {
                '25th': match_data['aantal_sprints'].quantile(0.25),
                '50th': match_data['aantal_sprints'].quantile(0.50),
                '75th': match_data['aantal_sprints'].quantile(0.75),
                '90th': match_data['aantal_sprints'].quantile(0.90)
            }
        }
        
        return benchmarks
    except:
        return get_fallback_benchmarks()

def get_fallback_benchmarks():
    """Fallback benchmarks als er geen historische data is"""
    return {
        'totale_afstand': {'25th': 8000, '50th': 9500, '75th': 11000, '90th': 12000},
        'hoge_intensiteit_afstand': {'25th': 400, '50th': 600, '75th': 800, '90th': 1000},
        'sprint_afstand': {'25th': 50, '50th': 100, '75th': 150, '90th': 200},
        'aantal_sprints': {'25th': 10, '50th': 15, '75th': 20, '90th': 25}
    }

def calculate_match_readiness(weekly_metrics, benchmarks):
    """Bereken wedstrijdgereedheid score"""
    if not weekly_metrics or not benchmarks:
        return None
    
    readiness_scores = {}
    
    for metric in ['totale_afstand', 'hoge_intensiteit_afstand', 'sprint_afstand', 'aantal_sprints']:
        weekly_value = weekly_metrics.get(metric, 0)
        benchmark_50th = benchmarks.get(metric, {}).get('50th', 0)
        
        if benchmark_50th > 0:
            # Score gebaseerd op percentage van benchmark
            score = (weekly_value / benchmark_50th) * 100
            readiness_scores[metric] = min(score, 150)  # Cap op 150%
        else:
            readiness_scores[metric] = 0
    
    # Gemiddelde readiness score
    avg_readiness = np.mean(list(readiness_scores.values())) if readiness_scores else 0
    
    return avg_readiness, readiness_scores

# Sidebar - Parameters
st.sidebar.header("📊 Analyse Parameters")

# Date range filter
start_datum = st.sidebar.date_input(
    "📅 Start Datum", 
    value=datetime.now().date() - timedelta(days=90),
    key="match_prep_start"
)
eind_datum = st.sidebar.date_input(
    "📅 Eind Datum", 
    value=datetime.now().date(),
    key="match_prep_end"
)

# Speler selectie
try:
    all_players = safe_fetchdf("""
        SELECT DISTINCT speler as naam 
        FROM gps_data 
        WHERE datum >= ? AND datum <= ?
        ORDER BY speler
    """, [start_datum.strftime('%Y-%m-%d'), eind_datum.strftime('%Y-%m-%d')])
    
    if not all_players.empty:
        selected_speler = st.sidebar.selectbox(
            "👤 Selecteer Speler", 
            all_players['naam'].tolist()
        )
    else:
        st.sidebar.error("Geen spelers gevonden in geselecteerde periode")
        st.stop()
        
except Exception as e:
    st.sidebar.error(f"Fout bij ophalen spelers: {e}")
    st.stop()

# Positie filter (optioneel)
positie_filter = st.sidebar.selectbox(
    "📍 Positie voor Benchmarks",
    ["Alle Posities", "Verdediger", "Middenvelder", "Aanvaller"],
    help="Kies positie voor positie-specifieke wedstrijd benchmarks"
)

position_for_benchmark = None if positie_filter == "Alle Posities" else positie_filter

# Main analysis
if selected_speler:
    st.markdown(f"## 📊 Analyse voor **{selected_speler}**")
    
    # Haal speler data op
    try:
        speler_data = safe_fetchdf("""
            SELECT g.*, t.type, r.rpe_score
            FROM gps_data g
            LEFT JOIN trainings_calendar t ON g.training_id = t.training_id
            LEFT JOIN rpe_data r ON g.training_id = r.training_id AND g.speler = r.speler
            WHERE g.speler = ? 
            AND g.datum >= ? AND g.datum <= ?
            ORDER BY g.datum DESC
        """, [selected_speler, start_datum.strftime('%Y-%m-%d'), eind_datum.strftime('%Y-%m-%d')])
        
        if speler_data.empty:
            st.warning(f"Geen data gevonden voor {selected_speler} in periode {start_datum} - {eind_datum}")
            st.stop()
        
        # Data preprocessing
        speler_data['datum'] = pd.to_datetime(speler_data['datum'])
        
        # Converteer numerieke kolommen
        numeric_cols = ['totale_afstand', 'hoge_intensiteit_afstand', 'sprint_afstand', 
                       'aantal_sprints', 'player_load', 'max_snelheid']
        
        for col in numeric_cols:
            if col in speler_data.columns:
                speler_data[col] = pd.to_numeric(speler_data[col], errors='coerce').fillna(0)
        
        # Sessie type identificatie
        speler_data['sessie_type'] = speler_data['type'].apply(
            lambda x: 'Wedstrijd' if x in ['Wedstrijd', 'Vriendschappelijk'] else 'Training'
        )
        
        st.success(f"✅ {len(speler_data)} sessies geladen ({len(speler_data[speler_data['sessie_type'] == 'Wedstrijd'])} wedstrijden, {len(speler_data[speler_data['sessie_type'] == 'Training'])} trainingen)")
        
        # Tabs voor verschillende analyses
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📈 Wekelijkse Belasting",
            "⚽ Wedstrijdvoorbereiding", 
            "📊 Volume vs Intensiteit",
            "🎯 Evolutie & Trends",
            "🏆 Wedstrijdprestaties"
        ])
        
        with tab1:
            st.markdown("### 📈 Wekelijkse Belasting Analyse")
            
            # Bereken wekelijkse metrics
            weeks = []
            weekly_data = []
            
            # Start van eerste week (maandag)
            first_date = speler_data['datum'].min()
            first_monday = first_date - timedelta(days=first_date.weekday())
            
            current_week = first_monday
            end_date = speler_data['datum'].max()
            
            while current_week <= end_date:
                weekly_metrics = calculate_weekly_load(speler_data, current_week.date())
                if weekly_metrics:  # Alleen weken met data
                    weekly_metrics['week_start'] = current_week.date()
                    weekly_metrics['week_label'] = f"Week {current_week.strftime('%d/%m')}"
                    weekly_data.append(weekly_metrics)
                
                current_week += timedelta(days=7)
            
            if weekly_data:
                weekly_df = pd.DataFrame(weekly_data)
                
                # Visualisatie wekelijkse belasting
                col1, col2 = st.columns(2)
                
                with col1:
                    # Totale Afstand per week
                    fig_distance = px.bar(
                        weekly_df, 
                        x='week_label', 
                        y='totale_afstand',
                        title="📏 Totale Afstand per Week",
                        labels={'totale_afstand': 'Afstand (m)', 'week_label': 'Week'}
                    )
                    fig_distance.update_layout(showlegend=False)
                    st.plotly_chart(fig_distance, use_container_width=True)
                
                with col2:
                    # Hoge Intensiteit per week
                    fig_hsi = px.bar(
                        weekly_df, 
                        x='week_label', 
                        y='hoge_intensiteit_afstand',
                        title="🚀 Hoge Intensiteit Afstand per Week",
                        labels={'hoge_intensiteit_afstand': 'HSR Afstand (m)', 'week_label': 'Week'},
                        color='hoge_intensiteit_afstand',
                        color_continuous_scale='Reds'
                    )
                    fig_hsi.update_layout(showlegend=False)
                    st.plotly_chart(fig_hsi, use_container_width=True)
                
                # Player Load en Sprint activiteit
                col3, col4 = st.columns(2)
                
                with col3:
                    # Player Load per week
                    fig_load = px.line(
                        weekly_df, 
                        x='week_label', 
                        y='player_load',
                        title="💪 Player Load Evolutie",
                        labels={'player_load': 'Player Load', 'week_label': 'Week'},
                        markers=True
                    )
                    st.plotly_chart(fig_load, use_container_width=True)
                
                with col4:
                    # Sprint activiteit
                    fig_sprints = px.bar(
                        weekly_df, 
                        x='week_label', 
                        y='aantal_sprints',
                        title="⚡ Aantal Sprints per Week",
                        labels={'aantal_sprints': 'Aantal Sprints', 'week_label': 'Week'},
                        color='aantal_sprints',
                        color_continuous_scale='Greens'
                    )
                    st.plotly_chart(fig_sprints, use_container_width=True)
                
                # Wekelijkse tabel
                st.markdown("#### 📋 Wekelijkse Belasting Overzicht")
                display_weekly = weekly_df.copy()
                display_weekly['Totale Afstand (km)'] = (display_weekly['totale_afstand'] / 1000).round(1)
                display_weekly['HSR Afstand (m)'] = display_weekly['hoge_intensiteit_afstand'].round(0)
                display_weekly['Sprint Afstand (m)'] = display_weekly['sprint_afstand'].round(0)
                display_weekly['Player Load'] = display_weekly['player_load'].round(1)
                display_weekly['Sessies'] = display_weekly['aantal_sessies']
                display_weekly['Gem. RPE'] = display_weekly['gemiddelde_rpe'].round(1) if 'gemiddelde_rpe' in display_weekly.columns else 'N/A'
                
                st.dataframe(
                    display_weekly[['week_label', 'Totale Afstand (km)', 'HSR Afstand (m)', 
                                   'Sprint Afstand (m)', 'Player Load', 'Sessies', 'Gem. RPE']],
                    use_container_width=True
                )
            else:
                st.info("Geen wekelijkse data beschikbaar voor geselecteerde periode")
        
        with tab2:
            st.markdown("### ⚽ Wedstrijdvoorbereiding Analyse")
            
            # Haal wedstrijd benchmarks op
            benchmarks = get_match_benchmarks(position_for_benchmark)
            
            # Selecteer komende wedstrijd of meest recente
            wedstrijden = speler_data[speler_data['sessie_type'] == 'Wedstrijd'].copy()
            
            if not wedstrijden.empty:
                st.markdown("#### 🎯 Wedstrijd Selectie")
                
                # Laat gebruiker een wedstrijd kiezen voor analyse
                wedstrijd_opties = []
                for _, row in wedstrijden.iterrows():
                    datum_str = row['datum'].strftime('%d/%m/%Y')
                    beschrijving = row.get('omschrijving', 'Wedstrijd')
                    wedstrijd_opties.append(f"{datum_str} - {beschrijving}")
                
                if wedstrijd_opties:
                    selected_wedstrijd_idx = st.selectbox(
                        "Selecteer wedstrijd voor analyse:",
                        range(len(wedstrijd_opties)),
                        format_func=lambda x: wedstrijd_opties[x]
                    )
                    
                    selected_wedstrijd = wedstrijden.iloc[selected_wedstrijd_idx]
                    wedstrijd_datum = selected_wedstrijd['datum'].date()
                    
                    st.info(f"📅 Analyseer voorbereiding voor wedstrijd op {wedstrijd_datum}")
                    
                    # Analyseer 7 dagen voor de wedstrijd
                    prep_start = wedstrijd_datum - timedelta(days=7)
                    prep_data = speler_data[
                        (speler_data['datum'].dt.date >= prep_start) & 
                        (speler_data['datum'].dt.date < wedstrijd_datum) &
                        (speler_data['sessie_type'] == 'Training')
                    ].copy()
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("#### 📊 Voorbereidingsweek Samenvatting")
                        
                        if not prep_data.empty:
                            prep_metrics = {
                                'totale_afstand': prep_data['totale_afstand'].sum(),
                                'hoge_intensiteit_afstand': prep_data['hoge_intensiteit_afstand'].sum(),
                                'sprint_afstand': prep_data['sprint_afstand'].sum(),
                                'aantal_sprints': prep_data['aantal_sprints'].sum(),
                                'player_load': prep_data['player_load'].sum(),
                                'aantal_sessies': len(prep_data)
                            }
                            
                            st.metric("🏃 Totale Afstand", f"{prep_metrics['totale_afstand']/1000:.1f} km")
                            st.metric("🚀 HSR Afstand", f"{prep_metrics['hoge_intensiteit_afstand']:.0f} m")
                            st.metric("⚡ Sprint Afstand", f"{prep_metrics['sprint_afstand']:.0f} m")
                            st.metric("💪 Player Load", f"{prep_metrics['player_load']:.1f}")
                            st.metric("📅 Training Sessies", f"{prep_metrics['aantal_sessies']}")
                        else:
                            st.warning("Geen trainingsdata gevonden in voorbereidingsweek")
                            prep_metrics = {}
                    
                    with col2:
                        st.markdown("#### 🎯 Wedstrijdgereedheid")
                        
                        if prep_metrics and benchmarks:
                            readiness_score, readiness_details = calculate_match_readiness(prep_metrics, benchmarks)
                            
                            if readiness_score is not None:
                                # Overall readiness
                                if readiness_score >= 80:
                                    readiness_status = "🟢 Optimaal Voorbereid"
                                    readiness_color = "green"
                                elif readiness_score >= 60:
                                    readiness_status = "🟡 Redelijk Voorbereid"  
                                    readiness_color = "orange"
                                else:
                                    readiness_status = "🔴 Ondervoorbereid"
                                    readiness_color = "red"
                                
                                st.metric(
                                    "Gereedheid Score", 
                                    f"{readiness_score:.0f}%",
                                    help="Gebaseerd op vergelijking met wedstrijd benchmarks"
                                )
                                st.markdown(f"**Status:** {readiness_status}")
                                
                                # Gedetailleerde readiness per metric
                                st.markdown("##### 📋 Detail per Metric:")
                                for metric, score in readiness_details.items():
                                    metric_names = {
                                        'totale_afstand': 'Totale Afstand',
                                        'hoge_intensiteit_afstand': 'HSR Afstand', 
                                        'sprint_afstand': 'Sprint Afstand',
                                        'aantal_sprints': 'Aantal Sprints'
                                    }
                                    display_name = metric_names.get(metric, metric)
                                    st.write(f"• {display_name}: {score:.0f}%")
                            else:
                                st.error("Kan wedstrijdgereedheid niet berekenen")
                        else:
                            st.info("Wedstrijdgereedheid analyse niet beschikbaar")
                    
                    # Voorbereiding vs Wedstrijd vergelijking
                    if not prep_data.empty:
                        st.markdown("#### 📊 Voorbereiding vs Wedstrijd Benchmarks")
                        
                        # Get position-specific benchmarks for the charts
                        position_benchmarks = get_match_benchmarks(position_for_benchmark)
                        
                        # Maak vergelijkingsgrafiek
                        comparison_data = []
                        
                        metrics_to_compare = [
                            ('totale_afstand', 'Totale Afstand (m)', prep_metrics.get('totale_afstand', 0)),
                            ('hoge_intensiteit_afstand', 'HSR Afstand (m)', prep_metrics.get('hoge_intensiteit_afstand', 0)),
                            ('sprint_afstand', 'Sprint Afstand (m)', prep_metrics.get('sprint_afstand', 0)),
                            ('aantal_sprints', 'Aantal Sprints', prep_metrics.get('aantal_sprints', 0))
                        ]
                        
                        for metric_key, metric_label, prep_value in metrics_to_compare:
                            benchmark_50th = position_benchmarks.get(metric_key, {}).get('50th', 0)
                            benchmark_75th = position_benchmarks.get(metric_key, {}).get('75th', 0)
                            
                            comparison_data.append({
                                'Metric': metric_label,
                                'Voorbereiding': prep_value,
                                'Wedstrijd 50th': benchmark_50th,
                                'Wedstrijd 75th': benchmark_75th
                            })
                        
                        # Split into 4 separate charts for better scaling
                        col1, col2 = st.columns(2)
                        
                        # Chart 1: Totale Afstand (grootste waarden)
                        with col1:
                            fig_distance = go.Figure()
                            metric_data = comparison_data[0]  # Totale Afstand
                            
                            fig_distance.add_trace(go.Bar(
                                name='Voorbereidingsweek',
                                x=['Voorbereiding'],
                                y=[metric_data['Voorbereiding']],
                                marker_color='lightblue',
                                showlegend=True
                            ))
                            
                            fig_distance.add_trace(go.Bar(
                                name='Wedstrijd 50th',
                                x=['Wedstrijd 50th'],
                                y=[metric_data['Wedstrijd 50th']],
                                marker_color='orange',
                                showlegend=True
                            ))
                            
                            fig_distance.add_trace(go.Bar(
                                name='Wedstrijd 75th',
                                x=['Wedstrijd 75th'],
                                y=[metric_data['Wedstrijd 75th']],
                                marker_color='red',
                                showlegend=True
                            ))
                            
                            fig_distance.update_layout(
                                title="📏 Totale Afstand (m)",
                                height=300,
                                showlegend=False
                            )
                            
                            st.plotly_chart(fig_distance, use_container_width=True)
                        
                        # Chart 2: HSR Afstand 
                        with col2:
                            fig_hsr = go.Figure()
                            metric_data = comparison_data[1]  # HSR Afstand
                            
                            fig_hsr.add_trace(go.Bar(
                                name='Voorbereidingsweek',
                                x=['Voorbereiding'],
                                y=[metric_data['Voorbereiding']],
                                marker_color='lightblue'
                            ))
                            
                            fig_hsr.add_trace(go.Bar(
                                name='Wedstrijd 50th',
                                x=['Wedstrijd 50th'],
                                y=[metric_data['Wedstrijd 50th']],
                                marker_color='orange'
                            ))
                            
                            fig_hsr.add_trace(go.Bar(
                                name='Wedstrijd 75th',
                                x=['Wedstrijd 75th'],
                                y=[metric_data['Wedstrijd 75th']],
                                marker_color='red'
                            ))
                            
                            fig_hsr.update_layout(
                                title="🚀 HSR Afstand (m)",
                                height=300,
                                showlegend=False
                            )
                            
                            st.plotly_chart(fig_hsr, use_container_width=True)
                        
                        # Second row for smaller values
                        col3, col4 = st.columns(2)
                        
                        # Chart 3: Sprint Afstand (kleinere waarden)
                        with col3:
                            fig_sprint_dist = go.Figure()
                            metric_data = comparison_data[2]  # Sprint Afstand
                            
                            fig_sprint_dist.add_trace(go.Bar(
                                name='Voorbereidingsweek',
                                x=['Voorbereiding'],
                                y=[metric_data['Voorbereiding']],
                                marker_color='lightblue'
                            ))
                            
                            fig_sprint_dist.add_trace(go.Bar(
                                name='Wedstrijd 50th',
                                x=['Wedstrijd 50th'],
                                y=[metric_data['Wedstrijd 50th']],
                                marker_color='orange'
                            ))
                            
                            fig_sprint_dist.add_trace(go.Bar(
                                name='Wedstrijd 75th',
                                x=['Wedstrijd 75th'],
                                y=[metric_data['Wedstrijd 75th']],
                                marker_color='red'
                            ))
                            
                            fig_sprint_dist.update_layout(
                                title="⚡ Sprint Afstand (m)",
                                height=300,
                                showlegend=False
                            )
                            
                            st.plotly_chart(fig_sprint_dist, use_container_width=True)
                        
                        # Chart 4: Aantal Sprints (kleinste waarden)
                        with col4:
                            fig_sprint_count = go.Figure()
                            metric_data = comparison_data[3]  # Aantal Sprints
                            
                            fig_sprint_count.add_trace(go.Bar(
                                name='Voorbereidingsweek',
                                x=['Voorbereiding'],
                                y=[metric_data['Voorbereiding']],
                                marker_color='lightblue'
                            ))
                            
                            fig_sprint_count.add_trace(go.Bar(
                                name='Wedstrijd 50th',
                                x=['Wedstrijd 50th'],
                                y=[metric_data['Wedstrijd 50th']],
                                marker_color='orange'
                            ))
                            
                            fig_sprint_count.add_trace(go.Bar(
                                name='Wedstrijd 75th',
                                x=['Wedstrijd 75th'],
                                y=[metric_data['Wedstrijd 75th']],
                                marker_color='red'
                            ))
                            
                            fig_sprint_count.update_layout(
                                title="🏃 Aantal Sprints",
                                height=300,
                                showlegend=False
                            )
                            
                            st.plotly_chart(fig_sprint_count, use_container_width=True)
                        
                        # Add legend explanation below the charts
                        st.markdown("""
                        **Legenda:**
                        - 🔵 **Voorbereiding**: Totaal van voorbereidingsweek (7 dagen voor wedstrijd)
                        - 🟠 **Wedstrijd 50th**: Mediaan wedstrijd prestatie (50e percentiel)  
                        - 🔴 **Wedstrijd 75th**: Hoge wedstrijd prestatie (75e percentiel)
                        """)
            else:
                st.info("Geen wedstrijddata gevonden in geselecteerde periode")
        
        with tab3:
            st.markdown("### 📊 Volume vs Intensiteit Analyse")
            
            # Scatter plot volume vs intensiteit
            fig_scatter = px.scatter(
                speler_data,
                x='totale_afstand',
                y='hoge_intensiteit_afstand', 
                color='sessie_type',
                size='player_load',
                hover_data=['datum', 'max_snelheid', 'aantal_sprints'],
                title="Volume vs Intensiteit per Sessie",
                labels={
                    'totale_afstand': 'Totale Afstand (m)',
                    'hoge_intensiteit_afstand': 'HSR Afstand (m)',
                    'sessie_type': 'Type Sessie'
                }
            )
            
            st.plotly_chart(fig_scatter, use_container_width=True)
            
            # Volume en intensiteit trends
            col1, col2 = st.columns(2)
            
            with col1:
                # Volume trend
                fig_volume = px.line(
                    speler_data.sort_values('datum'),
                    x='datum',
                    y='totale_afstand',
                    color='sessie_type',
                    title="📈 Volume Evolutie",
                    labels={'totale_afstand': 'Totale Afstand (m)'}
                )
                st.plotly_chart(fig_volume, use_container_width=True)
            
            with col2:
                # Intensiteit trend
                fig_intensity = px.line(
                    speler_data.sort_values('datum'),
                    x='datum',
                    y='hoge_intensiteit_afstand',
                    color='sessie_type', 
                    title="🚀 Intensiteit Evolutie",
                    labels={'hoge_intensiteit_afstand': 'HSR Afstand (m)'}
                )
                st.plotly_chart(fig_intensity, use_container_width=True)
        
        with tab4:
            st.markdown("### 🎯 Evolutie & Trends Analyse")
            
            # Bereken rolling averages
            speler_data_sorted = speler_data.sort_values('datum').copy()
            
            # 7-dagen rolling average
            speler_data_sorted['totale_afstand_7d'] = speler_data_sorted['totale_afstand'].rolling(window=7, min_periods=1).mean()
            speler_data_sorted['hsr_7d'] = speler_data_sorted['hoge_intensiteit_afstand'].rolling(window=7, min_periods=1).mean()
            speler_data_sorted['load_7d'] = speler_data_sorted['player_load'].rolling(window=7, min_periods=1).mean()
            
            # Multi-metric evolutie
            fig_evolution = make_subplots(
                rows=3, cols=1,
                subplot_titles=('Totale Afstand Trend', 'HSR Trend', 'Player Load Trend'),
                vertical_spacing=0.1
            )
            
            # Totale afstand
            fig_evolution.add_trace(
                go.Scatter(
                    x=speler_data_sorted['datum'],
                    y=speler_data_sorted['totale_afstand'],
                    mode='markers',
                    name='Werkelijke waarden',
                    opacity=0.6,
                    marker=dict(color='lightblue')
                ),
                row=1, col=1
            )
            
            fig_evolution.add_trace(
                go.Scatter(
                    x=speler_data_sorted['datum'],
                    y=speler_data_sorted['totale_afstand_7d'],
                    mode='lines',
                    name='7-dagen gemiddelde',
                    line=dict(color='blue', width=2)
                ),
                row=1, col=1
            )
            
            # HSR 
            fig_evolution.add_trace(
                go.Scatter(
                    x=speler_data_sorted['datum'],
                    y=speler_data_sorted['hoge_intensiteit_afstand'],
                    mode='markers',
                    name='HSR waarden',
                    opacity=0.6,
                    marker=dict(color='orange'),
                    showlegend=False
                ),
                row=2, col=1
            )
            
            fig_evolution.add_trace(
                go.Scatter(
                    x=speler_data_sorted['datum'],
                    y=speler_data_sorted['hsr_7d'],
                    mode='lines',
                    name='HSR 7d gem.',
                    line=dict(color='red', width=2),
                    showlegend=False
                ),
                row=2, col=1
            )
            
            # Player Load
            fig_evolution.add_trace(
                go.Scatter(
                    x=speler_data_sorted['datum'],
                    y=speler_data_sorted['player_load'],
                    mode='markers',
                    name='Load waarden',
                    opacity=0.6,
                    marker=dict(color='lightgreen'),
                    showlegend=False
                ),
                row=3, col=1
            )
            
            fig_evolution.add_trace(
                go.Scatter(
                    x=speler_data_sorted['datum'],
                    y=speler_data_sorted['load_7d'],
                    mode='lines',
                    name='Load 7d gem.',
                    line=dict(color='green', width=2),
                    showlegend=False
                ),
                row=3, col=1
            )
            
            fig_evolution.update_layout(
                height=800,
                title_text="Trainingsbelasting Evolutie met Trends",
                showlegend=True
            )
            
            fig_evolution.update_xaxes(title_text="Datum", row=3, col=1)
            fig_evolution.update_yaxes(title_text="Afstand (m)", row=1, col=1)
            fig_evolution.update_yaxes(title_text="HSR (m)", row=2, col=1)  
            fig_evolution.update_yaxes(title_text="Player Load", row=3, col=1)
            
            st.plotly_chart(fig_evolution, use_container_width=True)
        
        with tab5:
            st.markdown("### 🏆 Wedstrijdprestaties Overzicht")
            
            # Filter alleen wedstrijddata
            wedstrijd_data = speler_data[speler_data['sessie_type'] == 'Wedstrijd'].copy()
            
            if not wedstrijd_data.empty:
                st.markdown(f"**{len(wedstrijd_data)} wedstrijden gevonden voor {selected_speler}**")
                
                # Individuele wedstrijdprestaties
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.markdown("#### 📋 Individuele Wedstrijdprestaties")
                    
                    # Tabel met wedstrijdresultaten
                    wedstrijd_summary = wedstrijd_data[['datum', 'totale_afstand', 'hoge_intensiteit_afstand', 
                                                      'sprint_afstand', 'aantal_sprints', 'max_snelheid', 'player_load']].copy()
                    wedstrijd_summary['datum'] = pd.to_datetime(wedstrijd_summary['datum']).dt.strftime('%d-%m-%Y')
                    wedstrijd_summary['totale_afstand'] = wedstrijd_summary['totale_afstand'].round(0)
                    wedstrijd_summary['hoge_intensiteit_afstand'] = wedstrijd_summary['hoge_intensiteit_afstand'].round(0)
                    wedstrijd_summary['sprint_afstand'] = wedstrijd_summary['sprint_afstand'].round(0)
                    wedstrijd_summary['max_snelheid'] = wedstrijd_summary['max_snelheid'].round(1)
                    wedstrijd_summary['player_load'] = wedstrijd_summary['player_load'].round(1)
                    
                    # Hernoem kolommen voor duidelijkheid
                    wedstrijd_summary.columns = ['Datum', 'Totale Afstand (m)', 'HSR Afstand (m)', 
                                               'Sprint Afstand (m)', 'Aantal Sprints', 'Max Snelheid (km/h)', 'Player Load']
                    
                    st.dataframe(wedstrijd_summary.sort_values('Datum', ascending=False), use_container_width=True)
                
                with col2:
                    st.markdown("#### 📊 Gemiddelde Prestaties")
                    
                    # Bereken gemiddelden
                    avg_stats = {
                        'Totale Afstand': f"{wedstrijd_data['totale_afstand'].mean():.0f} m",
                        'HSR Afstand': f"{wedstrijd_data['hoge_intensiteit_afstand'].mean():.0f} m",
                        'Sprint Afstand': f"{wedstrijd_data['sprint_afstand'].mean():.0f} m",
                        'Aantal Sprints': f"{wedstrijd_data['aantal_sprints'].mean():.1f}",
                        'Max Snelheid': f"{wedstrijd_data['max_snelheid'].mean():.1f} km/h",
                        'Player Load': f"{wedstrijd_data['player_load'].mean():.1f}"
                    }
                    
                    for metric, value in avg_stats.items():
                        st.metric(metric, value)
                
                # Prestatie vergelijkingen
                st.markdown("#### 🎯 Prestatie Analyse")
                
                # Vergelijking met team gemiddelden (als beschikbaar)
                team_wedstrijd_data = safe_fetchdf("""
                    SELECT g.*, t.type
                    FROM gps_data g
                    JOIN trainings_calendar t ON g.training_id = t.training_id
                    WHERE t.type IN ('Wedstrijd', 'Vriendschappelijk')
                    AND g.datum >= ? AND g.datum <= ?
                """, [start_datum.strftime('%Y-%m-%d'), eind_datum.strftime('%Y-%m-%d')])
                
                if not team_wedstrijd_data.empty:
                    # Bereken team gemiddelden
                    team_avg = {
                        'totale_afstand': team_wedstrijd_data['totale_afstand'].mean(),
                        'hoge_intensiteit_afstand': team_wedstrijd_data['hoge_intensiteit_afstand'].mean(),
                        'sprint_afstand': team_wedstrijd_data['sprint_afstand'].mean(),
                        'player_load': team_wedstrijd_data['player_load'].mean()
                    }
                    
                    # Individuele gemiddelden
                    player_avg = {
                        'totale_afstand': wedstrijd_data['totale_afstand'].mean(),
                        'hoge_intensiteit_afstand': wedstrijd_data['hoge_intensiteit_afstand'].mean(),
                        'sprint_afstand': wedstrijd_data['sprint_afstand'].mean(),
                        'player_load': wedstrijd_data['player_load'].mean()
                    }
                    
                    # Vergelijking visualisatie
                    comparison_data = []
                    metrics = [
                        ('totale_afstand', 'Totale Afstand (m)'),
                        ('hoge_intensiteit_afstand', 'HSR Afstand (m)'),
                        ('sprint_afstand', 'Sprint Afstand (m)'),
                        ('player_load', 'Player Load')
                    ]
                    
                    for metric_key, metric_label in metrics:
                        comparison_data.extend([
                            {'Metric': metric_label, 'Type': selected_speler, 'Waarde': player_avg[metric_key]},
                            {'Metric': metric_label, 'Type': 'Team Gemiddelde', 'Waarde': team_avg[metric_key]}
                        ])
                    
                    comparison_df = pd.DataFrame(comparison_data)
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # Grouped bar chart
                        fig_comparison = px.bar(
                            comparison_df,
                            x='Metric',
                            y='Waarde',
                            color='Type',
                            title=f"📊 {selected_speler} vs Team Gemiddelde (Wedstrijden)",
                            barmode='group'
                        )
                        fig_comparison.update_layout(xaxis_tickangle=45, height=400)
                        st.plotly_chart(fig_comparison, use_container_width=True)
                    
                    with col2:
                        # Performance percentages
                        st.markdown("##### 🎯 Relatieve Prestatie")
                        for metric_key, metric_label in metrics:
                            player_val = player_avg[metric_key]
                            team_val = team_avg[metric_key]
                            
                            if team_val > 0:
                                percentage = ((player_val / team_val) - 1) * 100
                                
                                if percentage > 10:
                                    icon = "🟢"
                                    status = "Bovengemiddeld"
                                elif percentage > -10:
                                    icon = "🟡"
                                    status = "Gemiddeld"
                                else:
                                    icon = "🔴"
                                    status = "Ondergemiddeld"
                                
                                st.metric(
                                    f"{icon} {metric_label}",
                                    f"{percentage:+.1f}%",
                                    help=f"{status} ten opzichte van team"
                                )
                
                # Wedstrijd trends
                if len(wedstrijd_data) > 1:
                    st.markdown("#### 📈 Wedstrijd Trends")
                    
                    # Multi-metric wedstrijd evolutie
                    fig_match_trends = make_subplots(
                        rows=2, cols=2,
                        subplot_titles=('Totale Afstand', 'HSR Afstand', 'Sprint Afstand', 'Player Load'),
                        vertical_spacing=0.15,
                        horizontal_spacing=0.1
                    )
                    
                    wedstrijd_sorted = wedstrijd_data.sort_values('datum')
                    
                    # Totale Afstand
                    fig_match_trends.add_trace(
                        go.Scatter(
                            x=wedstrijd_sorted['datum'],
                            y=wedstrijd_sorted['totale_afstand'],
                            mode='lines+markers',
                            name='Totale Afstand',
                            line=dict(color='blue')
                        ),
                        row=1, col=1
                    )
                    
                    # HSR Afstand
                    fig_match_trends.add_trace(
                        go.Scatter(
                            x=wedstrijd_sorted['datum'],
                            y=wedstrijd_sorted['hoge_intensiteit_afstand'],
                            mode='lines+markers',
                            name='HSR Afstand',
                            line=dict(color='orange'),
                            showlegend=False
                        ),
                        row=1, col=2
                    )
                    
                    # Sprint Afstand
                    fig_match_trends.add_trace(
                        go.Scatter(
                            x=wedstrijd_sorted['datum'],
                            y=wedstrijd_sorted['sprint_afstand'],
                            mode='lines+markers',
                            name='Sprint Afstand',
                            line=dict(color='red'),
                            showlegend=False
                        ),
                        row=2, col=1
                    )
                    
                    # Player Load
                    fig_match_trends.add_trace(
                        go.Scatter(
                            x=wedstrijd_sorted['datum'],
                            y=wedstrijd_sorted['player_load'],
                            mode='lines+markers',
                            name='Player Load',
                            line=dict(color='green'),
                            showlegend=False
                        ),
                        row=2, col=2
                    )
                    
                    fig_match_trends.update_layout(
                        height=600,
                        title_text=f"Wedstrijdprestatie Evolutie - {selected_speler}",
                        showlegend=False
                    )
                    
                    st.plotly_chart(fig_match_trends, use_container_width=True)
                
                # Conclusies en aanbevelingen
                st.markdown("#### 💡 Wedstrijdprestatie Insights")
                
                if len(wedstrijd_data) >= 1:
                    # Bereken insights
                    laatste_wedstrijd = wedstrijd_data.iloc[-1]
                    insights = []
                    
                    # Prestatie benchmarks (gemiddelde professionele voetbal waarden)
                    benchmarks = {
                        'totale_afstand': 10000,  # 10km gemiddeld
                        'hoge_intensiteit_afstand': 1200,  # 1.2km HSR
                        'sprint_afstand': 350,  # 350m sprint
                        'player_load': 600,  # 600 player load
                        'max_snelheid': 30  # 30 km/h max snelheid
                    }
                    
                    # Totale afstand analyse
                    if laatste_wedstrijd['totale_afstand'] > benchmarks['totale_afstand'] * 1.1:
                        insights.append("🟢 **Totale Afstand**: Uitstekende afstand gelopen - zeer goede uithouding")
                    elif laatste_wedstrijd['totale_afstand'] > benchmarks['totale_afstand']:
                        insights.append("🟢 **Totale Afstand**: Goede afstand prestatie - boven gemiddelde")
                    elif laatste_wedstrijd['totale_afstand'] < benchmarks['totale_afstand'] * 0.8:
                        insights.append("🔴 **Totale Afstand**: Lage afstand - mogelijk vermoeidheid of tactische rol")
                    else:
                        insights.append("🟡 **Totale Afstand**: Gemiddelde prestatie")
                    
                    # HSR analyse
                    if laatste_wedstrijd['hoge_intensiteit_afstand'] > benchmarks['hoge_intensiteit_afstand'] * 1.1:
                        insights.append("🟢 **HSR Intensiteit**: Uitstekende hoge snelheidsafstand - explosieve prestatie")
                    elif laatste_wedstrijd['hoge_intensiteit_afstand'] > benchmarks['hoge_intensiteit_afstand']:
                        insights.append("🟢 **HSR Intensiteit**: Goede intensiteit - boven gemiddelde")
                    elif laatste_wedstrijd['hoge_intensiteit_afstand'] < benchmarks['hoge_intensiteit_afstand'] * 0.7:
                        insights.append("🔴 **HSR Intensiteit**: Lage intensiteit - meer explosief werk nodig")
                    else:
                        insights.append("🟡 **HSR Intensiteit**: Gemiddelde intensiteit prestatie")
                    
                    # Sprint analyse
                    if laatste_wedstrijd['sprint_afstand'] > benchmarks['sprint_afstand'] * 1.2:
                        insights.append("🟢 **Sprint Prestatie**: Uitstekende sprint afstand - zeer explosief")
                    elif laatste_wedstrijd['sprint_afstand'] < benchmarks['sprint_afstand'] * 0.6:
                        insights.append("🔴 **Sprint Prestatie**: Lage sprint afstand - sprint training aanbevolen")
                    else:
                        insights.append("🟡 **Sprint Prestatie**: Redelijke sprint prestatie")
                    
                    # Player load analyse
                    if laatste_wedstrijd['player_load'] > benchmarks['player_load'] * 1.2:
                        insights.append("🟡 **Belasting**: Zeer hoge player load - extra herstel nodig")
                    elif laatste_wedstrijd['player_load'] > benchmarks['player_load']:
                        insights.append("🟢 **Belasting**: Goede werklast - sterke fysieke inzet")
                    elif laatste_wedstrijd['player_load'] < benchmarks['player_load'] * 0.7:
                        insights.append("🔵 **Belasting**: Lage werklast - mogelijk meer intensiteit mogelijk")
                    else:
                        insights.append("🟡 **Belasting**: Gemiddelde werklast")
                    
                    # Max snelheid analyse
                    if laatste_wedstrijd['max_snelheid'] > benchmarks['max_snelheid']:
                        insights.append("🟢 **Max Snelheid**: Hoge topsnelheid bereikt - uitstekende sprints")
                    elif laatste_wedstrijd['max_snelheid'] < benchmarks['max_snelheid'] * 0.85:
                        insights.append("🟡 **Max Snelheid**: Lagere topsnelheid - sprint training overwegen")
                    
                    # Multi-wedstrijd analyses (alleen als er meerdere wedstrijden zijn)
                    if len(wedstrijd_data) >= 2:
                        gem_prestatie = wedstrijd_data.mean()
                        
                        # Trend analyse laatste wedstrijd
                        if len(wedstrijd_data) >= 2:
                            vorige_wedstrijd = wedstrijd_data.iloc[-2]
                            
                            # Afstand trend
                            distance_change = ((laatste_wedstrijd['totale_afstand'] - vorige_wedstrijd['totale_afstand']) / vorige_wedstrijd['totale_afstand']) * 100
                            if distance_change > 10:
                                insights.append("📈 **Trend**: Sterke verbetering in afstand (+{:.1f}%)".format(distance_change))
                            elif distance_change < -10:
                                insights.append("📉 **Trend**: Afname in afstand ({:.1f}%) - monitor vermoeidheid".format(distance_change))
                        
                        # Consistentie analyse
                        cv_distance = (wedstrijd_data['totale_afstand'].std() / wedstrijd_data['totale_afstand'].mean()) * 100
                        if cv_distance < 8:
                            insights.append("🟢 **Consistentie**: Zeer consistente afstand prestaties")
                        elif cv_distance > 15:
                            insights.append("🟡 **Consistentie**: Variabele prestaties - onderzoek oorzaken")
                    
                    # Toon alle insights
                    for insight in insights:
                        st.markdown(insight)
                        
                else:
                    st.info("Geen wedstrijddata beschikbaar voor insights.")
                
            else:
                st.info("Geen wedstrijddata gevonden voor de geselecteerde speler in deze periode.")
                st.markdown("""
                **Tips:**
                - Controleer of de speler wedstrijden heeft gespeeld in de geselecteerde periode
                - Zorg dat wedstrijden correct gelabeld zijn als 'Wedstrijd' of 'Vriendschappelijk' in de training calendar
                - Vergroot eventueel de datumreeks
                """)
    
    except Exception as e:
        st.error(f"Fout bij laden van data: {e}")
        st.write("Debug info:", str(e))

else:
    st.info("Selecteer een speler om de analyse te starten")

# Footer
st.markdown("---")
st.markdown("""
**📋 Gebruiksaanwijzing:**
- **Wekelijkse Belasting**: Monitor volume en intensiteit per week
- **Wedstrijdvoorbereiding**: Vergelijk trainingsweek met wedstrijdvereisten  
- **Volume vs Intensiteit**: Analyseer balans tussen volume en intensiteit
- **Evolutie & Trends**: Bekijk langetermijn ontwikkeling en krijg aanbevelingen

**⚠️ Belangrijk**: Zorg voor consistente data invoer voor accurate analyses
""")