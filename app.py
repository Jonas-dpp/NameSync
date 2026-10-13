"""Streamlit main application for Name Sync.

Features:
  - Routing via URL query parameters (`st.query_params`)
  - Home Page with cryptographically secure long random URLs
  - Participant interface with onboarding & max member checks
  - Optional Gender Lists (Male/Jungen - Blue, Female/Mädchen - Pink) configurable in Admin panel
  - Visual differentiation for male/female name entry forms
  - Transparency dashboard showing which members have/haven't submitted top names
  - Group deletion functionality (deletes group DB file, invalidates link)
  - Automatic 7-day cleanup of expired group databases
"""

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
    st.title("Name Sync 🤝✨")
    st.subheader("Gemeinsam die besten Namen finden")

    st.write(
        "Willkommen bei **Name Sync**! Erstelle eine Gruppe, teile den Einladungslink mit "
        "Freunden oder der Familie und sammelt gemeinsam Namensvorschläge. "
        "Seht direkt, welche Namen am beliebtesten sind und wo ihr euch einig seid!"
    )

    st.divider()

    if st.button("Neue Namens-Gruppe erstellen", type="primary", use_container_width=True):
        new_group_id = database.generate_group_id()
        try:
            database.create_group(new_group_id)
            st.session_state.is_admin = True
            st.session_state.group_id = new_group_id
            st.session_state.user_id = None
            st.query_params["group_id"] = new_group_id
            st.rerun()
        except Exception as exc:
            st.error(f"Fehler beim Erstellen der Gruppe: {exc}")


def render_participant_interface(group_id: str) -> None:
    """Renders participant UI, onboarding, name entry, and admin dashboard."""
    # 1. Check if group exists (separately managed DB)
    if not database.group_exists(group_id):
        st.error(
            "Diese Gruppe existiert nicht mehr. Der Link ist ungültig oder "
            "die Gruppe wurde vom Admin oder nach 7 Tagen inaktivität gelöscht."
        )
        if st.button("Zurück zur Startseite", type="primary"):
            clear_session_and_url()
        return

    # 2. Check current session user consistency
    current_user_id = st.session_state.get("user_id")
    current_user = None
    if current_user_id is not None:
        current_user = database.get_user(group_id, current_user_id)
        if current_user is None:
            st.session_state.user_id = None

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

    st.title("Name Sync 🤝✨")

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
    user_info = database.get_user(group_id, user_id)
    user_display_name = user_info["display_name"] if user_info else "Teilnehmer"

    st.subheader(f"Hallo, {user_display_name}! 👋")

    # Check if gender lists feature is enabled by admin
    gender_lists_enabled = database.get_gender_lists_enabled(group_id)

    if gender_lists_enabled:
        render_gender_differentiable_entry_form(group_id, user_id)
    else:
        render_standard_entry_form(group_id, user_id)

    st.divider()

    # 5. Admin Dashboard
    if st.session_state.get("is_admin", False):
        render_admin_dashboard(group_id)


def render_standard_entry_form(group_id: str, user_id: int) -> None:
    """Renders single neutral name entry form when gender option is disabled."""
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
                    added_id = database.add_name_suggestion(group_id, user_id, normalized_input, gender="neutral")
                    if added_id:
                        st.success(f"'{normalized_input.title()}' wurde hinzugefügt!")
                        st.rerun()
                    else:
                        st.warning("Ungültiger Name.")

    with col2:
        st.markdown("### 📋 Deine eingereichten Namen")
        my_names = database.get_user_names(group_id, user_id)
        if my_names:
            for idx, n in enumerate(my_names, 1):
                st.write(f"{idx}. **{n}**")
        else:
            st.info("Du hast noch keine Namen eingereicht.")


