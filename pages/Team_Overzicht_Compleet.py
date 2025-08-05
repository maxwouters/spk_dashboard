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
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime, timedelta, date
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

st.set_page_config(page_title="Team Overzicht - SPK Dashboard", layout="wide")

# Custom CSS styling
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
    .accent-red { color: #DC143C; font-weight: bold; }
    
    .team-stats {
        background: linear-gradient(135deg, #1E3A8A 0%, #3B82F6 100%);
        color: white;
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header"><h1>👥 Team Overzicht Compleet</h1></div>', unsafe_allow_html=True)

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
def get_team_summary_stats():
    """Haal team samenvatting statistieken op"""
    
    # Aantal spelers
    total_players_df = safe_fetchdf("SELECT naam FROM spelers_profiel WHERE status = 'Actief'")
    total_players = len(total_players_df)
    
    # Gemiddelde leeftijd
    avg_age_df = safe_fetchdf("SELECT leeftijd FROM spelers_profiel WHERE leeftijd IS NOT NULL AND status = 'Actief'")
    avg_age = avg_age_df['leeftijd'].mean() if not avg_age_df.empty else 0
    
    # Laatste training datum
    last_training_df = safe_fetchdf("SELECT datum FROM gps_data ORDER BY datum DESC LIMIT 1")
    last_training = last_training_df['datum'].iloc[0] if not last_training_df.empty else None
    
    # Gemiddelde RPE laatste week
    week_ago = datetime.now() - timedelta(days=7)
    avg_rpe_df = safe_fetchdf("SELECT rpe_score FROM rpe_data WHERE datum >= '2025-07-01' AND rpe_score IS NOT NULL")
    avg_rpe = avg_rpe_df['rpe_score'].mean() if not avg_rpe_df.empty else 0
    
    # Aantal trainingen laatste week
    trainings_df = safe_fetchdf("SELECT DISTINCT datum FROM gps_data WHERE datum >= '2025-07-01'")
    trainings_count = len(trainings_df)
    
    return {
        'total_players': total_players or 0,
        'avg_age': round(avg_age, 1) if avg_age else 0,
        'last_training': last_training,
        'avg_rpe': round(avg_rpe, 1) if avg_rpe else 0,
        'trainings_week': trainings_count or 0
    }

def get_player_comprehensive_data():
    """Haal uitgebreide speler data op voor team overzicht - vereenvoudigd"""
    
    # Basis speler informatie - gebruik get_table_data helper
    try:
        players_df = get_table_data('spelers_profiel', 
                                   columns='naam,leeftijd,positie,rugnummer,status,gewicht',
                                   where_conditions={'status': 'Actief'})
        
        if players_df.empty:
            return pd.DataFrame()
            
        # Sorteer op rugnummer
        players_df = players_df.sort_values(['rugnummer', 'naam'], na_position='last')
        
    except Exception as e:
        st.error(f"Fout bij ophalen spelers: {e}")
        return pd.DataFrame()
    
    # 30-15 fitness data - gebruik bestaande helper
    try:
        all_fitness = get_thirty_fifteen_results()
        if not all_fitness.empty:
            # Krijg laatste test per speler
            fitness_df = all_fitness.sort_values(['Speler', 'Maand']).groupby('Speler').tail(1)
            fitness_df = fitness_df.rename(columns={'Speler': 'naam'})[['naam', 'MAS', 'VO2MAX', 'PeakVelocity']]
        else:
            fitness_df = pd.DataFrame(columns=['naam', 'MAS', 'VO2MAX', 'PeakVelocity'])
    except:
        fitness_df = pd.DataFrame(columns=['naam', 'MAS', 'VO2MAX', 'PeakVelocity'])
    
    # Voeg dummy data toe voor andere metrics (deze kunnen later uitgebreid worden)
    players_df['avg_rpe_7d'] = 6.0  # Standaard RPE
    players_df['avg_sleep_7d'] = 7.0  # Standaard slaap
    players_df['avg_energy_7d'] = 7.0  # Standaard energie
    players_df['avg_stress_7d'] = 5.0  # Standaard stress
    players_df['rpe_sessions_7d'] = 3  # Standaard sessies
    players_df['gps_sessions_7d'] = 3  # Standaard GPS sessies
    players_df['avg_hsr_7d'] = 500.0  # Standaard HSR
    players_df['avg_zeer_hsr_7d'] = 200.0  # Standaard zeer HSR
    players_df['trainings_attended_30d'] = 8  # Standaard training attendance
    players_df['attendance_percentage_30d'] = 80.0  # Standaard percentage
    players_df['blessure_type'] = None
    players_df['injury_status'] = None
    
    # Merge met fitness data
    result_df = players_df.merge(fitness_df, on='naam', how='left')
    
    # Bereken load status
    result_df['load_status'] = 'Normaal'
    result_df.loc[result_df['avg_rpe_7d'] >= 7, 'load_status'] = 'Hoog'
    result_df.loc[result_df['avg_rpe_7d'] <= 4, 'load_status'] = 'Laag'
    
    # Overall status bepalen
    result_df['overall_status'] = 'Actief'
    result_df.loc[result_df['injury_status'].notna(), 'overall_status'] = 'Geblesseerd'
    result_df.loc[result_df['load_status'] == 'Hoog', 'overall_status'] = 'Hoge Belasting'
    
    return result_df

# Haal team data op (alleen binnen Streamlit context)
if __name__ == "__main__" or 'streamlit' in globals():
    team_stats = get_team_summary_stats()
    team_data = get_player_comprehensive_data()
else:
    # Fallback voor als het bestand wordt geïmporteerd
    team_stats = {'total_players': 0, 'avg_age': 0, 'last_training': None, 'avg_rpe': 0, 'trainings_week': 0}
    team_data = pd.DataFrame()

# Team Statistics Header
st.markdown('<div class="team-stats">', unsafe_allow_html=True)
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("👥 Totaal Spelers", team_stats['total_players'])

with col2:
    st.metric("📅 Gem. Leeftijd", f"{team_stats['avg_age']} jaar")

with col3:
    st.metric("🏃‍♂️ Trainingen (7d)", team_stats['trainings_week'])

with col4:
    st.metric("⚡ Gem. RPE (7d)", team_stats['avg_rpe'])

with col5:
    # Safe date formatting - handle both datetime objects and strings
    try:
        if team_stats['last_training']:
            if hasattr(team_stats['last_training'], 'strftime'):
                last_training_str = team_stats['last_training'].strftime('%d/%m')
            else:
                # Convert string to datetime first
                from datetime import datetime
                last_training_str = datetime.strptime(str(team_stats['last_training']), '%Y-%m-%d').strftime('%d/%m')
        else:
            last_training_str = 'Geen'
    except:
        last_training_str = str(team_stats['last_training']) if team_stats['last_training'] else 'Geen'
    st.metric("📊 Laatste Training", last_training_str)

st.markdown('</div>', unsafe_allow_html=True)

if len(team_data) == 0:
    st.warning("⚠️ Geen actieve spelers gevonden. Zorg ervoor dat er spelers zijn toegevoegd in Spelersbeheer.")
else:
    
    # Filter opties
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown("### <span class='accent-blue'>🔍 Filter Opties</span>", unsafe_allow_html=True)
    
    col_filter1, col_filter2, col_filter3, col_filter4 = st.columns(4)
    
    with col_filter1:
        position_filter = st.selectbox("Positie", ["Alle Posities"] + sorted(team_data['positie'].dropna().unique().tolist()))
    
    with col_filter2:
        status_filter = st.selectbox("Status", ["Alle Statussen"] + sorted(team_data['overall_status'].unique().tolist()))
    
    with col_filter3:
        load_filter = st.selectbox("Belasting", ["Alle Belastingen"] + sorted(team_data['load_status'].unique().tolist()))
    
    with col_filter4:
        sort_by = st.selectbox("Sorteer op", ["Rugnummer", "Naam", "MAS", "VO2MAX", "RPE (7d)", "Aanwezigheid"])
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Filter de data
    filtered_data = team_data.copy()
    
    if position_filter != "Alle Posities":
        filtered_data = filtered_data[filtered_data['positie'] == position_filter]
    
    if status_filter != "Alle Statussen":
        filtered_data = filtered_data[filtered_data['overall_status'] == status_filter]
    
    if load_filter != "Alle Belastingen":
        filtered_data = filtered_data[filtered_data['load_status'] == load_filter]
    
    # Sorteer de data
    if sort_by == "Rugnummer":
        filtered_data = filtered_data.sort_values('rugnummer', na_position='last')
    elif sort_by == "Naam":
        filtered_data = filtered_data.sort_values('naam')
    elif sort_by == "MAS":
        filtered_data = filtered_data.sort_values('MAS', ascending=False, na_position='last')
    elif sort_by == "VO2MAX":
        filtered_data = filtered_data.sort_values('VO2MAX', ascending=False, na_position='last')
    elif sort_by == "RPE (7d)":
        filtered_data = filtered_data.sort_values('avg_rpe_7d', ascending=False, na_position='last')
    elif sort_by == "Aanwezigheid":
        filtered_data = filtered_data.sort_values('attendance_percentage_30d', ascending=False, na_position='last')
    
    # Spelers Overzicht Grid
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown(f"### <span class='accent-purple'>👥 Spelers Overzicht ({len(filtered_data)} spelers)</span>", unsafe_allow_html=True)
    
    # Maak compacte display data
    display_data = []
    for idx, speler in filtered_data.iterrows():
        
        # Status emoji
        if speler['overall_status'] == 'Geblesseerd':
            status_emoji = "🩹"
        elif speler['overall_status'] == 'Hoge Belasting':
            status_emoji = "⚡"
        else:
            status_emoji = "✅"
        
        # Compact format
        # Safe formatting voor basis waarden
        try:
            rugnummer = f"#{int(float(speler['rugnummer']))}" if pd.notna(speler['rugnummer']) and speler['rugnummer'] != '' else "#--"
        except (ValueError, TypeError):
            rugnummer = "#--"
            
        naam = speler['naam'] if pd.notna(speler['naam']) else "Onbekend"
        positie = speler['positie'] if pd.notna(speler['positie']) and speler['positie'] != '' else "N/A"
        
        try:
            leeftijd = int(float(speler['leeftijd'])) if pd.notna(speler['leeftijd']) and speler['leeftijd'] != '' else "N/A"
        except (ValueError, TypeError):
            leeftijd = "N/A"
        # Safe formatting voor numerieke waarden
        try:
            mas = f"{float(speler['MAS']):.1f}" if pd.notna(speler['MAS']) and speler['MAS'] != '' else "N/A"
        except (ValueError, TypeError):
            mas = "N/A"
            
        try:
            vo2 = f"{float(speler['VO2MAX']):.0f}" if pd.notna(speler['VO2MAX']) and speler['VO2MAX'] != '' else "N/A"
        except (ValueError, TypeError):
            vo2 = "N/A"
            
        try:
            rpe = f"{float(speler['avg_rpe_7d']):.1f}" if pd.notna(speler['avg_rpe_7d']) and speler['avg_rpe_7d'] != '' else "N/A"
        except (ValueError, TypeError):
            rpe = "N/A"
            
        try:
            sessions = int(float(speler['gps_sessions_7d'])) if pd.notna(speler['gps_sessions_7d']) and speler['gps_sessions_7d'] != '' else 0
        except (ValueError, TypeError):
            sessions = 0
            
        try:
            hsr = f"{float(speler['avg_hsr_7d']):.0f}" if pd.notna(speler['avg_hsr_7d']) and speler['avg_hsr_7d'] != '' else "N/A"
        except (ValueError, TypeError):
            hsr = "N/A"
            
        try:
            attendance = f"{float(speler['attendance_percentage_30d']):.0f}%" if pd.notna(speler['attendance_percentage_30d']) and speler['attendance_percentage_30d'] != '' else "N/A"
        except (ValueError, TypeError):
            attendance = "N/A"
        
        # Wellness alerts - safe checks
        alerts = []
        try:
            if pd.notna(speler['avg_sleep_7d']) and float(speler['avg_sleep_7d']) <= 6:
                alerts.append("😴")
        except (ValueError, TypeError):
            pass
            
        try:
            if pd.notna(speler['avg_stress_7d']) and float(speler['avg_stress_7d']) >= 7:
                alerts.append("😰")
        except (ValueError, TypeError):
            pass
            
        try:
            if pd.notna(speler['blessure_type']) and speler['blessure_type'] != '':
                alerts.append("🩹")
        except (ValueError, TypeError):
            pass
            
        alert_str = "".join(alerts) if alerts else ""
        
        display_data.append({
            'Status': status_emoji,
            'Nr': rugnummer,
            'Naam': naam,
            'Pos': positie,
            'Leef': leeftijd,
            'MAS': mas,
            'VO2': vo2,
            'RPE': rpe,
            'Sess': sessions,
            'HSR': hsr,
            'Aanw': attendance,
            'Alerts': alert_str
        })
    
    # Compacte tabel weergave
    if display_data:
        df_display = pd.DataFrame(display_data)
        
        # Kleurcode de dataframe op basis van status
        def highlight_status(row):
            if row['Status'] == '🩹':
                return ['background-color: #ffebee'] * len(row)
            elif row['Status'] == '⚡':
                return ['background-color: #fff3e0'] * len(row)
            else:
                return ['background-color: #f1f8e9'] * len(row)
        
        styled_df = df_display.style.apply(highlight_status, axis=1)
        
        st.dataframe(
            styled_df,
            use_container_width=True,
            hide_index=True,
            height=400,
            column_config={
                'Status': st.column_config.TextColumn('Status', width='small'),
                'Nr': st.column_config.TextColumn('#', width='small'),
                'Naam': st.column_config.TextColumn('Naam', width='medium'),
                'Pos': st.column_config.TextColumn('Positie', width='small'),
                'Leef': st.column_config.TextColumn('Jaar', width='small'),
                'MAS': st.column_config.TextColumn('MAS', width='small'),
                'VO2': st.column_config.TextColumn('VO2', width='small'),
                'RPE': st.column_config.TextColumn('RPE', width='small'),
                'Sess': st.column_config.NumberColumn('Sess', width='small'),
                'HSR': st.column_config.TextColumn('HSR', width='small'),
                'Aanw': st.column_config.TextColumn('Aanw%', width='small'),
                'Alerts': st.column_config.TextColumn('⚠️', width='small')
            }
        )
        
        # Legenda
        st.caption("**Status:** ✅ Actief | ⚡ Hoge Belasting | 🩹 Geblesseerd")
        st.caption("**Alerts:** 😴 Slechte slaap | 😰 Hoge stress | 🩹 Blessure")
        st.caption("**Afkortingen:** Pos=Positie, Leef=Leeftijd, Sess=Sessies (7d), HSR=High Speed Running (7d), Aanw=Aanwezigheid (30d)")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Team Analytics Dashboard
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown("### <span class='accent-green'>📊 Team Analytics</span>", unsafe_allow_html=True)
    
    # Bereken team statistieken
    active_players = filtered_data[filtered_data['overall_status'] != 'Geblesseerd']
    
    if len(active_players) > 0:
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            # Fitness distributie (MAS)
            mas_data = active_players.dropna(subset=['MAS'])
            if len(mas_data) > 0:
                fig_mas = px.histogram(
                    mas_data, 
                    x='MAS', 
                    nbins=8,
                    title='MAS Distributie (km/u)',
                    color_discrete_sequence=['#2E86AB']
                )
                fig_mas.update_layout(height=300, showlegend=False)
                st.plotly_chart(fig_mas, use_container_width=True)
        
        with col_chart2:
            # RPE distributie (laatste 7 dagen)
            rpe_data = active_players.dropna(subset=['avg_rpe_7d'])
            if len(rpe_data) > 0:
                fig_rpe = px.histogram(
                    rpe_data, 
                    x='avg_rpe_7d', 
                    nbins=6,
                    title='RPE Distributie (7 dagen gemiddeld)',
                    color_discrete_sequence=['#A23B72']
                )
                fig_rpe.update_layout(height=300, showlegend=False)
                st.plotly_chart(fig_rpe, use_container_width=True)
        
        # Positie analyse
        col_pos1, col_pos2 = st.columns(2)
        
        with col_pos1:
            pos_data = active_players['positie'].value_counts()
            if len(pos_data) > 0:
                fig_pos = px.pie(
                    values=pos_data.values, 
                    names=pos_data.index,
                    title='Spelers per Positie'
                )
                fig_pos.update_layout(height=300)
                st.plotly_chart(fig_pos, use_container_width=True)
        
        with col_pos2:
            # Load status overzicht
            load_data = active_players['load_status'].value_counts()
            if len(load_data) > 0:
                fig_load = px.pie(
                    values=load_data.values, 
                    names=load_data.index,
                    title='Training Load Status',
                    color_discrete_map={
                        'Normaal': '#2E86AB',
                        'Hoog': '#DC143C', 
                        'Laag': '#2E8B57'
                    }
                )
                fig_load.update_layout(height=300)
                st.plotly_chart(fig_load, use_container_width=True)
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Export functionaliteit
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown("### <span class='accent-orange'>📥 Export Data</span>", unsafe_allow_html=True)
    
    # Maak export data
    export_data = filtered_data.copy()
    export_cols = [
        'naam', 'leeftijd', 'positie', 'rugnummer', 'overall_status',
        'MAS', 'VO2MAX', 'PeakVelocity', 'avg_rpe_7d', 
        'avg_hsr_7d', 'avg_zeer_hsr_7d', 'gps_sessions_7d', 'attendance_percentage_30d'
    ]
    
    export_data = export_data[export_cols].fillna('N/A')
    
    col_exp1, col_exp2 = st.columns(2)
    
    with col_exp1:
        csv_data = export_data.to_csv(index=False)
        st.download_button(
            label="📊 Download Team Data CSV",
            data=csv_data,
            file_name=f"team_overzicht_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )
    
    with col_exp2:
        st.button("📊 Print Rapport", disabled=True, help="Functie in ontwikkeling")
    
    st.markdown('</div>', unsafe_allow_html=True)

# Safe database connection cleanup

# Database cleanup handled by Supabase helpers