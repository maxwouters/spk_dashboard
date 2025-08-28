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
    from database_helpers import check_table_exists, get_table_columns, add_column_if_not_exists, safe_fetchdf
    SUPABASE_MODE = False

# Database setup - Initialize connection status
DATABASE_AVAILABLE = False
con = None

if SUPABASE_MODE:
    st.info("🌐 Using Supabase database")
    try:
        if test_supabase_connection():
            DATABASE_AVAILABLE = True
            con = None  # Will use Supabase helpers
            st.success("✅ Supabase connection successful")
        else:
            st.warning("⚠️ Supabase connection failed - some features may not work")
    except Exception as e:
        st.warning(f"⚠️ Supabase connection error: {e} - some features may not work")
else:
    # Legacy mode
    try:
        from db_config import get_database_connection
        con = get_database_connection()
        DATABASE_AVAILABLE = True
        st.success("✅ Database connection successful")
    except (ImportError, NameError, Exception) as e:
        st.warning(f"⚠️ Database connection not available: {e}")
        st.info("💡 Tip: Check if your database is properly configured")
        DATABASE_AVAILABLE = False
        con = None
import pandas as pd
from sklearn.cluster import KMeans
import matplotlib.pyplot as plt
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
import matplotlib.patches as patches
from matplotlib.backends.backend_pdf import PdfPages
import io
import base64
from matplotlib.font_manager import FontProperties as fm

# Font configuratie
try:
    tstar_font = fm(fname='/Users/maximwouters/Downloads/t-star-pro-cufonfonts/TStarProHeavy.ttf')
    tstar_font_normal = fm(fname='/Users/maximwouters/Downloads/t-star-pro-cufonfonts/TStarProMedium.ttf')
    trim_font = fm(fname='/Users/maximwouters/Downloads/Trim-Bold/Trim-Bold.otf')
except:
    # Fallback als fonts niet gevonden worden
    tstar_font = None
    tstar_font_normal = None
    trim_font = None


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

st.set_page_config(page_title="Training Planning - SPK Dashboard", layout="wide")

def create_training_overview(zones, loopvorm_type, base_column, percentage, intervalduur, rustduur, aantal_herhalingen, title="Training Overzicht", oefening_naam="", maand="", shuttle_afstand=20, zijde_lengte=25, aanwezige_spelers=None):
    """Creëer een visueel trainingsoverzicht voor download"""
    
    # Figuur maken - nu 1 rij met 2 kolommen, aangepaste verhoudingen
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 10), gridspec_kw={'width_ratios': [3, 1]})
    
    # Titel met oefening naam
    main_title = f'{title}'
    if oefening_naam:
        main_title += f'\nOefening: {oefening_naam}'
    
    if trim_font:
        fig.suptitle(main_title, fontsize=20, fontweight='bold', y=0.95, font_properties=trim_font)
    else:
        fig.suptitle(main_title, fontsize=20, fontweight='bold', y=0.95)
    
    # Kleurenpalette - zwart/grijs voor groepen, blauw voor parameters
    groep_colors = ['#000000', '#000000', '#000000']  # Zwart, Donkergrijs, Grijs
    param_colors = ['#1E3A8A', '#3B82F6']  # Blauw voor parameters
    groep_names = ['Groep A', 'Groep B', 'Groep C']
    
    # 1. Groepsindeling (links) - 3 groepen naast elkaar
    box_width = 0.28  # Breedte van elke groepbox
    box_spacing = 0.05  # Ruimte tussen groepen
    box_height = 0.75  # Hoogte van elke groepbox
    
    for i in range(3):
        groep_data = zones[zones["Groep"] == i]
        if len(groep_data) > 0:
            x_pos = 0.05 + i * (box_width + box_spacing)
            y_pos = 0.8
            
            # Groep box achtergrond
            box = plt.Rectangle((x_pos, y_pos - box_height), box_width, box_height, 
                              facecolor=groep_colors[i], alpha=0.15, edgecolor=groep_colors[i], linewidth=2)
            ax1.add_patch(box)
            
            avg_basis = groep_data[base_column].mean()
            avg_snelheid = groep_data["Doelsnelheid_km_u"].mean()
            avg_afstand = groep_data["Afstand_per_interval_m"].mean()
            
            # Groep header met grote tekst (gecentreerd)
            ax1.text(x_pos + box_width/2, y_pos - 0.05, f'{groep_names[i]}', 
                    fontsize=16, fontweight='bold', color=groep_colors[i], 
                    transform=ax1.transAxes, ha='center')
            
            # Metrics
            if base_column == "MAS":
                metric_name = "MAS"
                metric_unit = "km/u"
            elif base_column == "TrueVIFT":
                metric_name = "VIFT"
                metric_unit = "km/u"
            else:
                metric_name = "VO2Max"
                metric_unit = "ml/kg/min"
            
            font_props = tstar_font if tstar_font else None
            font_props_normal = tstar_font_normal if tstar_font_normal else None
            
            ax1.text(x_pos + 0.01, y_pos - 0.12, f'{metric_name}: {avg_basis:.1f} {metric_unit}', 
                    fontsize=15, fontweight='bold', color=groep_colors[i], transform=ax1.transAxes, 
                    font_properties=font_props)
            ax1.text(x_pos + 0.01, y_pos - 0.18, f'Snelheid: {avg_snelheid:.1f} km/u', 
                    fontsize=15, fontweight='bold', color=groep_colors[i], transform=ax1.transAxes, 
                    font_properties=font_props)
            ax1.text(x_pos + 0.01, y_pos - 0.24, f'Afstand: {avg_afstand:.0f} m', 
                    fontsize=15, fontweight='bold', color=groep_colors[i], transform=ax1.transAxes, 
                    font_properties=font_props)
            
            # Spelers onder elkaar - filter voor aanwezige spelers
            spelers_list = list(groep_data["Speler"].values)
            if aanwezige_spelers is not None:
                spelers_list = [speler for speler in spelers_list if speler in aanwezige_spelers]
            
            ax1.text(x_pos + 0.01, y_pos - 0.32, "Spelers:", 
                    fontsize=15, color=groep_colors[i], transform=ax1.transAxes, 
                    font_properties=font_props_normal)
            
            # Plaats elke speler op een nieuwe regel
            for j, speler in enumerate(spelers_list):
                ax1.text(x_pos + 0.02, y_pos - 0.36 - (j * 0.04), f"• {speler}", 
                        fontsize=15, color=groep_colors[i], fontweight='bold', transform=ax1.transAxes, 
                        font_properties=font_props_normal)
    
    ax1.set_xlim(0, 1)
    ax1.set_ylim(0, 1)
    ax1.axis('off')
    
    # 2. Training parameters (rechts)
    params = [
        ('Basis metric', base_column.replace("TrueVIFT", "VIFT").replace("VO2MAX", "VO2Max")),
        ('Intensiteit', f'{percentage}%'),
        ('Interval duur', f'{intervalduur}s'),
        ('Rust duur', f'{rustduur}s'),
        ('Aantal herhalingen', f'{aantal_herhalingen}'),
        ('Loopvorm', loopvorm_type),
        ('Totale training tijd', f'{((intervalduur + rustduur) * aantal_herhalingen - rustduur) / 60:.1f} min')
    ]
    
    y_start = 0.85
    box_height = 0.08
    box_spacing = 0.03
    
    for i, (label, value) in enumerate(params):
        y_pos = y_start - i * (box_height + box_spacing)
        
        # Parameter box
        box = plt.Rectangle((0.05, y_pos - box_height), 0.9, box_height, 
                          facecolor='#F3F4F6', edgecolor=param_colors[0], linewidth=1, alpha=0.8)
        ax2.add_patch(box)
        
        # Label en waarde
        ax2.text(0.1, y_pos - box_height/2, f'{label}:', 
                fontsize=15, fontweight='bold', color=param_colors[0], 
                transform=ax2.transAxes, va='center', font_properties=tstar_font)
        ax2.text(0.85, y_pos - box_height/2, value, 
                fontsize=15, fontweight='bold', color=param_colors[1], 
                transform=ax2.transAxes, va='center', ha='right', font_properties=tstar_font_normal)
    
    ax2.set_xlim(0, 1)
    ax2.set_ylim(0, 1)
    ax2.axis('off')
    
    plt.tight_layout()
    return fig

