"""
Authentication wrapper using streamlit-authenticator.

Credentials are stored in .streamlit/credentials.yaml (gitignored).
See credentials.example.yaml for the required structure.

Roles:
  admin  — full access including Admin page
  entry  — Data Entry, Records (read-only), Import, Export & Report
"""

from pathlib import Path
import streamlit as st

try:
    import streamlit_authenticator as stauth
    import yaml
    from yaml.loader import SafeLoader
    _AUTH_AVAILABLE = True
except ImportError:
    _AUTH_AVAILABLE = False

_CREDS_PATH = Path(__file__).parent.parent / ".streamlit" / "credentials.yaml"


def _load_config() -> dict | None:
    if not _AUTH_AVAILABLE:
        return None
    if not _CREDS_PATH.exists():
        return None
    with open(_CREDS_PATH) as f:
        return yaml.load(f, Loader=SafeLoader)


def login() -> tuple[bool, str | None, str | None]:
    """
    Render the login widget and return (authenticated, name, username).
    If credentials.yaml is missing, falls back to a dev bypass with role=admin.
    """
    config = _load_config()

    if config is None:
        # No credentials file — allow access in dev mode as admin
        st.warning(
            "No `.streamlit/credentials.yaml` found. Running in **dev mode** "
            "(admin access). Create the credentials file before deploying."
        )
        st.session_state["role"] = "admin"
        st.session_state["username"] = "dev"
        return True, "Developer", "dev"

    authenticator = stauth.Authenticate(
        config["credentials"],
        config["cookie"]["name"],
        config["cookie"]["key"],
        config["cookie"]["expiry_days"],
    )

    name, auth_status, username = authenticator.login("Login", "main")

    if auth_status is False:
        st.error("Incorrect username or password.")
        return False, None, None
    if auth_status is None:
        st.info("Please enter your credentials to continue.")
        return False, None, None

    # Successful login — store role in session state
    role = config["credentials"]["usernames"].get(username, {}).get("role", "entry")
    st.session_state["role"] = role
    st.session_state["username"] = username
    st.session_state["authenticator"] = authenticator

    return True, name, username


def logout():
    authenticator = st.session_state.get("authenticator")
    if authenticator:
        authenticator.logout("Logout", "sidebar")
    else:
        if st.sidebar.button("Logout"):
            for key in ("role", "username", "authenticator"):
                st.session_state.pop(key, None)
            st.rerun()


def require_role(*roles: str) -> bool:
    """
    Return True if the current user has one of the required roles.
    Shows an error and stops the page if not.
    """
    current = st.session_state.get("role", "")
    if current in roles:
        return True
    st.error("You do not have permission to view this page.")
    st.stop()
    return False


def current_username() -> str:
    return st.session_state.get("username", "unknown")


def current_role() -> str:
    return st.session_state.get("role", "")
