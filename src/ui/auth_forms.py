import streamlit as st
import requests
import os

API_URL = os.environ.get("SENTINEL_API_URL", "http://localhost:8000")


def show_login_form():
    st.markdown("## 🔐 Login to ModelSentinel")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button(
            "Login", use_container_width=True, type="primary"
        )
        if submitted:
            if not username or not password:
                st.error("Please enter username and password")
                return
            try:
                r = requests.post(
                    f"{API_URL}/login",
                    json={"username": username, "password": password},
                    timeout=10
                )
                if r.status_code == 200:
                    data = r.json()
                    st.session_state.token = data["access_token"]
                    st.session_state.username = data["username"]
                    st.session_state.role = data["role"]
                    st.session_state.logged_in = True
                    st.rerun()
                else:
                    st.error(r.json().get("detail", "Login failed"))
            except requests.exceptions.ConnectionError:
                st.error("Cannot connect to API")


def show_signup_form():
    st.markdown("## 📝 Create Account")
    with st.form("signup_form"):
        c1, c2 = st.columns(2)
        with c1:
            first_name = st.text_input("First Name")
        with c2:
            last_name = st.text_input("Last Name")
        username = st.text_input("Username")
        email = st.text_input("Email")
        password = st.text_input(
            "Password", type="password",
            help="8+ chars, uppercase, lowercase, number, special character"
        )
        confirm = st.text_input("Confirm Password", type="password")

        # Tier 1 Fix — removed admin role from signup dropdown
        # New users always start as readonly
        # Admin must manually upgrade roles after registration
        st.info(
            "New accounts start as Read-Only. "
            "An admin must upgrade your role after registration."
        )

        submitted = st.form_submit_button(
            "Create Account", use_container_width=True, type="primary"
        )
        if submitted:
            if not all([first_name, last_name, username,
                        email, password, confirm]):
                st.error("Please fill all fields")
                return
            if password != confirm:
                st.error("Passwords do not match")
                return
            try:
                r = requests.post(
                    f"{API_URL}/signup",
                    json={
                        "username": username,
                        "first_name": first_name,
                        "last_name": last_name,
                        "email": email,
                        "password": password,
                        "role": "readonly"
                    },
                    timeout=10
                )
                if r.status_code == 200:
                    st.success("Account created! Please login.")
                    st.session_state.show_signup = False
                    st.rerun()
                else:
                    st.error(r.json().get("detail", "Signup failed"))
            except requests.exceptions.ConnectionError:
                st.error("Cannot connect to API")


def show_auth_page():
    if st.session_state.get("logged_in"):
        return True
    if "show_signup" not in st.session_state:
        st.session_state.show_signup = False
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        if st.session_state.show_signup:
            show_signup_form()
            st.markdown("---")
            if st.button("Already have an account? Login",
                         use_container_width=True):
                st.session_state.show_signup = False
                st.rerun()
        else:
            show_login_form()
            st.markdown("---")
            if st.button("No account? Sign up",
                         use_container_width=True):
                st.session_state.show_signup = True
                st.rerun()
    return False


def logout():
    for key in ["token", "username", "role", "logged_in"]:
        st.session_state.pop(key, None)
    st.rerun()


def get_auth_headers():
    token = st.session_state.get("token", "")
    return {"Authorization": f"Bearer {token}"}