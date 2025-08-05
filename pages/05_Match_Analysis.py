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
from datetime import datetime, date, timedelta, time
import plotly.express as px
import plotly.graph_objects as go

st.title("⚽ Match Analysis & Ratings")

# Database setup
if SUPABASE_MODE:
    st.info("🌐 Using Supabase database")
    if not test_supabase_connection():
        st.error("❌ Cannot connect to Supabase")
        st.stop()
else:
    # Legacy mode
    try:
        con = get_database_connection()
    except NameError:
        st.error("❌ Database connection not available")
        st.stop()

# Database helper functions
def get_matches(limit=20):
    """Get matches from database - now only uses matches table since trainings are auto-synced"""
    try:
        from supabase_config import get_supabase_client
        client = get_supabase_client()
        
        # Get matches from matches table only (includes auto-synced trainings)
        matches_result = client.table('matches').select('*').order('datum', desc=True).limit(limit).execute()
        matches_data = matches_result.data if matches_result.data else []
        
        # Add source column for consistency
        for match in matches_data:
            if match.get('training_calendar_id'):
                match['source'] = 'trainingskalender'
            else:
                match['source'] = 'matches'
        
        # Convert to DataFrame
        if matches_data:
            matches_df = pd.DataFrame(matches_data)
            # Convert datum to datetime
            matches_df['datum'] = pd.to_datetime(matches_df['datum'], errors='coerce')
            return matches_df.head(limit)
        else:
            return pd.DataFrame()
        
    except Exception as e:
        st.error(f"Error loading matches: {e}")
        return pd.DataFrame()

def get_match_events(match_id):
    """Get events for a specific match"""
    try:
        from supabase_config import get_supabase_client
        client = get_supabase_client()
        
        events_result = client.table('match_events').select('*').eq('match_id', match_id).order('minuut').execute()
        events_data = events_result.data if events_result.data else []
        
        return pd.DataFrame(events_data) if events_data else pd.DataFrame()
    except Exception as e:
        st.error(f"Error loading match events: {e}")
        return pd.DataFrame()

def get_match_ratings(match_id):
    """Get ratings for a specific match"""
    try:
        from supabase_config import get_supabase_client
        client = get_supabase_client()
        
        ratings_result = client.table('match_ratings').select('*').eq('match_id', match_id).execute()
        ratings_data = ratings_result.data if ratings_result.data else []
        
        return pd.DataFrame(ratings_data) if ratings_data else pd.DataFrame()
    except Exception as e:
        st.error(f"Error loading match ratings: {e}")
        return pd.DataFrame()

def get_available_players():
    """Get list of available players from spelers_profiel database"""
    try:
        # Use the proper supabase helpers function to get real players
        from supabase_helpers import get_cached_player_list
        players = get_cached_player_list()
        
        if players:
            return players
        
        # If supabase helpers fail, try direct Supabase query
        try:
            from supabase_config import get_supabase_client
            client = get_supabase_client()
            
            # Get active players from spelers_profiel
            result = client.table('spelers_profiel').select('naam').eq('status', 'Actief').execute()
            if result.data:
                return sorted([player['naam'] for player in result.data if player['naam']])
                
        except Exception as e:
            st.error(f"Database connection error: {e}")
        
        # Last fallback - warn user about missing data
        st.warning("⚠️ Geen spelers gevonden in database. Voeg eerst spelers toe in Spelersbeheer.")
        return []
            
    except Exception as e:
        st.error(f"Error loading players: {e}")
        return []

# Tabs for different functionality
tab1, tab2, tab3, tab4 = st.tabs([
    "⚽ Matches", 
    "📋 Pre-Match", 
    "📊 Match Data", 
    "📈 Analytics"
])

