"""Streamlit main application for Name Sync.

Implements Sprints 2-5:
  - Routing via URL query parameters (`st.query_params`)
  - Home Page for creating groups
  - Participant Interface with 32-member limit & onboarding
  - Name submission with title-case normalization
  - Admin Dashboard with top names ranking & pairwise user matches
"""

import uuid
import pandas as pd
import streamlit as st
import database

MAX_GROUP_MEMBERS: int = 32


def init_session() -> None:
    """Initializes default Streamlit session state keys."""
    if "group_id" not in st.session_state:
        st.session_state.group_id = None
    if "user_id" not in st.session_state:
        st.session_state.user_id = None
    if "is_admin" not in st.session_state:
        st.session_state.is_admin = False


def clear_session_and_url() -> None:
    """Resets session state and query parameters to navigate back home."""
    st.session_state.group_id = None
    st.session_state.user_id = None
    st.session_state.is_admin = False
    st.query_params.clear()
    st.rerun()


def render_home_page() -> None:
    """Renders the inviting home page when no group parameter is present."""
    st.title("Name Sync")
    st.subheader("Gemeinsam die besten Namen finden")

    st.write(
        "Willkommen bei **Name Sync**! Erstelle eine Gruppe, teile den Einladungslink mit "
        "Freunden oder der Familie und sammelt gemeinsam Namensvorschläge. "
        "Seht direkt, welche Namen am beliebtesten sind und wo ihr euch einig seid!"
    )

    st.divider()

    if st.button("Neue Namens-Gruppe erstellen", type="primary", use_container_width=True):
        new_group_id = str(uuid.uuid4())
        try:
            database.create_group(new_group_id)
            st.session_state.is_admin = True
            st.session_state.group_id = new_group_id
            st.query_params["group_id"] = new_group_id
            st.rerun()
        except Exception as exc:
            st.error(f"Fehler beim Erstellen der Gruppe: {exc}")


def render_participant_interface(group_id: str) -> None:
    """Renders participant UI, onboarding, name entry, and admin dashboard."""
    # 1. Check if group exists
    if not database.group_exists(group_id):
        st.error("Diese Gruppe existiert nicht oder wurde nach 7 Tagen inaktivität gelöscht.")
        if st.button("Zurück zur Startseite"):
            clear_session_and_url()
        return

    # 2. Check current session user consistency
    current_user_id = st.session_state.get("user_id")
    current_user = None
    if current_user_id is not None:
        current_user = database.get_user(current_user_id)
        if current_user is None or current_user["group_id"] != group_id:
            st.session_state.user_id = None
            current_user = None

    # Sync is_admin from user record if user exists
    if current_user:
        st.session_state.is_admin = current_user["is_admin"]

    # 3. Check group member limit for new users
    user_count = database.get_user_count(group_id)
    if current_user is None and user_count >= MAX_GROUP_MEMBERS:
        st.error(f"Diese Gruppe ist bereits voll (Maximal {MAX_GROUP_MEMBERS} Personen).")
        if st.button("Zur Startseite"):
            clear_session_and_url()
        return

    st.title("Name Sync")

    # Display Share Link Header
    with st.expander("🔗 Einladungslink für diese Gruppe", expanded=False):
        st.info("Teile diese URL mit anderen Teilnehmern:")
        st.code(st.query_params.to_dict().get("group_id", group_id), language="text")

    st.divider()

    # 4. Onboarding Flow if user has no user_id in session
    if st.session_state.get("user_id") is None:
        st.subheader("Willkommen in der Gruppe!")
        with st.form("onboarding_form"):
            display_name_input = st.text_input(
                "Wie lautet dein Name?",
                placeholder="z.B. Anna",
                help="Gib deinen Namen ein, um der Gruppe beizutreten."
            )
            submitted = st.form_submit_button("Gruppe beitreten", type="primary")

            if submitted:
                cleaned_name = display_name_input.strip()
                if not cleaned_name:
                    st.warning("Bitte gib einen gültigen Namen ein.")
                else:
                    try:
                        new_user_id = database.create_user(
                            group_id=group_id,
                            display_name=cleaned_name,
                            is_admin=st.session_state.get("is_admin", False)
                        )
                        st.session_state.user_id = new_user_id
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Fehler beim Beitreten: {exc}")
        return

    # User is onboarded
    user_id = st.session_state.user_id
    user_info = database.get_user(user_id)
    user_display_name = user_info["display_name"] if user_info else "Teilnehmer"

    st.subheader(f"Hallo, {user_display_name}! 👋")

    # Name submission form
    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("### 💡 Namensvorschlag einreichen")
        with st.form("add_name_form", clear_on_submit=True):
            name_input = st.text_input(
                "Namensvorschlag:",
                placeholder="z.B. Anna Maria",
                help="Namen werden automatisch formatiert (z.B. 'anna' -> 'Anna')."
            )
            submit_name = st.form_submit_button("Name hinzufügen", type="primary")

            if submit_name:
                normalized_input = name_input.strip()
                if not normalized_input:
                    st.warning("Bitte gib einen Namen ein.")
                else:
                    added_id = database.add_name_suggestion(user_id, normalized_input)
                    if added_id:
                        st.success(f"'{normalized_input.title()}' wurde hinzugefügt!")
                        st.rerun()
                    else:
                        st.warning("Ungültiger Name.")

    with col2:
        st.markdown("### 📋 Deine eingereichten Namen")
        my_names = database.get_user_names(user_id)
        if my_names:
            for idx, n in enumerate(my_names, 1):
                st.write(f"{idx}. **{n}**")
        else:
            st.info("Du hast noch keine Namen eingereicht.")

    st.divider()

    # 5. Admin Dashboard
    if st.session_state.get("is_admin", False):
        render_admin_dashboard(group_id)


