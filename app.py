"""Streamlit entry point — Overview page. See SPEC.md Section 7.7."""
from pathlib import Path

import streamlit as st

DB_PATH = Path(__file__).parent / "data" / "kfc.duckdb"


def main() -> None:
    st.set_page_config(page_title="KFC Ontology", layout="wide")
    st.title("KFC Ontology — Overview")

    if not DB_PATH.exists():
        st.error(
            "Database not found. Run `python data/load.py` to bootstrap "
            "the DuckDB before launching the app."
        )
        st.stop()

    st.info("Phase 1 not yet built. This page is a scaffold.")


if __name__ == "__main__":
    main()
