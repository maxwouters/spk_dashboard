"""
Supabase database configuration for SPK Dashboard
Handles connection to Supabase PostgreSQL database
"""

import os
from supabase import create_client, Client
import pandas as pd

def get_supabase_config():
    """Get Supabase configuration from multiple sources"""
    
    # Try environment variables first (works everywhere)
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_ANON_KEY')
    if url and key:
        return url, key
    
    # Try reading from .streamlit/secrets.toml directly (for testing outside Streamlit)
    try:
        import toml
        from pathlib import Path
        secrets_file = Path('.streamlit/secrets.toml')
        if secrets_file.exists():
            secrets = toml.load(secrets_file)
            if 'supabase' in secrets:
                url = secrets['supabase'].get('url')
                key = secrets['supabase'].get('anon_key')
                if url and key:
                    return url, key
    except ImportError:
        # toml not available, skip this method
        pass
    except Exception:
        # Any other error reading secrets file
        pass
    
    # Try Streamlit secrets (when running in Streamlit)
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and 'supabase' in st.secrets:
            url = st.secrets.supabase.get('url')
            key = st.secrets.supabase.get('anon_key')
            if url and key:
                return url, key
    except:
        pass
    
    return None, None

def get_supabase_client() -> Client:
    """Get Supabase client connection"""
    url, key = get_supabase_config()
    
    if not url or not key:
        raise ValueError("""
        ⚠️ Supabase configuration missing!
        
        For local development, set environment variables:
        export SUPABASE_URL="your-project-url"
        export SUPABASE_ANON_KEY="your-anon-key"
        
        For Streamlit Cloud, add to secrets:
        [supabase]
        url = "your-project-url"
        anon_key = "your-anon-key"
        """)
    
    try:
        supabase = create_client(url, key)
        print("✅ Connected to Supabase")
        return supabase
    except Exception as e:
        print(f"❌ Supabase connection failed: {e}")
        raise

def execute_query(query: str, params: dict = None) -> pd.DataFrame:
    """Execute SQL query and return as DataFrame"""
    supabase = get_supabase_client()
    
    try:
        # For complex queries, use RPC or direct SQL
        result = supabase.rpc('execute_sql', {'query': query, 'params': params or {}}).execute()
        return pd.DataFrame(result.data)
    except Exception as e:
        print(f"⚠️ Query failed: {e}")
        return pd.DataFrame()

def insert_data(table: str, data: dict) -> bool:
    """Insert data into Supabase table"""
    supabase = get_supabase_client()
    
    try:
        result = supabase.table(table).insert(data).execute()
        return len(result.data) > 0
    except Exception as e:
        print(f"❌ Insert failed for table {table}: {e}")
        return False

def update_data(table: str, data: dict, match_column: str, match_value) -> bool:
    """Update data in Supabase table"""
    supabase = get_supabase_client()
    
    try:
        result = supabase.table(table).update(data).eq(match_column, match_value).execute()
        return len(result.data) > 0
    except Exception as e:
        print(f"❌ Update failed for table {table}: {e}")
        return False

def delete_data(table: str, match_column: str, match_value) -> bool:
    """Delete data from Supabase table"""
    supabase = get_supabase_client()
    
    try:
        result = supabase.table(table).delete().eq(match_column, match_value).execute()
        return True
    except Exception as e:
        print(f"❌ Delete failed for table {table}: {e}")
        return False

def get_table_data(table: str, columns: str = "*", limit: int = None) -> pd.DataFrame:
    """Get data from Supabase table as DataFrame"""
    supabase = get_supabase_client()
    
    try:
        query = supabase.table(table).select(columns)
        if limit:
            query = query.limit(limit)
        
        result = query.execute()
        return pd.DataFrame(result.data)
    except Exception as e:
        print(f"❌ Failed to get data from table {table}: {e}")
        return pd.DataFrame()

def is_supabase_configured() -> bool:
    """Check if Supabase credentials are available"""
    url, key = get_supabase_config()
    return bool(url and key)

# Test connection on import
if __name__ == "__main__":
    try:
        client = get_supabase_client()
        print("✅ Supabase connection test successful")
    except Exception as e:
        print(f"❌ Supabase connection test failed: {e}")