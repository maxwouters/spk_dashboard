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
import plotly.express as px
import plotly.graph_objects as go


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

st.set_page_config(page_title="SPK Dashboard", layout="wide")

st.subheader("🎯 Coaching Principes & Training Thema's")

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
# Database tabellen maken en migreren
try:
    # Check of nieuwe kolommen bestaan
    existing_columns = get_table_columns(con, "coaching_principes")
    
    # Voeg nieuwe kolommen toe als ze niet bestaan
    if 'spelfase' not in existing_columns:
        execute_db_query("ALTER TABLE coaching_principes ADD COLUMN spelfase TEXT DEFAULT 'Aanval'")
    
    if 'niveau' not in existing_columns:
        execute_db_query("ALTER TABLE coaching_principes ADD COLUMN niveau INTEGER DEFAULT 1")
    
    if 'parent_id' not in existing_columns:
        execute_db_query("ALTER TABLE coaching_principes ADD COLUMN parent_id INTEGER")
    
    # Migreer oude 'categorie' data naar 'spelfase' als deze nog bestaat
    if 'categorie' in existing_columns and 'spelfase' in existing_columns:
        # Map oude categorieën naar spelfases
        execute_db_query("""
            UPDATE coaching_principes 
            SET spelfase = CASE 
                WHEN categorie IN ('Aanval', 'Spelorganisatie') THEN 'Aanval'
                WHEN categorie IN ('Verdediging') THEN 'Verdediging'
                WHEN categorie IN ('Overgangsmomenten') THEN 'Omschakelen naar Aanval'
                WHEN categorie IN ('Technisch', 'Tactisch', 'Mentaal', 'Fysiek') THEN 'Aanval'
                ELSE 'Aanval'
            END
            WHERE spelfase IS NULL OR spelfase = 'Aanval'
        """)
        
        # Verwijder oude categorie kolom (optioneel)
        # execute_db_query("ALTER TABLE coaching_principes DROP COLUMN categorie")

except Exception as e:
    # Als tabel niet bestaat, maak nieuwe aan
    execute_db_query("""
        CREATE TABLE IF NOT EXISTS coaching_principes (
            principe_id INTEGER PRIMARY KEY,
            naam TEXT,
            spelfase TEXT DEFAULT 'Aanval',
            niveau INTEGER DEFAULT 1,
            parent_id INTEGER,
            beschrijving TEXT,
            kleur TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (parent_id) REFERENCES coaching_principes(principe_id)
        )
    """)

# Update training_principes tabel voor minuten i.p.v. percentage
try:
    # Check of kolom bestaat
    existing_columns = get_table_columns(con, "training_principes")
    
    if 'focus_minuten' not in existing_columns:
        execute_db_query("ALTER TABLE training_principes ADD COLUMN focus_minuten INTEGER DEFAULT 15")
    
    # Migreer bestaande percentage data naar minuten (aanname: 100% = custom training duur)
    if 'focus_percentage' in existing_columns and 'focus_minuten' in existing_columns:
        execute_db_query("""
            UPDATE training_principes 
            SET focus_minuten = CAST(focus_percentage * 0.9 AS INTEGER)
            WHERE focus_minuten IS NULL OR focus_minuten = 15
        """)

except Exception as e:
    # Als tabel niet bestaat, maak nieuwe aan
    execute_db_query("""
        CREATE TABLE IF NOT EXISTS training_principes (
            link_id INTEGER PRIMARY KEY,
            training_id INTEGER,
            principe_id INTEGER,
            focus_minuten INTEGER DEFAULT 15,
            notities TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (training_id) REFERENCES trainings_calendar(training_id),
            FOREIGN KEY (principe_id) REFERENCES coaching_principes(principe_id)
        )
    """)

# Sequences maken
try:
    execute_db_query("CREATE SEQUENCE IF NOT EXISTS principe_id_seq START 1")
    execute_db_query("CREATE SEQUENCE IF NOT EXISTS link_id_seq START 1")
except:
    pass

# Tabs voor verschillende secties
tab1, tab2, tab3, tab4 = st.tabs(["🎯 Principes", "🔗 Training Koppeling", "📊 Thema Analytics", "📈 Trend Analyse"])

