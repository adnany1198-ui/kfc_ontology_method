"""Compose page — build user-constructed entities. See SPEC §7.5."""
from __future__ import annotations

import streamlit as st

from backend import api
from components import provenance_badge, time_cursor_widget
from derived import REGISTRY, user_entities


def main() -> None:
    st.set_page_config(page_title="Compose", layout="wide")
    cur = time_cursor_widget.render()

    st.title("Compose — user-constructed entities")
    provenance_badge.render("derived",
                            "target-scoped composition over built-in entities")

    left, right = st.columns([1, 1])

    with left:
        st.markdown("### Build")
        _builder_form(cur)

    with right:
        st.markdown("### Existing user entities")
        _existing_list(cur)


def _builder_form(cur) -> None:
    name = st.text_input("Name", value="")
    op = st.selectbox(
        "Operation",
        ["weighted_sum", "threshold", "rolling_average", "trend_direction"],
    )

    # System-wide entities (CCC) not selectable for user composition per
    # CLAUDE.md §5; only target-scoped entities (OTS, SOY, DPI) are.
    selectable = [k for k in ("ots", "soy", "dpi") if k in REGISTRY]

    inputs = []
    params = {}
    if op == "weighted_sum":
        n = st.number_input("How many inputs?", 1, len(selectable), 2)
        for i in range(int(n)):
            c1, c2 = st.columns([2, 1])
            with c1:
                et = st.selectbox(f"Input {i+1}", selectable,
                                   key=f"compose_et_{i}",
                                   index=min(i, len(selectable)-1))
            with c2:
                w = st.number_input(f"weight {i+1}", value=0.5,
                                     min_value=-2.0, max_value=2.0, step=0.05,
                                     key=f"compose_w_{i}")
            inputs.append({"entity_type": et, "weight": float(w)})
    elif op == "threshold":
        et = st.selectbox("Input", selectable)
        thr = st.slider("threshold", 0.0, 1.0, 0.78, 0.01)
        inputs.append({"entity_type": et, "weight": 1.0})
        params["threshold"] = float(thr)
    else:
        et = st.selectbox("Input", selectable)
        win = st.slider("window_days", 7, 180, 30, 1)
        inputs.append({"entity_type": et, "weight": 1.0})
        params["window_days"] = int(win)

    composition_spec = {"operation": op, "inputs": inputs, "params": params}

    st.markdown("**Composition spec**")
    st.json(composition_spec)

    # Preview against a sample supplier.
    preview_target = st.selectbox(
        "Preview against target",
        REGISTRY[selectable[0]].list_targets(),
        index=0,
    )
    if st.button("Preview compute", key="preview_btn"):
        try:
            uid = user_entities.create("__preview__", composition_spec)
            try:
                result = user_entities.compute(uid, preview_target, cur)
                st.markdown("**Preview result**")
                st.json({"value": result.value, "components": result.components})
            finally:
                user_entities.delete(uid)
        except Exception as e:
            st.error(f"Preview failed: {e}")

    if st.button("Save", type="primary",
                 disabled=not name.strip(), key="save_btn"):
        try:
            uid = user_entities.create(name.strip(), composition_spec)
            st.success(f"Saved as user:{uid}")
            st.info("This entity now appears in the credit-product score-input "
                    "dropdown.")
        except Exception as e:
            st.error(f"Save failed: {e}")


def _existing_list(cur) -> None:
    items = api.list_user_entities()
    if not items:
        st.info("No user entities yet.")
        return
    for item in items:
        with st.expander(f"**{item['name']}** "
                          f"(user:{item['user_entity_id'][:8]}…)"):
            st.json(item["composition_spec"])
            if st.button("Delete", key=f"del_{item['user_entity_id']}"):
                user_entities.delete(item["user_entity_id"])
                st.rerun()


if __name__ == "__main__":
    main()