# Main page content
st.title("🎯 Training Planning")

# --- Upload CSV-bestand ---
if DATABASE_AVAILABLE:
    uploaded_file = st.file_uploader("Upload je 30-15 testresultaten (CSV)", type="csv")
else:
    st.info("📤 CSV upload niet beschikbaar zonder database connectie")
    uploaded_file = None

if uploaded_file:
    try:
        # Data inlezen
        df = pd.read_csv(uploaded_file, delimiter=';')
        st.info(f"📊 Bestand ingelezen: {len(df)} rijen gevonden")
        
        # Debug: toon ruwe data
        st.subheader("🔍 Ruwe CSV data (eerste 5 rijen)")
        st.dataframe(df.head())
        st.info(f"Kolommen gevonden: {list(df.columns)}")
        st.info(f"Data types: {df.dtypes.to_dict()}")
        
        # Check welke rijen NaN waarden hebben
        nan_info = df.isnull().sum()
        st.info(f"NaN waarden per kolom: {nan_info.to_dict()}")
        
        # Minder agressieve cleaning - alleen rijen waar ALLE waarden NaN zijn
        df_before_clean = len(df)
        df = df.dropna(how='all')  # Alleen rijen verwijderen waar ALLES leeg is
        st.info(f"📊 Na verwijderen volledig lege rijen: {len(df)} rijen (was {df_before_clean})")

        # Toon preview van de data
        st.subheader("📋 Preview van geüploade data")
        st.dataframe(df.head())

        # Kolommen hernoemen voor nieuwe structuur
        expected_columns = ["Speler", "Geboortedatum", "Leeftijd", "Gewicht", "FinishingTime", "RunningTime_s", "PeakVelocity", "TrueVIFT", "VO2MAX"]
        
        if len(df.columns) != len(expected_columns):
            st.error(f"❌ Verwacht {len(expected_columns)} kolommen, maar {len(df.columns)} gevonden. Controleer je CSV-formaat.")
            st.info("Verwachte kolommen: " + ", ".join(expected_columns))
            st.stop()
            
        df.columns = expected_columns
        
        # Debug: geboortedatum conversie
        st.info(f"🗓️ Geboortedatum originele waarden (eerste 3): {df['Geboortedatum'].head(3).tolist()}")
        try:
            df["Geboortedatum"] = pd.to_datetime(df["Geboortedatum"], dayfirst=True, errors="coerce").dt.date
            st.info("✅ Geboortedatum succesvol geconverteerd")
        except Exception as e:
            st.error(f"❌ Fout bij converteren geboortedatum: {str(e)}")
            # Fallback: probeer verschillende formaten
            st.info("🔄 Probeer alternatieve datum formaten...")
            try:
                df["Geboortedatum"] = pd.to_datetime(df["Geboortedatum"], format="%d/%m/%Y", errors="coerce").dt.date
                st.info("✅ Geboortedatum geconverteerd met DD/MM/YYYY formaat")
            except:
                df["Geboortedatum"] = pd.to_datetime(df["Geboortedatum"], errors="coerce").dt.date
                st.warning("⚠️ Geboortedatum geconverteerd met automatische detectie")

        # Comma to dot conversie voor getallen - alleen voor bestaande kolommen
        numeric_cols = ["Gewicht", "PeakVelocity", "TrueVIFT", "VO2MAX"]
        for col in numeric_cols:
            if col in df.columns:
                st.info(f"🔢 Converting {col} to numeric...")
                try:
                    # Debug: toon originele waarden
                    st.info(f"Originele {col} waarden (eerste 3): {df[col].head(3).tolist()}")
                    df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", "."), errors="coerce")
                    st.info(f"✅ {col} succesvol geconverteerd")
                except Exception as e:
                    st.error(f"❌ Fout bij converteren {col}: {str(e)}")
            else:
                st.warning(f"⚠️ Kolom {col} niet gevonden in data")

        # MAS berekenen (MAS = TrueVIFT × 0.95)
        df["MAS"] = df["TrueVIFT"] * 0.95

        # Maand selecteren of automatisch toevoegen
        default_month = datetime.today().strftime("%Y-%m")
        maand = st.text_input("Testmaand (bv. 2025-07)", value=default_month)
        df["Maand"] = maand

        # Toon finale data preview
        st.subheader("🔍 Finale data (incl. MAS en maand)")
        st.dataframe(df)

        # Upload knop toevoegen
        if st.button("📤 Toevoegen aan database", type="primary"):
            # Check database availability first
            if not DATABASE_AVAILABLE:
                st.error("❌ Database niet beschikbaar voor upload")
                st.stop()
            # Tabel aanmaken met nieuwe structuur (inclusief MAS kolom)
            execute_db_query("""
                CREATE TABLE IF NOT EXISTS thirty_fifteen_results (
                    Speler TEXT,
                    Geboortedatum DATE,
                    Leeftijd INTEGER,
                    Gewicht DOUBLE,
                    FinishingTime TEXT,
                    RunningTime_s INTEGER,
                    PeakVelocity DOUBLE,
                    TrueVIFT DOUBLE,
                    VO2MAX DOUBLE,
                    MAS DOUBLE,
                    Maand TEXT
                )
            """)

            # Check voor duplicaten - controleer of maand al bestaat (onafhankelijk van speler)
            if SUPABASE_MODE:
                try:
                    # Check op maand alleen - niet op specifieke speler
                    existing_df = safe_fetchdf(f"""
                        SELECT Speler FROM thirty_fifteen_results 
                        WHERE Maand = '{maand}'
                    """)
                    existing_records = len(existing_df)
                except:
                    existing_records = 0
            else:
                existing_records = (lambda result: result[0] if result else None)(execute_db_query("""
                    SELECT COUNT(*) FROM thirty_fifteen_results 
                    WHERE Maand = ?
                """, (maand,)))[0]
            
            if existing_records > 0:
                if st.checkbox(f"⚠️ Er zijn al records voor maand {maand}. Overschrijven?"):
                    if SUPABASE_MODE:
                        try:
                            from supabase_config import get_supabase_client
                            client = get_supabase_client()
                            result = client.table("thirty_fifteen_results").delete().eq("Maand", maand).execute()
                            st.warning(f"🗑️ Bestaande records voor {maand} verwijderd")
                        except Exception as e:
                            st.error(f"Fout bij verwijderen: {e}")
                    else:
                        execute_db_query("DELETE FROM thirty_fifteen_results WHERE Maand = ?", (maand,))
                        st.warning(f"🗑️ Bestaande records voor {maand} verwijderd")
                else:
                    st.error("❌ Upload geannuleerd om duplicaten te voorkomen")
                    st.stop()

            # Data toevoegen - explicit kolom mapping
            st.info("📝 Toevoegen aan database...")
            st.info(f"DataFrame kolommen: {list(df.columns)}")
            st.info(f"DataFrame data types: {df.dtypes.to_dict()}")
            
            # Explicit INSERT met kolom namen om type mismatches te voorkomen
            for index, row in df.iterrows():
                try:
                    execute_db_query("""
                        INSERT INTO thirty_fifteen_results 
                        (Speler, Geboortedatum, Leeftijd, Gewicht, FinishingTime, RunningTime_s, PeakVelocity, TrueVIFT, VO2MAX, MAS, Maand)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        str(row['Speler']),
                        row['Geboortedatum'],  
                        int(row['Leeftijd']) if pd.notna(row['Leeftijd']) else None,
                        float(row['Gewicht']) if pd.notna(row['Gewicht']) else None,
                        str(row['FinishingTime']),
                        int(row['RunningTime_s']) if pd.notna(row['RunningTime_s']) else None,
                        float(row['PeakVelocity']) if pd.notna(row['PeakVelocity']) else None,
                        float(row['TrueVIFT']) if pd.notna(row['TrueVIFT']) else None,
                        float(row['VO2MAX']) if pd.notna(row['VO2MAX']) else None,
                        float(row['MAS']) if pd.notna(row['MAS']) else None,
                        str(row['Maand'])
                    ))
                except Exception as e:
                    st.error(f"❌ Fout bij toevoegen rij {index + 1} (speler: {row['Speler']}): {str(e)}")
                    st.info(f"Rij data: {row.to_dict()}")
                    raise e
            
            # Verificatie
            if SUPABASE_MODE:
                try:
                    # Use a different approach for counting - get all records and count in Python
                    verification_df = safe_fetchdf(f"SELECT Speler FROM thirty_fifteen_results WHERE Maand = '{maand}'")
                    verification = len(verification_df)
                except:
                    verification = len(df)  # Fallback to DataFrame length
            else:
                verification = (lambda result: result[0] if result else None)(execute_db_query("SELECT COUNT(*) FROM thirty_fifteen_results WHERE Maand = ?", (maand,)))[0]
            
            st.success(f"✅ {verification} records succesvol toegevoegd aan database voor maand {maand}")
            
            # Force refresh
            st.rerun()
            
    except Exception as e:
        st.error(f"❌ Fout bij uploaden: {str(e)}")
        st.info("💡 Controleer of je CSV-bestand het juiste formaat heeft (semicolon gescheiden)")
        import traceback
        st.code(traceback.format_exc())

# --- Selectie van maand ---
# Database migratie is handled automatically in Supabase
# MAS column should already exist in the Supabase table

# Check of tabel bestaat (only if database is available)
if DATABASE_AVAILABLE:
    try:
        table_exists = check_table_exists("thirty_fifteen_results")
    except Exception as e:
        st.warning(f"⚠️ Kan tabel status niet controleren: {e}")
        table_exists = False
else:
    st.error("❌ Database niet beschikbaar - kan geen testresultaten laden")
    table_exists = False

if not table_exists:
    if DATABASE_AVAILABLE:
        st.warning("📭 Er zijn nog geen testresultaten toegevoegd. Upload eerst een CSV-bestand.")
    else:
        st.error("❌ Database connectie vereist om testresultaten te laden")
else:
    if SUPABASE_MODE:
        # Use Supabase-compatible queries
        try:
            maanden_df = safe_fetchdf("SELECT Maand FROM thirty_fifteen_results ORDER BY Maand DESC")
            if not maanden_df.empty:
                unique_maanden = sorted(maanden_df['Maand'].unique(), reverse=True)
                maand_selectie = st.selectbox("📅 Kies testmaand", unique_maanden)
                
                # Get data for selected month
                df = safe_fetchdf(f"SELECT * FROM thirty_fifteen_results WHERE Maand = '{maand_selectie}'")
            else:
                st.warning("Geen testresultaten gevonden in database.")
                df = pd.DataFrame()
        except Exception as e:
            st.error(f"Fout bij ophalen data: {e}")
            df = pd.DataFrame()
    else:
        # Legacy mode
        maanden = execute_db_query("SELECT DISTINCT Maand FROM thirty_fifteen_results ORDER BY Maand DESC")
        maand_selectie = st.selectbox("📅 Kies testmaand", [m[0] for m in maanden])
        df = safe_fetchdf("SELECT * FROM thirty_fifteen_results WHERE Maand = ?", (maand_selectie,))
    
    # Ensure numeric columns are properly typed for calculations
    if not df.empty:
        numeric_columns = ['MAS', 'TrueVIFT', 'VO2MAX']
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Check of MAS kolom bestaat, zo niet, bereken deze
    if 'MAS' not in df.columns:
        df['MAS'] = df['TrueVIFT'] * 0.95
    elif not df.empty:
        # Ensure MAS is numeric even if it exists
        df['MAS'] = pd.to_numeric(df['MAS'], errors='coerce')
    
    # Metric selectie voor trainingsbelasting berekening
    metric_keuze = st.radio("📊 Selecteer basis voor trainingsbelasting", ["MAS (Aanbevolen)", "TrueVIFT", "VO2Max"], horizontal=True)
    
    if metric_keuze == "MAS (Aanbevolen)":
        base_column = "MAS"
        base_description = "MAS (Maximum Aerobic Speed)"
    elif metric_keuze == "TrueVIFT":
        base_column = "TrueVIFT"
        base_description = "TrueVIFT"
    else:
        base_column = "VO2MAX"
        base_description = "VO2Max"
    
    st.subheader(f"📋 {base_description} per speler")
    
    # Toon relevante kolommen
    display_cols = ["Speler", "Leeftijd", "MAS", "TrueVIFT", "VO2MAX"]
    # Filter alleen kolommen die bestaan
    available_cols = [col for col in display_cols if col in df.columns]
    
    # Highlight de geselecteerde kolom
    styled_df = df[available_cols].style.apply(
        lambda x: ['background-color: #E8F4FD' if col == base_column else '' for col in x.index], 
        axis=1
    )
    st.dataframe(styled_df, use_container_width=True)
    
    # Info over MAS
    st.info("💡 **MAS (Maximum Aerobic Speed)** = TrueVIFT × 0.95 - Dit is de aanbevolen waarde voor trainingsbelasting berekeningen.")

    # --- Trainingszone dashboard ---
    st.subheader("⚙️ Intermitterende Loopvormen Dashboard")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 📊 Trainingsintensiteit")
        if base_column == "TrueVIFT":
            percentage = st.slider("Percentage van MAS", min_value=70, max_value=120, value=100, step=5)
        else:
            percentage = st.slider("Percentage van VO2Max", min_value=70, max_value=120, value=100, step=5)
        
        st.markdown("### ⏱️ Interval configuratie")
        intervalduur = st.number_input("Interval duur (seconden)", min_value=1, max_value=300, value=15, step=5)
        rustduur = st.number_input("Rust duur (seconden)", min_value=5, max_value=300, value=15, step=5)
        aantal_herhalingen = st.number_input("Aantal herhalingen", min_value=1, max_value=50, value=8)

    with col2:
        st.markdown("### 🎯 Loopvorm type")
        loopvorm_type = st.selectbox(
            "Selecteer loopvorm",
            ["Shuttle runs", "Rechte lijn", "Vierkant parcours", "Driehoek parcours"]
        )
        
        if loopvorm_type == "Shuttle runs":
            shuttle_afstand = st.number_input("Shuttle afstand (meter)", min_value=5, max_value=50, value=20)
        elif loopvorm_type == "Vierkant parcours":
            zijde_lengte = st.number_input("Zijde lengte (meter)", min_value=10, max_value=100, value=25)
        elif loopvorm_type == "Driehoek parcours":
            zijde_lengte = st.number_input("Zijde lengte (meter)", min_value=10, max_value=100, value=30)

    # Berekeningen op basis van geselecteerde metric
    zone_df = df.copy()
    if base_column == "MAS":
        # Gebruik MAS (VIFT × 0.95) direct
        zone_df["Doelsnelheid_km_u"] = zone_df["MAS"] * (percentage / 100)
    elif base_column == "TrueVIFT":
        # Direct gebruik van TrueVIFT (originele VIFT)
        zone_df["Doelsnelheid_km_u"] = zone_df["TrueVIFT"] * (percentage / 100)
    else:
        # Voor VO2Max: omrekening naar snelheid
        # VO2Max (ml/kg/min) naar geschatte MAS via formule: MAS ≈ VO2Max * 0.21 / 3.5
        zone_df["Geschatte_MAS"] = zone_df["VO2MAX"] * 0.21 / 3.5
        zone_df["Doelsnelheid_km_u"] = zone_df["Geschatte_MAS"] * (percentage / 100)
    
    zone_df["Doelsnelheid_m_s"] = zone_df["Doelsnelheid_km_u"] / 3.6
    zone_df["Afstand_per_interval_m"] = zone_df["Doelsnelheid_m_s"] * intervalduur

    # Specifieke berekeningen per loopvorm
    if loopvorm_type == "Shuttle runs":
        zone_df["Aantal_shuttles"] = zone_df["Afstand_per_interval_m"] / (shuttle_afstand * 2)
        zone_df["Aantal_shuttles"] = zone_df["Aantal_shuttles"].round(1)
    elif loopvorm_type == "Vierkant parcours":
        vierkant_omtrek = zijde_lengte * 4
        zone_df["Aantal_rondjes"] = zone_df["Afstand_per_interval_m"] / vierkant_omtrek
        zone_df["Aantal_rondjes"] = zone_df["Aantal_rondjes"].round(1)
    elif loopvorm_type == "Driehoek parcours":
        driehoek_omtrek = zijde_lengte * 3
        zone_df["Aantal_rondjes"] = zone_df["Afstand_per_interval_m"] / driehoek_omtrek
        zone_df["Aantal_rondjes"] = zone_df["Aantal_rondjes"].round(1)

    # Totale training tijd
    zone_df["Totale_werk_tijd"] = aantal_herhalingen * intervalduur
    zone_df["Totale_rust_tijd"] = (aantal_herhalingen - 1) * rustduur
    zone_df["Totale_training_tijd"] = zone_df["Totale_werk_tijd"] + zone_df["Totale_rust_tijd"]
    zone_df["Totale_afstand_m"] = zone_df["Afstand_per_interval_m"] * aantal_herhalingen

    st.subheader("🏃 Trainingsoverzicht per speler")

    # Kolommen voor weergave bepalen
    display_cols = ["Speler", "Doelsnelheid_km_u", "Afstand_per_interval_m"]

    if loopvorm_type == "Shuttle runs":
        display_cols.append("Aantal_shuttles")
    elif loopvorm_type in ["Vierkant parcours", "Driehoek parcours"]:
        display_cols.append("Aantal_rondjes")

    display_cols.extend(["Totale_afstand_m", "Totale_training_tijd"])

    # Kolom namen voor betere weergave
    col_names = {
        "Speler": "Speler",
        "Doelsnelheid_km_u": "Snelheid (km/u)",
        "Afstand_per_interval_m": "Afstand/interval (m)",
        "Aantal_shuttles": f"Shuttles ({shuttle_afstand}m heen+terug)" if loopvorm_type == "Shuttle runs" else "",
        "Aantal_rondjes": "Rondjes",
        "Totale_afstand_m": "Totale afstand (m)",
        "Totale_training_tijd": "Totale tijd (sec)"
    }

    # Data weergeven
    result_df = zone_df[display_cols].round(1)
    result_df.columns = [col_names.get(col, col) for col in display_cols]
    st.dataframe(result_df, use_container_width=True)

    # --- Groepsindeling op basis van geselecteerde metric ---
    st.subheader(f"👥 Groepsindeling voor training (basis: {metric_keuze})")

    # Clustering op basis van de geselecteerde basis metric en afstand
    kmeans = KMeans(n_clusters=3, random_state=42, n_init='auto')
    zones = zone_df.dropna(subset=[base_column, "Afstand_per_interval_m"]).copy()
    
    # Gebruik de oorspronkelijke basis metric voor clustering (niet de doelsnelheid)
    zones["Groep"] = kmeans.fit_predict(zones[[base_column, "Afstand_per_interval_m"]])

    # Groepen sorteren op gemiddelde van de basis metric (laagste = A, hoogste = C)
    groep_gemiddelden = zones.groupby("Groep")[base_column].mean().sort_values()
    groep_mapping = {old_groep: new_groep for new_groep, (old_groep, _) in enumerate(groep_gemiddelden.items())}
    zones["Groep"] = zones["Groep"].map(groep_mapping)

    # Groep labels toevoegen
    groep_labels = {i: f"Groep {chr(65+i)}" for i in range(3)}
    zones["Groep_Label"] = zones["Groep"].map(groep_labels)

    # Compacte groepsweergave
    col1, col2, col3 = st.columns(3)

    for i, col in enumerate([col1, col2, col3]):
        groep_data = zones[zones["Groep"] == i]
        groep_naam = f"Groep {chr(65+i)}"
        
        with col:
            st.markdown(f"### {groep_naam}")
            
            # Toon basis metric gemiddelde
            avg_basis_metric = groep_data[base_column].mean()
            if base_column == "MAS":
                st.metric("Gemiddelde MAS", f"{avg_basis_metric:.1f} km/u")
            elif base_column == "TrueVIFT":
                st.metric("Gemiddelde VIFT", f"{avg_basis_metric:.1f} km/u")
            else:
                st.metric("Gemiddelde VO2Max", f"{avg_basis_metric:.1f} ml/kg/min")
            
            # Toon trainingssnelheid en afstand
            avg_snelheid = groep_data["Doelsnelheid_km_u"].mean()
            avg_afstand = groep_data["Afstand_per_interval_m"].mean()
            
            st.metric("Trainingssnelheid", f"{avg_snelheid:.1f} km/u")
            st.metric("Afstand/interval", f"{avg_afstand:.0f} m")
            
            if loopvorm_type == "Shuttle runs":
                avg_shuttles = groep_data["Aantal_shuttles"].mean()
                st.metric("Shuttles", f"{avg_shuttles:.1f}")
            elif loopvorm_type in ["Vierkant parcours", "Driehoek parcours"]:
                avg_rondjes = groep_data["Aantal_rondjes"].mean()
                st.metric("Rondjes", f"{avg_rondjes:.1f}")
            
            st.markdown("**Spelers:**")
            for speler in groep_data["Speler"].values:
                st.write(f"• {speler}")

    # --- Training Selectie voor Aanwezigheid ---
    st.subheader("📅 Training Selectie")
    
    # Haal geplande trainingen op voor selectie in deze sectie
    if SUPABASE_MODE:
        try:
            trainingen_df = safe_fetchdf("SELECT training_id, datum, type, omschrijving FROM trainings_calendar ORDER BY datum DESC")
            geplande_trainingen_hier = [tuple(row) for row in trainingen_df.values] if not trainingen_df.empty else []
        except Exception as e:
            st.warning(f"⚠️ Kon trainingen niet laden: {e}")
            geplande_trainingen_hier = []
    else:
        # Legacy fallback
        geplande_trainingen_hier = execute_db_query("""
            SELECT training_id, datum, type, omschrijving 
            FROM trainings_calendar 
            ORDER BY datum DESC
        """)
    
    if geplande_trainingen_hier:
        # Maak opties voor selectbox
        training_opties_hier = ["Handmatig aanwezigheid instellen"] + [
            f"{training[2]} - {pd.to_datetime(training[1]).strftime('%A %d.%m')} ({training[3] if training[3] else 'Geen omschrijving'})"
            for training in geplande_trainingen_hier
        ]
        
        selected_training_hier = st.selectbox(
            "🏃 Kies training voor aanwezigheid:",
            training_opties_hier,
            help="Selecteer een geplande training om aanwezigheid automatisch te laden, of kies handmatig instellen"
        )
        
        # Als een training is geselecteerd
        if selected_training_hier != "Handmatig aanwezigheid instellen":
            selected_index_hier = training_opties_hier.index(selected_training_hier) - 1
            selected_training_data_hier = geplande_trainingen_hier[selected_index_hier]
            selected_training_id_hier = selected_training_data_hier[0]
            selected_datum_hier = selected_training_data_hier[1]
            selected_type_hier = selected_training_data_hier[2]
            
            # Haal aanwezigheid op voor deze training
            if SUPABASE_MODE:
                try:
                    aanwezigheid_df = safe_fetchdf(f"SELECT speler, status FROM training_attendance WHERE training_id = '{selected_training_id_hier}'")
                    aanwezigheid_data_hier = [tuple(row) for row in aanwezigheid_df.values] if not aanwezigheid_df.empty else []
                except Exception as e:
                    st.warning(f"⚠️ Kon aanwezigheid niet laden: {e}")
                    aanwezigheid_data_hier = []
            else:
                # Legacy fallback
                aanwezigheid_data_hier = execute_db_query("""
                    SELECT speler, status 
                    FROM training_attendance 
                    WHERE training_id = ?
                """, (selected_training_id_hier,))
            
            if aanwezigheid_data_hier:
                # Update session state met aanwezigheid
                for speler, status in aanwezigheid_data_hier:
                    st.session_state[f"aanwezig_{speler}"] = (status == "Aanwezig")
                
                # Stel automatische titel in
                datum_str_hier = pd.to_datetime(selected_datum_hier).strftime('%A %d.%m')
                auto_title_hier = f"{selected_type_hier} {datum_str_hier}"
                st.session_state["auto_training_title"] = auto_title_hier
                
                # Toon aanwezigheid
                alle_spelers = zones["Speler"].unique().tolist()
                aanwezige_spelers = []
                afwezige_spelers = []
                
                for speler in alle_spelers:
                    if st.session_state.get(f"aanwezig_{speler}", False):
                        aanwezige_spelers.append(speler)
                    else:
                        afwezige_spelers.append(speler)
                
                st.success(f"✅ Training geladen: {selected_training_hier}")
                st.info(f"📝 Automatische titel: '{auto_title_hier}'")
                
                # Toon samenvatting
                if aanwezige_spelers:
                    st.success(f"✅ **Aanwezig ({len(aanwezige_spelers)}):** {', '.join(aanwezige_spelers)}")
                
                if afwezige_spelers:
                    st.error(f"❌ **Afwezig ({len(afwezige_spelers)}):** {', '.join(afwezige_spelers)}")
                
                st.info(f"📊 Totaal: {len(aanwezige_spelers)}/{len(alle_spelers)} spelers")
                st.markdown("💡 *Om aanwezigheid te wijzigen, ga naar het Trainingskalender tabblad*")
                
            else:
                st.warning("⚠️ Nog geen aanwezigheid ingesteld voor deze training.")
                st.markdown("Ga naar het Trainingskalender tabblad om aanwezigheid in te stellen.")
        
        else:
            # Handmatige aanwezigheidslijst
            st.markdown("**Handmatig aanwezigheid instellen:**")
            
            # Reset automatische titel
            if "auto_training_title" in st.session_state:
                del st.session_state["auto_training_title"]
            
            # Krijg alle spelers uit de zones
            alle_spelers = zones["Speler"].unique().tolist()
            
            # Selecteer alle / Deselecteer alle knoppen
            col_btn1, col_btn2, col_spacer = st.columns([1, 1, 3])
            with col_btn1:
                if st.button("✅ Selecteer alle", help="Markeer alle spelers als aanwezig"):
                    for speler in alle_spelers:
                        st.session_state[f"aanwezig_{speler}"] = True
                    st.rerun()
            with col_btn2:
                if st.button("❌ Deselecteer alle", help="Markeer alle spelers als afwezig"):
                    for speler in alle_spelers:
                        st.session_state[f"aanwezig_{speler}"] = False
                    st.rerun()
            
            # Maak kolommen voor checkboxes (3 kolommen voor overzicht)
            cols = st.columns(3)
            aanwezige_spelers = []
            
            for i, speler in enumerate(alle_spelers):
                col_idx = i % 3
                with cols[col_idx]:
                    is_aanwezig = st.session_state.get(f"aanwezig_{speler}", True)
                    if st.checkbox(speler, key=f"aanwezig_{speler}", value=is_aanwezig):
                        aanwezige_spelers.append(speler)
            
            # Toon samenvatting
            if len(aanwezige_spelers) < len(alle_spelers):
                afwezige_spelers = [s for s in alle_spelers if s not in aanwezige_spelers]
                st.info(f"📊 Aanwezig: {len(aanwezige_spelers)}/{len(alle_spelers)} spelers")
                if afwezige_spelers:
                    st.warning(f"🚫 Afwezig: {', '.join(afwezige_spelers)}")
            else:
                st.success(f"✅ Alle {len(alle_spelers)} spelers zijn aanwezig")
    
    else:
        # Geen geplande trainingen - toon handmatige optie
        st.info("📭 Geen geplande trainingen gevonden. Gebruik handmatige aanwezigheid.")
        
        # Krijg alle spelers uit de zones
        alle_spelers = zones["Speler"].unique().tolist()
        aanwezige_spelers = []
        
        # Selecteer alle / Deselecteer alle knoppen
        col_btn1, col_btn2, col_spacer = st.columns([1, 1, 3])
        with col_btn1:
            if st.button("✅ Selecteer alle", help="Markeer alle spelers als aanwezig"):
                for speler in alle_spelers:
                    st.session_state[f"aanwezig_{speler}"] = True
                st.rerun()
        with col_btn2:
            if st.button("❌ Deselecteer alle", help="Markeer alle spelers als afwezig"):
                for speler in alle_spelers:
                    st.session_state[f"aanwezig_{speler}"] = False
                st.rerun()
        
        # Maak kolommen voor checkboxes
        cols = st.columns(3)
        
        for i, speler in enumerate(alle_spelers):
            col_idx = i % 3
            with cols[col_idx]:
                is_aanwezig = st.session_state.get(f"aanwezig_{speler}", True)
                if st.checkbox(speler, key=f"aanwezig_{speler}", value=is_aanwezig):
                    aanwezige_spelers.append(speler)
    
    # Database connection cleanup handled by Supabase helpers

    # Download sectie
    st.subheader("💾 Downloads")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 📊 Data Export")
        download_cols = ["Speler", "TrueVIFT", "VO2MAX", base_column, "Doelsnelheid_km_u", "Afstand_per_interval_m", "Groep_Label"]
        # Vermijd duplicaten in download kolommen
        download_cols = list(dict.fromkeys(download_cols))  # Behoud volgorde, verwijder duplicaten
        
        csv_data = zones[download_cols].to_csv(index=False)
        st.download_button(
            label="📥 Download data (CSV)",
            data=csv_data,
            file_name=f"training_{maand_selectie}_{metric_keuze.replace(' ', '_')}_{percentage}procent.csv",
            mime="text/csv"
        )
    
    with col2:
        st.markdown("#### 🎨 Visueel Overzicht")
        
        # Titel en oefening input - gebruik automatische titel als beschikbaar
        default_title = st.session_state.get("auto_training_title", f"Training Planning - {maand_selectie}")
        training_title = st.text_input(
            "Titel voor trainingsoverzicht",
            value=default_title,
            help="Voer een titel in voor het visuele overzicht (automatisch ingevuld als training geselecteerd)"
        )
        
        oefening_naam = st.text_input(
            "Naam van de oefening",
            value="",
            help="Geef de training/oefening een specifieke naam",
            placeholder="bijv. Interval Training, Speed Work, etc."
        )
        
        # Preview checkbox
        show_preview = st.checkbox("👁️ Toon preview", help="Bekijk hoe het overzicht eruit ziet")
        
        # Buttons voor download
        col_png, col_pdf = st.columns(2)
        
        with col_png:
            if st.button("🖼️ Download PNG", help="Download als afbeelding"):
                try:
                    # Gebruik juiste parameters
                    current_shuttle_afstand = shuttle_afstand if loopvorm_type == "Shuttle runs" and 'shuttle_afstand' in locals() else 20
                    current_zijde_lengte = zijde_lengte if loopvorm_type in ["Vierkant parcours", "Driehoek parcours"] and 'zijde_lengte' in locals() else 25
                    
                    fig = create_training_overview(
                        zones, loopvorm_type, base_column, percentage, 
                        intervalduur, rustduur, aantal_herhalingen, 
                        training_title, oefening_naam, maand_selectie, current_shuttle_afstand, current_zijde_lengte, aanwezige_spelers
                    )
                    
                    # Sla op als PNG
                    img_buffer = io.BytesIO()
                    fig.savefig(img_buffer, format='png', dpi=300, bbox_inches='tight')
                    img_buffer.seek(0)
                    
                    st.download_button(
                        label="📥 Download PNG bestand",
                        data=img_buffer.getvalue(),
                        file_name=f"training_overzicht_{maand_selectie}_{percentage}procent.png",
                        mime="image/png"
                    )
                    
                    plt.close(fig)
                    st.success("PNG gegenereerd!")
                    
                except Exception as e:
                    st.error(f"Fout bij genereren PNG: {e}")
        
        with col_pdf:
            if st.button("📄 Download PDF", help="Download als PDF"):
                try:
                    # Gebruik juiste parameters
                    current_shuttle_afstand = shuttle_afstand if loopvorm_type == "Shuttle runs" and 'shuttle_afstand' in locals() else 20
                    current_zijde_lengte = zijde_lengte if loopvorm_type in ["Vierkant parcours", "Driehoek parcours"] and 'zijde_lengte' in locals() else 25
                    
                    # Maak figuur
                    fig = create_training_overview(
                        zones, loopvorm_type, base_column, percentage, 
                        intervalduur, rustduur, aantal_herhalingen, 
                        training_title, oefening_naam, maand_selectie, current_shuttle_afstand, current_zijde_lengte, aanwezige_spelers
                    )
                    
                    # Sla op als PDF
                    pdf_buffer = io.BytesIO()
                    with PdfPages(pdf_buffer) as pdf:
                        pdf.savefig(fig, bbox_inches='tight')
                    pdf_buffer.seek(0)
                    
                    st.download_button(
                        label="📥 Download PDF bestand",
                        data=pdf_buffer.getvalue(),
                        file_name=f"training_overzicht_{maand_selectie}_{percentage}procent.pdf",
                        mime="application/pdf"
                    )
                    
                    plt.close(fig)
                    st.success("PDF gegenereerd!")
                    
                except Exception as e:
                    st.error(f"Fout bij genereren PDF: {e}")
    
    # Preview sectie
    if show_preview:
        st.subheader("👁️ Preview Trainingsoverzicht")
        try:
            current_shuttle_afstand = shuttle_afstand if loopvorm_type == "Shuttle runs" and 'shuttle_afstand' in locals() else 20
            current_zijde_lengte = zijde_lengte if loopvorm_type in ["Vierkant parcours", "Driehoek parcours"] and 'zijde_lengte' in locals() else 25
            
            fig = create_training_overview(
                zones, loopvorm_type, base_column, percentage, 
                intervalduur, rustduur, aantal_herhalingen, 
                training_title, oefening_naam, maand_selectie, current_shuttle_afstand, current_zijde_lengte, aanwezige_spelers
            )
            
            st.pyplot(fig)
            plt.close(fig)
            
        except Exception as e:
            st.error(f"Fout bij genereren preview: {e}")

# Safe database connection cleanup

# Database cleanup handled by Supabase helpers