with tab1:
    st.markdown("### 🎯 Coaching Principes Beheer")

# Helper functies voor hiërarchie
def get_principe_path(principe_id, con):
    """Krijg het volledige pad van een principe (parent > child > subchild)"""
    path = []
    current_id = principe_id
    
    while current_id:
        result = (lambda result: result[0] if result else None)(execute_db_query("""
            SELECT naam, parent_id FROM coaching_principes WHERE principe_id = ?
        """, (current_id,)))
        
        if result:
            naam, parent_id = result
            path.insert(0, naam)
            current_id = parent_id
        else:
            break
    
    return " > ".join(path)

def get_children(parent_id, con):
    """Krijg alle directe kinderen van een principe"""
    return execute_db_query("""
        SELECT principe_id, naam, spelfase, niveau, beschrijving, kleur
        FROM coaching_principes 
        WHERE parent_id = ? OR (parent_id IS NULL AND ? IS NULL)
        ORDER BY spelfase, naam
    """, (parent_id, parent_id))

# Nieuw principe toevoegen
with st.expander("➕ Nieuw Principe Toevoegen"):
    with st.form("nieuw_principe"):
        col1, col2 = st.columns(2)
        with col1:
            principe_naam = st.text_input("📝 Principe Naam", placeholder="Bijv. Positiespel")
            
            # Spelfase selectie
            spelfase = st.selectbox("⚽ Spelfase", 
                                  ["Aanval", "Verdediging", "Omschakelen naar Aanval", "Omschakelen naar Verdediging"])
            
            # Niveau selectie
            niveau = st.selectbox("📊 Niveau", 
                                [(1, "1 - Hoofdprincipe"), (2, "2 - Subprincipe"), (3, "3 - Sub-subprincipe")],
                                format_func=lambda x: x[1])[0]
            
        with col2:
            # Parent selectie (alleen als niveau > 1)
            parent_id = None
            if niveau > 1:
                # Haal mogelijke parents op
                max_parent_niveau = niveau - 1
                parents = execute_db_query("""
                    SELECT principe_id, naam, spelfase, niveau
                    FROM coaching_principes 
                    WHERE niveau = ? AND spelfase = ?
                    ORDER BY naam
                """, (max_parent_niveau, spelfase))
                
                if parents:
                    parent_options = {f"{p[1]} (Niveau {p[3]})": p[0] for p in parents}
                    if parent_options:
                        selected_parent = st.selectbox("👆 Parent Principe", list(parent_options.keys()))
                        parent_id = parent_options[selected_parent]
                else:
                    st.warning(f"⚠️ Geen niveau {max_parent_niveau} principes gevonden voor {spelfase}")
            
# Vast kleurenschema
            kleur_opties = {
                "🟢 Groen Licht": "#90EE90",
                "🟢 Groen Middel": "#32CD32", 
                "🟢 Groen Donker": "#006400",
                "🔴 Rood Licht": "#FFB6C1",
                "🔴 Rood Middel": "#FF6B6B",
                "🔴 Rood Donker": "#8B0000",
                "🟡 Geel Licht": "#FFFF99",
                "🟡 Geel Middel": "#FFD700",
                "🟡 Geel Donker": "#DAA520",
                "🟠 Oranje Licht": "#FFE4B5",
                "🟠 Oranje Middel": "#FFA500",
                "🟠 Oranje Donker": "#FF8C00",
                "🔵 Blauw Licht": "#ADD8E6",
                "🔵 Blauw Middel": "#4169E1",
                "🔵 Blauw Donker": "#000080"
            }
            
            selected_kleur_display = st.selectbox("🎨 Kleur", list(kleur_opties.keys()))
            principe_kleur = kleur_opties[selected_kleur_display]
            
        principe_beschrijving = st.text_area("📋 Beschrijving", 
                                           placeholder="Uitgebreide beschrijving van dit coaching principe...")
        
        submitted = st.form_submit_button("✅ Principe Toevoegen")
        
        if submitted and principe_naam:
            execute_db_query("""
                INSERT INTO coaching_principes (principe_id, naam, spelfase, niveau, parent_id, beschrijving, kleur)
                VALUES (nextval('principe_id_seq'), ?, ?, ?, ?, ?, ?)
            """, (principe_naam, spelfase, niveau, parent_id, principe_beschrijving, principe_kleur))
            
            st.success(f"✅ Principe '{principe_naam}' toegevoegd!")
            st.rerun()