with tab1:
    st.header("⚽ Match Management")
    
    # Twee kolommen: match toevoegen en overzicht
    col1, col2 = st.columns([1, 2])
    
    with col1:
        # Mode selection: Add new or Edit existing
        mode = st.radio("Modus", ["➕ Nieuwe Match", "✏️ Match Bewerken"], horizontal=True)
        
        if mode == "➕ Nieuwe Match":
            st.subheader("➕ Nieuwe Match")
            with st.form("nieuwe_match"):
                # Set better default values - next weekend
                next_saturday = date.today() + timedelta(days=(5-date.today().weekday()) % 7)
                
                match_datum = st.date_input("📅 Datum", value=next_saturday, help="Kies de wedstrijddatum")
                match_tijd = st.time_input("⏰ Tijd", value=time(15, 0), help="Kies de aftrap tijd")
                tegenstander = st.text_input("🆚 Tegenstander", help="Naam van de tegenstander")
                thuis_uit = st.selectbox("🏠 Thuis/Uit", ["Thuis", "Uit"])
                competitie = st.text_input("🏆 Competitie", value="Hoofdklasse")
                seizoen = st.text_input("📅 Seizoen", value=f"{datetime.now().year}/{datetime.now().year+1}")
                match_type = st.selectbox("📝 Type", ["Competitie", "Vriendschappelijk", "Beker", "Play-off"])
                
                submit_match = st.form_submit_button("✅ Match Toevoegen", type="primary")
                
                if submit_match and tegenstander:
                    try:
                        from supabase_config import get_supabase_client
                        client = get_supabase_client()
                        
                        # Get next match ID
                        matches_result = client.table('matches').select('match_id').execute()
                        existing_ids = [m['match_id'] for m in matches_result.data] if matches_result.data else []
                        next_id = int(max(existing_ids)) + 1 if existing_ids else 100001
                        
                        # Insert match
                        result = client.table('matches').insert({
                            'match_id': next_id,
                            'datum': str(match_datum),
                            'tijd': str(match_tijd),
                            'tegenstander': tegenstander,
                            'thuis_uit': thuis_uit,
                            'competitie': competitie,
                            'seizoen': seizoen,
                            'match_type': match_type,
                            'status': 'Gepland'
                        }).execute()
                        
                        if result.data:
                            st.success(f"✅ Match tegen {tegenstander} op {match_datum} om {match_tijd} toegevoegd!")
                            st.rerun()
                        else:
                            st.error("❌ Fout bij toevoegen match")
                            
                    except Exception as e:
                        st.error(f"❌ Fout: {e}")
                elif submit_match and not tegenstander:
                    st.error("⚠️ Vul de tegenstander in!")
        
        else:  # Edit mode
            st.subheader("✏️ Match Bewerken")
            
            # Get matches for editing
            matches_df = get_matches(50)
            if not matches_df.empty:
                # Match selection
                match_options = []
                for idx, match in matches_df.iterrows():
                    datum_str = str(match['datum'])
                    match_options.append(f"{datum_str} - {match['tegenstander']} ({'Thuis' if match['thuis_uit'] == 'Thuis' else 'Uit'})")
                
                selected_idx = st.selectbox("🎯 Selecteer Match om te bewerken", range(len(match_options)), format_func=lambda x: match_options[x])
                selected_match = matches_df.iloc[selected_idx]
                
                # Edit form
                with st.form("bewerk_match"):
                    st.info(f"Bewerken: Match ID {selected_match['match_id']}")
                    
                    # Parse existing date and time
                    try:
                        existing_date = datetime.strptime(str(selected_match['datum']), '%Y-%m-%d').date()
                    except:
                        existing_date = date.today()
                    
                    try:
                        existing_time = datetime.strptime(str(selected_match.get('tijd', '15:00')), '%H:%M:%S').time()
                    except:
                        existing_time = time(15, 0)
                    
                    edit_datum = st.date_input("📅 Datum", value=existing_date)
                    edit_tijd = st.time_input("⏰ Tijd", value=existing_time)
                    edit_tegenstander = st.text_input("🆚 Tegenstander", value=selected_match['tegenstander'])
                    edit_thuis_uit = st.selectbox("🏠 Thuis/Uit", ["Thuis", "Uit"], index=0 if selected_match['thuis_uit'] == 'Thuis' else 1)
                    edit_competitie = st.text_input("🏆 Competitie", value=selected_match.get('competitie', ''))
                    edit_seizoen = st.text_input("📅 Seizoen", value=selected_match.get('seizoen', ''))
                    edit_match_type = st.selectbox("📝 Type", ["Competitie", "Vriendschappelijk", "Beker", "Play-off"], 
                                                   index=["Competitie", "Vriendschappelijk", "Beker", "Play-off"].index(selected_match.get('match_type', 'Competitie')))
                    edit_status = st.selectbox("📊 Status", ["Gepland", "Gespeeld", "Geannuleerd"], 
                                               index=["Gepland", "Gespeeld", "Geannuleerd"].index(selected_match.get('status', 'Gepland')))
                    
                    # Goals (only if played)
                    if edit_status == "Gespeeld":
                        col_goals1, col_goals2 = st.columns(2)
                        with col_goals1:
                            # Ensure integer values for number_input
                            current_goals_for = int(selected_match.get('doelpunten_voor', 0)) if selected_match.get('doelpunten_voor') is not None else 0
                            edit_goals_for = st.number_input("🏆 Doelpunten Voor", min_value=0, max_value=20, 
                                                             value=current_goals_for)
                        with col_goals2:
                            current_goals_against = int(selected_match.get('doelpunten_tegen', 0)) if selected_match.get('doelpunten_tegen') is not None else 0
                            edit_goals_against = st.number_input("🥅 Doelpunten Tegen", min_value=0, max_value=20, 
                                                                 value=current_goals_against)
                    else:
                        edit_goals_for = 0
                        edit_goals_against = 0
                    
                    submit_edit = st.form_submit_button("💾 Wijzigingen Opslaan", type="primary")
                    
                    if submit_edit:
                        try:
                            from supabase_config import get_supabase_client
                            client = get_supabase_client()
                            
                            # Update match
                            update_data = {
                                'datum': str(edit_datum),
                                'tijd': str(edit_tijd),
                                'tegenstander': edit_tegenstander,
                                'thuis_uit': edit_thuis_uit,
                                'competitie': edit_competitie,
                                'seizoen': edit_seizoen,
                                'match_type': edit_match_type,
                                'status': edit_status,
                                'doelpunten_voor': int(edit_goals_for),
                                'doelpunten_tegen': int(edit_goals_against)
                            }
                            
                            result = client.table('matches').update(update_data).eq('match_id', int(selected_match['match_id'])).execute()
                            
                            if result.data:
                                st.success(f"✅ Match {edit_tegenstander} succesvol bijgewerkt!")
                                st.rerun()
                            else:
                                st.error("❌ Fout bij bijwerken match")
                                
                        except Exception as e:
                            st.error(f"❌ Fout: {e}")
            else:
                st.info("📅 Geen matches beschikbaar om te bewerken")
    
    with col2:
        st.subheader("📅 Komende & Recente Matches")
        
        # Load matches
        matches_df = get_matches(20)
        
        if not matches_df.empty:
            for idx, match in matches_df.iterrows():
                match_id = match['match_id']
                datum = match['datum']
                tijd = match.get('tijd', '')
                tegenstander = match['tegenstander']
                thuis_uit = match['thuis_uit']
                goals_for = match.get('doelpunten_voor', 0)
                goals_against = match.get('doelpunten_tegen', 0)
                match_type = match['match_type']
                status = match['status']
                source = match.get('source', 'matches')  # Determine source
                
                # Create unique key using index and timestamp to avoid duplicates
                unique_key = f"{idx}_{match_id}_{hash(str(datum))}"
                
                # Match card
                with st.container():
                    # Date and opponent
                    col_info, col_score = st.columns([2, 1])
                    
                    with col_info:
                        # Show source indicator
                        source_icon = "📅" if source == "trainingskalender" else "⚽"
                        datum_str = datum.strftime('%Y-%m-%d') if hasattr(datum, 'strftime') else str(datum)
                        st.markdown(f"{source_icon} **{datum_str}** {tijd}")
                        st.markdown(f"🆚 **{tegenstander}** ({'🏠' if thuis_uit == 'Thuis' else '🚌'} {thuis_uit})")
                        source_text = " (uit trainingskalender)" if source == "trainingskalender" else ""
                        st.write(f"📝 {match_type} - {status}{source_text}")
                    
                    with col_score:
                        if status == "Gespeeld":
                            score_color = "success" if goals_for > goals_against else "error" if goals_for < goals_against else "info"
                            st.markdown(f":{score_color}[{goals_for} - {goals_against}]")
                        else:
                            st.write("⏳ Nog te spelen")
                    
                    # Action buttons
                    col_a, col_b, col_c, col_d = st.columns(4)
                    
                    with col_a:
                        if st.button(f"📋 Opstelling", key=f"lineup_{unique_key}"):
                            st.session_state.selected_match_lineup = match_id
                    
                    with col_b:
                        if st.button(f"⚽ Match Data", key=f"events_{unique_key}"):
                            st.session_state.selected_match_events = match_id
                    
                    with col_c:
                        if st.button(f"📊 Ratings", key=f"ratings_{unique_key}"):
                            st.session_state.selected_match_ratings = match_id
                    
                    with col_d:
                        if st.button(f"🗑️", key=f"delete_{unique_key}", help="Match verwijderen"):
                            if st.session_state.get(f"confirm_delete_{match_id}", False):
                                # Confirmed deletion
                                try:
                                    from supabase_config import get_supabase_client
                                    client = get_supabase_client()
                                    
                                    # Delete associated data first
                                    client.table('match_lineups').delete().eq('match_id', int(match_id)).execute()
                                    client.table('match_events').delete().eq('match_id', int(match_id)).execute()
                                    client.table('match_ratings').delete().eq('match_id', int(match_id)).execute()
                                    
                                    # Delete the match
                                    result = client.table('matches').delete().eq('match_id', int(match_id)).execute()
                                    
                                    if result:
                                        st.success(f"✅ Match tegen {tegenstander} verwijderd!")
                                        # Clear confirmation state
                                        if f"confirm_delete_{match_id}" in st.session_state:
                                            del st.session_state[f"confirm_delete_{match_id}"]
                                        st.rerun()
                                    else:
                                        st.error("❌ Fout bij verwijderen match")
                                        
                                except Exception as e:
                                    st.error(f"❌ Fout: {e}")
                            else:
                                # First click - ask for confirmation
                                st.session_state[f"confirm_delete_{match_id}"] = True
                                st.warning(f"⚠️ Klik nogmaals om match tegen {tegenstander} definitief te verwijderen!")
                                st.rerun()
                    
                    st.divider()
        else:
            st.info("Nog geen matches toegevoegd.")

