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
from supabase import create_client
import os

st.title("🗄️ Database Beheer")

# Database setup with proper Supabase connection test
if SUPABASE_MODE:
    st.info("🌐 Using Supabase database")
    if not test_supabase_connection():
        st.error("❌ Cannot connect to Supabase")
        st.stop()
else:
    st.error("❌ Alleen Supabase mode wordt ondersteund")
    st.stop()

def get_supabase_client():
    """Get Supabase client"""
    try:
        supabase_url = st.secrets["supabase"]["url"]
        supabase_key = st.secrets["supabase"]["anon_key"]
    except:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
    
    if supabase_url and supabase_key:
        return create_client(supabase_url, supabase_key)
    else:
        st.error("❌ Supabase configuratie niet gevonden")
        return None

# Tab structuur voor verschillende database operaties
tab1, tab2, tab3, tab4 = st.tabs(["📊 Data Overzicht", "✏️ Data Bewerken", "🗑️ Data Verwijderen", "➕ Data Toevoegen"])

with tab1:
    st.subheader("📊 Database Tables Overzicht")
    
    # Selecteer table
    available_tables = [
        "trainings_calendar", "training_attendance", "gps_data", "rpe_data",
        "spelers_profiel", "matches", "thirty_fifteen_results"
    ]
    
    selected_table = st.selectbox("📋 Selecteer Table", available_tables)
    
    if st.button("📊 Toon Data", key="show_data"):
        try:
            df = safe_fetchdf(f"SELECT * FROM {selected_table} ORDER BY ROWID DESC LIMIT 100")
            
            if not df.empty:
                st.success(f"✅ {len(df)} records gevonden in {selected_table}")
                
                # Show column info
                st.markdown("**📋 Kolommen:**")
                col_info = []
                for col in df.columns:
                    dtype = str(df[col].dtype)
                    non_null = df[col].count()
                    col_info.append(f"• **{col}** ({dtype}) - {non_null} non-null values")
                
                st.markdown("<br>".join(col_info), unsafe_allow_html=True)
                
                # Show data
                st.markdown("**📊 Data Preview:**")
                st.dataframe(df, use_container_width=True)
                
                # Download option
                csv_data = df.to_csv(index=False)
                st.download_button(
                    label="💾 Download als CSV",
                    data=csv_data,
                    file_name=f"{selected_table}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            else:
                st.warning(f"📭 Geen data gevonden in {selected_table}")
                
        except Exception as e:
            st.error(f"❌ Fout bij ophalen data: {e}")

with tab2:
    st.subheader("✏️ Data Bewerken")
    
    # Selecteer table voor bewerken
    edit_table = st.selectbox("📋 Selecteer Table voor Bewerken", available_tables, key="edit_table")
    
    # Get data voor bewerken
    if st.button("🔍 Zoek Records", key="search_edit"):
        try:
            edit_df = safe_fetchdf(f"SELECT * FROM {edit_table} ORDER BY ROWID DESC LIMIT 50")
            st.session_state.edit_data = edit_df
            st.session_state.edit_table_name = edit_table
        except Exception as e:
            st.error(f"❌ Fout bij zoeken records: {e}")
    
    # Show editable data
    if 'edit_data' in st.session_state and not st.session_state.edit_data.empty:
        st.markdown(f"**📊 Bewerkbare data uit {st.session_state.edit_table_name}:**")
        
        # Select record to edit
        record_options = []
        for idx, row in st.session_state.edit_data.iterrows():
            if 'naam' in row:
                label = f"ID {idx}: {row['naam']}"
            elif 'speler' in row:
                label = f"ID {idx}: {row['speler']}"
            elif 'datum' in row:
                label = f"ID {idx}: {row['datum']}"
            else:
                label = f"Record {idx}"
            record_options.append((idx, label))
        
        selected_record_idx = st.selectbox(
            "📝 Selecteer Record om te Bewerken",
            options=[idx for idx, _ in record_options],
            format_func=lambda x: next(label for idx, label in record_options if idx == x)
        )
        
        if selected_record_idx is not None:
            selected_row = st.session_state.edit_data.iloc[selected_record_idx]
            
            st.markdown("**✏️ Bewerk Velden:**")
            
            with st.form("edit_record_form"):
                new_values = {}
                
                # Create input fields for each column
                for col in selected_row.index:
                    current_value = selected_row[col]
                    
                    if col.lower() in ['datum', 'geboortedatum', 'created_at']:
                        # Date fields
                        try:
                            if pd.notna(current_value) and current_value:
                                if isinstance(current_value, str):
                                    date_val = datetime.strptime(current_value, '%Y-%m-%d').date()
                                else:
                                    date_val = current_value
                            else:
                                date_val = date.today()
                            new_values[col] = st.date_input(f"📅 {col}", value=date_val, key=f"edit_{col}")
                        except:
                            new_values[col] = st.text_input(f"📅 {col}", value=str(current_value) if pd.notna(current_value) else "", key=f"edit_{col}")
                    
                    elif col.lower() in ['leeftijd', 'gewicht', 'lengte', 'rugnummer', 'training_id']:
                        # Numeric fields
                        try:
                            num_val = float(current_value) if pd.notna(current_value) and current_value else 0.0
                            new_values[col] = st.number_input(f"🔢 {col}", value=num_val, key=f"edit_{col}")
                        except:
                            new_values[col] = st.text_input(f"🔢 {col}", value=str(current_value) if pd.notna(current_value) else "", key=f"edit_{col}")
                    
                    else:
                        # Text fields
                        new_values[col] = st.text_input(f"📝 {col}", value=str(current_value) if pd.notna(current_value) else "", key=f"edit_{col}")
                
                col_save, col_cancel = st.columns(2)
                
                with col_save:
                    save_changes = st.form_submit_button("💾 Opslaan", type="primary")
                
                with col_cancel:
                    cancel_changes = st.form_submit_button("❌ Annuleren")
                
                if save_changes:
                    try:
                        client = get_supabase_client()
                        if client:
                            # Get primary key for update
                            primary_key_col = None
                            if 'speler_id' in selected_row.index:
                                primary_key_col = 'speler_id'
                            elif 'training_id' in selected_row.index:
                                primary_key_col = 'training_id'
                            elif 'id' in selected_row.index:
                                primary_key_col = 'id'
                            
                            if primary_key_col:
                                primary_key_value = selected_row[primary_key_col]
                                
                                # Convert date objects to strings for Supabase
                                update_data = {}
                                for key, value in new_values.items():
                                    if isinstance(value, date):
                                        update_data[key] = str(value)
                                    elif pd.isna(value):
                                        update_data[key] = None
                                    else:
                                        update_data[key] = value
                                
                                result = client.table(st.session_state.edit_table_name).update(update_data).eq(primary_key_col, primary_key_value).execute()
                                
                                if result.data:
                                    st.success("✅ Record succesvol bijgewerkt!")
                                    # Refresh data
                                    edit_df = safe_fetchdf(f"SELECT * FROM {st.session_state.edit_table_name} ORDER BY ROWID DESC LIMIT 50")
                                    st.session_state.edit_data = edit_df
                                    st.rerun()
                                else:
                                    st.error("❌ Geen data teruggekregen van update")
                            else:
                                st.error("❌ Geen primary key gevonden voor update")
                    except Exception as e:
                        st.error(f"❌ Fout bij opslaan: {e}")
                
                if cancel_changes:
                    st.info("❌ Wijzigingen geannuleerd")

with tab3:
    st.subheader("🗑️ Data Verwijderen")
    st.warning("⚠️ **LET OP**: Verwijderde data kan niet worden teruggehaald!")
    
    # Selecteer table voor verwijderen
    delete_table = st.selectbox("📋 Selecteer Table", available_tables, key="delete_table")
    
    # Get data voor verwijderen
    if st.button("🔍 Zoek Records om te Verwijderen", key="search_delete"):
        try:
            delete_df = safe_fetchdf(f"SELECT * FROM {delete_table} ORDER BY ROWID DESC LIMIT 50")
            st.session_state.delete_data = delete_df
            st.session_state.delete_table_name = delete_table
        except Exception as e:
            st.error(f"❌ Fout bij zoeken records: {e}")
    
    # Show deletable data
    if 'delete_data' in st.session_state and not st.session_state.delete_data.empty:
        st.markdown(f"**🗑️ Records uit {st.session_state.delete_table_name}:**")
        
        # Select record to delete
        delete_record_options = []
        for idx, row in st.session_state.delete_data.iterrows():
            if 'naam' in row:
                label = f"ID {idx}: {row['naam']}"
            elif 'speler' in row:
                label = f"ID {idx}: {row['speler']}"
            elif 'datum' in row:
                label = f"ID {idx}: {row['datum']}"
            else:
                label = f"Record {idx}"
            delete_record_options.append((idx, label))
        
        selected_delete_idx = st.selectbox(
            "🗑️ Selecteer Record om te Verwijderen",
            options=[idx for idx, _ in delete_record_options],
            format_func=lambda x: next(label for idx, label in delete_record_options if idx == x)
        )
        
        if selected_delete_idx is not None:
            selected_delete_row = st.session_state.delete_data.iloc[selected_delete_idx]
            
            st.markdown("**🗑️ Record om te verwijderen:**")
            st.json(selected_delete_row.to_dict())
            
            confirm_text = st.text_input("Type 'VERWIJDER' om te bevestigen:", key="confirm_delete_text")
            
            if st.button("🗑️ DEFINITIEF VERWIJDEREN", type="secondary", disabled=(confirm_text != "VERWIJDER")):
                try:
                    client = get_supabase_client()
                    if client:
                        # Get primary key for delete
                        primary_key_col = None
                        if 'speler_id' in selected_delete_row.index:
                            primary_key_col = 'speler_id'
                        elif 'training_id' in selected_delete_row.index:
                            primary_key_col = 'training_id'
                        elif 'id' in selected_delete_row.index:
                            primary_key_col = 'id'
                        
                        if primary_key_col:
                            primary_key_value = selected_delete_row[primary_key_col]
                            
                            result = client.table(st.session_state.delete_table_name).delete().eq(primary_key_col, primary_key_value).execute()
                            
                            st.success("✅ Record succesvol verwijderd!")
                            # Refresh data
                            delete_df = safe_fetchdf(f"SELECT * FROM {st.session_state.delete_table_name} ORDER BY ROWID DESC LIMIT 50")
                            st.session_state.delete_data = delete_df
                            st.rerun()
                        else:
                            st.error("❌ Geen primary key gevonden voor verwijdering")
                except Exception as e:
                    st.error(f"❌ Fout bij verwijderen: {e}")

with tab4:
    st.subheader("➕ Data Toevoegen")
    
    # Selecteer table voor toevoegen
    add_table = st.selectbox("📋 Selecteer Table", available_tables, key="add_table")
    
    # Get table structure
    if st.button("📋 Toon Table Structuur", key="show_structure"):
        try:
            structure_df = safe_fetchdf(f"SELECT * FROM {add_table} LIMIT 1")
            if not structure_df.empty:
                st.session_state.add_table_structure = structure_df.columns.tolist()
                st.session_state.add_table_name = add_table
                st.success(f"✅ Structuur geladen voor {add_table}")
            else:
                st.warning(f"⚠️ Geen data gevonden om structuur te bepalen voor {add_table}")
        except Exception as e:
            st.error(f"❌ Fout bij ophalen structuur: {e}")
    
    # Show add form
    if 'add_table_structure' in st.session_state:
        st.markdown(f"**➕ Nieuw record toevoegen aan {st.session_state.add_table_name}:**")
        
        with st.form("add_record_form"):
            add_values = {}
            
            for col in st.session_state.add_table_structure:
                if col.lower() in ['datum', 'geboortedatum', 'created_at']:
                    add_values[col] = st.date_input(f"📅 {col}", value=date.today(), key=f"add_{col}")
                elif col.lower() in ['leeftijd', 'gewicht', 'lengte', 'rugnummer', 'training_id']:
                    add_values[col] = st.number_input(f"🔢 {col}", value=0.0, key=f"add_{col}")
                else:
                    add_values[col] = st.text_input(f"📝 {col}", key=f"add_{col}")
            
            if st.form_submit_button("➕ Record Toevoegen", type="primary"):
                try:
                    client = get_supabase_client()
                    if client:
                        # Convert date objects to strings for Supabase
                        insert_data = {}
                        for key, value in add_values.items():
                            if isinstance(value, date):
                                insert_data[key] = str(value)
                            elif value == "":
                                insert_data[key] = None
                            else:
                                insert_data[key] = value
                        
                        result = client.table(st.session_state.add_table_name).insert(insert_data).execute()
                        
                        if result.data:
                            st.success("✅ Record succesvol toegevoegd!")
                            st.rerun()
                        else:
                            st.error("❌ Geen data teruggekregen van insert")
                except Exception as e:
                    st.error(f"❌ Fout bij toevoegen: {e}")

# Quick stats
st.markdown("---")
st.subheader("📈 Database Statistieken")

col1, col2, col3, col4 = st.columns(4)

with col1:
    try:
        trainings_count = safe_fetchdf("SELECT COUNT(*) as count FROM trainings_calendar")['count'].iloc[0]
        st.metric("🏃 Trainingen", trainings_count)
    except:
        st.metric("🏃 Trainingen", "Error")

with col2:
    try:
        spelers_count = safe_fetchdf("SELECT COUNT(*) as count FROM spelers_profiel")['count'].iloc[0]
        st.metric("👥 Spelers", spelers_count)
    except:
        st.metric("👥 Spelers", "Error")

with col3:
    try:
        gps_count = safe_fetchdf("SELECT COUNT(*) as count FROM gps_data")['count'].iloc[0]
        st.metric("📊 GPS Records", gps_count)
    except:
        st.metric("📊 GPS Records", "Error")

with col4:
    try:
        rpe_count = safe_fetchdf("SELECT COUNT(*) as count FROM rpe_data")['count'].iloc[0]
        st.metric("💪 RPE Records", rpe_count)
    except:
        st.metric("💪 RPE Records", "Error")