# Hiërarchische weergave van principes
st.markdown("### 📋 Coaching Principes Hiërarchie")

# Spelfase filter
spelfase_filter = st.selectbox("🎮 Filter op Spelfase", 
                             ["Alle", "Aanval", "Verdediging", "Omschakelen naar Aanval", "Omschakelen naar Verdediging"])

def render_principe_tree(parent_id=None, indent_level=0):
    """Recursief renderen van de principe boom"""
    # Haal kinderen op
    if spelfase_filter == "Alle":
        if parent_id is None:
            children = execute_db_query("""
                SELECT principe_id, naam, spelfase, niveau, beschrijving, kleur
                FROM coaching_principes 
                WHERE parent_id IS NULL
                ORDER BY spelfase, naam
            """)
        else:
            children = execute_db_query("""
                SELECT principe_id, naam, spelfase, niveau, beschrijving, kleur
                FROM coaching_principes 
                WHERE parent_id = ?
                ORDER BY spelfase, naam
            """, (parent_id,))
    else:
        if parent_id is None:
            children = execute_db_query("""
                SELECT principe_id, naam, spelfase, niveau, beschrijving, kleur
                FROM coaching_principes 
                WHERE parent_id IS NULL AND spelfase = ?
                ORDER BY naam
            """, (spelfase_filter,))
        else:
            children = execute_db_query("""
                SELECT principe_id, naam, spelfase, niveau, beschrijving, kleur
                FROM coaching_principes 
                WHERE parent_id = ? AND spelfase = ?
                ORDER BY naam
            """, (parent_id, spelfase_filter))
    
    for child in children:
        principe_id, naam, spelfase, niveau, beschrijving, kleur = child
        
        # Bepaal indentatie en icon op basis van niveau
        indent = "　" * indent_level
        if niveau == 1:
            icon = "📁"
        elif niveau == 2:
            icon = "📂"
        else:
            icon = "📄"
        
        # Toon principe
        with st.container():
            col1, col2, col3, col4 = st.columns([4, 1, 1, 1])
            
            with col1:
                # Hiërarchische weergave met indentatie
                st.markdown(f"{indent}{icon} **{naam}** [{spelfase}] (Niveau {niveau})")
                if beschrijving:
                    st.markdown(f"{indent}　　*{beschrijving}*")
            
            with col2:
                # Kleur indicator
                st.markdown(f"<div style='width: 20px; height: 20px; background-color: {kleur}; border-radius: 50%; margin: 5px;'></div>", 
                          unsafe_allow_html=True)
            
            with col3:
                # Training count
                training_count = (lambda result: result[0] if result else None)(execute_db_query("""
                    SELECT COUNT(DISTINCT tp.training_id) 
                    FROM training_principes tp
                    WHERE tp.principe_id = ?
                """, (principe_id,)))[0]
                st.metric("Trainingen", training_count)
            
            with col4:
                # Delete knop
                if st.button("🗑️", key=f"delete_principe_{principe_id}", help="Verwijderen"):
                    # Check voor kinderen
                    has_children = (lambda result: result[0] if result else None)(execute_db_query("""
                        SELECT COUNT(*) FROM coaching_principes WHERE parent_id = ?
                    """, (principe_id,)))[0]
                    
                    if has_children > 0:
                        st.error("❌ Kan niet verwijderen: heeft sub-principes")
                    else:
                        execute_db_query("DELETE FROM training_principes WHERE principe_id = ?", (principe_id,))
                        execute_db_query("DELETE FROM coaching_principes WHERE principe_id = ?", (principe_id,))
                        st.success("Principe verwijderd!")
                        st.rerun()
        
        # Recursief toon kinderen
        render_principe_tree(principe_id, indent_level + 1)

# Render de volledige boom
render_principe_tree()

# Check of er principes zijn en toon message
result = execute_db_query("SELECT COUNT(*) FROM coaching_principes")
total_principes = result[0][0] if result and result[0] else 0
if total_principes == 0:
    st.info("📭 Nog geen coaching principes toegevoegd. Gebruik de sectie hierboven om je eerste principe toe te voegen.")

