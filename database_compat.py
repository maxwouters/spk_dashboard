"""
Compatibility shim for database connections
"""

# Try to import Supabase first
try:
    from supabase_helpers import get_supabase_client
    def get_database_connection():
        return get_supabase_client()
except ImportError:
    # Try original db_config
    try:
        from db_config import get_database_connection
    except ImportError:
        # Last resort fallback
        def get_database_connection():
            import streamlit as st
            st.error("❌ No database connection available")
            st.stop()
