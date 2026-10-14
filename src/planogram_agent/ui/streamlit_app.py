"""Streamlit application for store product finder and route planner."""
from __future__ import annotations

import streamlit as st

from planogram_agent.data_loader import Dataset
from planogram_agent.interface import answer_question, create_finder, run_query
from planogram_agent.runtime.orchestrator import Orchestrator
from planogram_agent.runtime.state import Answer
from planogram_agent.schemas import NodeType
from planogram_agent.ui.map_plot import draw_floor, get_floor_stops


@st.cache_resource
def get_finder(folder: str) -> Orchestrator:
    """Load dataset and build finder cached by folder path."""
    return create_finder(folder)


def _build_start_options(dataset: Dataset) -> list[tuple[str, str | None, int | None]]:
    """Build selectbox options for starting points.

    Returns list of (display_label, start_arg, floor_arg).
    First option is the default: ('Use my message, or the entrance', None, None).
    """
    options: list[tuple[str, str | None, int | None]] = [
        ("Use my message, or the entrance", None, None)
    ]

    named_nodes = [n for n in dataset.graph.nodes if n.type != NodeType.JUNCTION]
    label_counts: dict[str, int] = {}
    for n in named_nodes:
        label_counts[n.label] = label_counts.get(n.label, 0) + 1

    added_entries: list[tuple[str, str, int]] = []
    for n in named_nodes:
        if label_counts[n.label] > 1:
            disp = f"{n.label} (Level {n.floor})"
            added_entries.append((disp, n.label, n.floor))
        else:
            disp = n.label
            added_entries.append((disp, n.label, n.floor))

    # Sort alphabetically with Entrance prioritized
    added_entries.sort(key=lambda x: (0 if "Entrance" in x[0] else 1, x[0]))
    for disp, lbl, fl in added_entries:
        options.append((disp, lbl, fl))

    return options


