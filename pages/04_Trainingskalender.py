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

def clear_training_cache():
    """Clear Streamlit cache to refresh training data"""
    if hasattr(st, 'cache_data'):
        st.cache_data.clear()
    if hasattr(st, 'legacy_caching'):
        st.legacy_caching.clear_cache()

import pandas as pd
from datetime import datetime, date, timedelta

st.title("📅 Trainingskalender")

# Database setup with proper Supabase connection test
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

# Database compatibility functions for simplified queries
def get_trainings(limit=50):
    """Get trainings from calendar"""
    try:
        df = safe_fetchdf(f"SELECT * FROM trainings_calendar ORDER BY datum DESC LIMIT {limit}")
        return df if not df.empty else pd.DataFrame()
    except Exception as e:
        st.error(f"Error loading trainings: {e}")
        return pd.DataFrame()

def get_training_attendance(training_id):
    """Get attendance for a specific training"""
    try:
        df = safe_fetchdf(f"SELECT * FROM training_attendance WHERE training_id = {training_id}")
        return df if not df.empty else pd.DataFrame()
    except Exception as e:
        st.error(f"Error loading attendance: {e}")
        return pd.DataFrame()

def get_available_players():
    """Get list of available players from multiple sources"""
    try:
        # Primary source: spelers_profiel table (main player database)
        players = set()
        
        # Get active players from main player database
        spelers_df = safe_fetchdf("SELECT naam FROM spelers_profiel WHERE status = 'Actief'")
        if not spelers_df.empty:
            spelers_players = [p for p in spelers_df['naam'].tolist() if p is not None and p != '']
            players.update(spelers_players)
        
        # Fallback: combine players from other data sources if spelers_profiel is empty
        if not players:
            # From GPS data
            gps_df = safe_fetchdf("SELECT DISTINCT speler FROM gps_data")
            if not gps_df.empty:
                gps_players = [p for p in gps_df['speler'].tolist() if p is not None and p != '']
                players.update(gps_players)
            
            # From RPE data  
            rpe_df = safe_fetchdf("SELECT DISTINCT speler FROM rpe_data")
            if not rpe_df.empty:
                rpe_players = [p for p in rpe_df['speler'].tolist() if p is not None and p != '']
                players.update(rpe_players)
                
            # From thirty fifteen results
            test_df = safe_fetchdf("SELECT DISTINCT Speler FROM thirty_fifteen_results")
            if not test_df.empty:
                test_players = [p for p in test_df['Speler'].tolist() if p is not None and p != '']
                players.update(test_players)
            
        return sorted(list(players))
    except Exception as e:
        st.error(f"Error loading players: {e}")
        return []

def update_training(training_id, datum, type_training, omschrijving, duur):
    """Update a training in the database"""
    try:
        st.write(f"🔄 Updating training {training_id}...")
        
        if SUPABASE_MODE:
            from supabase import create_client
            import os
            
            # Get Supabase credentials from environment or secrets
            try:
                supabase_url = st.secrets["supabase"]["url"]
                supabase_key = st.secrets["supabase"]["anon_key"]  # Fixed: was "key", should be "anon_key"
                st.write("🔑 Using Streamlit secrets")
            except Exception as secrets_error:
                st.write(f"⚠️ Streamlit secrets not available: {secrets_error}")
                supabase_url = os.getenv("SUPABASE_URL")
                supabase_key = os.getenv("SUPABASE_KEY")
                st.write("🔑 Using environment variables")
            
            if supabase_url and supabase_key:
                supabase = create_client(supabase_url, supabase_key)
                
                update_data = {
                    "datum": str(datum),
                    "type": type_training,
                    "omschrijving": omschrijving,
                    "geplande_duur_minuten": duur
                }
                
                st.write(f"📝 Update data: {update_data}")
                
                result = supabase.table("trainings_calendar").update(update_data).eq("training_id", training_id).execute()
                
                st.write(f"📊 Update result: {result}")
                
                if result.data:
                    st.write(f"✅ Update successful: {len(result.data)} records updated")
                    return True
                else:
                    st.write("❌ No data returned from update")
                    return False
            else:
                st.error("❌ No Supabase credentials available")
                return False
        else:
            st.error("❌ Only Supabase mode supported")
            return False
    except Exception as e:
        st.error(f"❌ Error updating training: {e}")
        st.write(f"🔍 Exception details: {str(e)}")
        return False

