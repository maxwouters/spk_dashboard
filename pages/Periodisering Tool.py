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
from plotly.subplots import make_subplots
import calendar


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

st.set_page_config(page_title="SPK Dashboard - Periodisering", layout="wide")

st.subheader("📅 Periodisering & Seizoensplanning")

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
# Database tabellen voor periodisering
execute_db_query("""
    CREATE TABLE IF NOT EXISTS seizoen_planning (
        planning_id INTEGER PRIMARY KEY,
        seizoen_naam TEXT,
        start_datum DATE,
        eind_datum DATE,
        type_seizoen TEXT,  -- Voorbereiding, Competitie, Tussenseizoen
        doelstellingen TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")

execute_db_query("""
    CREATE TABLE IF NOT EXISTS macro_cycli (
        macro_id INTEGER PRIMARY KEY,
        planning_id INTEGER,
        naam TEXT,
        start_datum DATE,
        eind_datum DATE,
        focus_type TEXT,  -- Conditie, Kracht, Snelheid, Recovery, Competition
        intensiteit_niveau INTEGER,  -- 1-5 schaal
        beschrijving TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (planning_id) REFERENCES seizoen_planning(planning_id)
    )
""")

execute_db_query("""
    CREATE TABLE IF NOT EXISTS meso_cycli (
        meso_id INTEGER PRIMARY KEY,
        macro_id INTEGER,
        naam TEXT,
        start_datum DATE,
        eind_datum DATE,
        week_nummer INTEGER,
        load_percentage INTEGER,  -- Percentage van max load
        focus_themas TEXT,
        wedstrijden INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (macro_id) REFERENCES macro_cycli(macro_id)
    )
""")

execute_db_query("""
    CREATE TABLE IF NOT EXISTS microcyclus_templates (
        template_id INTEGER PRIMARY KEY,
        naam TEXT,
        type_week TEXT,  -- Loading, Recovery, Competition, Deload
        beschrijving TEXT,
        dag_1_type TEXT,
        dag_1_intensiteit INTEGER,
        dag_2_type TEXT,
        dag_2_intensiteit INTEGER,
        dag_3_type TEXT,
        dag_3_intensiteit INTEGER,
        dag_4_type TEXT,
        dag_4_intensiteit INTEGER,
        dag_5_type TEXT,
        dag_5_intensiteit INTEGER,
        dag_6_type TEXT,
        dag_6_intensiteit INTEGER,
        dag_7_type TEXT,
        dag_7_intensiteit INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")

# Sequences maken
try:
    execute_db_query("CREATE SEQUENCE IF NOT EXISTS planning_id_seq START 1")
    execute_db_query("CREATE SEQUENCE IF NOT EXISTS macro_id_seq START 1")
    execute_db_query("CREATE SEQUENCE IF NOT EXISTS meso_id_seq START 1")
    execute_db_query("CREATE SEQUENCE IF NOT EXISTS template_id_seq START 1")
except:
    pass

# Helper functies
def get_week_number(start_date, target_date):
    """Bereken weeknummer vanaf startdatum"""
    delta = target_date - start_date
    return delta.days // 7 + 1

def calculate_periodization_load(week_number, total_weeks, macro_type):
    """Bereken load percentage op basis van periodisering model"""
    if macro_type == "Voorbereiding":
        # Graduele opbouw
        return min(100, 40 + (week_number / total_weeks) * 60)
    elif macro_type == "Competitie":
        # Ondulerende load met tapers voor belangrijke wedstrijden
        base_load = 85
        variation = 20 * (week_number % 3) / 2  # 3-week cycle
        return base_load + variation - 10
    elif macro_type == "Recovery":
        # Lage load met geleidelijke opbouw
        return max(30, 80 - (week_number / total_weeks) * 50)
    else:
        return 70  # Default

def create_default_templates():
    """Creëer standaard microcyclus templates"""
    templates = [
        {
            'naam': 'Loading Week',
            'type_week': 'Loading',
            'beschrijving': 'Hoge trainingsbelasting week',
            'dagen': [
                ('Training', 8), ('Training', 7), ('Recovery', 3), 
                ('Training', 8), ('Training', 6), ('Recovery', 2), ('Rust', 1)
            ]
        },
        {
            'naam': 'Recovery Week',
            'type_week': 'Recovery',
            'beschrijving': 'Actieve herstel week',
            'dagen': [
                ('Training', 5), ('Recovery', 3), ('Training', 4), 
                ('Recovery', 2), ('Training', 5), ('Recovery', 2), ('Rust', 1)
            ]
        },
        {
            'naam': 'Competition Week',
            'type_week': 'Competition',
            'beschrijving': 'Wedstrijd week met taper',
            'dagen': [
                ('Training', 6), ('Recovery', 3), ('Training', 4), 
                ('Recovery', 2), ('Activation', 4), ('Wedstrijd', 9), ('Recovery', 2)
            ]
        },
        {
            'naam': 'Deload Week',
            'type_week': 'Deload',
            'beschrijving': 'Verminderde belasting week',
            'dagen': [
                ('Training', 4), ('Recovery', 3), ('Training', 3), 
                ('Recovery', 2), ('Training', 4), ('Recovery', 2), ('Rust', 1)
            ]
        }
    ]
    
    # Check of templates al bestaan
    result = execute_db_query("SELECT COUNT(*) FROM microcyclus_templates")
    existing = result[0][0] if result and result[0] else 0
    
    if existing == 0:
        for template in templates:
            execute_db_query("""
                INSERT INTO microcyclus_templates 
                (template_id, naam, type_week, beschrijving,
                 dag_1_type, dag_1_intensiteit, dag_2_type, dag_2_intensiteit,
                 dag_3_type, dag_3_intensiteit, dag_4_type, dag_4_intensiteit,
                 dag_5_type, dag_5_intensiteit, dag_6_type, dag_6_intensiteit,
                 dag_7_type, dag_7_intensiteit)
                VALUES (nextval('template_id_seq'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                template['naam'], template['type_week'], template['beschrijving'],
                *[item for dag_type, intensiteit in template['dagen'] for item in (dag_type, intensiteit)]
            ))

# Initialiseer default templates
create_default_templates()

# Tabs voor verschillende onderdelen
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🎯 Seizoen Planning", 
    "📊 Macro Cycli", 
    "📈 Meso Cycli",
    "🔄 Micro Templates",
    "📅 Periodisering Overview"
])

with tab1:
    st.markdown("### 🎯 Seizoensplanning")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown("#### ➕ Nieuw Seizoen Toevoegen")
        
        with st.form("nieuw_seizoen"):
            seizoen_naam = st.text_input("📝 Seizoen Naam", 
                                       placeholder="bijv. Seizoen 2024-2025")
            
            col_a, col_b = st.columns(2)
            with col_a:
                start_datum = st.date_input("📅 Start Datum", 
                                          value=datetime(2024, 7, 1).date())
            with col_b:
                eind_datum = st.date_input("📅 Eind Datum", 
                                         value=datetime(2025, 6, 30).date())
            
            type_seizoen = st.selectbox("🏷️ Type Seizoen", 
                                      ["Competitie Seizoen", "Voorbereiding", "Tussenseizoen"])
            
            doelstellingen = st.text_area("🎯 Seizoen Doelstellingen",
                                        placeholder="Hoofddoelstellingen voor dit seizoen...")
            
            submitted = st.form_submit_button("✅ Seizoen Opslaan")
            
            if submitted and seizoen_naam:
                execute_db_query("""
                    INSERT INTO seizoen_planning 
                    (planning_id, seizoen_naam, start_datum, eind_datum, type_seizoen, doelstellingen)
                    VALUES (nextval('planning_id_seq'), ?, ?, ?, ?, ?)
                """, (seizoen_naam, start_datum, eind_datum, type_seizoen, doelstellingen))
                
                st.success(f"✅ Seizoen '{seizoen_naam}' aangemaakt!")
                st.rerun()
    
    with col2:
        st.markdown("#### 📋 Bestaande Seizoenen")
        
        seizoenen = execute_db_query("""
            SELECT planning_id, seizoen_naam, start_datum, eind_datum, type_seizoen
            FROM seizoen_planning 
            ORDER BY start_datum DESC
        """)
        
        if seizoenen:
            for seizoen in seizoenen:
                planning_id, naam, start, eind, type_s = seizoen
                start_str = pd.to_datetime(start).date().strftime('%d/%m/%Y')
                eind_str = pd.to_datetime(eind).date().strftime('%d/%m/%Y')
                
                with st.expander(f"📅 {naam} ({start_str} - {eind_str})"):
                    st.write(f"**Type:** {type_s}")
                    
                    # Seizoen statistieken
                    macro_count = (lambda result: result[0] if result else None)(execute_db_query("""
                        SELECT COUNT(*) FROM macro_cycli WHERE planning_id = ?
                    """, (planning_id,)))[0]
                    
                    st.write(f"**Macro Cycli:** {macro_count}")
                    
                    if st.button("🗑️ Verwijderen", key=f"del_seizoen_{planning_id}"):
                        execute_db_query("DELETE FROM meso_cycli WHERE macro_id IN (SELECT macro_id FROM macro_cycli WHERE planning_id = ?)", (planning_id,))
                        execute_db_query("DELETE FROM macro_cycli WHERE planning_id = ?", (planning_id,))
                        execute_db_query("DELETE FROM seizoen_planning WHERE planning_id = ?", (planning_id,))
                        st.rerun()
        else:
            st.info("📭 Nog geen seizoenen aangemaakt")

with tab2:
    st.markdown("### 📊 Macro Cyclus Beheer")
    
    # Seizoen selectie voor macro cycli
    seizoenen = execute_db_query("SELECT planning_id, seizoen_naam FROM seizoen_planning ORDER BY start_datum DESC")
    
    if seizoenen:
        seizoen_options = {f"{s[1]}": s[0] for s in seizoenen}
        selected_seizoen_naam = st.selectbox("📅 Selecteer Seizoen", list(seizoen_options.keys()))
        selected_seizoen_id = seizoen_options[selected_seizoen_naam]
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.markdown("#### ➕ Nieuwe Macro Cyclus")
            
            with st.form("nieuwe_macro"):
                macro_naam = st.text_input("📝 Macro Naam", 
                                         placeholder="bijv. Voorbereiding Fase 1")
                
                col_a, col_b = st.columns(2)
                with col_a:
                    macro_start = st.date_input("📅 Start Datum", key="macro_start")
                with col_b:
                    macro_eind = st.date_input("📅 Eind Datum", key="macro_eind")
                
                focus_type = st.selectbox("🎯 Focus Type", 
                                        ["Conditie Opbouw", "Kracht", "Snelheid", "Recovery", 
                                         "Competitie", "Techniek", "Tactiek"])
                
                intensiteit = st.slider("⚡ Intensiteit Niveau", 1, 5, 3,
                                       help="1=Zeer Laag, 5=Zeer Hoog")
                
                macro_beschrijving = st.text_area("📋 Beschrijving",
                                                 placeholder="Doelen en focus van deze macro cyclus...")
                
                macro_submitted = st.form_submit_button("✅ Macro Cyclus Opslaan")
                
                if macro_submitted and macro_naam:
                    execute_db_query("""
                        INSERT INTO macro_cycli 
                        (macro_id, planning_id, naam, start_datum, eind_datum, 
                         focus_type, intensiteit_niveau, beschrijving)
                        VALUES (nextval('macro_id_seq'), ?, ?, ?, ?, ?, ?, ?)
                    """, (selected_seizoen_id, macro_naam, macro_start, macro_eind,
                          focus_type, intensiteit, macro_beschrijving))
                    
                    st.success(f"✅ Macro cyclus '{macro_naam}' toegevoegd!")
                    st.rerun()
        
        with col2:
            st.markdown("#### 📋 Bestaande Macro Cycli")
            
            macro_cycli = execute_db_query("""
                SELECT macro_id, naam, start_datum, eind_datum, focus_type, intensiteit_niveau
                FROM macro_cycli 
                WHERE planning_id = ?
                ORDER BY start_datum
            """, (selected_seizoen_id,))
            
            if macro_cycli:
                for macro in macro_cycli:
                    macro_id, naam, start, eind, focus, intensiteit = macro
                    start_str = pd.to_datetime(start).date().strftime('%d/%m')
                    eind_str = pd.to_datetime(eind).date().strftime('%d/%m')
                    
                    # Intensiteit kleur
                    intensiteit_colors = {1: "🟢", 2: "🟡", 3: "🟠", 4: "🔴", 5: "🟣"}
                    intensiteit_icon = intensiteit_colors.get(intensiteit, "⚪")
                    
                    with st.expander(f"{intensiteit_icon} {naam} ({start_str} - {eind_str})"):
                        st.write(f"**Focus:** {focus}")
                        st.write(f"**Intensiteit:** {intensiteit}/5")
                        
                        # Meso cycli count
                        meso_count = (lambda result: result[0] if result else None)(execute_db_query("""
                            SELECT COUNT(*) FROM meso_cycli WHERE macro_id = ?
                        """, (macro_id,)))[0]
                        st.write(f"**Meso Cycli:** {meso_count}")
                        
                        if st.button("🗑️ Verwijderen", key=f"del_macro_{macro_id}"):
                            execute_db_query("DELETE FROM meso_cycli WHERE macro_id = ?", (macro_id,))
                            execute_db_query("DELETE FROM macro_cycli WHERE macro_id = ?", (macro_id,))
                            st.rerun()
            else:
                st.info("📭 Nog geen macro cycli voor dit seizoen")
    else:
        st.warning("⚠️ Maak eerst een seizoen aan")

with tab3:
    st.markdown("### 📈 Meso Cyclus Planning")
    
    if seizoenen:
        # Macro cyclus selectie
        macro_cycli = execute_db_query("""
            SELECT mc.macro_id, mc.naam, sp.seizoen_naam
            FROM macro_cycli mc
            JOIN seizoen_planning sp ON mc.planning_id = sp.planning_id
            ORDER BY mc.start_datum DESC
        """)
        
        if macro_cycli:
            macro_options = {f"{m[2]} - {m[1]}": m[0] for m in macro_cycli}
            selected_macro_naam = st.selectbox("📊 Selecteer Macro Cyclus", list(macro_options.keys()))
            selected_macro_id = macro_options[selected_macro_naam]
            
            # Automatische meso cyclus generatie
            st.markdown("#### 🔄 Automatische Meso Generatie")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                weken_per_meso = st.number_input("📅 Weken per Meso", min_value=2, max_value=6, value=3)
            with col2:
                base_load = st.number_input("⚡ Basis Load %", min_value=50, max_value=100, value=80)
            with col3:
                load_variatie = st.number_input("📊 Load Variatie %", min_value=5, max_value=30, value=15)
            
            if st.button("🔄 Genereer Automatische Meso Cycli", type="primary"):
                # Haal macro cyclus data op
                macro_data = (lambda result: result[0] if result else None)(execute_db_query("""
                    SELECT start_datum, eind_datum, focus_type FROM macro_cycli WHERE macro_id = ?
                """, (selected_macro_id,)))
                
                if macro_data:
                    start_datum, eind_datum, focus_type = macro_data
                    start_date = pd.to_datetime(start_datum).date()
                    end_date = pd.to_datetime(eind_datum).date()
                    
                    # Bereken aantal weken
                    total_weeks = (end_date - start_date).days // 7
                    aantal_mesos = total_weeks // weken_per_meso
                    
                    # Verwijder bestaande meso cycli
                    execute_db_query("DELETE FROM meso_cycli WHERE macro_id = ?", (selected_macro_id,))
                    
                    # Genereer meso cycli
                    for i in range(aantal_mesos):
                        meso_start = start_date + timedelta(weeks=i * weken_per_meso)
                        meso_end = start_date + timedelta(weeks=(i + 1) * weken_per_meso - 1)
                        
                        # Ensure we don't go past the macro end date
                        if meso_end > end_date:
                            meso_end = end_date
                        
                        # Load berekening met variatie
                        week_in_macro = i + 1
                        calculated_load = calculate_periodization_load(week_in_macro, aantal_mesos, focus_type)
                        
                        # Voeg variatie toe
                        if i % 3 == 2:  # Elke 3e week recovery
                            load_percentage = max(50, calculated_load - load_variatie)
                            focus_thema = f"{focus_type} - Recovery Week"
                        else:
                            load_percentage = min(100, calculated_load + (load_variatie * (i % 2)))
                            focus_thema = f"{focus_type} - Loading Week"
                        
                        execute_db_query("""
                            INSERT INTO meso_cycli 
                            (meso_id, macro_id, naam, start_datum, eind_datum, week_nummer, 
                             load_percentage, focus_themas, wedstrijden)
                            VALUES (nextval('meso_id_seq'), ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (selected_macro_id, f"Meso {i+1}", meso_start, meso_end,
                              week_in_macro, int(load_percentage), focus_thema, 0))
                    
                    st.success(f"✅ {aantal_mesos} meso cycli automatisch gegenereerd!")
                    st.rerun()
            
            # Bestaande meso cycli tonen
            st.markdown("#### 📋 Bestaande Meso Cycli")
            
            meso_cycli = execute_db_query("""
                SELECT meso_id, naam, start_datum, eind_datum, week_nummer, 
                       load_percentage, focus_themas, wedstrijden
                FROM meso_cycli 
                WHERE macro_id = ?
                ORDER BY start_datum
            """, (selected_macro_id,))
            
            if meso_cycli:
                for meso in meso_cycli:
                    meso_id, naam, start, eind, week_nr, load_pct, focus, wedstrijden = meso
                    start_str = pd.to_datetime(start).date().strftime('%d/%m')
                    eind_str = pd.to_datetime(eind).date().strftime('%d/%m')
                    
                    # Load percentage kleur
                    if load_pct < 70:
                        load_color = "🟢"
                    elif load_pct < 85:
                        load_color = "🟡"
                    else:
                        load_color = "🔴"
                    
                    with st.expander(f"{load_color} {naam} - Week {week_nr} ({start_str}-{eind_str}) - {load_pct}% Load"):
                        col_a, col_b = st.columns(2)
                        
                        with col_a:
                            st.write(f"**Focus:** {focus}")
                            st.write(f"**Load:** {load_pct}%")
                        
                        with col_b:
                            st.write(f"**Wedstrijden:** {wedstrijden}")
                            
                            # Edit opties
                            nieuwe_load = st.number_input(f"Nieuwe Load %", 
                                                        min_value=30, max_value=100, 
                                                        value=load_pct, key=f"load_{meso_id}")
                            
                            if st.button("💾 Update", key=f"update_{meso_id}"):
                                execute_db_query("""
                                    UPDATE meso_cycli SET load_percentage = ? WHERE meso_id = ?
                                """, (nieuwe_load, meso_id))
                                st.rerun()
                
                # Visualisatie van load periodisering
                if len(meso_cycli) > 1:
                    st.markdown("#### 📈 Load Periodisering Visualisatie")
                    
                    df_meso = pd.DataFrame(meso_cycli, columns=[
                        'meso_id', 'naam', 'start_datum', 'eind_datum', 'week_nummer',
                        'load_percentage', 'focus_themas', 'wedstrijden'
                    ])
                    
                    fig = px.line(df_meso, x='week_nummer', y='load_percentage',
                                title="Trainingsload Periodisering",
                                markers=True, line_shape='spline')
                    
                    fig.add_hline(y=80, line_dash="dash", line_color="orange", 
                                annotation_text="Hoge Load Threshold")
                    fig.add_hline(y=60, line_dash="dash", line_color="green", 
                                annotation_text="Recovery Threshold")
                    
                    fig.update_layout(
                        xaxis_title="Week Nummer",
                        yaxis_title="Load Percentage (%)",
                        yaxis_range=[40, 105]
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("📭 Nog geen meso cycli voor deze macro cyclus")
        else:
            st.warning("⚠️ Maak eerst macro cycli aan")

with tab4:
    st.markdown("### 🔄 Microcyclus Templates")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown("#### ➕ Nieuwe Template")
        
        with st.form("nieuwe_template"):
            template_naam = st.text_input("📝 Template Naam")
            template_type = st.selectbox("🏷️ Week Type", 
                                       ["Loading", "Recovery", "Competition", "Deload"])
            template_beschrijving = st.text_area("📋 Beschrijving")
            
            st.markdown("**📅 Dag Configuratie:**")
            
            dagen = []
            dag_namen = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"]
            
            for i, dag_naam in enumerate(dag_namen):
                col_a, col_b = st.columns(2)
                with col_a:
                    dag_type = st.selectbox(f"{dag_naam} Type", 
                                          ["Training", "Wedstrijd", "Recovery", "Activation", "Rust"],
                                          key=f"dag_type_{i}")
                with col_b:
                    dag_intensiteit = st.slider(f"{dag_naam} Intensiteit", 
                                               1, 10, 5, key=f"dag_int_{i}")
                dagen.append((dag_type, dag_intensiteit))
            
            template_submitted = st.form_submit_button("✅ Template Opslaan")
            
            if template_submitted and template_naam:
                execute_db_query("""
                    INSERT INTO microcyclus_templates 
                    (template_id, naam, type_week, beschrijving,
                     dag_1_type, dag_1_intensiteit, dag_2_type, dag_2_intensiteit,
                     dag_3_type, dag_3_intensiteit, dag_4_type, dag_4_intensiteit,
                     dag_5_type, dag_5_intensiteit, dag_6_type, dag_6_intensiteit,
                     dag_7_type, dag_7_intensiteit)
                    VALUES (nextval('template_id_seq'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (template_naam, template_type, template_beschrijving,
                      *[item for dag_type, intensiteit in dagen for item in (dag_type, intensiteit)]))
                
                st.success(f"✅ Template '{template_naam}' opgeslagen!")
                st.rerun()
    
    with col2:
        st.markdown("#### 📋 Bestaande Templates")
        
        templates = execute_db_query("""
            SELECT template_id, naam, type_week, beschrijving,
                   dag_1_type, dag_1_intensiteit, dag_2_type, dag_2_intensiteit,
                   dag_3_type, dag_3_intensiteit, dag_4_type, dag_4_intensiteit,
                   dag_5_type, dag_5_intensiteit, dag_6_type, dag_6_intensiteit,
                   dag_7_type, dag_7_intensiteit
            FROM microcyclus_templates
            ORDER BY type_week, naam
        """)
        
        if templates:
            for template in templates:
                template_id = template[0]
                naam = template[1]
                type_week = template[2]
                beschrijving = template[3]
                
                # Type icon
                type_icons = {
                    "Loading": "🔴",
                    "Recovery": "🟢", 
                    "Competition": "🏆",
                    "Deload": "🟡"
                }
                icon = type_icons.get(type_week, "⚪")
                
                with st.expander(f"{icon} {naam} ({type_week})"):
                    st.write(f"**Beschrijving:** {beschrijving}")
                    
                    # Toon week schema
                    dag_namen = ["Ma", "Di", "Wo", "Do", "Vr", "Za", "Zo"]
                    dag_data = template[4:]  # Alle dag data
                    
                    # Organiseer dag data in pairs (type, intensiteit)
                    week_schema = []
                    for i in range(0, len(dag_data), 2):
                        dag_type = dag_data[i]
                        dag_intensiteit = dag_data[i + 1] if i + 1 < len(dag_data) else 1
                        week_schema.append((dag_type, dag_intensiteit))
                    
                    # Visualiseer week
                    cols = st.columns(7)
                    for i, (dag_naam, (dag_type, intensiteit)) in enumerate(zip(dag_namen, week_schema)):
                        with cols[i]:
                            # Intensiteit kleur
                            if intensiteit <= 3:
                                color = "#2ECC71"  # Groen
                            elif intensiteit <= 6:
                                color = "#F39C12"  # Oranje
                            else:
                                color = "#E74C3C"  # Rood
                            
                            st.markdown(f"""
                            <div style='text-align: center; padding: 10px; border-radius: 5px; background-color: {color}20; border: 2px solid {color};'>
                                <strong>{dag_naam}</strong><br>
                                {dag_type}<br>
                                <small>{intensiteit}/10</small>
                            </div>
                            """, unsafe_allow_html=True)
                    
                    if st.button("🗑️ Verwijderen", key=f"del_template_{template_id}"):
                        execute_db_query("DELETE FROM microcyclus_templates WHERE template_id = ?", (template_id,))
                        st.rerun()
        else:
            st.info("📭 Nog geen templates aangemaakt")

with tab5:
    st.markdown("### 📅 Periodisering Overview")
    
    # Seizoen selectie voor overview
    seizoenen = execute_db_query("SELECT planning_id, seizoen_naam FROM seizoen_planning ORDER BY start_datum DESC")
    
    if seizoenen:
        seizoen_options = {f"{s[1]}": s[0] for s in seizoenen}
        overview_seizoen = st.selectbox("📅 Selecteer Seizoen voor Overview", 
                                      list(seizoen_options.keys()), key="overview_seizoen")
        overview_seizoen_id = seizoen_options[overview_seizoen]
        
        # Haal volledige planning data op
        planning_data = execute_db_query("""
            SELECT 
                sp.seizoen_naam, sp.start_datum, sp.eind_datum,
                mc.macro_id, mc.naam as macro_naam, mc.start_datum as macro_start, 
                mc.eind_datum as macro_eind, mc.focus_type, mc.intensiteit_niveau,
                meso.meso_id, meso.naam as meso_naam, meso.start_datum as meso_start,
                meso.eind_datum as meso_eind, meso.week_nummer, meso.load_percentage
            FROM seizoen_planning sp
            LEFT JOIN macro_cycli mc ON sp.planning_id = mc.planning_id
            LEFT JOIN meso_cycli meso ON mc.macro_id = meso.macro_id
            WHERE sp.planning_id = ?
            ORDER BY mc.start_datum, meso.start_datum
        """, (overview_seizoen_id,))
        
        if planning_data:
            df_planning = pd.DataFrame(planning_data, columns=[
                'seizoen_naam', 'seizoen_start', 'seizoen_eind', 'macro_id', 'macro_naam',
                'macro_start', 'macro_eind', 'focus_type', 'intensiteit_niveau',
                'meso_id', 'meso_naam', 'meso_start', 'meso_eind', 'week_nummer', 'load_percentage'
            ])
            
            # Convert dates
            date_columns = ['seizoen_start', 'seizoen_eind', 'macro_start', 'macro_eind', 'meso_start', 'meso_eind']
            for col in date_columns:
                df_planning[col] = pd.to_datetime(df_planning[col])
            
            # Seizoen overzicht metrics
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                aantal_macros = df_planning['macro_id'].nunique()
                st.metric("Macro Cycli", aantal_macros)
            
            with col2:
                aantal_mesos = df_planning['meso_id'].nunique()
                st.metric("Meso Cycli", aantal_mesos)
            
            with col3:
                if not df_planning['load_percentage'].isna().all():
                    avg_load = df_planning['load_percentage'].mean()
                    st.metric("Gem. Load", f"{avg_load:.0f}%")
                else:
                    st.metric("Gem. Load", "N/A")
            
            with col4:
                seizoen_duur = (df_planning['seizoen_eind'].iloc[0] - df_planning['seizoen_start'].iloc[0]).days
                st.metric("Seizoen Duur", f"{seizoen_duur} dagen")
            
            # Timeline visualisatie
            st.markdown("#### 📊 Periodisering Timeline")
            
            fig = go.Figure()
            
            # Macro cycli als brede balken
            macro_data = df_planning.dropna(subset=['macro_id']).drop_duplicates(subset=['macro_id'])
            
            for _, macro in macro_data.iterrows():
                # Intensiteit kleur mapping
                intensity_colors = {1: "#2ECC71", 2: "#F39C12", 3: "#E67E22", 4: "#E74C3C", 5: "#8E44AD"}
                color = intensity_colors.get(macro['intensiteit_niveau'], "#95A5A6")
                
                fig.add_trace(go.Scatter(
                    x=[macro['macro_start'], macro['macro_eind']],
                    y=[macro['macro_naam'], macro['macro_naam']],
                    mode='lines',
                    line=dict(color=color, width=20),
                    name=f"{macro['macro_naam']} (Int: {macro['intensiteit_niveau']})",
                    hovertemplate=f"<b>{macro['macro_naam']}</b><br>" +
                                f"Focus: {macro['focus_type']}<br>" +
                                f"Start: {macro['macro_start'].strftime('%d/%m/%Y')}<br>" +
                                f"Eind: {macro['macro_eind'].strftime('%d/%m/%Y')}<br>" +
                                f"Intensiteit: {macro['intensiteit_niveau']}/5<extra></extra>"
                ))
            
            fig.update_layout(
                title="Macro Cycli Timeline",
                xaxis_title="Datum",
                yaxis_title="Macro Cyclus",
                height=max(400, len(macro_data) * 50),
                showlegend=True
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Load periodisering grafiek
            if not df_planning['load_percentage'].isna().all():
                st.markdown("#### 📈 Load Periodisering")
                
                meso_data = df_planning.dropna(subset=['meso_id', 'load_percentage'])
                
                if len(meso_data) > 0:
                    fig_load = px.line(meso_data, x='week_nummer', y='load_percentage',
                                     color='macro_naam', markers=True,
                                     title="Trainingsload per Week",
                                     labels={'week_nummer': 'Week Nummer', 
                                            'load_percentage': 'Load Percentage (%)'})
                    
                    # Voeg load zones toe
                    fig_load.add_hline(y=80, line_dash="dash", line_color="red", 
                                     annotation_text="Hoge Load")
                    fig_load.add_hline(y=60, line_dash="dash", line_color="orange", 
                                     annotation_text="Gemiddelde Load")
                    fig_load.add_hline(y=40, line_dash="dash", line_color="green", 
                                     annotation_text="Recovery Load")
                    
                    st.plotly_chart(fig_load, use_container_width=True)
            
            # Planning tabel
            st.markdown("#### 📋 Detailleerde Planning")
            
            # Maak overzicht tabel
            if not df_planning.empty:
                display_data = df_planning.dropna(subset=['macro_id']).copy()
                
                if not display_data.empty:
                    display_data['Periode'] = display_data.apply(
                        lambda row: f"{row['macro_start'].strftime('%d/%m')} - {row['macro_eind'].strftime('%d/%m')}" 
                        if pd.notna(row['macro_start']) else "N/A", axis=1
                    )
                    
                    display_columns = ['macro_naam', 'focus_type', 'intensiteit_niveau', 'Periode']
                    column_names = ['Macro Cyclus', 'Focus Type', 'Intensiteit', 'Periode']
                    
                    display_df = display_data[display_columns].drop_duplicates()
                    display_df.columns = column_names
                    
                    # Style op basis van intensiteit
                    def style_intensiteit(row):
                        intensiteit = row['Intensiteit']
                        if intensiteit <= 2:
                            return ['background-color: #2ECC7120' for _ in row]
                        elif intensiteit <= 3:
                            return ['background-color: #F39C1220' for _ in row]
                        else:
                            return ['background-color: #E74C3C20' for _ in row]
                    
                    styled_df = display_df.style.apply(style_intensiteit, axis=1)
                    st.dataframe(styled_df, use_container_width=True)
        else:
            st.info("📭 Nog geen planning data voor dit seizoen")
    else:
        st.warning("⚠️ Maak eerst een seizoen aan")

# Database cleanup
# Safe database connection cleanup
# Database cleanup handled by Supabase helpers