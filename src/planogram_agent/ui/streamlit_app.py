"""Streamlit application for store product finder and route planner."""
from __future__ import annotations

import logging
from collections.abc import MutableMapping
from typing import Any

import streamlit as st

from planogram_agent.autocomplete import suggest
from planogram_agent.basket import (
    EMPTY_BASKET_MESSAGE,
    add_item,
    basket_finder_for,
    clear_basket,
    plan_basket,
    remove_item,
    set_quantity,
)
from planogram_agent.data_loader import Dataset
from planogram_agent.images import product_image
from planogram_agent.interface import answer_question, create_finder, run_query
from planogram_agent.runtime.orchestrator import Orchestrator
from planogram_agent.runtime.state import Answer
from planogram_agent.schemas import NodeType
from planogram_agent.ui.map_plot import (
    clarification_option_label,
    draw_floor,
    floor_change_lines,
    floor_display_order,
    get_floor_stops,
    route_floor_segments,
)

logger = logging.getLogger(__name__)


@st.cache_resource
def get_finder(folder: str) -> Orchestrator:
    """Load dataset and build finder cached by folder path."""
    return create_finder(folder)


def apply_suggestion(state: MutableMapping[str, Any], name: str | None) -> bool:
    """Put a picked suggestion's exact product name in the query box. Returns True if it changed."""
    if not name or state.get("last_suggestion") == name:
        return False
    state["last_suggestion"] = name
    state["query_input"] = name
    return True


def _show_picture(target: Any, finder: Orchestrator, store_folder: str, sku: str) -> None:
    """Draw a product's picture (real file or generated tile) into a column or the sidebar."""
    img = product_image(sku, finder.dataset, store_folder, finder.settings)
    target.image(img.data, width=finder.settings.image_tile_px)


def _add_to_basket(finder: Orchestrator, sku: str, name: str) -> None:
    """Button callback: add one of a product and keep the message for the basket panel."""
    result = add_item(st.session_state.basket, sku, name, finder.settings)
    st.session_state.basket_note = (result.ok, result.message)


def _set_basket_quantity(finder: Orchestrator, sku: str) -> None:
    set_quantity(st.session_state.basket, sku, st.session_state[f"basket_qty_{sku}"], finder.settings)
    st.session_state.basket_note = None


def _remove_from_basket(sku: str) -> None:
    remove_item(st.session_state.basket, sku)
    st.session_state.basket_note = None


def _clear_basket() -> None:
    clear_basket(st.session_state.basket)
    st.session_state.basket_note = None


def _render_basket_panel(finder: Orchestrator, store_folder: str) -> bool:
    """Sidebar basket: quantity and remove per item, clear, plan. Returns True if plan was clicked."""
    settings = finder.settings
    basket = st.session_state.basket
    st.sidebar.header("Basket")
    note = st.session_state.get("basket_note")
    if note:
        ok, message = note
        (st.sidebar.caption if ok else st.sidebar.warning)(message)

    if not basket:
        st.sidebar.caption("Your basket is empty.")
    for sku, entry in basket.items():
        qty_key = f"basket_qty_{sku}"
        st.session_state[qty_key] = entry["qty"]  # an add may have changed it since the widget last ran
        col_pic, col_name = st.sidebar.columns([1, 2])
        _show_picture(col_pic, finder, store_folder, sku)
        col_name.markdown(f"**{entry['name']}**")
        col_qty, col_remove = st.sidebar.columns([2, 1])
        col_qty.number_input(
            "Quantity",
            min_value=settings.basket_min_quantity,
            max_value=settings.basket_max_quantity,
            step=1,
            key=qty_key,
            on_change=_set_basket_quantity,
            args=(finder, sku),
        )
        col_remove.button("Remove", key=f"basket_remove_{sku}", on_click=_remove_from_basket, args=(sku,))

    if basket:
        st.sidebar.button("Clear basket", key="basket_clear", on_click=_clear_basket)
    return st.sidebar.button("Plan route for basket", key="basket_plan", type="primary")


