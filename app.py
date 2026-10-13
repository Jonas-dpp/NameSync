"""Streamlit entry point for Name Sync (Sprint 1).

Initializes database and executes automatic cleanup before rendering UI components.
"""

import streamlit as st
import database


def main() -> None:
    """Main function executing backend initialization and basic Streamlit UI."""
    try:
        database.init_db()
        database.cleanup_old_groups()
    except Exception as exc:
        st.error(f"Fehler bei der Datenbank-Initialisierung oder beim Cleanup: {exc}")
        return

    st.title("Name Sync Backend aktiv")
    st.success("Datenbank-Cleanup durchgeführt.")


if __name__ == "__main__":
    main()