def delete_training(training_id, specific_training_data=None):
    """Delete a training and all related attendance records"""
    try:
        st.write(f"🗑️ Deleting training {training_id}...")
        
        if SUPABASE_MODE:
            from supabase import create_client
            import os
            
            # Get Supabase credentials from environment or secrets
            try:
                supabase_url = st.secrets["supabase"]["url"]
                supabase_key = st.secrets["supabase"]["anon_key"]  # Fixed: was "key", should be "anon_key"
                st.write("🔑 Using Streamlit secrets")
            except Exception as secrets_error:
                st.write(f"⚠️ Streamlit secrets not available: {secrets_error}")
                supabase_url = os.getenv("SUPABASE_URL")
                supabase_key = os.getenv("SUPABASE_KEY")
                st.write("🔑 Using environment variables")
            
            if supabase_url and supabase_key:
                supabase = create_client(supabase_url, supabase_key)
                
                # First delete attendance records
                st.write("🧹 Deleting attendance records...")
                attendance_result = supabase.table("training_attendance").delete().eq("training_id", training_id).execute()
                st.write(f"📊 Attendance delete result: {attendance_result}")
                
                # Delete training - if we have specific training data, use it for precision
                if specific_training_data:
                    st.write(f"🎯 Using specific training data for precise deletion:")
                    st.write(f"   Date: {specific_training_data['datum']}")
                    st.write(f"   Type: {specific_training_data['type']}")
                    
                    # Use multiple fields to ensure we delete the right record
                    training_result = supabase.table("trainings_calendar").delete().eq("training_id", training_id).eq("datum", str(specific_training_data['datum'])).eq("type", specific_training_data['type']).execute()
                else:
                    st.write("🗑️ Deleting training record by ID only...")
                    training_result = supabase.table("trainings_calendar").delete().eq("training_id", training_id).execute()
                
                st.write(f"📊 Training delete result: {training_result}")
                
                if training_result.data is not None:  # Supabase delete can return empty list
                    st.write("✅ Delete operation completed")
                    return True
                else:
                    st.write("❌ No training record found to delete")
                    return False
            else:
                st.error("❌ No Supabase credentials available")
                return False
        else:
            st.error("❌ Only Supabase mode supported")
            return False
    except Exception as e:
        st.error(f"❌ Error deleting training: {e}")
        st.write(f"🔍 Exception details: {str(e)}")
        return False

def update_attendance_status(training_id, speler, new_status):
    """Update attendance status for a specific player"""
    try:
        if SUPABASE_MODE:
            from supabase import create_client
            import os
            
            # Get Supabase credentials from environment or secrets
            try:
                supabase_url = st.secrets["supabase"]["url"]
                supabase_key = st.secrets["supabase"]["anon_key"]  # Fixed: was "key", should be "anon_key"
            except:
                supabase_url = os.getenv("SUPABASE_URL")
                supabase_key = os.getenv("SUPABASE_KEY")
            
            if supabase_url and supabase_key:
                supabase = create_client(supabase_url, supabase_key)
                
                # Check if record exists
                existing = supabase.table("training_attendance").select("*").eq("training_id", training_id).eq("speler", speler).execute()
                
                if existing.data:
                    # Update existing record
                    result = supabase.table("training_attendance").update({
                        "status": new_status
                    }).eq("training_id", training_id).eq("speler", speler).execute()
                else:
                    # Insert new record
                    result = supabase.table("training_attendance").insert({
                        "training_id": training_id,
                        "speler": speler,
                        "status": new_status
                    }).execute()
                return True
        return False
    except Exception as e:
        st.error(f"Error updating attendance: {e}")
        return False

