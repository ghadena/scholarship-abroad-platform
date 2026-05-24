"""Import page — data entry via the form or scripts/bulk_import.py for bulk loads."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st

from app.auth import login, logout, require_role

st.set_page_config(page_title="Import", page_icon="📥", layout="wide")
authenticated, name, _ = login()
if not authenticated:
    st.stop()
logout()
require_role("admin", "entry")

st.title("Import Data")
st.info(
    "To import students in bulk, use the **Data Entry** page to add records individually, "
    "or run `scripts/bulk_import.py` from the command line for large batch imports.\n\n"
    "```\nDATABASE_URL=\"postgresql://...\" python3 scripts/bulk_import.py /path/to/file.xlsx\n```"
)