with tab2:
    st.header("📋 Pre-Match Planning")
    
    # Match selectie
    matches_df = get_matches(10)
    upcoming_matches = matches_df[matches_df['datum'] >= str(date.today())] if not matches_df.empty else pd.DataFrame()
    
    if not upcoming_matches.empty:
        match_options = [f"{row['datum']} - {row['tegenstander']} ({'Thuis' if row['thuis_uit'] == 'Thuis' else 'Uit'})" 
                        for _, row in upcoming_matches.iterrows()]
        
        selected_match_idx = st.selectbox("🎯 Selecteer Match", range(len(match_options)), format_func=lambda x: match_options[x])
        selected_match_id = int(upcoming_matches.iloc[selected_match_idx]['match_id'])
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🔍 Opponent Scouting")
            
            # Get existing scouting data
            try:
                from supabase_config import get_supabase_client
                client = get_supabase_client()
                scouting_result = client.table('opponent_scouting').select('*').eq('match_id', selected_match_id).execute()
                existing_scout = scouting_result.data[0] if scouting_result.data else {}
            except:
                existing_scout = {}
            
            with st.form(f"scouting_{selected_match_id}"):
                formation = st.text_input("⚽ Formatie", value=existing_scout.get('formation', '4-4-2'))
                key_players = st.text_area("⭐ Sleutelspelers", value=existing_scout.get('key_players', ''))
                strengths = st.text_area("💪 Sterke Punten", value=existing_scout.get('strengths', ''))
                weaknesses = st.text_area("🎯 Zwakke Punten", value=existing_scout.get('weaknesses', ''))
                tactical_notes = st.text_area("📋 Tactische Notities", value=existing_scout.get('tactical_notes', ''))
                previous_results = st.text_input("📊 Vorige Resultaten", value=existing_scout.get('previous_results', ''))
                
                if st.form_submit_button("💾 Scouting Opslaan"):
                    try:
                        from supabase_config import get_supabase_client
                        client = get_supabase_client()
                        
                        # Delete existing
                        client.table('opponent_scouting').delete().eq('match_id', selected_match_id).execute()
                        
                        # Get next scout ID
                        scout_result = client.table('opponent_scouting').select('scout_id').execute()
                        existing_ids = [s['scout_id'] for s in scout_result.data if s['scout_id']] if scout_result.data else []
                        next_id = int(max(existing_ids)) + 1 if existing_ids else 1
                        
                        # Insert new
                        client.table('opponent_scouting').insert({
                            'scout_id': next_id,
                            'match_id': selected_match_id,
                            'formation': formation,
                            'key_players': key_players,
                            'strengths': strengths,
                            'weaknesses': weaknesses,
                            'tactical_notes': tactical_notes,
                            'previous_results': previous_results,
                            'scout_date': str(date.today())
                        }).execute()
                        
                        st.success("✅ Scouting opgeslagen!")
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Fout: {e}")
        
        with col2:
            st.subheader("👥 Squad Planning")
            
            available_players = get_available_players()
            
            if available_players:
                st.write("**Beschikbare Spelers:**")
                
                # Show players with recent performance data
                for player in available_players:  # Show all available players
                    with st.expander(f"👤 {player}"):
                        # Get recent GPS data
                        try:
                            recent_gps = safe_fetchdf(f"""
                                SELECT AVG(totale_afstand) as avg_distance, AVG(max_snelheid) as avg_max_speed
                                FROM gps_data 
                                WHERE speler = '{player}' 
                                AND datum >= (CURRENT_DATE - INTERVAL '7 days')
                            """)
                            
                            if not recent_gps.empty and recent_gps['avg_distance'].iloc[0] is not None:
                                st.write(f"📊 **Gem. Afstand (7d)**: {recent_gps['avg_distance'].iloc[0]:.0f}m")
                                st.write(f"⚡ **Gem. Max Snelheid**: {recent_gps['avg_max_speed'].iloc[0]:.1f} km/h")
                            else:
                                st.write("📊 Geen recente GPS data")
                                
                        except:
                            st.write("📊 GPS data niet beschikbaar")
                        
                        # Get recent RPE
                        try:
                            recent_rpe = safe_fetchdf(f"""
                                SELECT AVG(rpe_score) as avg_rpe
                                FROM rpe_data 
                                WHERE speler = '{player}' 
                                AND datum >= (CURRENT_DATE - INTERVAL '7 days')
                            """)
                            
                            if not recent_rpe.empty and recent_rpe['avg_rpe'].iloc[0] is not None:
                                st.write(f"💪 **Gem. RPE (7d)**: {recent_rpe['avg_rpe'].iloc[0]:.1f}")
                            
                        except:
                            pass
            else:
                st.info("💡 Geen spelers gevonden. Voeg eerst spelers toe via andere modules.")
    else:
        st.info("📅 Geen komende matches gevonden. Voeg eerst een match toe in de 'Matches' tab.")