# Twee kolommen: links planning, rechts kalender overzicht
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("➕ Training Toevoegen")
    
    with st.form("training_toevoegen"):
        training_datum = st.date_input("📅 Datum", value=date.today())
        training_type = st.selectbox("🏃 Type", [
            "Training", "Wedstrijd", "Vriendschappelijk", 
            "Fysieke Test", "Tactische Training", "Conditietraining",
            "Individuele Training", "Team Building"
        ])
        omschrijving = st.text_area("📝 Omschrijving", height=100)
        geplande_duur = st.number_input("⏱️ Geplande Duur (minuten)", min_value=30, max_value=180, value=90, step=15)
        
        submit_training = st.form_submit_button("✅ Training Toevoegen")
        
        if submit_training:
            try:
                if SUPABASE_MODE:
                    from supabase import create_client
                    import os
                    
                    # Get Supabase credentials from environment or secrets
                    try:
                        supabase_url = st.secrets["supabase"]["url"]
                        supabase_key = st.secrets["supabase"]["anon_key"]  # Fixed: was "key", should be "anon_key"
                        st.write(f"🔑 Using Streamlit secrets for Supabase")
                    except Exception as secrets_error:
                        st.write(f"⚠️ Streamlit secrets not available: {secrets_error}")
                        supabase_url = os.getenv("SUPABASE_URL")
                        supabase_key = os.getenv("SUPABASE_KEY")
                        if supabase_url and supabase_key:
                            st.write(f"🔑 Using environment variables for Supabase")
                        else:
                            st.write(f"❌ No Supabase credentials found in environment")
                    
                    if supabase_url and supabase_key:
                        supabase = create_client(supabase_url, supabase_key)
                        
                        # Get next ID manually (Supabase compatible way)
                        existing_df = safe_fetchdf("SELECT MAX(training_id) as max_id FROM trainings_calendar")
                        next_id = 1 if existing_df.empty or existing_df['max_id'].iloc[0] is None else existing_df['max_id'].iloc[0] + 1
                        
                        result = supabase.table('trainings_calendar').insert({
                            'training_id': next_id,
                            'datum': str(training_datum),
                            'type': training_type,
                            'omschrijving': omschrijving,
                            'geplande_duur_minuten': geplande_duur
                        }).execute()
                        
                        if result.data:
                            st.success(f"✅ Training '{training_type}' toegevoegd voor {training_datum}")
                            
                            # Auto-sync to matches table if it's a Wedstrijd or Vriendschappelijk
                            if training_type in ['Wedstrijd', 'Vriendschappelijk']:
                                try:
                                    # Auto-create match record
                                    training_data = {
                                        'training_id': next_id,
                                        'datum': str(training_datum),
                                        'type': training_type,
                                        'omschrijving': omschrijving,
                                        'tijd': '15:00'  # Default time
                                    }
                                    
                                    # Import and use auto-sync function
                                    from auto_match_sync import auto_sync_match_from_training
                                    match_id = auto_sync_match_from_training(training_data)
                                    
                                    if match_id:
                                        st.info(f"🎉 Ook automatisch toegevoegd aan wedstrijden (Match ID: {match_id})")
                                    else:
                                        st.warning("⚠️ Training toegevoegd, maar kon niet automatisch synchroniseren met wedstrijden")
                                        
                                except Exception as sync_error:
                                    st.warning(f"⚠️ Training toegevoegd, maar auto-sync naar wedstrijden mislukt: {sync_error}")
                            
                            clear_training_cache()  # Clear cache to show new training immediately
                            st.rerun()
                        else:
                            st.error("❌ Fout bij toevoegen training")
                    else:
                        st.error("❌ Supabase configuratie niet gevonden")
                else:
                    st.error("❌ Alleen Supabase mode wordt ondersteund")
                    
            except Exception as e:
                st.error(f"❌ Fout bij toevoegen training: {e}")
                st.write(f"Debug info: {str(e)}")

with col2:
    st.subheader("📅 Komende Trainingen")
    
    # Load trainings
    trainings_df = get_trainings(20)
    
    if not trainings_df.empty:
        # Filter for upcoming trainings (next 14 days)
        today = date.today()
        upcoming_date = today + timedelta(days=14)
        
        trainings_df['datum'] = pd.to_datetime(trainings_df['datum']).dt.date
        upcoming_trainings = trainings_df[
            (trainings_df['datum'] >= today) & 
            (trainings_df['datum'] <= upcoming_date)
        ].sort_values('datum')
        
        if not upcoming_trainings.empty:
            for _, training in upcoming_trainings.iterrows():
                training_id = training['training_id']
                datum = training['datum']
                training_type = training['type']
                omschrijving = training['omschrijving']
                duur = training.get('geplande_duur_minuten', 90)
                
                # Training card
                with st.container():
                    st.markdown(f"**{datum}** - {training_type}")
                    if omschrijving:
                        st.write(f"📝 {omschrijving}")
                    st.write(f"⏱️ {duur} minuten")
                    
                    col_a, col_b, col_c = st.columns(3)
                    
                    with col_a:
                        if st.button(f"👥 Aanwezigheid", key=f"attendance_{training_id}"):
                            st.session_state.selected_training_attendance = training_id
                    
                    with col_b:
                        if st.button(f"✏️ Bewerken", key=f"edit_{training_id}"):
                            st.session_state.selected_training_edit = training_id
                    
                    with col_c:
                        if st.button(f"🗑️ Verwijderen", key=f"delete_{training_id}"):
                            st.session_state.selected_training_delete = training_id
                    
                    st.divider()
        else:
            st.info("📅 Geen komende trainingen gepland")
    else:
        st.info("📅 Nog geen trainingen toegevoegd")

