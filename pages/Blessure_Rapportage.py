import streamlit as st
import sqlite3
import datetime
import pandas as pd

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

# Database setup
if SUPABASE_MODE:
    st.info("🌐 Using Supabase database")
    if not test_supabase_connection():
        st.error("❌ Cannot connect to Supabase")
        st.stop()
    con = None  # Will use Supabase helpers
else:
    # Legacy mode
    try:
        con = get_database_connection()
    except NameError:
        st.error("❌ Database connection not available")
        st.stop()
import pandas as pd
import datetime
from typing import Optional
import sqlite3
import os

def show_blessure_rapportage():
    st.markdown("""
    <style>
        .injury-form {
            background: linear-gradient(135deg, #FAFCFF 0%, #E8F4FD 100%);
            padding: 1.5rem;
            border-radius: 10px;
            border-left: 4px solid #2E86AB;
            margin: 1rem 0;
            box-shadow: 0 2px 4px rgba(46, 134, 171, 0.1);
        }
        
        .injury-card {
            background: white;
            padding: 1.2rem;
            border-radius: 8px;
            border: 1px solid #E8F4FD;
            margin: 0.8rem 0;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        
        .injury-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(46, 134, 171, 0.15);
        }
        
        .status-active { color: #E74C3C; font-weight: bold; }
        .status-recovery { color: #F39C12; font-weight: bold; }
        .status-healed { color: #27AE60; font-weight: bold; }
        .status-healthy { 
            color: #2E8B57; 
            font-weight: bold; 
            background: linear-gradient(135deg, #F0FDF4 0%, #DCFCE7 100%);
            border-left: 4px solid #2E8B57 !important;
        }
        .accent-blue { color: #2E86AB; font-weight: bold; }
        .accent-orange { color: #F18F01; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)
    
    
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

def init_database():
    """Initialiseer SQLite database voor blessure tracking"""
    db_path = "blessures.db"
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS blessures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            speler_naam TEXT NOT NULL,
            blessure_type TEXT NOT NULL,
            locatie TEXT NOT NULL,
            ernst TEXT NOT NULL,
            datum_start DATE NOT NULL,
            datum_einde DATE,
            voorspelling_dagen INTEGER,
            status TEXT NOT NULL,
            beschrijving TEXT,
            behandeling TEXT,
            opmerkingen TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()

def show_injury_form():
    """Formulier voor nieuwe blessure rapportage"""
    st.markdown('<div class="injury-form">', unsafe_allow_html=True)
    st.markdown("### <span class='accent-blue'>🩹 Nieuwe Blessure Rapporteren</span>", unsafe_allow_html=True)
    
    # Haal spelersnamen op uit database
    players = get_player_names()
    
    with st.form("injury_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            speler_naam = st.selectbox(
                "Speler Naam *", 
                options=[""] + players,
                help="Selecteer de speler uit de database"
            )
            
            blessure_type = st.selectbox(
                "Type Blessure *",
                [
                    "Spierblessure",
                    "Gewrichtsblessure", 
                    "Overbelasting",
                    "Traumatisch",
                    "Huidwond",
                    "Andere"
                ]
            )
            
            locatie = st.selectbox(
                "Locatie *",
                [
                    "Enkel",
                    "Knie",
                    "Hamstring",
                    "Quadriceps",
                    "Kuit",
                    "Voet",
                    "Rug",
                    "Schouder",
                    "Elleboog",
                    "Pols/Hand",
                    "Hoofd/Nek",
                    "Andere"
                ]
            )
            
            ernst = st.selectbox(
                "Ernst *",
                ["Licht", "Matig", "Zwaar", "Zeer zwaar"]
            )
        
        with col2:
            datum_start = st.date_input(
                "Datum Blessure *",
                value=datetime.date.today(),
                help="Datum waarop de blessure is opgetreden"
            )
            
            voorspelling_dagen = st.number_input(
                "Voorspelde uitval (dagen) *",
                min_value=0,
                max_value=365,
                value=7,
                help="Geschatte duur van uitval in dagen"
            )
            
            status = st.selectbox(
                "Huidige Status *",
                ["Actief", "In behandeling", "Genezen"]
            )
            
            datum_einde = st.date_input(
                "Herstel Datum (optioneel)",
                value=None,
                help="Alleen invullen als speler volledig hersteld is"
            )
        
        beschrijving = st.text_area(
            "Beschrijving Incident",
            help="Gedetailleerde beschrijving van hoe de blessure ontstond"
        )
        
        behandeling = st.text_area(
            "Behandelplan",
            help="Geplande of lopende behandeling"
        )
        
        opmerkingen = st.text_area(
            "Opmerkingen",
            help="Aanvullende opmerkingen of observaties"
        )
        
        submitted = st.form_submit_button("💾 Blessure Opslaan", type="primary")
        
        if submitted:
            if speler_naam and blessure_type and locatie and ernst:
                success = save_injury(
                    speler_naam, blessure_type, locatie, ernst,
                    datum_start, datum_einde, voorspelling_dagen,
                    status, beschrijving, behandeling, opmerkingen
                )
                if success:
                    st.success("✅ Blessure succesvol opgeslagen!")
                    st.rerun()
                else:
                    st.error("❌ Fout bij opslaan van blessure")
            else:
                st.error("❌ Vul alle verplichte velden in (*)")
    
    st.markdown('</div>', unsafe_allow_html=True)

def save_injury(speler_naam, blessure_type, locatie, ernst, datum_start, datum_einde, 
                voorspelling_dagen, status, beschrijving, behandeling, opmerkingen):
    """Sla nieuwe blessure op in database"""
    if SUPABASE_MODE:
        try:
            from supabase_config import get_supabase_client
            supabase = get_supabase_client()
            
            # Prepare data for Supabase insert - using existing columns only
            # Map to existing column names from original schema
            injury_data = {
                'speler': speler_naam,
                'blessure_type': blessure_type,
                'datum_blessure': str(datum_start),  # Use existing column name
                'verwachte_herstel': str(datum_einde) if datum_einde else None,  # Use existing column name
                'status': status,
                'kine_comments': f"Locatie: {locatie}, Ernst: {ernst}, Voorspelling: {voorspelling_dagen} dagen\n\nBeschrijving: {beschrijving}\n\nBehandeling: {behandeling}\n\nOpmerkingen: {opmerkingen}",  # Combine all extra info
                'created_at': datetime.datetime.now().isoformat()
            }
            
            result = supabase.table('blessures').insert(injury_data).execute()
            if not result.data:
                st.error("Failed to save injury to Supabase")
                return False
            return True
            
        except Exception as e:
            st.error(f"Error saving injury: {e}")
            return False
    else:
        # Legacy SQLite mode
        conn = sqlite3.connect("blessures.db")
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO blessures (
                speler_naam, blessure_type, locatie, ernst, datum_start, 
                datum_einde, voorspelling_dagen, status, beschrijving, 
                behandeling, opmerkingen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            speler_naam, blessure_type, locatie, ernst, datum_start,
            datum_einde, voorspelling_dagen, status, beschrijving,
            behandeling, opmerkingen
        ))
        
        conn.commit()
        conn.close()
        return True

def show_injury_overview():
    """Overzicht van alle blessures"""
    st.markdown("### <span class='accent-blue'>📋 Blessure Status - Alle Spelers</span>", unsafe_allow_html=True)
    
    # Haal ALLE actieve spelers op uit spelersbeheer
    try:
        # Use the existing get_player_names function which handles both modes
        player_names = get_player_names()
        if not player_names:
            st.warning("Geen spelers gevonden in het systeem. Voeg eerst spelers toe via Spelersbeheer.")
            return
        
        # Convert to DataFrame format expected by merge
        all_players = pd.DataFrame({'naam': player_names})
        
    except Exception as e:
        st.error(f"Kon spelers niet ophalen uit database: {e}")
        return
    
    if all_players.empty:
        st.warning("Geen spelers gevonden in het systeem. Voeg eerst spelers toe via Spelersbeheer.")
        return
    
    # Haal blessure data op
    injury_df = get_injuries_dataframe()
    
    # Merge alle spelers met blessure data (LEFT JOIN)
    if not injury_df.empty:
        # Handle column name differences between SQLite and Supabase
        merge_column = 'speler' if 'speler' in injury_df.columns else 'speler_naam'
        player_injury_status = all_players.merge(
            injury_df, 
            left_on='naam', 
            right_on=merge_column, 
            how='left'
        )
    else:
        # Als geen blessures, maak placeholder dataframe
        player_injury_status = all_players.copy()
        player_injury_status['blessure_type'] = None
        player_injury_status['status'] = None
        player_injury_status['ernst'] = None
        player_injury_status['datum_start'] = None
        player_injury_status['voorspelling_dagen'] = None
    
    # Filter opties
    col1, col2, col3 = st.columns(3)
    
    with col1:
        status_filter = st.selectbox(
            "Filter op Status",
            ["Alle", "Gezond", "Actief", "In behandeling", "Genezen"]
        )
    
    with col2:
        speler_filter = st.selectbox(
            "Filter op Speler", 
            ["Alle"] + sorted(all_players['naam'].tolist())
        )
    
    with col3:
        ernst_filter = st.selectbox(
            "Filter op Ernst",
            ["Alle", "Licht", "Matig", "Zwaar", "Zeer zwaar"]
        )
    
    # Filter dataframe
    filtered_df = player_injury_status.copy()
    
    # Status filtering (inclusief gezonde spelers)
    if status_filter == "Gezond":
        filtered_df = filtered_df[filtered_df['status'].isna()]
    elif status_filter != "Alle":
        filtered_df = filtered_df[filtered_df['status'] == status_filter]
    
    # Speler filtering
    if speler_filter != "Alle":
        filtered_df = filtered_df[filtered_df['naam'] == speler_filter]
    
    # Ernst filtering
    if ernst_filter != "Alle" and 'ernst' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['ernst'] == ernst_filter]
    
    # Toon blessures als cards
    for _, injury in filtered_df.iterrows():
        show_injury_card(injury)
    
    # Toon ook tabel voor overzicht
    if not filtered_df.empty:
        st.markdown("### <span class='accent-blue'>📊 Tabel Overzicht</span>", unsafe_allow_html=True)
        
        # Bereken dagen uit roulatie voor spelers met blessures
        filtered_df['dagen_uit'] = filtered_df.apply(
            lambda row: calculate_days_out(row) if pd.notna(row.get('status')) else 0, 
            axis=1
        )
        
        # Maak display kolommen - veilig voor ontbrekende kolommen
        display_df = filtered_df.copy()
        display_df['speler_naam'] = display_df['naam']  # Gebruik naam kolom
        display_df['blessure_status'] = display_df.get('status', pd.Series()).fillna('Gezond')
        display_df['blessure_type'] = display_df.get('blessure_type', pd.Series()).fillna('Geen')
        display_df['ernst'] = display_df.get('ernst', pd.Series()).fillna('-')
        display_df['dagen_uit'] = display_df.get('dagen_uit', pd.Series()).fillna(0)
        
        # Zorg ervoor dat alle benodigde kolommen bestaan
        required_columns = ['speler_naam', 'blessure_status', 'blessure_type', 'ernst', 'datum_start', 'voorspelling_dagen', 'dagen_uit']
        for col in required_columns:
            if col not in display_df.columns:
                display_df[col] = '-' if col not in ['dagen_uit'] else 0
        
        # Selecteer relevante kolommen voor tabel
        table_df = display_df[required_columns].copy()
        
        st.dataframe(
            table_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "speler_naam": "Speler",
                "blessure_status": "Status", 
                "blessure_type": "Type Blessure",
                "ernst": "Ernst",
                "datum_start": "Start Datum",
                "voorspelling_dagen": "Voorspelling (dagen)",
                "dagen_uit": "Dagen Uit"
            }
        )
        
        # Statistieken
        st.markdown("### <span class='accent-orange'>📈 Statistieken</span>", unsafe_allow_html=True)
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_players = len(display_df)
            st.metric("👥 Totaal Spelers", total_players)
        
        with col2:
            healthy_players = len(display_df[display_df['blessure_status'] == 'Gezond'])
            st.metric("✅ Gezonde Spelers", healthy_players, delta=f"{(healthy_players/total_players*100):.0f}%")
        
        with col3:
            injured_players = len(display_df[display_df['blessure_status'] != 'Gezond'])
            st.metric("🩹 Geblesseerde Spelers", injured_players)
        
        with col4:
            if injured_players > 0:
                avg_days_out = display_df[display_df['dagen_uit'] > 0]['dagen_uit'].mean()
                st.metric("📊 Gem. Dagen Uit", f"{avg_days_out:.1f}" if pd.notna(avg_days_out) else "0")
            else:
                st.metric("📊 Gem. Dagen Uit", "0")

def show_injury_card(player):
    """Toon individuele speler card (met of zonder blessure)"""
    
    # Check of speler een blessure heeft
    if pd.isna(player['status']) or player['status'] is None:
        # Gezonde speler - gebruik Streamlit containers
        with st.container():
            st.success(f"👤 **{player['naam']}** - ✅ **Gezond**")
            st.info("🎯 Geen blessures geregistreerd - Speler is beschikbaar voor training en wedstrijden")
            st.divider()
    else:
        # Speler met blessure
        status_colors = {
            "Actief": "🔴",
            "In behandeling": "🟡", 
            "Genezen": "🟢"
        }
        
        dagen_uit = calculate_days_out(player)
        # Handle different column names for player name
        speler_naam = player.get('naam') or player.get('speler_naam') or player.get('speler')
        
        with st.container():
            # Header met status
            status_icon = status_colors.get(player['status'], '⚪')
            if player['status'] == 'Actief':
                st.error(f"👤 **{speler_naam}** - {status_icon} **{player['status']}**")
            elif player['status'] == 'In behandeling':
                st.warning(f"👤 **{speler_naam}** - {status_icon} **{player['status']}**")
            else:
                st.success(f"👤 **{speler_naam}** - {status_icon} **{player['status']}**")
            
            # Details in kolommen
            col1, col2 = st.columns(2)
            
            with col1:
                st.write(f"🩹 **Type:** {player.get('blessure_type') or 'N/A'}")
                st.write(f"📍 **Locatie:** {player.get('locatie') or 'N/A'}")
                st.write(f"⚠️ **Ernst:** {player.get('ernst') or 'N/A'}")
            
            with col2:
                st.write(f"📅 **Datum:** {player.get('datum_start') or player.get('datum_blessure') or 'N/A'}")
                st.write(f"⏱️ **Voorspelling:** {player.get('voorspelling_dagen') or 'N/A'} dagen")
                st.write(f"📊 **Actueel uit:** {dagen_uit} dagen")
            
            # Extra informatie
            if 'beschrijving' in player and player['beschrijving']:
                st.write(f"📝 **Beschrijving:** {player['beschrijving']}")
            
            if 'behandeling' in player and player['behandeling']:
                st.write(f"🏥 **Behandeling:** {player['behandeling']}")
            
            if 'opmerkingen' in player and player['opmerkingen']:
                st.write(f"💭 **Opmerkingen:** {player['opmerkingen']}")
            
            # Timestamps
            if 'created_at' in player and player['created_at']:
                st.caption(f"Aangemaakt: {player['created_at'][:10]}")
            
            # Update en Delete knoppen voor elke blessure (alleen als speler een blessure heeft)
            if pd.notna(player.get('status')):  # Only show for players with injuries
                # Try different possible ID fields
                injury_id = (player.get('blessure_id') or 
                           player.get('id') or 
                           player.get('injury_id') or
                           f"{speler_naam}_{player.get('datum_blessure', 'unknown')}")  # Fallback to composite key
                
                if injury_id and injury_id != 'None':
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if st.button(f"✏️ Update {speler_naam}", key=f"update_{injury_id}"):
                            show_update_form(player)
                    
                    with col2:
                        if st.button(f"🗑️ Verwijder", key=f"delete_{injury_id}", type="secondary"):
                            if st.session_state.get(f"confirm_delete_{injury_id}", False):
                                success = delete_injury(injury_id)
                                if success:
                                    st.success(f"Blessure van {speler_naam} is verwijderd!")
                                    st.rerun()
                                else:
                                    st.error("❌ Fout bij verwijderen van blessure")
                            else:
                                st.session_state[f"confirm_delete_{injury_id}"] = True
                                st.warning("Klik nogmaals om te bevestigen")
                                st.rerun()
            
            st.divider()

def show_update_form(injury):
    """Toon update formulier voor bestaande blessure"""
    st.markdown("### 🔄 Blessure Updaten")
    
    injury_id = injury.get('blessure_id') or injury.get('id')
    with st.form(f"update_form_{injury_id}"):
        col1, col2 = st.columns(2)
        
        with col1:
            new_status = st.selectbox(
                "Status",
                ["Actief", "In behandeling", "Genezen"],
                index=["Actief", "In behandeling", "Genezen"].index(injury['status'])
            )
            
            # Safe date parsing
            current_end_date = None
            if injury.get('datum_einde'):
                try:
                    if isinstance(injury['datum_einde'], str):
                        current_end_date = datetime.datetime.strptime(injury['datum_einde'], '%Y-%m-%d').date()
                    else:
                        current_end_date = injury['datum_einde']
                except (ValueError, TypeError):
                    current_end_date = None
            
            new_datum_einde = st.date_input(
                "Herstel Datum",
                value=current_end_date
            )
        
        with col2:
            new_behandeling = st.text_area(
                "Behandelplan Update",
                value=injury['behandeling'] or ""
            )
            
            new_opmerkingen = st.text_area(
                "Nieuwe Opmerkingen",
                value=injury['opmerkingen'] or ""
            )
        
        if st.form_submit_button("💾 Update Opslaan"):
            success = update_injury(
                injury_id, new_status, new_datum_einde, 
                new_behandeling, new_opmerkingen
            )
            if success:
                st.success("✅ Blessure bijgewerkt!")
                st.rerun()
            else:
                st.error("❌ Fout bij bijwerken van blessure")

def update_injury(injury_id, status, datum_einde, behandeling, opmerkingen):
    """Update bestaande blessure"""
    if SUPABASE_MODE:
        try:
            from supabase_config import get_supabase_client
            supabase = get_supabase_client()
            
            # Get current record to merge with existing kine_comments
            current_record = supabase.table('blessures').select('kine_comments').eq('blessure_id', injury_id).execute()
            existing_comments = current_record.data[0]['kine_comments'] if current_record.data else ''
            
            # Parse existing data and update with new values
            parsed_data = parse_kine_comments(existing_comments)
            parsed_data['behandeling'] = behandeling
            parsed_data['opmerkingen'] = opmerkingen
            
            # Reconstruct kine_comments
            new_comments = f"Locatie: {parsed_data.get('locatie', '')}, Ernst: {parsed_data.get('ernst', '')}, Voorspelling: {parsed_data.get('voorspelling_dagen', '')} dagen\n\nBeschrijving: {parsed_data.get('beschrijving', '')}\n\nBehandeling: {behandeling}\n\nOpmerkingen: {opmerkingen}"
            
            update_data = {
                'status': status,
                'verwachte_herstel': str(datum_einde) if datum_einde else None,  # Use existing column name
                'kine_comments': new_comments
            }
            
            # Handle composite key scenario
            if injury_id and '_' in str(injury_id) and 'unknown' not in str(injury_id):
                # Composite key format: "speler_datum"
                speler_name, datum = injury_id.split('_', 1)
                result = supabase.table('blessures').update(update_data).eq('speler', speler_name).eq('datum_blessure', datum).execute()
            else:
                result = supabase.table('blessures').update(update_data).eq('blessure_id', injury_id).execute()
            return True
            
        except Exception as e:
            st.error(f"Error updating injury: {e}")
            return False
    else:
        # Legacy SQLite mode
        conn = sqlite3.connect("blessures.db")
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE blessures 
            SET status = ?, datum_einde = ?, behandeling = ?, opmerkingen = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (status, datum_einde, behandeling, opmerkingen, injury_id))
        
        conn.commit()
        conn.close()
        return True

def delete_injury(injury_id):
    """Verwijder een blessure uit de database"""
    if SUPABASE_MODE:
        try:
            from supabase_config import get_supabase_client
            supabase = get_supabase_client()
            
            # Handle composite key scenario
            if injury_id and '_' in str(injury_id) and 'unknown' not in str(injury_id):
                # Composite key format: "speler_datum"
                speler_name, datum = injury_id.split('_', 1)
                result = supabase.table('blessures').delete().eq('speler', speler_name).eq('datum_blessure', datum).execute()
            else:
                result = supabase.table('blessures').delete().eq('blessure_id', injury_id).execute()
            return True
            
        except Exception as e:
            st.error(f"Error deleting injury: {e}")
            return False
    else:
        # Legacy SQLite mode
        conn = sqlite3.connect("blessures.db")
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM blessures WHERE id = ?", (injury_id,))
        
        conn.commit()
        conn.close()
        return True

def show_injury_statistics():
    """Toon blessure statistieken"""
    st.markdown("### <span class='accent-blue'>📈 Blessure Statistieken</span>", unsafe_allow_html=True)
    
    df = get_injuries_dataframe()
    
    if df.empty:
        st.info("🔍 Geen data beschikbaar voor statistieken.")
        return
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Totaal Blessures", len(df))
    
    with col2:
        active_count = len(df[df['status'].isin(['Actief', 'In behandeling'])])
        st.metric("Actieve Blessures", active_count)
    
    with col3:
        if 'voorspelling_dagen' in df.columns:
            avg_days = pd.to_numeric(df['voorspelling_dagen'], errors='coerce').mean()
            st.metric("Gem. Uitval (dagen)", f"{avg_days:.1f}" if not pd.isna(avg_days) else "0")
        else:
            st.metric("Gem. Uitval (dagen)", "N/A")
    
    with col4:
        healed_count = len(df[df['status'] == 'Genezen'])
        st.metric("Genezen", healed_count)
    
    # Charts
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 🩹 Blessures per Type")
        if 'blessure_type' in df.columns:
            type_counts = df['blessure_type'].value_counts()
            st.bar_chart(type_counts)
        else:
            st.info("Geen blessure type data beschikbaar")
    
    with col2:
        st.markdown("#### 📍 Blessures per Locatie")
        if 'locatie' in df.columns:
            location_counts = df['locatie'].dropna().value_counts()
            if not location_counts.empty:
                st.bar_chart(location_counts)
            else:
                st.info("Geen locatie data beschikbaar")
        else:
            st.info("Geen locatie data beschikbaar")
    
    # Status verdeling
    st.markdown("#### 📊 Status Verdeling")
    if 'status' in df.columns:
        status_counts = df['status'].value_counts()
        st.bar_chart(status_counts)
    else:
        st.info("Geen status data beschikbaar")
    
    # Ernst verdeling
    st.markdown("#### ⚠️ Ernst Verdeling")
    if 'ernst' in df.columns:
        severity_counts = df['ernst'].dropna().value_counts()
        if not severity_counts.empty:
            st.bar_chart(severity_counts)
        else:
            st.info("Geen ernst data beschikbaar")
    else:
        st.info("Geen ernst data beschikbaar")

def parse_kine_comments(comments):
    """Parse combined data from kine_comments field"""
    if not comments:
        return {}
    
    data = {}
    lines = comments.split('\n')
    
    for line in lines:
        if 'Locatie:' in line:
            data['locatie'] = line.split('Locatie: ')[1].split(',')[0].strip()
        elif 'Ernst:' in line:
            parts = line.split('Ernst: ')[1].split(',')
            data['ernst'] = parts[0].strip()
            if len(parts) > 1 and 'Voorspelling:' in parts[1]:
                data['voorspelling_dagen'] = parts[1].split('Voorspelling: ')[1].split(' dagen')[0].strip()
        elif 'Beschrijving:' in line:
            data['beschrijving'] = line.split('Beschrijving: ')[1].strip()
        elif 'Behandeling:' in line:
            data['behandeling'] = line.split('Behandeling: ')[1].strip()
        elif 'Opmerkingen:' in line:
            data['opmerkingen'] = line.split('Opmerkingen: ')[1].strip()
    
    return data

def get_injuries_dataframe():
    """Haal alle blessures op uit database als DataFrame"""
    if SUPABASE_MODE:
        try:
            from supabase_config import get_supabase_client
            supabase = get_supabase_client()
            result = supabase.table('blessures').select('*').order('created_at', desc=True).execute()
            df = pd.DataFrame(result.data)
            
            # Parse kine_comments to extract individual fields
            if not df.empty and 'kine_comments' in df.columns:
                for idx, row in df.iterrows():
                    parsed_data = parse_kine_comments(row.get('kine_comments', ''))
                    for key, value in parsed_data.items():
                        df.at[idx, key] = value
                
                # Map column names to match expected format
                df['datum_start'] = df.get('datum_blessure')
                df['datum_einde'] = df.get('verwachte_herstel')
                df['speler_naam'] = df.get('speler')  # For compatibility
            
            return df
        except Exception as e:
            st.error(f"Error loading injuries from Supabase: {e}")
            return pd.DataFrame()
    else:
        # Legacy SQLite mode
        conn = sqlite3.connect("blessures.db")
        try:
            df = pd.read_sql_query("""
                SELECT * FROM blessures 
                ORDER BY created_at DESC
            """, conn)
            return df
        except:
            return pd.DataFrame()
        finally:
            conn.close()

def calculate_days_out(injury):
    """Bereken aantal dagen uit de roulatie"""
    try:
        # Handle different column names for start date
        start_date_str = injury.get('datum_start') or injury.get('datum_blessure')
        if not start_date_str:
            return 0
            
        # Parse date string (handle both string and date formats)
        if isinstance(start_date_str, str):
            start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
        else:
            start_date = start_date_str
        
        # Handle end date
        end_date_str = injury.get('datum_einde') or injury.get('verwachte_herstel')
        if end_date_str and injury.get('status') == 'Genezen':
            if isinstance(end_date_str, str):
                end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').date()
            else:
                end_date = end_date_str
            return (end_date - start_date).days
        else:
            return (datetime.date.today() - start_date).days
    except (ValueError, TypeError):
        return 0

def get_player_names():
    """Haal alle spelersnamen op uit de hoofddatabase"""
    try:
        if SUPABASE_MODE:
            # Use Supabase mode - try to get cached player list first
            if hasattr(st.session_state, 'cached_players') and st.session_state.cached_players:
                return st.session_state.cached_players
            else:
                # Fallback to manual query via safe_fetchdf
                players_df = safe_fetchdf("SELECT DISTINCT speler FROM gps_data ORDER BY speler")
                if not players_df.empty:
                    players = players_df['speler'].tolist()
                    st.session_state.cached_players = players
                    return players
        else:
            # Legacy mode
            conn = get_database_connection()
            query = """
            SELECT DISTINCT naam FROM spelers_profiel
            UNION
            SELECT DISTINCT Speler as naam FROM thirty_fifteen_results
            UNION
            SELECT DISTINCT speler as naam FROM gps_data
            ORDER BY naam
            """
            result = conn.execute(query)
            conn.close()
            players = [row[0] for row in result if row[0] is not None]
            return players
        
    except Exception as e:
        st.error(f"Fout bij ophalen spelersnamen: {e}")
        
    # Fallback naar handmatige lijst
    return [
        "Barry Djaumo", "Brian Roekens", "Brusk Er", "Daan Straetmans", 
        "Daan Vanhoof", "Jari Decraemer", "Joy Matuta", "Matis Willeput",
        "Niels Vaesen", "Nik Vangrunderbeek", "Samuel Sanchez", 
        "Senne Goossens", "Stan Roosen", "Thomas Desmet", "Tom Goovaerts",
        "Wannes Van Tricht", "Yani Urdinov", "Yoan Yangassa"
    ]

# Main execution
st.title("🏥 Blessure Rapportage & Opvolging")

# Initialiseer database
init_database()

# Tabs voor verschillende functionaliteiten
tab1, tab2, tab3 = st.tabs(["📝 Nieuwe Blessure", "📊 Overzicht", "📈 Statistieken"])

with tab1:
    show_injury_form()

with tab2:
    show_injury_overview()

with tab3:
    show_injury_statistics()