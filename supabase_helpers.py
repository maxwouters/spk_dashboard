"""
Supabase helper functions for SPK Dashboard
IMPROVED VERSION - Better query parsing and error handling
"""

import pandas as pd
from supabase_config import get_supabase_client
import streamlit as st
from typing import Optional, List, Dict, Any
import re

@st.cache_data(ttl=300)  # Cache for 5 minutes
def safe_fetchdf(query: str, params: Dict = None) -> pd.DataFrame:
    """
    Safe query execution that returns DataFrame
    IMPROVED: Better Supabase query handling
    """
    try:
        supabase = get_supabase_client()
        
        # Handle the most common GPS queries specifically
        if "gps_data" in query.lower() and "count(*)" in query.lower():
            # Handle COUNT queries
            return handle_count_query(query, params)
        
        if "gps_data" in query.lower() and "select" in query.lower():
            # Handle SELECT queries from gps_data
            return handle_gps_select_query(query, params)
        
        if query.strip().upper().startswith('SELECT'):
            return handle_generic_select_query(query, params)
        
        return pd.DataFrame()
        
    except Exception as e:
        print(f"Query failed: {e}")
        st.error(f"Database query failed: {e}")
        return pd.DataFrame()

def handle_count_query(query: str, params: Dict = None) -> pd.DataFrame:
    """Handle COUNT(*) queries with proper WHERE clause parsing"""
    import re
    try:
        supabase = get_supabase_client()
        
        # Extract table name
        match = re.search(r'FROM\s+(\w+)', query, re.IGNORECASE)
        if not match:
            return pd.DataFrame()
        
        table_name = match.group(1)
        query_builder = supabase.table(table_name).select("*", count="exact")
        
        # Parse WHERE clause from the query string itself
        if "WHERE" in query.upper():
            where_part = query.upper().split("WHERE", 1)[1].strip()
            
            # Handle simple WHERE conditions (speler = 'Barry Djaumo')
            if "=" in where_part:
                # Parse column = 'value' patterns - need to search original case
                original_where = query.split("WHERE", 1)[1].strip() if "WHERE" in query else query.split("where", 1)[1].strip()
                pattern = r"(\w+)\s*=\s*'([^']+)'"
                matches = re.findall(pattern, original_where)
                
                for column, value in matches:
                    query_builder = query_builder.eq(column.lower(), value)
            
            # Handle date range conditions (datum >= '2025-07-01' AND datum <= '2025-07-31') 
            original_where = query.split("WHERE", 1)[1].strip() if "WHERE" in query else query.split("where", 1)[1].strip()
            date_pattern = r"datum\s*>=\s*'([^']+)'"
            date_match = re.search(date_pattern, original_where, re.IGNORECASE)
            if date_match:
                start_date = date_match.group(1)
                query_builder = query_builder.gte('datum', start_date)
                
            date_pattern_end = r"datum\s*<=\s*'([^']+)'"
            date_match_end = re.search(date_pattern_end, original_where, re.IGNORECASE)
            if date_match_end:
                end_date = date_match_end.group(1)
                query_builder = query_builder.lte('datum', end_date)
        
        result = query_builder.execute()
        count = result.count if hasattr(result, 'count') else len(result.data)
        return pd.DataFrame([{'count': count}])
        
    except Exception as e:
        print(f"Count query failed: {e}")
        return pd.DataFrame([{'count': 0}])

def handle_gps_select_query(query: str, params: Dict = None) -> pd.DataFrame:
    """Handle SELECT queries from gps_data table"""
    try:
        supabase = get_supabase_client()
        
        # Start with gps_data table
        query_builder = supabase.table("gps_data")
        
        # Extract SELECT columns
        select_match = re.search(r'SELECT\s+(.+?)\s+FROM', query, re.IGNORECASE | re.DOTALL)
        columns = "*"
        if select_match:
            columns = select_match.group(1).strip()
            if columns != "*":
                # Clean up column names
                columns = re.sub(r'\s+', ' ', columns)
        
        query_builder = query_builder.select(columns)
        
        # Handle WHERE clause
        if "WHERE" in query.upper():
            query_builder = apply_where_conditions(query_builder, query, params)
        
        # Handle ORDER BY
        if "ORDER BY" in query.upper():
            order_match = re.search(r'ORDER BY\s+(\w+)(?:\s+(DESC|ASC))?', query, re.IGNORECASE)
            if order_match:
                column = order_match.group(1)
                desc = order_match.group(2) and order_match.group(2).upper() == 'DESC'
                query_builder = query_builder.order(column, desc=desc)
        
        # Handle LIMIT
        if "LIMIT" in query.upper():
            limit_match = re.search(r'LIMIT\s+(\d+)', query, re.IGNORECASE)
            if limit_match:
                limit = int(limit_match.group(1))
                query_builder = query_builder.limit(limit)
        
        result = query_builder.execute()
        return pd.DataFrame(result.data)
        
    except Exception as e:
        print(f"GPS query failed: {e}")
        return pd.DataFrame()