# Handle attendance management
if 'selected_training_attendance' in st.session_state:
    training_id = st.session_state.selected_training_attendance
    
    st.subheader(f"👥 Aanwezigheid Beheren (Training ID: {training_id})")
    
    # Get training details
    training_details = trainings_df[trainings_df['training_id'] == training_id]
    if not training_details.empty:
        training = training_details.iloc[0]
        st.write(f"📅 **{training['datum']}** - {training['type']}")
        if training['omschrijving']:
            st.write(f"📝 {training['omschrijving']}")
    
    # Get available players
    available_players = get_available_players()
    
    if available_players:
        # Get current attendance
        attendance_df = get_training_attendance(training_id)
        current_attendance = {}
        if not attendance_df.empty:
            current_attendance = dict(zip(attendance_df['speler'], attendance_df['status']))
        
        st.write("**Speler Aanwezigheid:**")
        
        # Create columns for player status
        cols = st.columns(3)
        updated_attendance = {}
        
        for i, player in enumerate(available_players):  # Show all available players
            col_idx = i % 3
            with cols[col_idx]:
                current_status = current_attendance.get(player, "Onbekend")
                status = st.selectbox(
                    f"👤 {player}", 
                    ["Aanwezig", "Afwezig", "Geblesseerd", "Onbekend"],
                    index=["Aanwezig", "Afwezig", "Geblesseerd", "Onbekend"].index(current_status),
                    key=f"status_{player}_{training_id}"
                )
                updated_attendance[player] = status
        
        if st.button("💾 Aanwezigheid Opslaan", type="primary"):
            try:
                from supabase_config import get_supabase_client
                client = get_supabase_client()
                
                # Delete existing attendance
                client.table('training_attendance').delete().eq('training_id', training_id).execute()
                
                # Insert new attendance
                for player, status in updated_attendance.items():
                    if status != "Onbekend":
                        # Get next attendance ID
                        existing_df = safe_fetchdf("SELECT MAX(attendance_id) as max_id FROM training_attendance")
                        next_attendance_id = 1 if existing_df.empty or existing_df['max_id'].iloc[0] is None else existing_df['max_id'].iloc[0] + 1
                        
                        client.table('training_attendance').insert({
                            'attendance_id': next_attendance_id,
                            'training_id': training_id,
                            'speler': player,
                            'status': status
                        }).execute()
                        next_attendance_id += 1
                
                st.success("✅ Aanwezigheid opgeslagen!")
                del st.session_state.selected_training_attendance
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ Fout bij opslaan: {e}")
    else:
        st.warning("⚠️ Geen spelers gevonden. Voeg eerst spelers toe via andere modules.")
    
    if st.button("❌ Annuleren"):
        del st.session_state.selected_training_attendance
        st.rerun()

# Handle training deletion
if 'selected_training_delete' in st.session_state:
    training_id = st.session_state.selected_training_delete
    
    st.error(f"🗑️ Training verwijderen (ID: {training_id})")
    st.write("⚠️ Dit zal de training en alle aanwezigheidsgegevens permanent verwijderen.")
    
    col_confirm, col_cancel = st.columns(2)
    
    with col_confirm:
        if st.button("✅ Ja, Verwijderen", type="primary"):
            try:
                from supabase_config import get_supabase_client
                client = get_supabase_client()
                
                # Delete attendance first
                client.table('training_attendance').delete().eq('training_id', training_id).execute()
                
                # Delete training
                client.table('trainings_calendar').delete().eq('training_id', training_id).execute()
                
                st.success("✅ Training verwijderd!")
                del st.session_state.selected_training_delete
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ Fout bij verwijderen: {e}")
    
    with col_cancel:
        if st.button("❌ Annuleren"):
            del st.session_state.selected_training_delete
            st.rerun()

# Training geschiedenis en statistieken  
st.divider()

# Tabs voor huidige vs historische trainingen
hist_tab1, hist_tab2 = st.tabs(["📅 Afgelopen Trainingen", "📊 Training Statistieken"])