def render_admin_dashboard(group_id: str) -> None:
    """Renders admin analytics: ranking and user overlaps."""
    st.subheader("👑 Admin Dashboard")

    tab1, tab2 = st.tabs(["🏆 Beliebteste Namen", "🤝 Namens-Überschneidungen"])

    with tab1:
        ranking = database.get_group_name_ranking(group_id)
        if not ranking:
            st.info("Noch keine Namensvorschläge in dieser Gruppe eingereicht.")
        else:
            df = pd.DataFrame(ranking, columns=["Name", "Stimmen"])

            c1, c2 = st.columns([2, 1])
            with c1:
                st.bar_chart(df.set_index("Name"))
            with c2:
                st.dataframe(df, use_container_width=True, hide_index=True)

    with tab2:
        matches = database.get_group_user_matches(group_id)
        if not matches:
            st.info(
                "Noch keine Namens-Überschneidungen vorhanden. "
                "Sobald mindestens 2 Personen dieselben Namen vorschlagen, werden sie hier angezeigt!"
            )
        else:
            for user1, user2, shared_count, shared_names in matches:
                names_str = ", ".join(shared_names)
                st.markdown(
                    f"⭐ **{user1} & {user2}**: **{shared_count}** gemeinsame(r) Name(n)  \n"
                    f"*Gemeinsam:* {names_str}"
                )
                st.divider()


def main() -> None:
    """Main Streamlit application entry point."""
    init_session()

    # Automatic database initialization & cleanup on app load
    try:
        database.init_db()
        database.cleanup_old_groups()
    except Exception as exc:
        st.error(f"Fehler bei Datenbank-Initialisierung: {exc}")
        return

    # Check URL parameter
    query_params = st.query_params
    url_group_id = query_params.get("group_id", None)

    if url_group_id:
        st.session_state.group_id = url_group_id
        render_participant_interface(url_group_id)
    else:
        st.session_state.group_id = None
        render_home_page()


if __name__ == "__main__":
    main()