def render_gender_differentiable_entry_form(group_id: str, user_id: int) -> None:
    """Renders easily differentiable male (blue) and female (pink) submission forms."""
    st.markdown("### 💡 Namensvorschläge nach Geschlecht")
    st.write("Wähle eine Kategorie aus, um Namensvorschläge hinzuzufügen:")

    col_male, col_female = st.columns(2)

    # Male Section - Styled with Blue theme
    with col_male:
        st.markdown(
            """
            <div style="
                background-color: #EBF3FA;
                border-left: 6px solid #2B6CB0;
                border-radius: 8px;
                padding: 16px;
                margin-bottom: 12px;
            ">
                <h3 style="color: #2B6CB0; margin-top: 0;">💙 Jungen / Männlich</h3>
                <p style="color: #2D3748; font-size: 0.9em;">Namensliste für Jungen</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("add_male_name_form", clear_on_submit=True):
            male_name_input = st.text_input(
                "Jungennamen eingeben:",
                placeholder="z.B. Liam",
                key="input_male_name"
            )
            submit_male = st.form_submit_button("💙 Jungennamen hinzufügen", type="primary")

            if submit_male:
                normalized = male_name_input.strip()
                if not normalized:
                    st.warning("Bitte einen Namen eingeben.")
                else:
                    database.add_name_suggestion(group_id, user_id, normalized, gender="male")
                    st.success(f"'{normalized.title()}' wurde zu den Jungennamen hinzugefügt!")
                    st.rerun()

        st.markdown("#### 💙 Deine Jungennamen")
        male_names = database.get_user_names(group_id, user_id, gender="male")
        if male_names:
            for idx, n in enumerate(male_names, 1):
                st.markdown(f"{idx}. **{n}**")
        else:
            st.caption("Noch keine Jungennamen eingereicht.")

    # Female Section - Styled with Pink theme
    with col_female:
        st.markdown(
            """
            <div style="
                background-color: #FDF0F5;
                border-left: 6px solid #D53F8C;
                border-radius: 8px;
                padding: 16px;
                margin-bottom: 12px;
            ">
                <h3 style="color: #D53F8C; margin-top: 0;">💗 Mädchen / Weiblich</h3>
                <p style="color: #2D3748; font-size: 0.9em;">Namensliste für Mädchen</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("add_female_name_form", clear_on_submit=True):
            female_name_input = st.text_input(
                "Mädchennamen eingeben:",
                placeholder="z.B. Emma",
                key="input_female_name"
            )
            submit_female = st.form_submit_button("💗 Mädchennamen hinzufügen", type="primary")

            if submit_female:
                normalized = female_name_input.strip()
                if not normalized:
                    st.warning("Bitte einen Namen eingeben.")
                else:
                    database.add_name_suggestion(group_id, user_id, normalized, gender="female")
                    st.success(f"'{normalized.title()}' wurde zu den Mädchennamen hinzugefügt!")
                    st.rerun()

        st.markdown("#### 💗 Deine Mädchennamen")
        female_names = database.get_user_names(group_id, user_id, gender="female")
        if female_names:
            for idx, n in enumerate(female_names, 1):
                st.markdown(f"{idx}. **{n}**")
        else:
            st.caption("Noch keine Mädchennamen eingereicht.")


def render_admin_dashboard(group_id: str) -> None:
    """Renders admin controls, rankings, matches, transparency status, and group deletion."""
    st.subheader("👑 Admin Dashboard")

    gender_lists_enabled = database.get_gender_lists_enabled(group_id)

    # Admin Settings Expander
    with st.expander("⚙️ Gruppen-Einstellungen & Verwaltung", expanded=True):
        col_set1, col_set2 = st.columns([2, 1])

        with col_set1:
            st.markdown("#### Getrennte Geschlechterlisten (💙 Jungen / 💗 Mädchen)")
            st.write(
                "Aktiviere diese Option, um zwei getrennte Namenslisten (männlich & weiblich) anzuzeigen."
            )
            new_gender_state = st.toggle(
                "Zwei Namenslisten nach Geschlecht aktivieren",
                value=gender_lists_enabled,
                key="toggle_gender_lists"
            )
            if new_gender_state != gender_lists_enabled:
                database.set_gender_lists_enabled(group_id, new_gender_state)
                st.success("Einstellung für Geschlechterlisten aktualisiert!")
                st.rerun()

        with col_set2:
            st.markdown("#### 🗑️ Gruppe löschen")
            st.write("Löscht die gesamte Gruppe und deren Datenbank unwiderruflich.")

            if st.button("🚨 Gruppe jetzt löschen", type="secondary", use_container_width=True):
                st.session_state["show_delete_confirm"] = True

            if st.session_state.get("show_delete_confirm", False):
                st.warning("Möchtest du diese Gruppe wirklich löschen?")
                c_del1, c_del2 = st.columns(2)
                with c_del1:
                    if st.button("Ja, endgültig löschen", type="primary", use_container_width=True):
                        database.delete_group(group_id)
                        st.session_state["show_delete_confirm"] = False
                        st.success("Gruppe wurde gelöscht.")
                        clear_session_and_url()
                with c_del2:
                    if st.button("Abbrechen", use_container_width=True):
                        st.session_state["show_delete_confirm"] = False
                        st.rerun()

    st.divider()

    # Dashboard Tabs
    tabs = st.tabs(["🏆 Beliebteste Namen", "🤝 Namens-Überschneidungen", "🔍 Transparenz-Übersicht"])

    # TAB 1: Ranking
    with tabs[0]:
        if gender_lists_enabled:
            c_m, c_f = st.columns(2)

            with c_m:
                st.markdown("#### 💙 Beliebteste Jungennamen")
                m_ranking = database.get_group_name_ranking(group_id, gender="male")
                if not m_ranking:
                    st.info("Noch keine Jungennamen vorschlagen.")
                else:
                    df_m = pd.DataFrame(m_ranking, columns=["Name", "Stimmen"])
                    st.dataframe(df_m, use_container_width=True, hide_index=True)

            with c_f:
                st.markdown("#### 💗 Beliebteste Mädchennamen")
                f_ranking = database.get_group_name_ranking(group_id, gender="female")
                if not f_ranking:
                    st.info("Noch keine Mädchennamen vorschlagen.")
                else:
                    df_f = pd.DataFrame(f_ranking, columns=["Name", "Stimmen"])
                    st.dataframe(df_f, use_container_width=True, hide_index=True)
        else:
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

    # TAB 2: Pairwise Matches
    with tabs[1]:
        if gender_lists_enabled:
            st.markdown("#### 💙 Überschneidungen Jungennamen")
            m_matches = database.get_group_user_matches(group_id, gender="male")
            if not m_matches:
                st.info("Keine Überschneidungen bei Jungennamen.")
            else:
                for u1, u2, count, shared in m_matches:
                    st.write(f"⭐ **{u1} & {u2}**: {count} gemeinsame(r) Jungenname(n) ({', '.join(shared)})")

            st.divider()

            st.markdown("#### 💗 Überschneidungen Mädchennamen")
            f_matches = database.get_group_user_matches(group_id, gender="female")
            if not f_matches:
                st.info("Keine Überschneidungen bei Mädchennamen.")
            else:
                for u1, u2, count, shared in f_matches:
                    st.write(f"⭐ **{u1} & {u2}**: {count} gemeinsame(r) Mädchenname(n) ({', '.join(shared)})")
        else:
            matches = database.get_group_user_matches(group_id)
            if not matches:
                st.info("Noch keine Namens-Überschneidungen vorhanden.")
            else:
                for user1, user2, shared_count, shared_names in matches:
                    names_str = ", ".join(shared_names)
                    st.markdown(
                        f"⭐ **{user1} & {user2}**: **{shared_count}** gemeinsame(r) Name(n)  \n"
                        f"*Gemeinsam:* {names_str}"
                    )
                    st.divider()

    # TAB 3: Transparency Overview
    with tabs[2]:
        st.markdown("### 🔍 Transparenz: Wer hat bereits Favoriten eingereicht?")
        st.write("Aus Transparenzgründen kann der Admin hier einsehen, welche Mitglieder bereits Vorschläge abgegeben haben.")

        if gender_lists_enabled:
            c_trans_m, c_trans_f = st.columns(2)

            with c_trans_m:
                st.markdown("#### 💙 Abgabe-Status Jungennamen")
                statuses_m = database.get_user_submission_statuses(group_id, gender="male")
                for s in statuses_m:
                    admin_tag = " (Admin)" if s["is_admin"] else ""
                    if s["has_submitted"]:
                        st.success(f"✅ **{s['display_name']}**{admin_tag}: {s['submitted_count']} Name(n)")
                    else:
                        st.warning(f"❌ **{s['display_name']}**{admin_tag}: Noch keine Jungennamen eingereicht")

            with c_trans_f:
                st.markdown("#### 💗 Abgabe-Status Mädchennamen")
                statuses_f = database.get_user_submission_statuses(group_id, gender="female")
                for s in statuses_f:
                    admin_tag = " (Admin)" if s["is_admin"] else ""
                    if s["has_submitted"]:
                        st.success(f"✅ **{s['display_name']}**{admin_tag}: {s['submitted_count']} Name(n)")
                    else:
                        st.warning(f"❌ **{s['display_name']}**{admin_tag}: Noch keine Mädchennamen eingereicht")
        else:
            statuses = database.get_user_submission_statuses(group_id)
            for s in statuses:
                admin_tag = " (Admin)" if s["is_admin"] else ""
                if s["has_submitted"]:
                    st.success(f"✅ **{s['display_name']}**{admin_tag}: Hat {s['submitted_count']} Vorschlag/Vorschläge eingereicht")
                else:
                    st.warning(f"❌ **{s['display_name']}**{admin_tag}: Hat noch keine Vorschläge eingereicht")


def main() -> None:
    """Main Streamlit application entry point."""
    init_session()

    # Automatic database directory check & 7-day cleanup on app load
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