with hist_tab1:
    st.subheader("📅 Afgelopen Trainingen")
    
    # Debug controls
    col_debug, col_refresh = st.columns([3, 1])
    with col_debug:
        if st.button("🔄 Ververs Cache", help="Forceer het verversen van training data"):
            clear_training_cache()
            st.success("✅ Cache geleegd! De pagina wordt automatisch ververst.")
            st.rerun()
    with col_refresh:
        show_debug = st.checkbox("🔍 Debug Info")
    
    # Filter opties voor historische trainingen
    col_period, col_type = st.columns(2)
    
    with col_period:
        period_options = {
            "Laatste 7 dagen": 7,
            "Laatste 14 dagen": 14, 
            "Laatste 30 dagen": 30,
            "Laatste 3 maanden": 90,
            "Alle trainingen": 365
        }
        selected_period = st.selectbox("📅 Periode", list(period_options.keys()), index=1)
        days_back = period_options[selected_period]
    
    with col_type:
        # Get unique training types for filter
        all_trainings = get_trainings(100)  # Get more trainings for filtering
        training_types = ["Alle"] + sorted(all_trainings['type'].unique().tolist()) if not all_trainings.empty else ["Alle"]
        selected_type = st.selectbox("🏃 Type Filter", training_types)
    
    # Load historical trainings
    if not all_trainings.empty:
        # Apply date filter
        end_date = date.today()
        start_date = end_date - timedelta(days=days_back)
        
        # Debug info
        if show_debug:
            st.write(f"🔍 Debug Info:")
            st.write(f"   📅 Datum range: {start_date} tot {end_date}")
            st.write(f"   📊 Totaal aantal trainingen geladen: {len(all_trainings)}")
            st.write("   📋 Alle trainingen:")
            for _, t in all_trainings.iterrows():
                st.write(f"      - ID {t['training_id']}: {t['datum']} - {t['type']}")
        
        all_trainings['datum'] = pd.to_datetime(all_trainings['datum']).dt.date
        historical_trainings = all_trainings[
            (all_trainings['datum'] <= end_date) & 
            (all_trainings['datum'] >= start_date)
        ].sort_values('datum', ascending=False)
        
        # More debug info
        if show_debug:
            st.write(f"   📊 Na datum filtering: {len(historical_trainings)} trainingen")
            if not historical_trainings.empty:
                st.write("   📋 Gefilterde trainingen:")
                for _, t in historical_trainings.iterrows():
                    st.write(f"      - ID {t['training_id']}: {t['datum']} - {t['type']}")
        
        # Apply type filter
        if selected_type != "Alle":
            historical_trainings = historical_trainings[historical_trainings['type'] == selected_type]
        
        if not historical_trainings.empty:
            st.info(f"📊 {len(historical_trainings)} trainingen gevonden in de periode {start_date} tot {end_date}" + 
                   (f" (Type: {selected_type})" if selected_type != "Alle" else ""))
            
            # Detailed training cards
            for idx, training in historical_trainings.iterrows():
                training_id = training['training_id']
                datum = training['datum']
                training_type = training['type']
                omschrijving = training['omschrijving']
                duur = training.get('geplande_duur_minuten', 90)
                
                # Create unique identifier using row index to avoid duplicate ID issues
                unique_key = f"{training_id}_{datum}_{training_type}_{idx}"
                
                # Calculate days ago
                days_ago = (date.today() - datum).days
                if days_ago == 0:
                    date_display = "Vandaag"
                elif days_ago == 1:
                    date_display = "Gisteren"
                else:
                    date_display = f"{days_ago} dagen geleden"
                
                with st.expander(f"📅 {datum} - {training_type} ({date_display})"):
                    col_info, col_actions = st.columns([2, 1])
                    
                    with col_info:
                        st.write(f"**📅 Datum**: {datum}")
                        st.write(f"**🏃 Type**: {training_type}")
                        if omschrijving:
                            st.write(f"**📝 Omschrijving**: {omschrijving}")
                        st.write(f"**⏱️ Duur**: {duur} minuten")
                    
                    with col_actions:
                        if st.button(f"👥 Bekijken", key=f"view_attendance_{unique_key}"):
                            st.session_state.view_training_attendance = training_id
                            # Clear other states
                            if 'edit_training_id' in st.session_state:
                                del st.session_state.edit_training_id
                            if 'delete_training_id' in st.session_state:
                                del st.session_state.delete_training_id
                            if 'delete_training_data' in st.session_state:
                                del st.session_state.delete_training_data
                            st.rerun()
                            
                        if st.button(f"✏️ Bewerken", key=f"edit_training_{unique_key}"):
                            # Store both training_id and the specific training data
                            st.session_state.edit_training_id = training_id
                            st.session_state.edit_training_data = {
                                'training_id': training_id,
                                'datum': datum,
                                'type': training_type,
                                'omschrijving': omschrijving,
                                'geplande_duur_minuten': duur,
                                'row_index': idx
                            }
                            # Clear other states
                            if 'view_training_attendance' in st.session_state:
                                del st.session_state.view_training_attendance
                            if 'delete_training_id' in st.session_state:
                                del st.session_state.delete_training_id
                            if 'delete_training_data' in st.session_state:
                                del st.session_state.delete_training_data
                            st.write(f"🔧 Selected training {training_id} ({datum} - {training_type}) for editing")
                            st.rerun()
                            
                        if st.button(f"🗑️ Verwijderen", key=f"delete_training_{unique_key}"):
                            # Store both training_id and the specific training data  
                            st.session_state.delete_training_id = training_id
                            st.session_state.delete_training_data = {
                                'training_id': training_id,
                                'datum': datum,
                                'type': training_type,
                                'omschrijving': omschrijving,
                                'geplande_duur_minuten': duur,
                                'row_index': idx
                            }
                            # Clear other states
                            if 'view_training_attendance' in st.session_state:
                                del st.session_state.view_training_attendance
                            if 'edit_training_id' in st.session_state:
                                del st.session_state.edit_training_id
                            st.write(f"🗑️ Selected training {training_id} ({datum} - {training_type}) for deletion")
                            st.rerun()
                    
                    # Show attendance summary if available
                    attendance_df = get_training_attendance(training_id)
                    if not attendance_df.empty:
                        st.markdown("**👥 Aanwezigheid Samenvatting:**")
                        
                        attendance_summary = attendance_df['status'].value_counts()
                        col_aanwezig, col_afwezig, col_geblesseerd = st.columns(3)
                        
                        with col_aanwezig:
                            aanwezig = attendance_summary.get('Aanwezig', 0)
                            st.metric("✅ Aanwezig", aanwezig)
                        
                        with col_afwezig:
                            afwezig = attendance_summary.get('Afwezig', 0)
                            st.metric("❌ Afwezig", afwezig)
                        
                        with col_geblesseerd:
                            geblesseerd = attendance_summary.get('Geblesseerd', 0)
                            st.metric("🏥 Geblesseerd", geblesseerd)
                        
                        # Show player list in compact format
                        if len(attendance_df) > 0:
                            players_by_status = {}
                            for _, row in attendance_df.iterrows():
                                status = row['status']
                                if status not in players_by_status:
                                    players_by_status[status] = []
                                players_by_status[status].append(row['speler'])
                            
                            for status, players in players_by_status.items():
                                if players:
                                    emoji = "✅" if status == "Aanwezig" else "❌" if status == "Afwezig" else "🏥"
                                    st.write(f"{emoji} **{status}**: {', '.join(players[:5])}" + 
                                           (f" (+{len(players)-5} meer)" if len(players) > 5 else ""))
                    else:
                        st.info("📋 Geen aanwezigheidsgegevens beschikbaar voor deze training")
        else:
            st.info(f"📅 Geen trainingen gevonden in de geselecteerde periode" + 
                   (f" voor type '{selected_type}'" if selected_type != "Alle" else ""))
    else:
        st.info("📅 Geen historische trainingen beschikbaar")

