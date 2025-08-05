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
from datetime import datetime, date
import uuid


# Cache clearing function
def clear_data_cache():
    """Clear Streamlit cache to ensure fresh data after updates"""
    try:
        if SUPABASE_MODE:
            safe_fetchdf.clear()
        st.cache_data.clear()
    except Exception as e:
        st.warning(f"Cache clearing failed: {e}")

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

st.set_page_config(page_title="Spelersbeheer - SPK Dashboard", layout="wide")

# Custom CSS styling consistent with other pages
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
    
    .player-card {
        background: linear-gradient(135deg, #F0F8FF 0%, #E8F4FD 100%);
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #2E86AB;
        margin: 0.5rem 0;
    }
    
    .coach-card {
        background: linear-gradient(135deg, #FFF8F0 0%, #FFF0E6 100%);
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #F18F01;
        margin: 0.5rem 0;
    }
    
    .form-container {
        background: #FAFCFF;
        padding: 1.5rem;
        border-radius: 10px;
        border: 1px solid #E8F4FD;
        margin: 1rem 0;
    }
    
    .success-message {
        background: #F0FFF4;
        border: 1px solid #90EE90;
        border-radius: 8px;
        padding: 1rem;
        margin: 1rem 0;
        color: #2E8B57;
    }
    
    .error-message {
        background: #FFF0F0;
        border: 1px solid #FFB6C1;
        border-radius: 8px;
        padding: 1rem;
        margin: 1rem 0;
        color: #DC143C;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header"><h1>⚽ Spelersbeheer</h1></div>', unsafe_allow_html=True)

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

def migrate_coaches_from_contact_list():
    """Migreer coaches van contact_lijst naar coaches_profiel"""
    try:
        # Check of er al coaches zijn in coaches_profiel
        result = execute_db_query("SELECT COUNT(*) FROM coaches_profiel")
        existing_coaches = result[0][0] if result else 0
        
        if existing_coaches == 0:
            # Haal coaches op uit contact_lijst
            contact_coaches = execute_db_query("""
                SELECT naam, email, telefoon, functie, actief, created_at
                FROM contact_lijst 
                WHERE functie LIKE '%trainer%' OR functie LIKE '%coach%'
                OR functie = 'Hoofdtrainer' OR functie = 'Assistent Trainer'
            """)
            
            migrated_count = 0
            for coach_data in contact_coaches:
                naam, email, telefoon, functie, actief, created_at = coach_data
                
                # Maak unieke coach_id
                coach_id = str(uuid.uuid4())
                
                # Bepaal status op basis van actief boolean
                status = "Actief" if actief else "Inactief"
                
                # Insert coach in coaches_profiel
                execute_db_query("""
                    INSERT INTO coaches_profiel 
                    (coach_id, naam, functie, telefoon, email, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (coach_id, naam, functie, telefoon, email, status, created_at))
                
                migrated_count += 1
            
            if migrated_count > 0:
                return f"✅ {migrated_count} coaches gemigreerd van contactenlijst!"
        
        return None
    except Exception as e:
        return f"❌ Fout bij migreren coaches: {str(e)}"

# Maak benodigde tabellen als ze niet bestaan
execute_db_query("""
    CREATE TABLE IF NOT EXISTS spelers_profiel (
        speler_id VARCHAR PRIMARY KEY,
        naam VARCHAR NOT NULL,
        geboortedatum DATE,
        leeftijd INTEGER,
        gewicht DOUBLE,
        lengte DOUBLE,
        positie VARCHAR,
        rugnummer INTEGER,
        telefoon VARCHAR,
        email VARCHAR,
        adres TEXT,
        status VARCHAR DEFAULT 'Actief',
        type VARCHAR DEFAULT 'Speler',
        opmerkingen TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")

execute_db_query("""
    CREATE TABLE IF NOT EXISTS coaches_profiel (
        coach_id VARCHAR PRIMARY KEY,
        naam VARCHAR NOT NULL,
        functie VARCHAR,
        telefoon VARCHAR,
        email VARCHAR,
        adres TEXT,
        specialisatie VARCHAR,
        certificaten TEXT,
        ervaring_jaren INTEGER,
        status VARCHAR DEFAULT 'Actief',
        opmerkingen TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")

def show_spelers_overzicht():
    """Toon overzicht van alle spelers"""
    # Haal alle spelers op uit de database
    try:
        spelers_query = """
            SELECT speler_id, naam, geboortedatum, leeftijd, gewicht, positie, 
                   rugnummer, telefoon, email, status, created_at
            FROM spelers_profiel 
            ORDER BY naam
        """
        spelers_df = safe_fetchdf(spelers_query)
        
        # Als er geen spelers zijn, probeer data te migreren van bestaande tabellen
        if len(spelers_df) == 0:
            # Migreer data van thirty_fifteen_results als die bestaat
            try:
                existing_players = safe_fetchdf("""
                    SELECT DISTINCT Speler as naam, Geboortedatum as geboortedatum, 
                           Leeftijd as leeftijd, Gewicht as gewicht
                    FROM thirty_fifteen_results
                    WHERE Speler IS NOT NULL
                """)
                
                if len(existing_players) > 0:
                    for _, speler in existing_players.iterrows():
                        speler_id = str(uuid.uuid4())
                        execute_db_query("""
                            INSERT INTO spelers_profiel (speler_id, naam, geboortedatum, leeftijd, gewicht)
                            VALUES (?, ?, ?, ?, ?)
                        """, (speler_id, speler.naam, speler.geboortedatum, speler.leeftijd, speler.gewicht))
                    
                    st.success(f"✅ {len(existing_players)} spelers gemigreerd van bestaande data!")
                    spelers_df = safe_fetchdf(spelers_query)
            except:
                pass
    except Exception as e:
        st.error(f"Fout bij ophalen spelers: {str(e)}")
        spelers_df = pd.DataFrame()
    
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown("### <span class='accent-blue'>👥 Spelers Overzicht</span>", unsafe_allow_html=True)
    
    if len(spelers_df) > 0:
        # Filter opties
        col_filter1, col_filter2, col_filter3 = st.columns(3)
        
        with col_filter1:
            status_filter = st.selectbox("Status filter", ["Alle", "Actief", "Inactief", "Geblesseerd"])
        
        with col_filter2:
            positie_filter = st.selectbox("Positie filter", ["Alle"] + list(spelers_df['positie'].dropna().unique()))
        
        with col_filter3:
            naam_filter = st.text_input("Zoek op naam")
        
        # Filter de data
        filtered_df = spelers_df.copy()
        
        if status_filter != "Alle":
            filtered_df = filtered_df[filtered_df['status'] == status_filter]
        
        if positie_filter != "Alle":
            filtered_df = filtered_df[filtered_df['positie'] == positie_filter]
        
        if naam_filter:
            filtered_df = filtered_df[filtered_df['naam'].str.contains(naam_filter, case=False, na=False)]
        
        st.markdown(f"**{len(filtered_df)} spelers gevonden**")
        
        # Toon spelers in cards
        for _, speler in filtered_df.iterrows():
            leeftijd_str = f"{speler['leeftijd']} jaar" if pd.notna(speler['leeftijd']) else "Onbekend"
            gewicht_str = f"{speler['gewicht']} kg" if pd.notna(speler['gewicht']) else "Onbekend"
            positie_str = speler['positie'] if pd.notna(speler['positie']) else "Niet ingesteld"
            rugnummer_str = f"#{speler['rugnummer']}" if pd.notna(speler['rugnummer']) else ""
            
            status_icon = "🟢" if speler['status'] == 'Actief' else "🔴" if speler['status'] == 'Inactief' else "🟡"
            
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.markdown(f"""
                <div class="player-card">
                    <strong>{status_icon} {speler['naam']} {rugnummer_str}</strong><br>
                    <small>Leeftijd: {leeftijd_str} | Gewicht: {gewicht_str} | Positie: {positie_str}</small><br>
                    <small>Telefoon: {speler['telefoon'] if pd.notna(speler['telefoon']) else 'Niet ingesteld'} | 
                    Email: {speler['email'] if pd.notna(speler['email']) else 'Niet ingesteld'}</small>
                </div>
                """, unsafe_allow_html=True)
            
            with col2:
                if st.button(f"🗑️ Verwijder", key=f"delete_speler_{speler['speler_id']}", type="secondary"):
                    if st.session_state.get(f"confirm_delete_{speler['speler_id']}", False):
                        try:
                            execute_db_query("DELETE FROM spelers_profiel WHERE speler_id = ?", (speler['speler_id'],))
                            st.success(f"Speler {speler['naam']} verwijderd!")
                            # Clear cache to ensure fresh data
                            clear_data_cache()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Fout bij verwijderen: {str(e)}")
                    else:
                        st.session_state[f"confirm_delete_{speler['speler_id']}"] = True
                        st.warning("Klik nogmaals om te bevestigen")
                        
                if st.button(f"✏️ Bewerk", key=f"edit_speler_{speler['speler_id']}", type="primary"):
                    st.session_state.edit_speler_id = speler['speler_id']
                    st.session_state.show_edit_form = True
        
        # Export functionaliteit
        csv_data = filtered_df.to_csv(index=False)
        st.download_button(
            label="📥 Download spelers CSV",
            data=csv_data,
            file_name=f"spelers_overzicht_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
        
    else:
        st.info("📝 Nog geen spelers in het systeem. Voeg een nieuwe speler toe!")
    
    st.markdown('</div>', unsafe_allow_html=True)

def show_coaches_overzicht():
    """Toon overzicht van alle coaches"""
    try:
        coaches_query = """
            SELECT coach_id, naam, functie, telefoon, email, specialisatie, 
                   ervaring_jaren, status, created_at
            FROM coaches_profiel 
            ORDER BY naam
        """
        coaches_df = safe_fetchdf(coaches_query)
        
        # Als er geen coaches zijn, probeer te migreren van contactenlijst
        if len(coaches_df) == 0:
            migration_result = migrate_coaches_from_contact_list()
            if migration_result:
                st.success(migration_result)
                coaches_df = safe_fetchdf(coaches_query)
    except Exception as e:
        st.error(f"Fout bij ophalen coaches: {str(e)}")
        coaches_df = pd.DataFrame()
    
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown("### <span class='accent-orange'>👨‍💼 Coaches Overzicht</span>", unsafe_allow_html=True)
    
    # Handmatige migratie knop
    if len(coaches_df) == 0:
        col_migrate, col_spacer = st.columns([2, 3])
        with col_migrate:
            if st.button("🔄 Migreer Coaches van Contactenlijst", type="secondary"):
                migration_result = migrate_coaches_from_contact_list()
                if migration_result:
                    st.success(migration_result)
                    st.rerun()
                else:
                    st.info("Geen coaches gevonden in contactenlijst om te migreren.")
    
    if len(coaches_df) > 0:
        st.markdown(f"**{len(coaches_df)} coaches gevonden**")
        
        # Toon coaches in cards
        for _, coach in coaches_df.iterrows():
            functie_str = coach['functie'] if pd.notna(coach['functie']) else "Niet ingesteld"
            specialisatie_str = coach['specialisatie'] if pd.notna(coach['specialisatie']) else "Niet ingesteld"
            ervaring_str = f"{coach['ervaring_jaren']} jaar" if pd.notna(coach['ervaring_jaren']) else "Onbekend"
            
            status_icon = "🟢" if coach['status'] == 'Actief' else "🔴"
            
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.markdown(f"""
                <div class="coach-card">
                    <strong>{status_icon} {coach['naam']}</strong><br>
                    <small>Functie: {functie_str} | Specialisatie: {specialisatie_str} | Ervaring: {ervaring_str}</small><br>
                    <small>Telefoon: {coach['telefoon'] if pd.notna(coach['telefoon']) else 'Niet ingesteld'} | 
                    Email: {coach['email'] if pd.notna(coach['email']) else 'Niet ingesteld'}</small>
                </div>
                """, unsafe_allow_html=True)
            
            with col2:
                if st.button(f"🗑️ Verwijder", key=f"delete_coach_{coach['coach_id']}", type="secondary"):
                    if st.session_state.get(f"confirm_delete_coach_{coach['coach_id']}", False):
                        try:
                            execute_db_query("DELETE FROM coaches_profiel WHERE coach_id = ?", (coach['coach_id'],))
                            st.success(f"Coach {coach['naam']} verwijderd!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Fout bij verwijderen: {str(e)}")
                    else:
                        st.session_state[f"confirm_delete_coach_{coach['coach_id']}"] = True
                        st.warning("Klik nogmaals om te bevestigen")
                        
                if st.button(f"✏️ Bewerk", key=f"edit_coach_{coach['coach_id']}", type="primary"):
                    st.session_state.edit_coach_id = coach['coach_id']
                    st.session_state.show_edit_coach_form = True
        
        # Export functionaliteit
        csv_data = coaches_df.to_csv(index=False)
        st.download_button(
            label="📥 Download coaches CSV",
            data=csv_data,
            file_name=f"coaches_overzicht_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
        
    else:
        st.info("📝 Nog geen coaches in het systeem. Voeg een nieuwe coach toe!")
    
    st.markdown('</div>', unsafe_allow_html=True)

def show_add_speler_form():
    """Formulier voor het toevoegen van een nieuwe speler"""
    st.markdown('<div class="info-card">', unsafe_allow_html=True)
    st.markdown("### <span class='accent-green'>➕ Nieuwe Speler Toevoegen</span>", unsafe_allow_html=True)
    
    with st.form("add_speler_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            naam = st.text_input("Naam *", placeholder="Voor- en achternaam")
            geboortedatum = st.date_input("Geboortedatum", value=None, 
                                         min_value=date(1960, 1, 1), 
                                         max_value=date.today())
            gewicht = st.number_input("Gewicht (kg)", min_value=30.0, max_value=150.0, step=0.1, value=None)
            positie = st.selectbox("Positie", [
                "", "Keeper", "Verdediger", "Middenvelder", "Aanvaller",
                "Linksback", "Rechtsback", "Centrale verdediger", 
                "Defensieve middenvelder", "Centrale middenvelder", 
                "Aanvallende middenvelder", "Vleugelspeler", "Spits"
            ])
            telefoon = st.text_input("Telefoon", placeholder="+32 xxx xx xx xx")
            
        with col2:
            leeftijd = st.number_input("Leeftijd", min_value=10, max_value=50, step=1, value=None)
            lengte = st.number_input("Lengte (cm)", min_value=140, max_value=220, step=1, value=None)
            rugnummer = st.number_input("Rugnummer", min_value=1, max_value=99, step=1, value=None)
            status = st.selectbox("Status", ["Actief", "Inactief", "Geblesseerd"], index=0)
            email = st.text_input("Email", placeholder="speler@example.com")
        
        adres = st.text_area("Adres", placeholder="Straat, nummer, postcode, stad")
        opmerkingen = st.text_area("Opmerkingen", placeholder="Extra informatie over de speler")
        
        submitted = st.form_submit_button("➕ Speler Toevoegen", type="primary")
        
        if submitted:
            if not naam:
                st.error("⚠️ Naam is verplicht!")
            else:
                try:
                    speler_id = str(uuid.uuid4())
                    
                    execute_db_query("""
                        INSERT INTO spelers_profiel 
                        (speler_id, naam, geboortedatum, leeftijd, gewicht, lengte, positie, 
                         rugnummer, telefoon, email, adres, status, opmerkingen)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (speler_id, naam, geboortedatum, leeftijd, gewicht, lengte, positie,
                          rugnummer, telefoon, email, adres, status, opmerkingen))
                    
                    st.success(f"✅ Speler {naam} succesvol toegevoegd!")
                    # Clear cache to ensure fresh data
                    clear_data_cache()
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Fout bij toevoegen speler: {str(e)}")
    
    st.markdown('</div>', unsafe_allow_html=True)

def show_add_coach_form():
    """Formulier voor het toevoegen van een nieuwe coach"""
    st.markdown('<div class="info-card">', unsafe_allow_html=True)
    st.markdown("### <span class='accent-orange'>➕ Nieuwe Coach Toevoegen</span>", unsafe_allow_html=True)
    
    with st.form("add_coach_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            naam = st.text_input("Naam *", placeholder="Voor- en achternaam")
            functie = st.selectbox("Functie", [
                "", "Hoofdtrainer", "Assistent-trainer", "Keeperstrainer", 
                "Fysiotherapeut", "Performance Analyst", "Jeugdtrainer",
                "Technisch Directeur", "Conditietrainer"
            ])
            telefoon = st.text_input("Telefoon", placeholder="+32 xxx xx xx xx")
            specialisatie = st.text_input("Specialisatie", placeholder="Bv. Jeugdontwikkeling, Tactieken")
            
        with col2:
            email = st.text_input("Email", placeholder="coach@example.com")
            ervaring_jaren = st.number_input("Ervaring (jaren)", min_value=0, max_value=50, step=1, value=None)
            status = st.selectbox("Status", ["Actief", "Inactief"], index=0)
            certificaten = st.text_input("Certificaten", placeholder="UEFA A, B licentie, etc.")
        
        adres = st.text_area("Adres", placeholder="Straat, nummer, postcode, stad")
        opmerkingen = st.text_area("Opmerkingen", placeholder="Extra informatie over de coach")
        
        submitted = st.form_submit_button("➕ Coach Toevoegen", type="primary")
        
        if submitted:
            if not naam:
                st.error("⚠️ Naam is verplicht!")
            else:
                try:
                    coach_id = str(uuid.uuid4())
                    
                    execute_db_query("""
                        INSERT INTO coaches_profiel 
                        (coach_id, naam, functie, telefoon, email, adres, specialisatie, 
                         certificaten, ervaring_jaren, status, opmerkingen)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (coach_id, naam, functie, telefoon, email, adres, specialisatie,
                          certificaten, ervaring_jaren, status, opmerkingen))
                    
                    st.success(f"✅ Coach {naam} succesvol toegevoegd!")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Fout bij toevoegen coach: {str(e)}")
    
    st.markdown('</div>', unsafe_allow_html=True)

def show_edit_speler_form(speler_id):
    """Formulier voor het bewerken van een speler"""
    try:
        # Use safe_fetchdf for better Supabase compatibility
        result_df = safe_fetchdf(f"""
            SELECT * FROM spelers_profiel WHERE speler_id = '{speler_id}'
        """)
        
        if not result_df.empty:
            speler_row = result_df.iloc[0]
            # Convert to list format for backward compatibility
            speler = [
                speler_row.get('speler_id'),
                speler_row.get('naam'), 
                speler_row.get('geboortedatum'),
                speler_row.get('leeftijd'),
                speler_row.get('gewicht'),
                speler_row.get('lengte'),
                speler_row.get('positie'),
                speler_row.get('rugnummer'),
                speler_row.get('telefoon'),
                speler_row.get('email'),
                speler_row.get('adres'),
                speler_row.get('status'),
                speler_row.get('type'),
                speler_row.get('opmerkingen'),
                speler_row.get('created_at'),
                speler_row.get('updated_at')
            ]
        else:
            speler = None
        
        if not speler:
            st.error("Speler niet gevonden!")
            return
            
        st.markdown('<div class="info-card">', unsafe_allow_html=True)
        st.markdown(f"### <span class='accent-blue'>✏️ Bewerk Speler: {speler[1]}</span>", unsafe_allow_html=True)
        
        with st.form("edit_speler_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                naam = st.text_input("Naam *", value=speler[1] or "")
                
                # Safe geboortedatum conversion
                try:
                    if speler[2] and pd.notna(speler[2]):
                        if isinstance(speler[2], str):
                            geboortedatum_value = datetime.strptime(speler[2], '%Y-%m-%d').date()
                        else:
                            geboortedatum_value = speler[2]
                    else:
                        geboortedatum_value = date(1990, 1, 1)  # Default date
                except (ValueError, TypeError):
                    geboortedatum_value = date(1990, 1, 1)  # Default date
                    
                geboortedatum = st.date_input("Geboortedatum", value=geboortedatum_value,
                                             min_value=date(1960, 1, 1), 
                                             max_value=date.today())
                # Safe gewicht conversion
                try:
                    gewicht_value = float(speler[4]) if speler[4] and str(speler[4]) != 'nan' and pd.notna(speler[4]) else None
                except (ValueError, TypeError):
                    gewicht_value = None
                gewicht = st.number_input("Gewicht (kg)", min_value=30.0, max_value=150.0, step=0.1, 
                                        value=gewicht_value)
                positie = st.selectbox("Positie", [
                    "", "Keeper", "Verdediger", "Middenvelder", "Aanvaller",
                    "Linksback", "Rechtsback", "Centrale verdediger", 
                    "Defensieve middenvelder", "Centrale middenvelder", 
                    "Aanvallende middenvelder", "Vleugelspeler", "Spits"
                ], index=0 if not speler[6] else max(0, [
                    "", "Keeper", "Verdediger", "Middenvelder", "Aanvaller",
                    "Linksback", "Rechtsback", "Centrale verdediger", 
                    "Defensieve middenvelder", "Centrale middenvelder", 
                    "Aanvallende middenvelder", "Vleugelspeler", "Spits"
                ].index(speler[6]) if speler[6] in [
                    "", "Keeper", "Verdediger", "Middenvelder", "Aanvaller",
                    "Linksback", "Rechtsback", "Centrale verdediger", 
                    "Defensieve middenvelder", "Centrale middenvelder", 
                    "Aanvallende middenvelder", "Vleugelspeler", "Spits"
                ] else 0))
                telefoon = st.text_input("Telefoon", value=speler[8] or "")
                
            with col2:
                # Safe leeftijd conversion
                try:
                    leeftijd_value = int(speler[3]) if speler[3] and pd.notna(speler[3]) and str(speler[3]) != 'nan' else None
                except (ValueError, TypeError):
                    leeftijd_value = None
                leeftijd = st.number_input("Leeftijd", min_value=10, max_value=50, step=1, 
                                         value=leeftijd_value)
                
                # Safe lengte conversion
                try:
                    lengte_value = int(speler[5]) if speler[5] and pd.notna(speler[5]) and str(speler[5]) != 'nan' else None
                except (ValueError, TypeError):
                    lengte_value = None
                lengte = st.number_input("Lengte (cm)", min_value=140, max_value=220, step=1, 
                                       value=lengte_value)
                
                # Safe rugnummer conversion
                try:
                    rugnummer_value = int(speler[7]) if speler[7] and pd.notna(speler[7]) and str(speler[7]) != 'nan' else None
                except (ValueError, TypeError):
                    rugnummer_value = None
                rugnummer = st.number_input("Rugnummer", min_value=1, max_value=99, step=1, 
                                          value=rugnummer_value)
                status = st.selectbox("Status", ["Actief", "Inactief", "Geblesseerd"], 
                                    index=max(0, ["Actief", "Inactief", "Geblesseerd"].index(speler[11]) 
                                            if speler[11] in ["Actief", "Inactief", "Geblesseerd"] else 0))
                email = st.text_input("Email", value=speler[9] or "")
            
            adres = st.text_area("Adres", value=speler[10] or "")
            opmerkingen = st.text_area("Opmerkingen", value=speler[13] or "")
            
            col_submit, col_cancel = st.columns(2)
            
            with col_submit:
                submitted = st.form_submit_button("💾 Opslaan", type="primary")
            
            with col_cancel:
                cancelled = st.form_submit_button("❌ Annuleren")
            
            if submitted:
                if not naam:
                    st.error("⚠️ Naam is verplicht!")
                else:
                    try:
                        # Use proper Supabase helpers for updates
                        if SUPABASE_MODE:
                            from supabase_config import get_supabase_client
                            
                            supabase = get_supabase_client()
                            if supabase:
                                result = supabase.table("spelers_profiel").update({
                                    "naam": naam,
                                    "geboortedatum": str(geboortedatum),
                                    "leeftijd": leeftijd,
                                    "gewicht": gewicht,
                                    "lengte": lengte,
                                    "positie": positie,
                                    "rugnummer": rugnummer,
                                    "telefoon": telefoon,
                                    "email": email,
                                    "adres": adres,
                                    "status": status,
                                    "opmerkingen": opmerkingen,
                                    "updated_at": "now()"
                                }).eq("speler_id", speler_id).execute()
                                
                                if result.data:
                                    st.success(f"✅ Speler {naam} succesvol bijgewerkt!")
                                    # Clear cache to ensure fresh data
                                    clear_data_cache()
                                    st.session_state.show_edit_form = False
                                    if 'edit_speler_id' in st.session_state:
                                        del st.session_state.edit_speler_id
                                    st.rerun()
                                else:
                                    st.error("❌ Update failed - geen data geretourneerd")
                            else:
                                st.error("❌ Supabase client niet beschikbaar")
                        else:
                            # Fallback to legacy method
                            execute_db_query("""
                                UPDATE spelers_profiel 
                                SET naam=?, geboortedatum=?, leeftijd=?, gewicht=?, lengte=?, positie=?, 
                                    rugnummer=?, telefoon=?, email=?, adres=?, status=?, opmerkingen=?,
                                    updated_at=CURRENT_TIMESTAMP
                                WHERE speler_id=?
                            """, (naam, geboortedatum, leeftijd, gewicht, lengte, positie,
                                  rugnummer, telefoon, email, adres, status, opmerkingen, speler_id))
                            
                            st.success(f"✅ Speler {naam} succesvol bijgewerkt!")
                            # Clear cache to ensure fresh data
                            clear_data_cache()
                            st.session_state.show_edit_form = False
                            if 'edit_speler_id' in st.session_state:
                                del st.session_state.edit_speler_id
                            st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Fout bij bijwerken speler: {str(e)}")
            
            if cancelled:
                st.session_state.show_edit_form = False
                if 'edit_speler_id' in st.session_state:
                    del st.session_state.edit_speler_id
                st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)
        
    except Exception as e:
        st.error(f"Fout bij ophalen speler gegevens: {str(e)}")

def main_spelersbeheer():
    """Main function voor spelersbeheer pagina"""
    # Tab structuur
    tab1, tab2, tab3, tab4 = st.tabs(["👥 Spelers", "👨‍💼 Coaches", "➕ Nieuwe Speler", "➕ Nieuwe Coach"])
    
    with tab1:
        # Check of we een edit form moeten tonen
        if st.session_state.get('show_edit_form', False) and 'edit_speler_id' in st.session_state:
            show_edit_speler_form(st.session_state.edit_speler_id)
        else:
            show_spelers_overzicht()
    
    with tab2:
        # Check of we een coach edit form moeten tonen
        if st.session_state.get('show_edit_coach_form', False) and 'edit_coach_id' in st.session_state:
            # Hier zou je een edit coach form functie kunnen toevoegen (vergelijkbaar met spelers)
            st.info("Coach bewerken functionaliteit kan hier worden toegevoegd")
        else:
            show_coaches_overzicht()
    
    with tab3:
        show_add_speler_form()
    
    with tab4:
        show_add_coach_form()

# Main uitvoering
if __name__ == "__main__":
    main_spelersbeheer()

# Safe database connection cleanup

# Database cleanup handled by Supabase helpers