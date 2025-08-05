"""
Database helper functions - now Supabase-first with legacy fallback
"""

import pandas as pd
import streamlit as st

# Import Supabase helpers as primary
try:
    from supabase_helpers import (
        safe_fetchdf as supabase_fetchdf,
        get_table_data,
        insert_data,
        update_data,
        delete_data,
        check_table_exists as supabase_table_exists,
        get_table_columns as supabase_table_columns,
        test_supabase_connection
    )
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

# Enhanced safe_fetchdf that tries Supabase first
def safe_fetchdf(conn_or_query, query_or_params=None, params=None):
    """
    Enhanced safe_fetchdf - tries Supabase first, then falls back to legacy
    Usage: 
    - safe_fetchdf("SELECT * FROM spelers_profiel")  # Supabase query
    - safe_fetchdf(conn, "SELECT * FROM table", params)  # Legacy mode
    """
    # If first arg is string, assume it's a Supabase query
    if isinstance(conn_or_query, str) and SUPABASE_AVAILABLE:
        try:
            return supabase_fetchdf(conn_or_query, query_or_params or {})
        except Exception as e:
            st.warning(f"Supabase query failed, trying legacy: {e}")
    
    # Legacy mode - continue with original logic
    return legacy_safe_fetchdf(conn_or_query, query_or_params, params)

def legacy_safe_fetchdf(conn, query, params=None):
    """Original safe_fetchdf logic for legacy database support"""

def check_table_exists(conn, table_name):
    """Check if a table exists - works with both DuckDB and SQLite"""
    try:
        # Try DuckDB syntax first
        result = conn.execute("""
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_name = ?
        """, (table_name,)).fetchone()
        return result[0] > 0
    except:
        try:
            # Fall back to SQLite syntax
            result = conn.execute("""
                SELECT COUNT(*) 
                FROM sqlite_master 
                WHERE type='table' AND name = ?
            """, (table_name,)).fetchone()
            return result[0] > 0
        except:
            return False

def get_table_columns(conn, table_name):
    """Get column names from a table - works with both DuckDB and SQLite"""
    try:
        # Try DuckDB syntax first
        columns = conn.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = ?
        """, (table_name,)).fetchall()
        return [col[0] for col in columns]
    except:
        try:
            # Fall back to SQLite syntax
            result = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
            return [col[1] for col in result]  # column name is at index 1
        except:
            return []

def add_column_if_not_exists(conn, table_name, column_name, column_type):
    """Add a column to a table if it doesn't exist"""
    existing_columns = get_table_columns(conn, table_name)
    
    if column_name not in existing_columns and len(existing_columns) > 0:
        try:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
            return True
        except Exception as e:
            print(f"Could not add column {column_name}: {e}")
            return False
    return False

def safe_query(conn, query, params=None):
    """Execute a query safely with error handling"""
    try:
        if params:
            return conn.execute(query, params)
        else:
            return conn.execute(query)
    except Exception as e:
        print(f"Query failed: {e}")
        return None

def safe_fetchdf(conn, query, params=None):
    """Execute a query and return as pandas DataFrame - works with both DuckDB and SQLite"""
    import pandas as pd
    
    try:
        if params:
            result = conn.execute(query, params)
        else:
            result = conn.execute(query)
        
        # Try DuckDB's fetchdf() first
        if hasattr(result, 'fetchdf'):
            return result.fetchdf()
        else:
            # Fallback for SQLite - convert to DataFrame manually
            rows = result.fetchall()
            if not rows:
                return pd.DataFrame()
            
            # Get column names from cursor description
            if hasattr(result, 'description') and result.description:
                columns = [description[0] for description in result.description]
            else:
                # If no description available, try to get from cursor
                columns = [f'col_{i}' for i in range(len(rows[0]) if rows else 0)]
                
            return pd.DataFrame(rows, columns=columns)
            
    except Exception as e:
        print(f"Query failed: {e}")
        import pandas as pd
        return pd.DataFrame()