# Handle detailed attendance viewing
if 'view_training_attendance' in st.session_state:
    training_id = st.session_state.view_training_attendance
    
    st.subheader(f"👥 Gedetailleerde Aanwezigheid (Training ID: {training_id})")
    
    # Get training details
    training_details = all_trainings[all_trainings['training_id'] == training_id] if not all_trainings.empty else pd.DataFrame()
    if not training_details.empty:
        training = training_details.iloc[0]
        st.write(f"📅 **{training['datum']}** - {training['type']}")
        if training['omschrijving']:
            st.write(f"📝 {training['omschrijving']}")
    
    # Show detailed attendance
    attendance_df = get_training_attendance(training_id)
    if not attendance_df.empty:
        st.markdown("**👥 Volledige Aanwezigheidslijst:**")
        
        # Group by status for better display
        for status in ['Aanwezig', 'Afwezig', 'Geblesseerd']:
            status_players = attendance_df[attendance_df['status'] == status]
            if not status_players.empty:
                emoji = "✅" if status == "Aanwezig" else "❌" if status == "Afwezig" else "🏥"
                st.write(f"{emoji} **{status} ({len(status_players)} spelers):**")
                
                # Display players in columns
                players = status_players['speler'].tolist()
                cols = st.columns(3)
                for i, player in enumerate(players):
                    with cols[i % 3]:
                        st.write(f"• {player}")
                
                st.write("")  # Add spacing
    else:
        st.info("📋 Geen aanwezigheidsgegevens gevonden voor deze training")
    
    if st.button("❌ Sluiten"):
        del st.session_state.view_training_attendance
        st.rerun()

with hist_tab2:
    st.subheader("📊 Training Statistieken")

    # Get attendance data for statistics
    try:
        # Recent trainings with attendance
        recent_trainings = safe_fetchdf("""
            SELECT t.training_id, t.datum, t.type, 
                   COUNT(ta.speler) as aantal_spelers,
                   SUM(CASE WHEN ta.status = 'Aanwezig' THEN 1 ELSE 0 END) as aanwezig,
                   SUM(CASE WHEN ta.status = 'Afwezig' THEN 1 ELSE 0 END) as afwezig,
                   SUM(CASE WHEN ta.status = 'Geblesseerd' THEN 1 ELSE 0 END) as geblesseerd
            FROM trainings_calendar t
            LEFT JOIN training_attendance ta ON t.training_id = ta.training_id
            WHERE t.datum >= (CURRENT_DATE - INTERVAL '30 days')
            GROUP BY t.training_id, t.datum, t.type
            ORDER BY t.datum DESC
        """)
        
        if not recent_trainings.empty:
            col1, col2, col3 = st.columns(3)
            
            with col1:
                total_trainings = len(recent_trainings)
                st.metric("🏃 Trainingen (30 dagen)", total_trainings)
            
            with col2:
                avg_attendance = recent_trainings['aanwezig'].mean() if 'aanwezig' in recent_trainings.columns else 0
                st.metric("👥 Gem. Aanwezigheid", f"{avg_attendance:.1f}")
            
            with col3:
                total_players = recent_trainings['aantal_spelers'].sum() if 'aantal_spelers' in recent_trainings.columns else 0
                st.metric("📊 Totaal Deelnames", total_players)
            
            # Recent trainings table
            st.markdown("**Recente Trainingen:**")
            display_df = recent_trainings[['datum', 'type', 'aanwezig', 'afwezig', 'geblesseerd']].copy()
            display_df.columns = ['Datum', 'Type', 'Aanwezig', 'Afwezig', 'Geblesseerd']
            st.dataframe(display_df, use_container_width=True)
        else:
            st.info("📊 Nog geen training statistieken beschikbaar")
            
    except Exception as e:
        st.warning(f"⚠️ Statistieken tijdelijk niet beschikbaar: {e}")
        # Show basic training count
        trainings_df = get_trainings(20)
        if not trainings_df.empty:
            st.metric("🏃 Totaal Trainingen", len(trainings_df))