def main() -> None:
    st.set_page_config(page_title="Store Product Finder", layout="wide")
    st.title("Store Product Finder")

    # 1. Sidebar
    st.sidebar.header("Settings")
    store_folder = st.sidebar.text_input("Store folder", value="data/store_demo")

    try:
        finder = get_finder(store_folder)
    except Exception as exc:  # noqa: BLE001
        st.sidebar.error(f"Failed to load store: {exc}")
        st.error(f"Could not load store data from '{store_folder}'. Please check folder path.")
        return

    # Start point selector
    start_options = _build_start_options(finder.dataset)
    options_map = {opt[0]: (opt[1], opt[2]) for opt in start_options}
    selected_label = st.sidebar.selectbox("Start point", list(options_map.keys()))
    override_start, override_floor = options_map[selected_label]

    # Step-free toggle
    step_free = st.sidebar.toggle("Step-free route (accessible only)", value=False)
    override_accessible: bool | None = True if step_free else None

    # AI model indicator line
    st.sidebar.text(finder.model_label)

    # Show details checkbox
    show_details = st.sidebar.checkbox("Show details", value=False)

    # 2. Session state tracking
    if "last_answer" not in st.session_state:
        st.session_state.last_answer = None
    if "session_id" not in st.session_state:
        st.session_state.session_id = None
    if "query_input" not in st.session_state:
        st.session_state.query_input = ""

    # 3. Main Area: Example buttons
    st.write("Ask for any product, brand or item in the supermarket:")
    col_ex1, col_ex2, col_ex3 = st.columns(3)
    clicked_example: str | None = None

    with col_ex1:
        if st.button("Example: Multi-product", use_container_width=True):
            clicked_example = "Store Brand Shredded Cheddar 400 g and Daily Bake White Sandwich Bread 400 g"
    with col_ex2:
        if st.button("Example: Milk", use_container_width=True):
            clicked_example = "milk"
    with col_ex3:
        if st.button("Example: Out-of-stock", use_container_width=True):
            clicked_example = "ArtBox Watercolour Paints 12 pack"

    if clicked_example is not None:
        st.session_state.query_input = clicked_example

    # Query text area and Find button
    query_text = st.text_area(
        "Search query",
        value=st.session_state.query_input,
        placeholder="e.g. Daily Bake Plain Bagels 4 pack",
        label_visibility="collapsed",
    )
    find_button = st.button("Find", type="primary")

    query_to_execute: str | None = None
    if clicked_example is not None:
        query_to_execute = clicked_example
    elif find_button:
        query_to_execute = query_text

    # Run query
    if query_to_execute is not None:
        stripped_query = query_to_execute.strip()
        if not stripped_query:
            st.info("Please enter a product name or item to search.")
            st.session_state.last_answer = None
        else:
            try:
                ans = run_query(
                    finder,
                    stripped_query,
                    start=override_start,
                    floor=override_floor,
                    accessible_only=override_accessible,
                )
                st.session_state.last_answer = ans
                st.session_state.session_id = ans.session_id
            except Exception as exc:  # noqa: BLE001
                st.error(f"Search could not be completed: {exc}")

    last_answer: Answer | None = st.session_state.last_answer

    if last_answer is not None:
        st.divider()

        # Messages
        for msg in last_answer.messages:
            st.info(msg)

        if last_answer.status == "partial":
            st.warning("Some items could not be found, are out of stock, or could not be placed.")
        elif last_answer.status == "error":
            st.error("Could not find the requested items.")

        # Clarification question
        if last_answer.status == "needs_clarification" and last_answer.question:
            q = last_answer.question
            st.subheader(f"Clarification needed for '{q.item_text}'")
            st.write("Which product did you mean?")
            for opt in q.options:
                button_title = f"{opt.name} ({opt.sku})"
                if st.button(button_title, key=f"opt_{q.item_index}_{opt.sku}", use_container_width=True):
                    try:
                        resolved = answer_question(
                            finder,
                            session_id=st.session_state.session_id or "",
                            item_index=q.item_index,
                            sku=opt.sku,
                        )
                        st.session_state.last_answer = resolved
                        st.rerun()
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Error selecting option: {exc}")

        # Item cards
        if last_answer.items:
            st.subheader("Items")
            status_labels = {
                "available": "Available",
                "unavailable": "Out of stock",
                "not_found": "Not found in catalogue",
                "not_placed": "Not placed on shelves",
                "needs_choice": "Needs choice",
                "error": "Error",
            }
            for it in last_answer.items:
                with st.container(border=True):
                    display_name = it.name or it.requested
                    st.markdown(f"**{display_name}**")
                    stat_text = status_labels.get(it.status, it.status)
                    qty_text = f" | Quantity: {it.quantity}" if it.status == "available" else ""
                    st.write(f"Status: {stat_text}{qty_text}")

                    if it.chosen_location:
                        loc = it.chosen_location
                        st.write(f"Location: Level {loc.floor}, {loc.zone}, Bay {loc.bay}, Shelf {loc.shelf_level}")
                    elif it.locations:
                        loc = it.locations[0]
                        st.write(f"Location: Level {loc.floor}, {loc.zone}, Bay {loc.bay}, Shelf {loc.shelf_level}")
                    else:
                        st.write("Location: No shelf location")

                    if it.reason:
                        st.caption(it.reason)

        # Route
        if last_answer.route is not None:
            st.subheader("Route")
            route = last_answer.route
            walk_m = round(route.walking_distance)
            st.write(f"about {walk_m} m of walking, {route.floor_changes} floor change(s)")

            if route.directions_text:
                st.markdown(route.directions_text)

            # Map tabs
            floors = sorted(finder.dataset.graph.floors)
            tabs = st.tabs([f"Level {fl}" for fl in floors])
            for tab, fl in zip(tabs, floors):
                with tab:
                    fig = draw_floor(finder.dataset, last_answer, fl)
                    st.pyplot(fig)
                    # Caption under each floor's map
                    fl_stops = get_floor_stops(last_answer, fl)
                    if fl_stops:
                        stops_list = [f"{s_num}. {name} ({loc_str})" for s_num, sku, name, loc_str in fl_stops]
                        st.caption(f"Stops on Level {fl}: {', '.join(stops_list)}")
                    else:
                        st.caption(f"No stops on Level {fl}")

        # Details trace
        if show_details and last_answer.trace:
            with st.expander("Execution Details", expanded=False):
                for ev in last_answer.trace:
                    ok_str = "OK" if ev.ok else "Failed"
                    note_str = f" - {ev.note}" if ev.note else ""
                    st.text(f"[{ev.stage}] {ok_str} ({ev.ms:.1f} ms){note_str}")


if __name__ == "__main__":
    main()