with tab2:
    st.markdown("### 🔗 Training Koppeling aan Principes")
    
    # Haal trainingen op
    trainings = execute_db_query("""
        SELECT training_id, datum, type, omschrijving 
        FROM trainings_calendar 
        WHERE datum >= CURRENT_DATE - INTERVAL '30 days'
        ORDER BY datum DESC
    """)
    
    # Haal principes op met hiërarchische informatie
    available_principes = execute_db_query("""
        SELECT principe_id, naam, spelfase, niveau, parent_id, kleur
        FROM coaching_principes 
        ORDER BY spelfase, niveau, naam
    """)
    
    if trainings and available_principes:
        # Selecteer training
        training_options = {f"{pd.to_datetime(t[1]).date().strftime('%d/%m/%Y')} - {t[2]} - {t[3] or 'Geen beschrijving'}": t[0] 
                          for t in trainings}
        
        geselecteerde_training_display = st.selectbox("🏃 Selecteer Training", list(training_options.keys()))
        geselecteerde_training_id = training_options[geselecteerde_training_display]
        
        # Toon huidige koppelingen
        huidige_koppelingen = execute_db_query("""
            SELECT tp.link_id, cp.naam, cp.spelfase, cp.niveau, cp.kleur, tp.focus_minuten, tp.notities, cp.principe_id
            FROM training_principes tp
            JOIN coaching_principes cp ON tp.principe_id = cp.principe_id
            WHERE tp.training_id = ?
            ORDER BY cp.spelfase, cp.niveau, tp.focus_minuten DESC
        """, (geselecteerde_training_id,))
        
        if huidige_koppelingen:
            st.markdown("#### 📋 Huidige Thema's voor deze Training")
            
            total_minuten = sum([k[5] or 0 for k in huidige_koppelingen])
            
            # Groepeer per spelfase
            spelfases = {}
            for koppeling in huidige_koppelingen:
                link_id, naam, spelfase, niveau, kleur, minuten, notities, principe_id = koppeling
                if spelfase not in spelfases:
                    spelfases[spelfase] = []
                spelfases[spelfase].append(koppeling)
            
            for spelfase, koppelingen in spelfases.items():
                st.markdown(f"**🎮 {spelfase}**")
                
                for koppeling in koppelingen:
                    link_id, naam, spelfase, niveau, kleur, minuten, notities, principe_id = koppeling
                    
                    col1, col2, col3 = st.columns([3, 1, 1])
                    
                    with col1:
                        # Toon volledig pad
                        full_path = get_principe_path(principe_id, con)
                        indent = "　" * (niveau - 1)
                        niveau_icon = "📁" if niveau == 1 else "📂" if niveau == 2 else "📄"
                        
                        st.markdown(f"<div style='background-color: {kleur}20; padding: 8px; border-radius: 5px; border-left: 4px solid {kleur};'>"
                                  f"{indent}{niveau_icon} <strong>{full_path}</strong><br>"
                                  f"<small>Focus: {minuten or 0} min | {notities or 'Geen notities'}</small></div>", 
                                  unsafe_allow_html=True)
                    
                    with col2:
                        st.metric("Minuten", f"{minuten or 0} min")
                    
                    with col3:
                        if st.button("🗑️", key=f"delete_link_{link_id}", help="Verwijder koppeling"):
                            execute_db_query("DELETE FROM training_principes WHERE link_id = ?", (link_id,))
                            st.rerun()
            
            # Training tijd overzicht
            if total_minuten > 0:
                training_duur = 90  # Standaard training duur
                percentage_gebruikt = (total_minuten / training_duur) * 100
                
                st.progress(min(percentage_gebruikt / 100, 1.0))
                if total_minuten > training_duur:
                    st.warning(f"⚠️ Totaal {total_minuten} minuten (meer dan {training_duur} min training)")
                elif total_minuten < training_duur:
                    resterende_tijd = training_duur - total_minuten
                    st.info(f"ℹ️ Totaal: {total_minuten} min van {training_duur} min (nog {resterende_tijd} min beschikbaar)")
                else:
                    st.success(f"✅ Training volledig ingedeeld ({training_duur} minuten)")
        else:
            st.info("📭 Nog geen thema's gekoppeld aan deze training")
        
        # Nieuwe koppeling toevoegen
        st.markdown("#### ➕ Nieuw Thema Toevoegen")
        
        with st.form("nieuwe_koppeling"):
            col1, col2 = st.columns(2)
            
            with col1:
                # Maak hiërarchische principe opties
                principe_options = {}
                for p in available_principes:
                    principe_id, naam, spelfase, niveau, parent_id, kleur = p
                    full_path = get_principe_path(principe_id, con)
                    indent = "　" * (niveau - 1)
                    niveau_icon = "📁" if niveau == 1 else "📂" if niveau == 2 else "📄"
                    display_name = f"{indent}{niveau_icon} {full_path} [{spelfase}]"
                    principe_options[display_name] = principe_id
                
                geselecteerd_principe_display = st.selectbox("🎯 Selecteer Principe", list(principe_options.keys()))
                geselecteerd_principe_id = principe_options[geselecteerd_principe_display]
                
                focus_minuten = st.number_input("⏱️ Focus Minuten", min_value=1, max_value=120, value=15,
                                               help="Hoeveel minuten van de training besteed je aan dit principe?")
            
            with col2:
                koppeling_notities = st.text_area("📝 Notities", 
                                                 placeholder="Specifieke oefeningen, focus punten, etc.",
                                                 height=100)
            
            submitted = st.form_submit_button("✅ Koppeling Toevoegen")
            
            if submitted:
                execute_db_query("""
                    INSERT INTO training_principes (link_id, training_id, principe_id, focus_minuten, notities)
                    VALUES (nextval('link_id_seq'), ?, ?, ?, ?)
                """, (geselecteerde_training_id, geselecteerd_principe_id, focus_minuten, koppeling_notities))
                
                st.success("✅ Thema gekoppeld aan training!")
                st.rerun()
    
    elif not trainings:
        st.warning("⚠️ Geen trainingen gevonden. Voeg eerst trainingen toe in de Trainingskalender.")
    elif not available_principes:
        st.warning("⚠️ Geen coaching principes gevonden. Voeg eerst principes toe.")