def apply_where_conditions(query_builder, query: str, params: Dict = None):
    """Apply WHERE conditions to query builder"""
    try:
        # Extract WHERE clause
        where_match = re.search(r'WHERE\s+(.+?)(?:\s+ORDER|\s+LIMIT|$)', query, re.IGNORECASE | re.DOTALL)
        if not where_match:
            return query_builder
        
        where_clause = where_match.group(1).strip()
        
        # Handle parameterized queries (? placeholders)
        if params and isinstance(params, (list, tuple)) and '?' in where_clause:
            # Parse multi-parameter WHERE clauses properly
            conditions = [cond.strip() for cond in where_clause.split(' AND ')]
            param_index = 0
            
            for condition in conditions:
                condition = condition.strip()
                if '?' in condition:
                    if param_index < len(params):
                        # Extract column name from "column = ?" pattern
                        if ' = ?' in condition:
                            column = condition.split(' = ?')[0].strip()
                            query_builder = query_builder.eq(column, params[param_index])
                            param_index += 1
            return query_builder
        
        # Parse all conditions - split by AND but handle quoted strings properly
        conditions = []
        current_condition = ""
        in_quotes = False
        quote_char = None
        
        i = 0
        while i < len(where_clause):
            char = where_clause[i]
            
            # Handle quotes
            if char in ["'", '"'] and (i == 0 or where_clause[i-1] != '\\'):
                if not in_quotes:
                    in_quotes = True
                    quote_char = char
                elif char == quote_char:
                    in_quotes = False
                    quote_char = None
            
            # Handle AND outside of quotes
            if not in_quotes and where_clause[i:i+3].upper() == 'AND':
                conditions.append(current_condition.strip())
                current_condition = ""
                i += 3
                continue
            
            current_condition += char
            i += 1
        
        # Add the last condition
        if current_condition.strip():
            conditions.append(current_condition.strip())
        
        # Process each condition
        for condition in conditions:
            condition = condition.strip()
            
            # Handle IS NOT NULL first (most specific)
            if 'IS NOT NULL' in condition.upper():
                column_match = re.search(r'(\w+)\s+IS NOT NULL', condition, re.IGNORECASE)
                if column_match:
                    column = column_match.group(1)
                    query_builder = query_builder.not_.is_('null')
            
            # Handle greater than or equal (column >= 'value') - check before single '='
            elif '>=' in condition:
                parts = condition.split('>=', 1)
                if len(parts) == 2:
                    column = parts[0].strip()
                    value = parts[1].strip().strip("'\"")
                    query_builder = query_builder.gte(column, value)
            
            # Handle less than or equal (column <= 'value') - check before single '='
            elif '<=' in condition:
                parts = condition.split('<=', 1)
                if len(parts) == 2:
                    column = parts[0].strip()
                    value = parts[1].strip().strip("'\"")
                    query_builder = query_builder.lte(column, value)
            
            # Handle greater than (column > 'value') - check before single '='
            elif '>' in condition:
                parts = condition.split('>', 1)
                if len(parts) == 2:
                    column = parts[0].strip()
                    value = parts[1].strip().strip("'\"")
                    query_builder = query_builder.gt(column, value)
            
            # Handle less than (column < 'value') - check before single '='
            elif '<' in condition:
                parts = condition.split('<', 1)
                if len(parts) == 2:
                    column = parts[0].strip()
                    value = parts[1].strip().strip("'\"")
                    query_builder = query_builder.lt(column, value)
            
            # Handle equality conditions (column = 'value') - check last to avoid conflicts
            elif '=' in condition:
                parts = condition.split('=', 1)
                if len(parts) == 2:
                    column = parts[0].strip()
                    value = parts[1].strip().strip("'\"")
                    query_builder = query_builder.eq(column, value)
        
        return query_builder
        
    except Exception as e:
        print(f"WHERE condition failed: {e}")
        return query_builder

