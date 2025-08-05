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
from datetime import datetime, timedelta
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

st.set_page_config(page_title="SPK Dashboard", layout="wide", initial_sidebar_state="expanded")

st.subheader("📅 Trainingskalender")

# Database setup is already handled at the top of the file
# The trainings_calendar table should already exist in Supabase
# If not, it will be created automatically when first record is inserted

# Sidebar voor maand/jaar selectie
current_date = datetime.now()
col_year, col_month = st.sidebar.columns(2)

with col_year:
    year = st.selectbox("Jaar", 
                       options=list(range(current_date.year - 1, current_date.year + 2)),
                       index=1,
                       key="year_select")

with col_month:
    month = st.selectbox("Maand",
                        options=list(range(1, 13)),
                        format_func=lambda x: calendar.month_name[x],
                        index=current_date.month - 1,
                        key="month_select")

# Snelle toevoeg sectie in sidebar
st.sidebar.markdown("### ➕ Snelle Toevoeg")
with st.sidebar.form("nieuwe_training"):
    training_datum = st.date_input("📅 Datum", value=datetime.today().date())
    training_type = st.selectbox("🏃 Type", ["Training", "Wedstrijd", "Vriendschappelijk", "Test"])
    training_omschrijving = st.text_input("📝 Omschrijving", placeholder="Korte beschrijving")
    
    submitted = st.form_submit_button("✅ Toevoegen")
    
    if submitted:
        if SUPABASE_MODE:
            # Use Supabase client for insert
            try:
                from supabase_config import get_supabase_client
                import random
                
                client = get_supabase_client()
                
                # Get the highest existing training_id and increment it
                try:
                    existing_trainings = safe_fetchdf("SELECT training_id FROM trainings_calendar ORDER BY training_id DESC LIMIT 1")
                    if not existing_trainings.empty and not pd.isna(existing_trainings.iloc[0]['training_id']):
                        next_id = int(existing_trainings.iloc[0]['training_id']) + 1
                    else:
                        next_id = 1
                except:
                    next_id = random.randint(1000, 9999)  # Fallback to random ID
                
                result = client.table("trainings_calendar").insert({
                    "training_id": next_id,
                    "datum": str(training_datum),
                    "type": training_type,
                    "omschrijving": training_omschrijving,
                    "created_at": datetime.now().isoformat()
                }).execute()
                
                if result.data:
                    st.success(f"✅ {training_type} toegevoegd!")
                    st.rerun()
                else:
                    st.error("❌ Kon training niet toevoegen")
            except Exception as e:
                st.error(f"❌ Database fout: {e}")
        else:
            # Legacy mode (fallback)
            execute_db_query("""
                INSERT INTO trainings_calendar (datum, type, omschrijving)
                VALUES (?, ?, ?)
            """, (training_datum, training_type, training_omschrijving))
            
            st.success(f"✅ {training_type} toegevoegd!")
            st.rerun()

# Haal trainingen op voor geselecteerde maand
first_day = datetime(year, month, 1).date()
if month == 12:
    last_day = datetime(year + 1, 1, 1).date() - timedelta(days=1)
else:
    last_day = datetime(year, month + 1, 1).date() - timedelta(days=1)

if SUPABASE_MODE:
    # Use Supabase query for getting trainings
    try:
        trainings_df = safe_fetchdf(f"""
            SELECT training_id, datum, type, omschrijving 
            FROM trainings_calendar 
            WHERE datum >= '{first_day}' AND datum <= '{last_day}'
            ORDER BY datum
        """)
        trainings = [tuple(row) for row in trainings_df.values] if not trainings_df.empty else []
    except Exception as e:
        st.error(f"Fout bij ophalen trainingen: {e}")
        trainings = []
else:
    # Legacy mode
    trainings = execute_db_query("""
        SELECT training_id, datum, type, omschrijving 
        FROM trainings_calendar 
        WHERE datum >= ? AND datum <= ?
        ORDER BY datum
    """, (first_day, last_day))

# Maak dictionary voor snelle lookup
trainings_dict = {}
for training in trainings:
    training_id, datum, type_tr, omschrijving = training
    
    # Skip trainings with invalid IDs (NaN or None)
    if pd.isna(training_id) or training_id is None:
        continue
        
    datum_obj = pd.to_datetime(datum).date()
    if datum_obj not in trainings_dict:
        trainings_dict[datum_obj] = []
    trainings_dict[datum_obj].append({
        'id': int(training_id),  # Ensure ID is integer
        'type': type_tr, 
        'omschrijving': omschrijving
    })