with tab3:
    st.markdown("### 📊 Thema Analytics")
    
    # Analyse periode selectie
    col1, col2 = st.columns(2)
    with col1:
        analyse_periode = st.selectbox("📅 Analyse Periode", 
                                     ["Laatste 30 dagen", "Laatste 90 dagen", "Laatste 6 maanden", "Alles"])
    
    with col2:
        weergave_type = st.selectbox("📈 Weergave Type", 
                                   ["Minuten Verdeling", "Absolute Uren", "Training Count"])
    
    # Bepaal datumfilter
    today = datetime.today().date()
    if analyse_periode == "Laatste 30 dagen":
        filter_datum = today - pd.DateOffset(days=30)
    elif analyse_periode == "Laatste 90 dagen":
        filter_datum = today - pd.DateOffset(days=90)
    elif analyse_periode == "Laatste 6 maanden":
        filter_datum = today - pd.DateOffset(months=6)
    else:
        filter_datum = date(2000, 1, 1)
    
    # Haal analytics data op
    analytics_data = execute_db_query("""
        SELECT 
            cp.principe_id,
            cp.naam,
            cp.spelfase,
            cp.niveau,
            cp.kleur,
            COUNT(DISTINCT tc.training_id) as aantal_trainingen,
            SUM(tp.focus_minuten) as totaal_minuten,
            AVG(tp.focus_minuten) as gemiddeld_minuten
        FROM training_principes tp
        JOIN coaching_principes cp ON tp.principe_id = cp.principe_id
        JOIN trainings_calendar tc ON tp.training_id = tc.training_id
        WHERE tc.datum >= ?
        GROUP BY cp.principe_id, cp.naam, cp.spelfase, cp.niveau, cp.kleur
        ORDER BY cp.spelfase, totaal_minuten DESC
    """, (filter_datum,))
    
    if analytics_data:
        # Voeg volledige paden toe
        analytics_with_paths = []
        for row in analytics_data:
            principe_id, naam, spelfase, niveau, kleur, aantal_trainingen, totaal_minuten, gemiddeld_minuten = row
            full_path = get_principe_path(principe_id, con)
            analytics_with_paths.append((full_path, spelfase, niveau, kleur, aantal_trainingen, totaal_minuten, gemiddeld_minuten))
        
        df_analytics = pd.DataFrame(analytics_with_paths, 
                                  columns=['Principe', 'Spelfase', 'Niveau', 'Kleur', 'Aantal_Trainingen', 
                                         'Totaal_Minuten', 'Gemiddeld_Minuten'])
        
        # Metrics overzicht
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            totaal_trainingen = (lambda result: result[0] if result else None)(execute_db_query("""
                SELECT COUNT(DISTINCT tp.training_id) 
                FROM training_principes tp
                JOIN trainings_calendar tc ON tp.training_id = tc.training_id
                WHERE tc.datum >= ?
            """, (filter_datum,)))[0]
            st.metric("Trainingen met Thema's", totaal_trainingen)
        
        with col2:
            unieke_principes = len(df_analytics)
            st.metric("Actieve Principes", unieke_principes)
        
        with col3:
            gemiddeld_per_training = df_analytics['Totaal_Minuten'].sum() / totaal_trainingen if totaal_trainingen > 0 else 0
            st.metric("Gem. Focus per Training", f"{gemiddeld_per_training:.0f} min")
        
        with col4:
            meest_gebruikt = df_analytics.iloc[0]['Principe'] if len(df_analytics) > 0 else "N/A"
            st.metric("Meest Gebruikt", meest_gebruikt)
        
        # Visualisaties
        col1, col2 = st.columns(2)
        
        with col1:
            # Pie chart voor principe verdeling
            if weergave_type == "Absolute Uren":
                values = df_analytics['Totaal_Minuten'] / 60  # Converteer naar uren
                title = "Verdeling Totale Uren"
            elif weergave_type == "Training Count":
                values = df_analytics['Aantal_Trainingen']
                title = "Aantal Trainingen per Principe"
            else:  # Percentage Verdeling
                values = df_analytics['Totaal_Minuten']
                title = "Verdeling Focus Minuten"
            
            fig_pie = px.pie(df_analytics, values=values, names='Principe', 
                           color='Principe', color_discrete_map={row['Principe']: row['Kleur'] for _, row in df_analytics.iterrows()},
                           title=title)
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_pie, use_container_width=True)
        
        with col2:
            # Bar chart voor spelfase verdeling
            spelfase_data = df_analytics.groupby('Spelfase').agg({
                'Totaal_Minuten': 'sum',
                'Aantal_Trainingen': 'sum'
            }).reset_index()
            
            if weergave_type == "Absolute Uren":
                y_values = spelfase_data['Totaal_Minuten'] / 60
                y_title = "Totaal Uren"
            elif weergave_type == "Training Count":
                y_values = spelfase_data['Aantal_Trainingen']
                y_title = "Aantal Trainingen"
            else:  # Percentage Verdeling -> Minuten
                y_values = spelfase_data['Totaal_Minuten']
                y_title = "Totaal Minuten"
            
            # Kleurmapping voor spelfases
            spelfase_colors = {
                'Aanval': '#2E86AB',
                'Verdediging': '#C73E1D', 
                'Omschakelen naar Aanval': '#F18F01',
                'Omschakelen naar Verdediging': '#A23B72'
            }
            
            fig_bar = px.bar(spelfase_data, x='Spelfase', y=y_values,
                           title=f"{y_title} per Spelfase",
                           color='Spelfase',
                           color_discrete_map=spelfase_colors)
            fig_bar.update_layout(showlegend=False, xaxis_tickangle=45)
            st.plotly_chart(fig_bar, use_container_width=True)
        
        # Detailed tabel
        st.markdown("#### 📋 Gedetailleerd Overzicht")
        
        # Voeg berekende kolommen toe
        df_display = df_analytics.copy()
        df_display['Totaal_Uren'] = (df_display['Totaal_Minuten'] / 60).round(1)
        df_display['Gem_Minuten_Per_Training'] = df_display['Gemiddeld_Minuten'].round(1)
        
        # Format voor weergave
        df_display = df_display[['Principe', 'Spelfase', 'Niveau', 'Aantal_Trainingen', 'Totaal_Minuten', 
                               'Gem_Minuten_Per_Training', 'Totaal_Uren']]
        df_display.columns = ['Principe', 'Spelfase', 'Niveau', 'Trainingen', 'Totaal Min', 'Gem Min per Training', 'Totaal Uren']
        
        # Style de tabel met kleuren
        def highlight_rows(row):
            principe = row['Principe']
            matching_row = df_analytics[df_analytics['Principe'] == principe]
            if not matching_row.empty:
                kleur = matching_row.iloc[0]['Kleur']
                return [f'background-color: {kleur}20' for _ in row]
            return ['' for _ in row]
        
        st.dataframe(df_display.style.apply(highlight_rows, axis=1), use_container_width=True)
        
    else:
        st.info(f"📭 Nog geen thema analytics beschikbaar voor {analyse_periode.lower()}")