# Handle training editing
if 'edit_training_id' in st.session_state:
    training_id = st.session_state.edit_training_id
    
    st.subheader(f"✏️ Training {training_id} Bewerken")
    
    # Use stored training data if available, otherwise fall back to database lookup
    if 'edit_training_data' in st.session_state:
        training_data = st.session_state.edit_training_data
        st.success(f"✅ Loaded specific training: {training_data['datum']} - {training_data['type']}")
        
        # Convert to the expected format
        training = {
            'training_id': training_data['training_id'],
            'datum': training_data['datum'], 
            'type': training_data['type'],
            'omschrijving': training_data['omschrijving'],
            'geplande_duur_minuten': training_data['geplande_duur_minuten']
        }
        training_found = True
    else:
        # Fallback to database lookup (may select wrong training if duplicates exist)
        st.warning("⚠️ Using database lookup - may not be exact training due to duplicate IDs")
        all_trainings = get_trainings(100)
        training_details = all_trainings[all_trainings['training_id'] == training_id] if not all_trainings.empty else pd.DataFrame()
        
        if not training_details.empty:
            training = training_details.iloc[0]
            training_found = True
        else:
            training_found = False
    
    if training_found:
        
        with st.form("edit_training_form"):
            st.markdown("### 📝 Training Details")
            edit_datum = st.date_input("📅 Datum", value=training['datum'])
            edit_type = st.selectbox("🏃 Type", [
                "Training", "Wedstrijd", "Vriendschappelijk", 
                "Fysieke Test", "Tactische Training", "Conditietraining",
                "Individuele Training", "Team Building"
            ], index=0 if training['type'] not in ["Training", "Wedstrijd", "Vriendschappelijk", "Fysieke Test", "Tactische Training", "Conditietraining", "Individuele Training", "Team Building"] else ["Training", "Wedstrijd", "Vriendschappelijk", "Fysieke Test", "Tactische Training", "Conditietraining", "Individuele Training", "Team Building"].index(training['type']))
            edit_omschrijving = st.text_area("📝 Omschrijving", value=training.get('omschrijving', ''), height=100)
            edit_duur = st.number_input("⏱️ Geplande Duur (minuten)", value=int(training.get('geplande_duur_minuten', 90)), min_value=15, max_value=300, step=15)
            
            col_save, col_cancel = st.columns(2)
            with col_save:
                save_changes = st.form_submit_button("💾 Wijzigingen Opslaan", type="primary")
            with col_cancel:
                cancel_edit = st.form_submit_button("❌ Annuleren")
            
            if save_changes:
                if update_training(training_id, edit_datum, edit_type, edit_omschrijving, edit_duur):
                    st.success("✅ Training succesvol bijgewerkt!")
                    del st.session_state.edit_training_id
                    if 'edit_training_data' in st.session_state:
                        del st.session_state.edit_training_data
                    clear_training_cache()  # Clear cache to show updated training
                    st.rerun()
                else:
                    st.error("❌ Er is een fout opgetreden bij het bijwerken van de training")
            
            if cancel_edit:
                del st.session_state.edit_training_id
                if 'edit_training_data' in st.session_state:
                    del st.session_state.edit_training_data
                st.rerun()
        
        # Show attendance editing
        st.markdown("### 👥 Aanwezigheid Bewerken")
        attendance_df = get_training_attendance(training_id)
        available_players = get_available_players()
        
        if available_players:
            # Show current attendance
            if not attendance_df.empty:
                st.markdown("**Huidige Aanwezigheid:**")
                for _, row in attendance_df.iterrows():
                    col_player, col_status, col_action = st.columns([2, 1, 1])
                    with col_player:
                        st.write(f"👤 {row['speler']}")
                    with col_status:
                        current_status = row['status']
                        status_emoji = "✅" if current_status == "Aanwezig" else "❌" if current_status == "Afwezig" else "🏥"
                        st.write(f"{status_emoji} {current_status}")
                    with col_action:
                        new_status = st.selectbox("Status", ["Aanwezig", "Afwezig", "Geblesseerd"], 
                                                index=["Aanwezig", "Afwezig", "Geblesseerd"].index(current_status),
                                                key=f"status_{training_id}_{row['speler']}")
                        if new_status != current_status:
                            if st.button("💾", key=f"update_status_{training_id}_{row['speler']}"):
                                if update_attendance_status(training_id, row['speler'], new_status):
                                    st.success(f"Status van {row['speler']} bijgewerkt naar {new_status}")
                                    st.rerun()
            
            # Add new attendance
            st.markdown("**Speler Toevoegen:**")
            # Filter out players already in attendance
            existing_players = attendance_df['speler'].tolist() if not attendance_df.empty else []
            remaining_players = [p for p in available_players if p not in existing_players]
            
            if remaining_players:
                col_add_player, col_add_status, col_add_btn = st.columns([2, 1, 1])
                with col_add_player:
                    add_player = st.selectbox("Speler selecteren", remaining_players, key=f"add_player_{training_id}")
                with col_add_status:
                    add_status = st.selectbox("Status", ["Aanwezig", "Afwezig", "Geblesseerd"], key=f"add_status_{training_id}")
                with col_add_btn:
                    if st.button("➕ Toevoegen", key=f"add_attendance_{training_id}"):
                        if update_attendance_status(training_id, add_player, add_status):
                            st.success(f"{add_player} toegevoegd als {add_status}")
                            st.rerun()
            else:
                st.info("Alle spelers hebben al een aanwezigheidsstatus voor deze training")
    else:
        st.error("Training niet gevonden")
        if st.button("❌ Terug"):
            del st.session_state.edit_training_id
            st.rerun()