def handle_generic_select_query(query: str, params: Dict = None) -> pd.DataFrame:
    """Handle generic SELECT queries"""
    try:
        supabase = get_supabase_client()
        
        # Extract table name
        table_match = re.search(r'FROM\s+(\w+)', query, re.IGNORECASE)
        if not table_match:
            return pd.DataFrame()
        
        table_name = table_match.group(1)
        
        # Extract columns
        select_match = re.search(r'SELECT\s+(.+?)\s+FROM', query, re.IGNORECASE | re.DOTALL)
        columns = "*"
        if select_match:
            columns = select_match.group(1).strip()
        
        query_builder = supabase.table(table_name).select(columns)
        
        # Apply WHERE, ORDER BY, LIMIT
        if "WHERE" in query.upper():
            query_builder = apply_where_conditions(query_builder, query, params)
        
        if "ORDER BY" in query.upper():
            order_match = re.search(r'ORDER BY\s+(\w+)(?:\s+(DESC|ASC))?', query, re.IGNORECASE)
            if order_match:
                column = order_match.group(1)
                desc = order_match.group(2) and order_match.group(2).upper() == 'DESC'
                query_builder = query_builder.order(column, desc=desc)
        
        if "LIMIT" in query.upper():
            limit_match = re.search(r'LIMIT\s+(\d+)', query, re.IGNORECASE)
            if limit_match:
                limit = int(limit_match.group(1))
                query_builder = query_builder.limit(limit)
        
        result = query_builder.execute()
        return pd.DataFrame(result.data)
        
    except Exception as e:
        print(f"Generic query failed: {e}")
        return pd.DataFrame()

# Keep all other existing functions...
def get_table_data(table_name: str, columns: str = "*", where_conditions: Dict = None, limit: int = None) -> pd.DataFrame:
    """Get data from Supabase table with optional filtering"""
    try:
        supabase = get_supabase_client()
        query = supabase.table(table_name).select(columns)
        
        # Apply WHERE conditions
        if where_conditions:
            for column, value in where_conditions.items():
                query = query.eq(column, value)
        
        # Apply limit
        if limit:
            query = query.limit(limit)
        
        result = query.execute()
        return pd.DataFrame(result.data)
        
    except Exception as e:
        st.error(f"Failed to get data from {table_name}: {e}")
        return pd.DataFrame()

def check_table_exists(table_name: str) -> bool:
    """Check if table exists in Supabase"""
    try:
        supabase = get_supabase_client()
        # Try to select from table with limit 0
        result = supabase.table(table_name).select("*").limit(0).execute()
        return True
    except:
        return False

def get_player_names() -> List[str]:
    """Get list of active player names"""
    df = get_table_data('spelers_profiel', columns='naam', where_conditions={'status': 'Actief'})
    if df.empty:
        # Fallback to thirty_fifteen_results if spelers_profiel is empty
        df = get_table_data('thirty_fifteen_results', columns='Speler')
        return sorted(df['Speler'].unique().tolist()) if not df.empty else []
    return sorted(df['naam'].tolist())

def get_training_data(speler: str = None, limit: int = None) -> pd.DataFrame:
    """Get training data with optional player filter"""
    conditions = {'speler': speler} if speler else None
    return get_table_data('gps_data', where_conditions=conditions, limit=limit)

def get_thirty_fifteen_results(speler: str = None) -> pd.DataFrame:
    """Get 30-15 test results"""
    conditions = {'Speler': speler} if speler else None
    df = get_table_data('thirty_fifteen_results', where_conditions=conditions)
    return df.sort_values('Maand', ascending=False) if not df.empty else df

# Cache commonly used data
@st.cache_data(ttl=600)  # Cache for 10 minutes
def get_cached_player_list():
    """Get cached list of players"""
    return get_player_names()

@st.cache_data(ttl=300)  # Cache for 5 minutes  
def get_cached_training_data(speler: str = None):
    """Get cached training data"""
    return get_training_data(speler)

# Connection test
def test_supabase_connection() -> bool:
    """Test if Supabase connection works"""
    try:
        supabase = get_supabase_client()
        # Try a simple query on gps_data table (more reliable)
        result = supabase.table('gps_data').select("speler").limit(1).execute()
        return True
    except Exception as e:
        st.error(f"Supabase connection test failed: {e}")
        return False