with tab3:
    st.header("📊 Match Data & Events")
    
    # Match selection for events/ratings
    matches_df = get_matches(20)
    
    if not matches_df.empty:
        match_options = [f"{row['datum']} - {row['tegenstander']} ({'Thuis' if row['thuis_uit'] == 'Thuis' else 'Uit'}) [{row['status']}]" 
                        for _, row in matches_df.iterrows()]
        
        selected_match_idx = st.selectbox("🎯 Selecteer Match voor Events/Ratings", range(len(match_options)), format_func=lambda x: match_options[x])
        selected_match_id = int(matches_df.iloc[selected_match_idx]['match_id'])
        selected_match = matches_df.iloc[selected_match_idx]
        
        # Match score input eerst
        st.subheader("⚽ Match Score")
        
        with st.form("match_score_update"):
            col1, col2, col3 = st.columns([1, 1, 1])
            with col1:
                # Safe conversion to handle NaN values
                goals_for_value = selected_match.get('doelpunten_voor', 0)
                goals_for_value = 0 if pd.isna(goals_for_value) else int(goals_for_value)
                goals_for = st.number_input("🏆 Doelpunten Voor", min_value=0, max_value=20, value=goals_for_value)
            with col2:
                # Safe conversion to handle NaN values
                goals_against_value = selected_match.get('doelpunten_tegen', 0)
                goals_against_value = 0 if pd.isna(goals_against_value) else int(goals_against_value)
                goals_against = st.number_input("🥅 Doelpunten Tegen", min_value=0, max_value=20, value=goals_against_value)
            with col3:
                match_status = st.selectbox("📊 Status", ["Gepland", "Gespeeld", "Geannuleerd"], 
                                          index=["Gepland", "Gespeeld", "Geannuleerd"].index(selected_match.get('status', 'Gepland')))
            
            submit_score = st.form_submit_button("💾 Update Match Score", type="primary")
        
        if submit_score:
            try:
                from supabase_config import get_supabase_client
                client = get_supabase_client()
                
                # Check if this is a match from trainingskalender or matches table
                match_source = selected_match.get('source', 'matches')
                
                if match_source == 'trainingskalender':
                    # For trainingskalender matches, we need to create a proper match record
                    # or update if it already exists in matches table
                    
                    # First check if a match record already exists
                    existing_match_result = client.table('matches').select('*').eq('match_id', int(selected_match_id)).execute()
                    existing_match = existing_match_result.data if existing_match_result.data else []
                    
                    if not existing_match:
                        # Create new match record from trainingskalender data
                        result = client.table('matches').insert({
                            'match_id': int(selected_match_id),
                            'datum': str(selected_match['datum']).split()[0],  # Just date part
                            'tijd': selected_match.get('tijd', ''),
                            'tegenstander': selected_match['tegenstander'],
                            'thuis_uit': selected_match.get('thuis_uit', 'Onbekend'),
                            'competitie': selected_match.get('competitie', 'Vriendschappelijk'),
                            'seizoen': selected_match.get('seizoen', '2024/2025'),
                            'match_type': selected_match['match_type'],
                            'doelpunten_voor': int(goals_for),
                            'doelpunten_tegen': int(goals_against),
                            'status': match_status
                        }).execute()
                        
                        st.success(f"✅ Match record aangemaakt en score bijgewerkt: {goals_for}-{goals_against} (Status: {match_status})")
                    else:
                        # Update existing match record
                        client.table('matches').update({
                            'doelpunten_voor': int(goals_for),
                            'doelpunten_tegen': int(goals_against),
                            'status': match_status
                        }).eq('match_id', selected_match_id).execute()
                        
                        st.success(f"✅ Score bijgewerkt: {goals_for}-{goals_against} (Status: {match_status})")
                else:
                    # Regular match from matches table
                    client.table('matches').update({
                        'doelpunten_voor': int(goals_for),
                        'doelpunten_tegen': int(goals_against),
                        'status': match_status
                    }).eq('match_id', selected_match_id).execute()
                    
                    st.success(f"✅ Score bijgewerkt: {goals_for}-{goals_against} (Status: {match_status})")
                
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ Fout: {e}")
        
        # Show current score
        if goals_for > goals_against:
            st.success(f"🏆 Huidige stand: **{goals_for} - {goals_against}** (Overwinning!)")
        elif goals_for == goals_against:
            st.info(f"🤝 Huidige stand: **{goals_for} - {goals_against}** (Gelijkspel)")
        else:
            st.error(f"❌ Huidige stand: **{goals_for} - {goals_against}** (Nederlaag)")
        
        st.divider()
        
        # Events, ratings and lineup tabs
        event_tab1, event_tab2, event_tab3 = st.tabs(["⚽ Match Events", "⭐ Player Ratings", "👕 Opstelling & Minuten"])
        
        with event_tab1:
            st.subheader("⚽ Match Events")
            
            # Add new event
            with st.form("add_event"):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    # Prioritize players from lineup if available
                    try:
                        from supabase_config import get_supabase_client
                        client = get_supabase_client()
                        
                        # Get players from lineup who played minutes
                        lineup_result = client.table('match_lineups').select('speler, minuten_gespeeld').eq('match_id', selected_match_id).execute()
                        lineup_players = [p['speler'] for p in lineup_result.data if p.get('minuten_gespeeld', 0) > 0] if lineup_result.data else []
                        
                        # Get all available players as fallback
                        all_available_players = get_available_players()
                        
                        # Combine: lineup players first, then others
                        other_players = [p for p in all_available_players if p not in lineup_players]
                        available_players = lineup_players + other_players
                        
                        # Show info if using lineup
                        if lineup_players:
                            st.info(f"👕 {len(lineup_players)} spelers uit opstelling beschikbaar")
                            
                    except Exception:
                        available_players = get_available_players()
                    
                    event_player = st.selectbox("👤 Speler", available_players)
                
                with col2:
                    event_type = st.selectbox("📝 Event Type", [
                        "Goal", "Assist", "Gele Kaart", "Rode Kaart", 
                        "Wissel In", "Wissel Uit", "Penalty", "Eigen Doelpunt"
                    ])
                
                with col3:
                    event_minute = st.number_input("⏱️ Minuut", min_value=1, max_value=120, value=45)
                
                event_description = st.text_input("📝 Omschrijving (optioneel)")
                
                if st.form_submit_button("➕ Event Toevoegen"):
                    if event_player:
                        try:
                            from supabase_config import get_supabase_client
                            client = get_supabase_client()
                            
                            # Get next event ID
                            events_result = client.table('match_events').select('event_id').execute()
                            existing_ids = [e['event_id'] for e in events_result.data if e['event_id']] if events_result.data else []
                            next_id = int(max(existing_ids)) + 1 if existing_ids else 1
                            
                            client.table('match_events').insert({
                                'event_id': next_id,
                                'match_id': int(selected_match_id),
                                'speler': event_player,
                                'event_type': event_type,
                                'minuut': int(event_minute),
                                'omschrijving': event_description
                            }).execute()
                            
                            st.success(f"✅ Event toegevoegd: {event_player} - {event_type} ({event_minute}')")
                            st.rerun()
                            
                        except Exception as e:
                            st.error(f"❌ Fout: {e}")
            
            # Show existing events
            events_df = get_match_events(selected_match_id)
            
            if not events_df.empty:
                st.subheader("📋 Match Events")
                
                for _, event in events_df.iterrows():
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        emoji = "⚽" if event['event_type'] == "Goal" else "🟨" if event['event_type'] == "Gele Kaart" else "🟥" if event['event_type'] == "Rode Kaart" else "📝"
                        st.write(f"{emoji} **{event['minuut']}'** - {event['speler']} ({event['event_type']})")
                        if event.get('omschrijving'):
                            st.write(f"   📝 {event['omschrijving']}")
                    
                    with col2:
                        if st.button(f"🗑️ Verwijder", key=f"delete_event_{event['event_id']}"):
                            try:
                                from supabase_config import get_supabase_client
                                client = get_supabase_client()
                                
                                client.table('match_events').delete().eq('event_id', event['event_id']).execute()
                                st.success("✅ Event verwijderd!")
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"❌ Fout: {e}")
            else:
                st.info("📋 Nog geen match events toegevoegd")
        
        with event_tab2:
            st.subheader("⭐ Player Ratings")
            
            # Prioritize players from lineup for ratings
            try:
                from supabase_config import get_supabase_client
                client = get_supabase_client()
                
                # Get players from lineup who played more than 10 minutes (eligible for ratings)
                lineup_result = client.table('match_lineups').select('speler, minuten_gespeeld, positie').eq('match_id', selected_match_id).execute()
                lineup_players_data = lineup_result.data if lineup_result.data else []
                
                # Filter: only players with more than 10 minutes are eligible for ratings
                eligible_players_data = [p for p in lineup_players_data if p.get('minuten_gespeeld', 0) > 10]
                eligible_players = [p['speler'] for p in eligible_players_data]
                
                # Players with 1-10 minutes (not eligible for ratings)
                short_play_players = [p for p in lineup_players_data if 0 < p.get('minuten_gespeeld', 0) <= 10]
                unused_players = [p for p in lineup_players_data if p.get('minuten_gespeeld', 0) == 0]
                
                # Get all available players as fallback
                col_refresh_ratings, col_space = st.columns([1, 4])
                with col_refresh_ratings:
                    if st.button("🔄 Vernieuw Spelers", key="refresh_ratings", help="Vernieuw spelerslijst voor ratings"):
                        from supabase_helpers import get_cached_player_list
                        get_cached_player_list.clear()
                        st.rerun()
                
                # Use only eligible players for ratings
                available_players = eligible_players
                
                # Show lineup info with filtering explanation
                if eligible_players:
                    st.success(f"⭐ {len(eligible_players)} spelers beschikbaar voor ratings (>10 minuten gespeeld)")
                    
                    # Show minutes played for context
                    minutes_info = {p['speler']: p.get('minuten_gespeeld', 0) for p in eligible_players_data}
                    
                    # Show excluded players info
                    if short_play_players or unused_players:
                        with st.expander("ℹ️ Uitgesloten van ratings", expanded=False):
                            if short_play_players:
                                st.info(f"🕐 **{len(short_play_players)} spelers speelden 1-10 minuten** (te kort voor rating):")
                                for p in short_play_players:
                                    st.write(f"   • {p['speler']}: {p.get('minuten_gespeeld', 0)} minuten")
                            
                            if unused_players:
                                st.info(f"🪑 **{len(unused_players)} spelers speelden 0 minuten** (wisselspelers):")
                                for p in unused_players:
                                    st.write(f"   • {p['speler']}: {p.get('positie', 'Onbekend')}")
                
                else:
                    st.warning("⚠️ Geen spelers beschikbaar voor ratings - niemand speelde meer dan 10 minuten")
                    if lineup_players_data:
                        st.info("💡 Voer eerst speelminuten in via het 'Opstelling & Minuten' tabblad")
                    
            except Exception:
                # Fallback: no filtering if we can't get lineup data
                st.warning("⚠️ Kan opstelling niet ophalen - ratings voor alle spelers beschikbaar")
                available_players = get_available_players()
                minutes_info = {}
            
            if available_players:
                # Get existing ratings
                ratings_df = get_match_ratings(selected_match_id)
                existing_ratings = {}
                if not ratings_df.empty:
                    existing_ratings = dict(zip(ratings_df['speler'], ratings_df['rating']))
                
                st.write("**Speler Ratings (1-10):**")
                
                # Create rating inputs
                ratings_to_save = {}
                cols = st.columns(2)
                
                for i, player in enumerate(available_players):  # Show all available players
                    col_idx = i % 2
                    with cols[col_idx]:
                        current_rating = existing_ratings.get(player, 6.0)
                        
                        # Show minutes played if available
                        minutes_played = minutes_info.get(player, 0) if 'minutes_info' in locals() else 0
                        player_label = f"⭐ {player}"
                        if minutes_played > 0:
                            player_label += f" ({minutes_played} min)"
                        elif player in lineup_players:
                            player_label += " (👕 In opstelling)"
                        
                        rating = st.slider(
                            player_label, 
                            min_value=1.0, 
                            max_value=10.0, 
                            value=float(current_rating), 
                            step=0.1,
                            key=f"rating_{player}_{selected_match_id}"
                        )
                        ratings_to_save[player] = rating
                
                if st.button("💾 Ratings Opslaan", type="primary"):
                    try:
                        from supabase_config import get_supabase_client
                        client = get_supabase_client()
                        
                        # Delete existing ratings
                        client.table('match_ratings').delete().eq('match_id', int(selected_match_id)).execute()
                        
                        # Insert new ratings
                        for player, rating in ratings_to_save.items():
                            if rating > 1.0:  # Only save non-default ratings
                                # Get next rating ID
                                ratings_result = client.table('match_ratings').select('rating_id').execute()
                                existing_ids = [r['rating_id'] for r in ratings_result.data if r['rating_id']] if ratings_result.data else []
                                next_id = int(max(existing_ids)) + 1 if existing_ids else 1
                                
                                # Get player position from lineup if available
                                player_position = 'Unknown'
                                if 'lineup_players_data' in locals():
                                    for lineup_player in lineup_players_data:
                                        if lineup_player['speler'] == player:
                                            player_position = lineup_player.get('positie', 'Unknown') or 'Unknown'
                                            break
                                
                                # Ensure rating is numeric
                                numeric_rating = float(rating) if rating else 6.0
                                
                                client.table('match_ratings').insert({
                                    'rating_id': next_id,
                                    'match_id': int(selected_match_id),
                                    'speler': player,
                                    'rating': numeric_rating,  # Ensure numeric storage
                                    'positie': player_position,
                                    'man_of_the_match': numeric_rating >= 8.5  # Auto-assign MOTM for high ratings
                                }).execute()
                        
                        st.success("✅ Ratings opgeslagen!")
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Fout: {e}")
                
                # Show average rating
                if existing_ratings:
                    # Safe conversion of ratings to float
                    numeric_ratings = []
                    for rating in existing_ratings.values():
                        try:
                            numeric_ratings.append(float(rating))
                        except (ValueError, TypeError):
                            pass  # Skip invalid ratings
                    
                    if numeric_ratings:
                        avg_rating = sum(numeric_ratings) / len(numeric_ratings)
                        st.metric("📊 Gemiddelde Team Rating", f"{avg_rating:.1f}")
                    else:
                        st.info("📊 Geen geldige ratings gevonden")
            else:
                st.info("💡 Geen spelers beschikbaar voor ratings")
        
        with event_tab3:
            st.subheader("👕 Opstelling & Speelminuten")
            
            # Get all available players with refresh option
            col_refresh, col_info = st.columns([1, 4])
            with col_refresh:
                if st.button("🔄 Vernieuw Spelerslijst", help="Vernieuw de spelerslijst als spelers ontbreken"):
                    # Clear cache and reload players
                    from supabase_helpers import get_cached_player_list
                    get_cached_player_list.clear()
                    st.rerun()
            
            all_players = get_available_players()
            
            with col_info:
                if all_players:
                    st.info(f"📋 {len(all_players)} spelers beschikbaar voor selectie")
            
            if all_players:
                st.write("⚽ **Speelminuten Invoer**")
                
                # Get existing lineup data for this match
                try:
                    from supabase_config import get_supabase_client
                    client = get_supabase_client()
                    
                    lineup_result = client.table('match_lineups').select('*').eq('match_id', selected_match_id).execute()
                    existing_lineup = lineup_result.data if lineup_result.data else []
                    
                    existing_dict = {}
                    for lineup in existing_lineup:
                        existing_dict[lineup['speler']] = {
                            'positie': lineup.get('positie') or '',
                            'start_elf': lineup.get('start_elf') or False,
                            'minuten_gespeeld': lineup.get('minuten_gespeeld') or 0,
                            'captain': lineup.get('captain') or False,
                            'keeper': lineup.get('keeper') or False
                        }
                    
                    # Show current match info
                    match_result = client.table('matches').select('datum, tegenstander, thuis_uit, status').eq('match_id', selected_match_id).execute()
                    if match_result.data:
                        match_info = match_result.data[0]
                        st.info(f"📅 **{match_info['datum']}** - {match_info['tegenstander']} ({'Thuis' if match_info['thuis_uit'] == 'Thuis' else 'Uit'}) - Status: {match_info['status']}")
                    
                    with st.form(f"lineup_minutes_{selected_match_id}"):
                        st.write("**👥 Selecteer Spelers & Voer Speelminuten In:**")
                        
                        # Quick preset buttons
                        col_preset1, col_preset2, col_preset3 = st.columns(3)
                        with col_preset1:
                            full_match = st.checkbox("⚡ Volledige wedstrijd (90 min)", key="preset_full")
                        with col_preset2:
                            half_match = st.checkbox("⏱️ Halve wedstrijd (45 min)", key="preset_half")
                        with col_preset3:
                            custom_minutes = st.number_input("📝 Custom minuten", min_value=0, max_value=120, value=90, key="preset_custom")
                        
                        lineup_data = []
                        starting_eleven_count = 0
                        
                        # Create input fields for each player
                        for i, player in enumerate(all_players):  # Show all available players
                            existing = existing_dict.get(player, {
                                'positie': '', 'start_elf': False, 'minuten_gespeeld': 0, 
                                'captain': False, 'keeper': False
                            })
                            
                            # Player row
                            col1, col2, col3, col4, col5, col6 = st.columns([2, 1, 1, 1, 0.5, 0.5])
                            
                            with col1:
                                st.write(f"**{player}**")
                            
                            with col2:
                                positie = st.selectbox(
                                    "Positie", 
                                    ["", "GK", "VV", "CV", "LV", "RV", "CDM", "CM", "CAM", "LM", "RM", "LW", "RW", "CF", "ST"],
                                    index=0 if not existing['positie'] else (["", "GK", "VV", "CV", "LV", "RV", "CDM", "CM", "CAM", "LM", "RM", "LW", "RW", "CF", "ST"].index(existing['positie']) if existing['positie'] in ["", "GK", "VV", "CV", "LV", "RV", "CDM", "CM", "CAM", "LM", "RM", "LW", "RW", "CF", "ST"] else 0),
                                    key=f"pos_{i}",
                                    label_visibility="collapsed"
                                )
                            
                            with col3:
                                start_elf = st.checkbox("Start XI", value=existing['start_elf'], key=f"start_{i}")
                                if start_elf:
                                    starting_eleven_count += 1
                            
                            with col4:
                                # Default minutes based on presets
                                default_minutes = existing['minuten_gespeeld']
                                if full_match and start_elf:
                                    default_minutes = 90
                                elif half_match and start_elf:
                                    default_minutes = 45
                                elif start_elf and custom_minutes > 0:
                                    default_minutes = custom_minutes
                                
                                minuten = st.number_input(
                                    "Min",
                                    min_value=0,
                                    max_value=120,
                                    value=default_minutes,
                                    key=f"min_{i}",
                                    label_visibility="collapsed"
                                )
                            
                            with col5:
                                captain = st.checkbox("(C)", value=existing['captain'], key=f"cap_{i}")
                            
                            with col6:
                                keeper = st.checkbox("GK", value=existing['keeper'], key=f"gk_{i}")
                            
                            # Only add to lineup if player has position or minutes
                            if positie or minuten > 0 or start_elf:
                                lineup_data.append({
                                    'speler': player,
                                    'positie': positie,
                                    'start_elf': start_elf,
                                    'minuten_gespeeld': minuten,
                                    'captain': captain,
                                    'keeper': keeper
                                })
                        
                        # Validation warnings
                        if starting_eleven_count != 11:
                            st.warning(f"⚠️ Je hebt {starting_eleven_count} spelers in de start XI geselecteerd. Een team heeft exact 11 startende spelers nodig.")
                        
                        captain_count = sum(1 for player in lineup_data if player['captain'])
                        if captain_count > 1:
                            st.warning(f"⚠️ Je hebt {captain_count} aanvoerders geselecteerd. Er kan maar 1 aanvoerder zijn.")
                        
                        keeper_count = sum(1 for player in lineup_data if player['keeper'])
                        if keeper_count != 1:
                            st.warning(f"⚠️ Je hebt {keeper_count} keepers geselecteerd. Er moet exact 1 keeper zijn.")
                        
                        # Submit button
                        if st.form_submit_button("💾 Opstelling & Minuten Opslaan"):
                            try:
                                # Delete existing lineup data
                                client.table('match_lineups').delete().eq('match_id', int(selected_match_id)).execute()
                                
                                # Insert new lineup data
                                for player_data in lineup_data:
                                    client.table('match_lineups').insert({
                                        'match_id': int(selected_match_id),
                                        'speler': player_data['speler'],
                                        'positie': player_data['positie'],
                                        'start_elf': player_data['start_elf'],
                                        'minuten_gespeeld': int(player_data['minuten_gespeeld']),
                                        'captain': player_data['captain'],
                                        'keeper': player_data['keeper']
                                    }).execute()
                                
                                st.success(f"✅ Opstelling opgeslagen! {len(lineup_data)} spelers toegevoegd.")
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"❌ Fout bij opslaan: {e}")
                    
                    # Show current lineup summary
                    if existing_lineup:
                        st.subheader("📋 Huidige Opstelling")
                        
                        # Show starting XI
                        starting_xi = [p for p in existing_lineup if p.get('start_elf')]
                        if starting_xi:
                            st.write("**🥇 Basis Opstelling:**")
                            for player in starting_xi:
                                captain_badge = " (C)" if player.get('captain') else ""
                                keeper_badge = " 🥅" if player.get('keeper') else ""
                                st.write(f"- **{player['speler']}**{captain_badge}{keeper_badge} - {player.get('positie', 'Onbekend')} - {player.get('minuten_gespeeld', 0)} min")
                        
                        # Show substitutes
                        subs = [p for p in existing_lineup if not p.get('start_elf') and p.get('minuten_gespeeld', 0) > 0]
                        if subs:
                            st.write("**🔄 Wisselspelers die speelden:**")
                            for player in subs:
                                st.write(f"- **{player['speler']}** - {player.get('positie', 'Onbekend')} - {player.get('minuten_gespeeld', 0)} min")
                        
                        # Show total minutes analytics
                        total_minutes = sum(p.get('minuten_gespeeld', 0) for p in existing_lineup)
                        st.metric("📊 Totaal Speelminuten", f"{total_minutes} min")
                        
                        if len(existing_lineup) > 0:
                            avg_minutes = total_minutes / len(existing_lineup)
                            st.metric("📊 Gemiddeld per Speler", f"{avg_minutes:.1f} min")
                
                except Exception as e:
                    st.error(f"❌ Fout bij laden van opstelling data: {e}")
            else:
                st.info("💡 Geen spelers beschikbaar voor opstelling")
    else:
        st.info("📅 Geen matches gevonden. Voeg eerst matches toe.")