# Genereer kalender
cal = calendar.monthcalendar(year, month)
month_name = calendar.month_name[month]

st.markdown(f"### {month_name} {year}")

# Dagnames header
col_headers = st.columns(7)
day_names = ['Ma', 'Di', 'Wo', 'Do', 'Vr', 'Za', 'Zo']
for i, day_name in enumerate(day_names):
    col_headers[i].markdown(f"**{day_name}**")

# Kalender rijen
for week in cal:
    cols = st.columns(7)
    for i, day in enumerate(week):
        with cols[i]:
            if day == 0:
                st.markdown("<div style='height: 100px;'></div>", unsafe_allow_html=True)
            else:
                current_date_obj = datetime(year, month, day).date()
                today = datetime.today().date()
                
                # Dag nummer
                if current_date_obj == today:
                    st.markdown(f"**🟡 {day}**")
                elif current_date_obj < today:
                    st.markdown(f"<span style='color: gray'>{day}</span>", unsafe_allow_html=True)
                else:
                    st.markdown(f"**{day}**")
                
                # Trainingen voor deze dag
                if current_date_obj in trainings_dict:
                    for training in trainings_dict[current_date_obj]:
                        # Type emoji
                        emoji = "🏃" if training['type'] == "Training" else "⚽" if training['type'] == "Wedstrijd" else "🤝" if training['type'] == "Vriendschappelijk" else "📊"
                        
                        # Korte weergave
                        short_desc = training['omschrijving'][:15] + "..." if training['omschrijving'] and len(training['omschrijving']) > 15 else training['omschrijving'] or ""
                        
                        with st.container():
                            st.markdown(f"<div style='background-color: #f0f0f0; padding: 2px; margin: 1px; border-radius: 3px; font-size: 10px;'>{emoji} {training['type']}<br>{short_desc}</div>", 
                                      unsafe_allow_html=True)
                            
                            # Verwijder knop
                            if st.button("🗑️", key=f"del_{training['id']}", help="Verwijderen"):
                                # Validate training ID before deletion
                                if pd.isna(training['id']) or training['id'] is None:
                                    st.error("❌ Kan training niet verwijderen: ongeldige ID")
                                else:
                                    if SUPABASE_MODE:
                                        try:
                                            from supabase_config import get_supabase_client
                                            client = get_supabase_client()
                                            # Ensure ID is integer for Supabase
                                            training_id = int(training['id'])
                                            result = client.table("trainings_calendar").delete().eq("training_id", training_id).execute()
                                            if result.data:
                                                st.success("Training verwijderd!")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Fout bij verwijderen: {e}")
                                    else:
                                        execute_db_query("DELETE FROM trainings_calendar WHERE training_id = ?", (training['id'],))
                                        st.rerun()

# Legenda
st.markdown("---")
col_leg1, col_leg2, col_leg3, col_leg4 = st.columns(4)
with col_leg1:
    st.markdown("🏃 **Training**")
with col_leg2:
    st.markdown("⚽ **Wedstrijd**")
with col_leg3:
    st.markdown("🤝 **Vriendschappelijk**")
with col_leg4:
    st.markdown("📊 **Test**")

# Komende trainingen lijst
st.markdown("---")
st.markdown("### 📅 Komende Trainingen")

upcoming_trainings = execute_db_query("""
    SELECT training_id, datum, type, omschrijving 
    FROM trainings_calendar 
    WHERE datum >= ?
    ORDER BY datum
    LIMIT 5
""", (datetime.today().date(),))

if upcoming_trainings:
    for training in upcoming_trainings:
        training_id, datum, type_tr, omschrijving = training
        datum_obj = pd.to_datetime(datum).date()
        datum_str = datum_obj.strftime("%d/%m/%Y")
        
        # Type emoji
        emoji = "🏃" if type_tr == "Training" else "⚽" if type_tr == "Wedstrijd" else "🤝" if type_tr == "Vriendschappelijk" else "📊"
        
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"{emoji} **{type_tr}** - {datum_str}")
            if omschrijving:
                st.markdown(f"*{omschrijving}*")
        with col2:
            if st.button("🔗 Planning", key=f"plan_{training_id}", help="Gebruik voor Training Planning"):
                st.info("🔄 Ga naar 'Training Planning' voor verdere configuratie")
else:
    st.info("📭 Geen komende trainingen gepland")

# Safe database connection cleanup

# Database cleanup handled by Supabase helpers