with tab4:
    st.markdown("### 📈 Trend Analyse")
    
    # Trend analyse over tijd
    trend_data = execute_db_query("""
        SELECT 
            tc.datum,
            cp.principe_id,
            cp.naam as principe,
            cp.spelfase,
            cp.niveau,
            cp.kleur,
            tp.focus_minuten
        FROM training_principes tp
        JOIN coaching_principes cp ON tp.principe_id = cp.principe_id
        JOIN trainings_calendar tc ON tp.training_id = tc.training_id
        WHERE tc.datum >= CURRENT_DATE - INTERVAL '90 days'
        ORDER BY tc.datum
    """)
    
    if trend_data:
        # Voeg volledige paden toe aan trend data
        trend_with_paths = []
        for row in trend_data:
            datum, principe_id, principe, spelfase, niveau, kleur, focus_minuten = row
            full_path = get_principe_path(principe_id, con)
            trend_with_paths.append((datum, full_path, spelfase, niveau, kleur, focus_minuten))
        
        df_trend = pd.DataFrame(trend_with_paths, columns=['Datum', 'Principe', 'Spelfase', 'Niveau', 'Kleur', 'Focus_Minuten'])
        df_trend['Datum'] = pd.to_datetime(df_trend['Datum'])
        
        # Selecteer principes voor trend
        unique_principes = df_trend['Principe'].unique()
        selected_principes = st.multiselect("🎯 Selecteer Principes voor Trend", 
                                          unique_principes, 
                                          default=unique_principes[:3] if len(unique_principes) > 3 else unique_principes)
        
        if selected_principes:
            # Filter data
            trend_filtered = df_trend[df_trend['Principe'].isin(selected_principes)]
            
            # Groepeer per week
            trend_filtered['Week'] = trend_filtered['Datum'].dt.to_period('W').dt.start_time
            weekly_trend = trend_filtered.groupby(['Week', 'Principe'])['Focus_Minuten'].sum().reset_index()
            
            # Line chart
            fig_trend = px.line(weekly_trend, x='Week', y='Focus_Minuten', color='Principe',
                              title="Focus Trend per Week (Minuten)",
                              labels={'Focus_Minuten': 'Focus Minuten', 'Week': 'Week'})
            fig_trend.update_layout(hovermode='x unified')
            st.plotly_chart(fig_trend, use_container_width=True)
            
            # Trend statistieken
            st.markdown("#### 📊 Trend Statistieken")
            
            for principe in selected_principes:
                principe_data = weekly_trend[weekly_trend['Principe'] == principe]
                if len(principe_data) >= 2:
                    eerste_waarde = principe_data['Focus_Minuten'].iloc[0]
                    laatste_waarde = principe_data['Focus_Minuten'].iloc[-1]
                    verandering = laatste_waarde - eerste_waarde
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric(f"{principe} - Eerste Week", f"{eerste_waarde} min")
                    with col2:
                        st.metric(f"{principe} - Laatste Week", f"{laatste_waarde} min")
                    with col3:
                        st.metric(f"{principe} - Verandering", f"{verandering:+.0f} min", delta=f"{verandering:+.0f} min")
        else:
            st.info("📊 Selecteer principes om trends te bekijken")
    else:
        st.info("📭 Nog geen trend data beschikbaar (laatste 90 dagen)")

# Safe database connection cleanup

# Database cleanup handled by Supabase helpers