# Handle training deletion
if 'delete_training_id' in st.session_state:
    training_id = st.session_state.delete_training_id
    
    st.subheader(f"🗑️ Training {training_id} Verwijderen")
    
    # Use stored training data if available, otherwise fall back to database lookup
    if 'delete_training_data' in st.session_state:
        training_data = st.session_state.delete_training_data
        st.success(f"✅ Loaded specific training: {training_data['datum']} - {training_data['type']}")
        
        # Convert to the expected format
        training = {
            'training_id': training_data['training_id'],
            'datum': training_data['datum'], 
            'type': training_data['type'],
            'omschrijving': training_data['omschrijving'],
            'geplande_duur_minuten': training_data['geplande_duur_minuten']
        }
        training_found = True
    else:
        # Fallback to database lookup (may select wrong training if duplicates exist)
        st.warning("⚠️ Using database lookup - may not be exact training due to duplicate IDs")
        all_trainings = get_trainings(100)
        training_details = all_trainings[all_trainings['training_id'] == training_id] if not all_trainings.empty else pd.DataFrame()
        
        if not training_details.empty:
            training = training_details.iloc[0]
            training_found = True
        else:
            training_found = False
    
    if training_found:
        
        st.warning("⚠️ **LET OP**: Deze actie kan niet ongedaan worden gemaakt!")
        
        st.markdown("### Trainingsdetails die worden verwijderd:")
        st.write(f"**📅 Datum**: {training['datum']}")
        st.write(f"**🏃 Type**: {training['type']}")
        if training.get('omschrijving'):
            st.write(f"**📝 Omschrijving**: {training['omschrijving']}")
        
        # Show attendance that will be deleted
        attendance_df = get_training_attendance(training_id)
        if not attendance_df.empty:
            st.write(f"**👥 Aanwezigheidsgegevens**: {len(attendance_df)} spelers worden ook verwijderd")
            
            with st.expander("Toon aanwezigheidsgegevens die worden verwijderd"):
                for status in ['Aanwezig', 'Afwezig', 'Geblesseerd']:
                    status_players = attendance_df[attendance_df['status'] == status]
                    if not status_players.empty:
                        emoji = "✅" if status == "Aanwezig" else "❌" if status == "Afwezig" else "🏥"
                        st.write(f"{emoji} **{status}**: {', '.join(status_players['speler'].tolist())}")
        
        st.markdown("---")
        
        col_delete, col_cancel = st.columns(2)
        
        with col_delete:
            confirm_text = st.text_input("Type 'VERWIJDER' om te bevestigen:", key=f"confirm_delete_{training_id}")
            if st.button("🗑️ DEFINITIEF VERWIJDEREN", type="secondary", disabled=(confirm_text != "VERWIJDER"), key=f"final_delete_{training_id}"):
                # Pass specific training data if available for precise deletion
                specific_data = st.session_state.get('delete_training_data')
                if delete_training(training_id, specific_data):
                    st.success("✅ Training en alle gerelateerde gegevens zijn succesvol verwijderd!")
                    del st.session_state.delete_training_id
                    if 'delete_training_data' in st.session_state:
                        del st.session_state.delete_training_data
                    clear_training_cache()  # Clear cache to refresh training list
                    st.rerun()
                else:
                    st.error("❌ Er is een fout opgetreden bij het verwijderen van de training")
        
        with col_cancel:
            st.write("")  # Spacing
            st.write("")  # Spacing  
            if st.button("❌ Annuleren", key=f"cancel_delete_{training_id}"):
                del st.session_state.delete_training_id
                if 'delete_training_data' in st.session_state:
                    del st.session_state.delete_training_data
                st.rerun()
    else:
        st.error("Training niet gevonden")
        if st.button("❌ Terug"):
            del st.session_state.delete_training_id
            if 'delete_training_data' in st.session_state:
                del st.session_state.delete_training_data
            st.rerun()