def _render_product_search(finder: Orchestrator, store_folder: str) -> tuple[str, str] | None:
    """Product search with suggestions; returns the picked product as (sku, name), if any.

    Uses the streamlit-searchbox add-on for as-you-type suggestions. If the add-on cannot be
    imported or fails to render, falls back to suggestion buttons shown after pressing Enter,
    each with its own Add to basket button.
    """
    names = {p.sku: p.name for p in finder.dataset.products}

    def search(term: str) -> list[tuple[str, str]]:
        return [(s.label, s.sku) for s in suggest(term, finder.dataset, finder.settings)]

    try:
        from streamlit_searchbox import st_searchbox

        sku = st_searchbox(
            search,
            label="Find a product",
            placeholder="Type a few letters, e.g. bre",
            key="product_searchbox",
        )
        return (sku, names[sku]) if sku in names else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Search box add-on unavailable, using suggestion buttons: %s", exc)

    term = st.text_input(
        "Find a product",
        placeholder="Type a few letters, e.g. bre, then press Enter",
        key="product_search_text",
    )
    picked: tuple[str, str] | None = None
    for s in suggest(term, finder.dataset, finder.settings):
        col_pic, col_pick, col_add = st.columns([1, 5, 1], vertical_alignment="center")
        _show_picture(col_pic, finder, store_folder, s.sku)
        if col_pick.button(s.label, key=f"suggest_{s.sku}", use_container_width=True):
            st.session_state.pop("last_suggestion", None)  # a button click is always a fresh pick
            picked = (s.sku, s.name)
        col_add.button(
            "Add to basket",
            key=f"add_suggest_{s.sku}",
            on_click=_add_to_basket,
            args=(finder, s.sku, s.name),
            use_container_width=True,
        )
    return picked


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
    if "basket" not in st.session_state:
        st.session_state.basket = {}
    if "answer_from_basket" not in st.session_state:
        st.session_state.answer_from_basket = False

    # Sidebar basket panel
    plan_clicked = _render_basket_panel(finder, store_folder)

    # 3. Main Area: product search with suggestions, then example buttons
    picked = _render_product_search(finder, store_folder)
    if picked is not None:
        st.session_state.picked_product = picked
        apply_suggestion(st.session_state, picked[1])
    if st.session_state.get("picked_product"):
        picked_sku, picked_name = st.session_state.picked_product
        col_pic, col_add = st.columns([1, 6], vertical_alignment="center")
        _show_picture(col_pic, finder, store_folder, picked_sku)
        col_add.button(
            f"Add {picked_name} to basket",
            key="add_picked",
            on_click=_add_to_basket,
            args=(finder, picked_sku, picked_name),
        )

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
                st.session_state.answer_from_basket = False
            except Exception as exc:  # noqa: BLE001
                st.error(f"Search could not be completed: {exc}")
    elif plan_clicked:
        try:
            ans = plan_basket(
                finder,
                st.session_state.basket,
                start=override_start,
                floor=override_floor,
                accessible_only=override_accessible,
            )
            if ans is None:
                st.info(EMPTY_BASKET_MESSAGE)
            else:
                st.session_state.session_id = ans.session_id
                st.session_state.answer_from_basket = True
            st.session_state.last_answer = ans
        except Exception as exc:  # noqa: BLE001
            st.error(f"Basket route could not be planned: {exc}")

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
                button_title = clarification_option_label(finder.dataset, opt.sku, opt.name)
                if st.button(button_title, key=f"opt_{q.item_index}_{opt.sku}", use_container_width=True):
                    try:
                        # The pending session lives on the orchestrator that produced the answer
                        asked_by = basket_finder_for(finder) if st.session_state.answer_from_basket else finder
                        resolved = answer_question(
                            asked_by,
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
                    body = st.container()
                    if it.sku:
                        col_pic, body = st.columns([1, 5])
                        _show_picture(col_pic, finder, store_folder, it.sku)
                    with body:
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

                        if it.sku and it.name:
                            st.button(
                                "Add to basket",
                                key=f"add_item_{it.index}_{it.sku}",
                                on_click=_add_to_basket,
                                args=(finder, it.sku, it.name),
                            )

        # Route
        if last_answer.route is not None:
            st.subheader("Route")
            route = last_answer.route
            walk_m = round(route.walking_distance)
            st.write(f"about {walk_m} m of walking, {route.floor_changes} floor change(s)")

            if route.directions_text:
                st.markdown(route.directions_text)

            # One plain line per floor change, under the route
            for line in floor_change_lines(last_answer):
                st.markdown(line)

            # Every floor map stays visible, the floor of the first stop first
            segments = route_floor_segments(finder.dataset, last_answer)
            for fl in floor_display_order(finder.dataset, last_answer):
                st.markdown(f"#### Level {fl}")
                fig = draw_floor(finder.dataset, last_answer, fl)
                st.pyplot(fig)
                fl_stops = get_floor_stops(last_answer, fl)
                if fl_stops:
                    stops_list = [f"{s_num}. {name} ({loc_str})" for s_num, sku, name, loc_str in fl_stops]
                    st.caption(f"Stops on Level {fl}: {', '.join(stops_list)}")
                elif segments.get(fl):
                    st.caption(f"No stops on Level {fl}; the route passes through this floor")
                else:
                    st.caption(f"No route on Level {fl}")

        # Details trace
        if show_details and last_answer.trace:
            with st.expander("Execution Details", expanded=False):
                for ev in last_answer.trace:
                    ok_str = "OK" if ev.ok else "Failed"
                    note_str = f" - {ev.note}" if ev.note else ""
                    st.text(f"[{ev.stage}] {ok_str} ({ev.ms:.1f} ms){note_str}")


if __name__ == "__main__":
    main()