with tab4:
    st.header("📈 Match Analytics")
    
    matches_df = get_matches(50)
    
    if not matches_df.empty:
        # Filter for matches with scores (either status = 'Gespeeld' or has goals data)
        played_matches = matches_df[
            (matches_df['status'] == 'Gespeeld') | 
            ((pd.to_numeric(matches_df['doelpunten_voor'], errors='coerce') > 0) |
             (pd.to_numeric(matches_df['doelpunten_tegen'], errors='coerce') > 0))
        ].copy()
        
        if not played_matches.empty:
            # Convert numeric columns
            played_matches['doelpunten_voor'] = pd.to_numeric(played_matches['doelpunten_voor'], errors='coerce').fillna(0)
            played_matches['doelpunten_tegen'] = pd.to_numeric(played_matches['doelpunten_tegen'], errors='coerce').fillna(0)
            
            # Calculate results
            played_matches['result'] = played_matches.apply(
                lambda row: 'Win' if row['doelpunten_voor'] > row['doelpunten_tegen'] 
                           else 'Draw' if row['doelpunten_voor'] == row['doelpunten_tegen'] 
                           else 'Loss', axis=1
            )
            
            # Statistics
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                total_matches = len(played_matches)
                st.metric("🏟️ Gespeelde Matches", total_matches)
            
            with col2:
                wins = len(played_matches[played_matches['result'] == 'Win'])
                win_rate = (wins / total_matches * 100) if total_matches > 0 else 0
                st.metric("🏆 Overwinningen", f"{wins} ({win_rate:.1f}%)")
            
            with col3:
                total_goals_for = played_matches['doelpunten_voor'].sum()
                avg_goals_for = total_goals_for / total_matches if total_matches > 0 else 0
                st.metric("⚽ Doelpunten Voor", f"{total_goals_for} (⌀{avg_goals_for:.1f})")
            
            with col4:
                total_goals_against = played_matches['doelpunten_tegen'].sum()
                avg_goals_against = total_goals_against / total_matches if total_matches > 0 else 0
                st.metric("🥅 Doelpunten Tegen", f"{total_goals_against} (⌀{avg_goals_against:.1f})")
            
            # Charts
            col1, col2 = st.columns(2)
            
            with col1:
                # Results pie chart
                if total_matches > 0:
                    results_count = played_matches['result'].value_counts()
                    fig_results = px.pie(
                        values=results_count.values, 
                        names=results_count.index,
                        title="Match Results",
                        color_discrete_map={'Win': 'green', 'Draw': 'orange', 'Loss': 'red'}
                    )
                    st.plotly_chart(fig_results, use_container_width=True)
            
            with col2:
                # Goals trend
                if total_matches > 0:
                    played_matches['datum'] = pd.to_datetime(played_matches['datum'])
                    played_matches_sorted = played_matches.sort_values('datum')
                    
                    fig_goals = go.Figure()
                    fig_goals.add_trace(go.Scatter(
                        x=played_matches_sorted['datum'],
                        y=played_matches_sorted['doelpunten_voor'],
                        mode='lines+markers',
                        name='Doelpunten Voor',
                        line=dict(color='green')
                    ))
                    fig_goals.add_trace(go.Scatter(
                        x=played_matches_sorted['datum'],
                        y=played_matches_sorted['doelpunten_tegen'],
                        mode='lines+markers',
                        name='Doelpunten Tegen',
                        line=dict(color='red')
                    ))
                    fig_goals.update_layout(title="Goals Trend", xaxis_title="Datum", yaxis_title="Doelpunten")
                    st.plotly_chart(fig_goals, use_container_width=True)
            
            # Events & Ratings Analytics
            st.divider()
            st.subheader("⚽ Events & Ratings Analytics")
            
            # Get all events and ratings for played matches
            all_events = []
            all_ratings = []
            
            for match_id in played_matches['match_id']:
                events_df = get_match_events(match_id)
                ratings_df = get_match_ratings(match_id)
                
                if not events_df.empty:
                    events_df['match_id'] = match_id
                    all_events.append(events_df)
                
                if not ratings_df.empty:
                    ratings_df['match_id'] = match_id
                    all_ratings.append(ratings_df)
            
            if all_events or all_ratings:
                col1, col2 = st.columns(2)
                
                with col1:
                    # Events analysis
                    if all_events:
                        combined_events = pd.concat(all_events, ignore_index=True)
                        
                        # Event type distribution
                        event_counts = combined_events['event_type'].value_counts()
                        fig_events = px.bar(
                            x=event_counts.index,
                            y=event_counts.values,
                            title="Event Types Distribution",
                            labels={'x': 'Event Type', 'y': 'Count'}
                        )
                        st.plotly_chart(fig_events, use_container_width=True)
                        
                        # Top performers by event type
                        st.write("**🏆 Top Goal Scorers:**")
                        goals_df = combined_events[combined_events['event_type'] == 'Goal']
                        if not goals_df.empty:
                            goal_scorers = goals_df['speler'].value_counts().head(5)
                            for i, (player, goals) in enumerate(goal_scorers.items(), 1):
                                st.write(f"{i}. {player}: {goals} goals")
                        else:
                            st.write("Geen goals geregistreerd")
                        
                        st.write("**🅰️ Top Assists:**")
                        assists_df = combined_events[combined_events['event_type'] == 'Assist']
                        if not assists_df.empty:
                            assist_providers = assists_df['speler'].value_counts().head(5)
                            for i, (player, assists) in enumerate(assist_providers.items(), 1):
                                st.write(f"{i}. {player}: {assists} assists")
                        else:
                            st.write("Geen assists geregistreerd")
                    else:
                        st.info("📝 Geen match events beschikbaar")
                
                with col2:
                    # Ratings analysis
                    if all_ratings:
                        combined_ratings = pd.concat(all_ratings, ignore_index=True)
                        combined_ratings['rating'] = pd.to_numeric(combined_ratings['rating'], errors='coerce')
                        
                        # Average ratings by player
                        avg_ratings = combined_ratings.groupby('speler')['rating'].agg(['mean', 'count']).reset_index()
                        avg_ratings = avg_ratings[avg_ratings['count'] >= 2]  # At least 2 matches
                        avg_ratings = avg_ratings.sort_values('mean', ascending=False)
                        
                        if not avg_ratings.empty:
                            fig_ratings = px.bar(
                                avg_ratings.head(10),
                                x='speler',
                                y='mean',
                                title="Top 10 Average Player Ratings",
                                labels={'mean': 'Average Rating', 'speler': 'Player'}
                            )
                            fig_ratings.update_layout(xaxis_tickangle=-45)
                            st.plotly_chart(fig_ratings, use_container_width=True)
                            
                            # Best rated players
                            st.write("**⭐ Highest Rated Players:**")
                            for i, row in avg_ratings.head(5).iterrows():
                                st.write(f"{i+1}. {row['speler']}: {row['mean']:.1f} ({int(row['count'])} matches)")
                        else:
                            st.info("📊 Onvoldoende rating data (min. 2 matches)")
                    else:
                        st.info("⭐ Geen player ratings beschikbaar")
            else:
                st.info("📊 Geen events of ratings data beschikbaar voor analyse")
            
            st.divider()
            
            # Recent matches table
            st.subheader("📋 Recente Matches")
            recent_matches = played_matches.head(10)[['datum', 'tegenstander', 'thuis_uit', 'doelpunten_voor', 'doelpunten_tegen', 'result']].copy()
            recent_matches.columns = ['Datum', 'Tegenstander', 'Thuis/Uit', 'Voor', 'Tegen', 'Resultaat']
            st.dataframe(recent_matches, use_container_width=True)
            
        else:
            st.info("📊 Nog geen gespeelde matches voor analytics")
    else:
        st.info("📅 Geen match data beschikbaar")