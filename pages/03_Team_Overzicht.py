import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# Supabase helpers (primary)
try:
    from supabase_helpers import (
        safe_fetchdf,
        get_table_data, 
        get_thirty_fifteen_results, 
        test_supabase_connection,
        check_table_exists
    )
    SUPABASE_MODE = True
except ImportError:
    # Fallback to legacy
    from db_config import get_database_connection
    SUPABASE_MODE = False

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

st.title("👥 Team Overzicht")

if SUPABASE_MODE:
    # Supabase mode
    st.info("🌐 Using Supabase database")
    
    if not test_supabase_connection():
        st.error("❌ Cannot connect to Supabase")
        st.stop()
    
    # Get thirty_fifteen test data
    all_data = get_thirty_fifteen_results()
    
    # Calculate MAS if not present
    if not all_data.empty and 'MAS' not in all_data.columns:
        all_data['MAS'] = all_data['TrueVIFT'] * 0.95
else:
    # Legacy mode
    # Legacy mode fallback
    try:
        con = get_database_connection()
    except NameError:
        st.error("❌ Database connection not available")
        st.stop()
    # Check of er data is
    table_exists = check_table_exists('thirty_fifteen_results')

    if not table_exists:
        st.warning("📭 Er zijn nog geen testresultaten beschikbaar.")
        st.stop()
    
    # Haal alle data op
    all_data = safe_fetchdf("SELECT * FROM thirty_fifteen_results ORDER BY Maand DESC, Speler")
    
    # Check en bereken MAS als deze niet bestaat
    if 'MAS' not in all_data.columns:
        all_data['MAS'] = all_data['TrueVIFT'] * 0.95
    
    if len(all_data) == 0:
        st.warning("📭 Er zijn nog geen testresultaten beschikbaar.")
    else:
        # Datum en metric selectie
        col1, col2 = st.columns(2)
        with col1:
            beschikbare_maanden = sorted(all_data["Maand"].unique(), reverse=True)
            selected_maand = st.selectbox("📅 Selecteer test datum", beschikbare_maanden)
        with col2:
            team_metric = st.selectbox("📊 Selecteer metric", ["MAS (Aanbevolen)", "TrueVIFT", "VO2Max"])
        
        if team_metric == "MAS (Aanbevolen)":
            metric_col = "MAS"
            metric_unit = "km/u"
            metric_name = "MAS"
        elif team_metric == "TrueVIFT":
            metric_col = "TrueVIFT"
            metric_unit = "km/u"
            metric_name = "TrueVIFT"
        else:
            metric_col = "VO2MAX"
            metric_unit = "ml/kg/min"
            metric_name = "VO2Max"
        
        # Filter data voor geselecteerde maand
        team_data = all_data[all_data["Maand"] == selected_maand].copy()
        
        if len(team_data) == 0:
            st.warning(f"Geen teamdata gevonden voor {selected_maand}")
        else:
            # Bereken team statistieken
            team_gemiddelde = team_data[metric_col].mean()
            team_mediaan = team_data[metric_col].median()
            team_min = team_data[metric_col].min()
            team_max = team_data[metric_col].max()
            team_std = team_data[metric_col].std()
            
            # Team statistieken weergeven
            st.subheader("📊 Team Statistieken")
            col1, col2, col3, col4, col5 = st.columns(5)
            
            with col1:
                st.metric("🎯 Gemiddelde", f"{team_gemiddelde:.1f} {metric_unit}")
            with col2:
                st.metric("📈 Mediaan", f"{team_mediaan:.1f} {metric_unit}")
            with col3:
                st.metric("⬇️ Minimum", f"{team_min:.1f} {metric_unit}")
            with col4:
                st.metric("⬆️ Maximum", f"{team_max:.1f} {metric_unit}")
            with col5:
                st.metric("📏 Spreiding", f"{team_std:.1f} {metric_unit}")
            
            # Voeg vergelijking met gemiddelde toe
            team_data["Verschil_vs_Gemiddelde"] = team_data[metric_col] - team_gemiddelde
            team_data["Percentage_vs_Gemiddelde"] = (team_data[metric_col] / team_gemiddelde * 100) - 100
            team_data["Prestatie_Categorie"] = team_data["Verschil_vs_Gemiddelde"].apply(
                lambda x: "🟢 Boven gemiddeld" if x > 0.5 
                else "🔴 Onder gemiddeld" if x < -0.5 
                else "🟡 Gemiddeld"
            )
            
            # Visualisatie - Team vergelijking
            st.subheader(f"📈 Team Vergelijking - {team_metric}")
            
            col1, col2 = st.columns([2, 1])
            
            with col1:
                # Bar chart met alle spelers
                fig = go.Figure()
                
                # Kleur per prestatie categorie
                colors = team_data["Prestatie_Categorie"].map({
                    "🟢 Boven gemiddeld": "#2ecc71",
                    "🟡 Gemiddeld": "#f39c12", 
                    "🔴 Onder gemiddeld": "#e74c3c"
                })
                
                fig.add_trace(go.Bar(
                    x=team_data["Speler"],
                    y=team_data[metric_col],
                    marker_color=colors,
                    text=team_data[metric_col].round(1),
                    textposition='outside',
                    name=f'{team_metric} per speler'
                ))
                
                # Voeg gemiddelde lijn toe
                fig.add_hline(
                    y=team_gemiddelde, 
                    line_dash="dash", 
                    line_color="blue",
                    annotation_text=f"Team gemiddelde: {team_gemiddelde:.1f} {metric_unit}"
                )
                
                fig.update_layout(
                    title=f"Team {team_metric} Resultaten - {selected_maand}",
                    xaxis_title="Speler",
                    yaxis_title=f"{team_metric} ({metric_unit})",
                    height=500,
                    showlegend=False,
                    xaxis_tickangle=-45
                )
                
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                # Verdeling grafiek
                fig_pie = go.Figure(data=[go.Pie(
                    labels=["Boven gemiddeld", "Gemiddeld", "Onder gemiddeld"],
                    values=[
                        len(team_data[team_data["Prestatie_Categorie"] == "🟢 Boven gemiddeld"]),
                        len(team_data[team_data["Prestatie_Categorie"] == "🟡 Gemiddeld"]),
                        len(team_data[team_data["Prestatie_Categorie"] == "🔴 Onder gemiddeld"])
                    ],
                    marker_colors=["#2ecc71", "#f39c12", "#e74c3c"]
                )])
                
                fig_pie.update_layout(
                    title="Prestatie Verdeling",
                    height=400
                )
                
                st.plotly_chart(fig_pie, use_container_width=True)
            
            # Gedetailleerde tabel
            st.subheader("📋 Gedetailleerd Team Overzicht")
            
            # Sorteer op geselecteerde metric (hoogste eerst)
            display_data = team_data.sort_values(metric_col, ascending=False).copy()
            display_data["Ranking"] = range(1, len(display_data) + 1)
            
            # Kolommen voor weergave
            display_cols = ["Ranking", "Speler", "Leeftijd", metric_col, "Verschil_vs_Gemiddelde", "Percentage_vs_Gemiddelde", "Prestatie_Categorie"]
            col_names = {
                "Ranking": "#",
                "Speler": "Speler",
                "Leeftijd": "Leeftijd",
                "TrueVIFT": "MAS (km/u)",
                "VO2MAX": "VO2Max (ml/kg/min)",
                "Verschil_vs_Gemiddelde": f"Verschil ({metric_unit})",
                "Percentage_vs_Gemiddelde": "Verschil (%)",
                "Prestatie_Categorie": "Prestatie"
            }
            
            result_table = display_data[display_cols].copy()
            result_table.columns = [col_names.get(col, col) for col in display_cols]
            
            # Format de percentages
            result_table["Verschil (%)"] = result_table["Verschil (%)"].apply(lambda x: f"{x:+.1f}%")
            result_table[f"Verschil ({metric_unit})"] = result_table[f"Verschil ({metric_unit})"].apply(lambda x: f"{x:+.1f}")
            
            st.dataframe(
                result_table,
                use_container_width=True,
                hide_index=True
            )
            
            # Historische vergelijking (als er meerdere maanden zijn)
            beschikbare_maanden = sorted(all_data["Maand"].unique(), reverse=True)
            if len(beschikbare_maanden) > 1:
                st.subheader("📈 Historische Team Progressie")
                
                # Bereken gemiddelden per maand voor beide metrics
                maand_gemiddelden = all_data.groupby("Maand").agg({
                    "TrueVIFT": ["mean", "median", "min", "max", "std", "count"],
                    "VO2MAX": ["mean", "median", "min", "max", "std"],
                    "Leeftijd": "mean"
                }).reset_index()
                
                # Flatten column names
                maand_gemiddelden.columns = ["Maand", "MAS_mean", "MAS_median", "MAS_min", "MAS_max", "MAS_std", "Aantal_Spelers",
                                           "VO2_mean", "VO2_median", "VO2_min", "VO2_max", "VO2_std", "Leeftijd_mean"]
                
                # Lijn grafiek voor team progressie
                fig_hist = go.Figure()
                
                if team_metric == "TrueVIFT (MAS)":
                    y_mean = maand_gemiddelden["MAS_mean"]
                    y_max = maand_gemiddelden["MAS_max"]
                    y_min = maand_gemiddelden["MAS_min"]
                else:
                    y_mean = maand_gemiddelden["VO2_mean"]
                    y_max = maand_gemiddelden["VO2_max"]
                    y_min = maand_gemiddelden["VO2_min"]
                
                fig_hist.add_trace(go.Scatter(
                    x=maand_gemiddelden["Maand"],
                    y=y_mean,
                    mode='lines+markers',
                    name='Team Gemiddelde',
                    line=dict(color='blue', width=3),
                    marker=dict(size=8)
                ))
                
                fig_hist.add_trace(go.Scatter(
                    x=maand_gemiddelden["Maand"],
                    y=y_max,
                    mode='lines+markers',
                    name='Beste Prestatie',
                    line=dict(color='green', width=2),
                    marker=dict(size=6)
                ))
                
                fig_hist.add_trace(go.Scatter(
                    x=maand_gemiddelden["Maand"],
                    y=y_min,
                    mode='lines+markers',
                    name='Laagste Prestatie',
                    line=dict(color='red', width=2),
                    marker=dict(size=6)
                ))
                
                fig_hist.update_layout(
                    title=f"Team {team_metric} Ontwikkeling Over Tijd",
                    xaxis_title="Test Maand",
                    yaxis_title=f"{team_metric} ({metric_unit})",
                    height=400
                )
                
                st.plotly_chart(fig_hist, use_container_width=True)
                
                # Historische tabel
                st.subheader("📊 Historische Team Statistieken")
                if team_metric == "TrueVIFT (MAS)":
                    hist_display = maand_gemiddelden[["Maand", "MAS_mean", "MAS_median", "MAS_min", "MAS_max", "MAS_std", "Aantal_Spelers"]].round(1)
                    hist_display.columns = ["Test Maand", "Gemiddelde (km/u)", "Mediaan (km/u)", "Min (km/u)", "Max (km/u)", "Spreiding (km/u)", "Aantal Spelers"]
                else:
                    hist_display = maand_gemiddelden[["Maand", "VO2_mean", "VO2_median", "VO2_min", "VO2_max", "VO2_std", "Aantal_Spelers"]].round(1)
                    hist_display.columns = ["Test Maand", "Gemiddelde (ml/kg/min)", "Mediaan (ml/kg/min)", "Min (ml/kg/min)", "Max (ml/kg/min)", "Spreiding (ml/kg/min)", "Aantal Spelers"]
                
                st.dataframe(hist_display, use_container_width=True, hide_index=True)
            
            # Export team data
            csv_team = team_data[["Speler", "Leeftijd", "TrueVIFT", "VO2MAX", "Verschil_vs_Gemiddelde", "Percentage_vs_Gemiddelde", "Prestatie_Categorie"]].to_csv(index=False)
            st.download_button(
                label=f"📥 Download team overzicht {selected_maand}",
                data=csv_team,
                file_name=f"team_overzicht_{selected_maand}_{team_metric.replace(' ', '_')}.csv",
                mime="text/csv"
            )

# Safe database connection cleanup

# Database cleanup handled by Supabase helpers