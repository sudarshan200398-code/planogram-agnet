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
from planogram_agent.llm.no_model import NoModelClient
from planogram_agent.runtime.orchestrator import Orchestrator
from planogram_agent.runtime.state import Answer, ItemResult
from planogram_agent.schemas import NodeType
from planogram_agent.ui.map_plot import (
    clarification_option_label,
    draw_floor,
    floor_change_lines,
    floor_display_order,
    get_floor_stops,
    route_floor_segments,
)
from planogram_agent.ui.present import card_lines, search_options, status_badge, step_rows
from planogram_agent.ui.style import CSS

logger = logging.getLogger(__name__)

SEARCH_KEY = "product_searchbox"
SEARCH_PLACEHOLDER = "Type a product or a list, for example: milk, bread, rice cooker"
SEARCH_HINT = 'Pick a product to see it, or choose Search for "…" (or press Enter) to search everything you typed.'


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


def _badge(colour: str, text: str) -> str:
    return f":{colour}-badge[{text}]"


def _show_picture(target: Any, finder: Orchestrator, store_folder: str, sku: str) -> None:
    """Draw a product's picture (real file or generated tile) into a column or container."""
    img = product_image(sku, finder.dataset, store_folder, finder.settings)
    target.image(img.data, width=finder.settings.image_tile_px)


def _add_to_basket(finder: Orchestrator, sku: str, name: str) -> None:
    """Button callback: add one of a product and keep a short confirmation for the basket panel."""
    before = st.session_state.basket.get(sku, {}).get("qty", 0)
    result = add_item(st.session_state.basket, sku, name, finder.settings)
    after = st.session_state.basket.get(sku, {}).get("qty", 0)
    st.session_state.basket_note = (True, f"Added: {name}") if after > before else (result.ok, result.message)


def _set_basket_quantity(finder: Orchestrator, sku: str) -> None:
    set_quantity(st.session_state.basket, sku, st.session_state[f"basket_qty_{sku}"], finder.settings)
    st.session_state.basket_note = None


def _remove_from_basket(sku: str) -> None:
    remove_item(st.session_state.basket, sku)
    st.session_state.basket_note = None


def _clear_basket() -> None:
    clear_basket(st.session_state.basket)
    st.session_state.basket_note = None


def _on_dropdown_pick(value: Any) -> None:
    """Called by the search add-on when a row is picked: queue it and clear the add-on's stored
    result, so picking the same row again is reported again (relies on the pinned add-on 0.1.24).

    With clear_on_submit the add-on then remounts under a new key, so its last 'submit' is not
    sent again on later reruns (a clarification click or an Add would otherwise repeat the pick).
    """
    st.session_state.pending_pick = value
    st.session_state[SEARCH_KEY]["result"] = None


def _render_search_bar(finder: Orchestrator, store_folder: str) -> bool:
    """The one search bar. Picks are queued in session state; returns True if the fallback Find was clicked.

    Uses the streamlit-searchbox add-on: 'Search for "<text>"' first (Enter picks it), then matching
    products. If the add-on cannot be imported or fails to render, falls back to a text box with a
    Find button and suggestion rows underneath, each with its own Add button.
    """
    def rows(term: str) -> list[tuple[str, tuple[str, str]]]:
        return search_options(term, finder.dataset, finder.settings)

    try:
        from streamlit_searchbox import st_searchbox

        st_searchbox(
            rows,
            label=None,
            placeholder=SEARCH_PLACEHOLDER,
            key=SEARCH_KEY,
            submit_function=_on_dropdown_pick,
            clear_on_submit=True,
        )
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("Search box add-on unavailable, using the plain search box: %s", exc)

    col_text, col_find = st.columns([5, 1], vertical_alignment="bottom")
    term = col_text.text_input(
        "Search products",
        placeholder=SEARCH_PLACEHOLDER,
        key="product_search_text",
        label_visibility="collapsed",
    )
    find_text = col_find.button("Find", type="primary", key="find_text", use_container_width=True)
    for s in suggest(term, finder.dataset, finder.settings):
        col_pic, col_pick, col_add = st.columns([1, 6, 1.2], vertical_alignment="center")
        _show_picture(col_pic, finder, store_folder, s.sku)
        if col_pick.button(s.label, key=f"suggest_{s.sku}", use_container_width=True):
            st.session_state.pop("last_suggestion", None)  # a button click is always a fresh pick
            st.session_state.pending_pick = ("product", s.sku)
        col_add.button(
            "Add",
            key=f"add_suggest_{s.sku}",
            on_click=_add_to_basket,
            args=(finder, s.sku, s.name),
            use_container_width=True,
        )
    return find_text


def _render_basket_panel(finder: Orchestrator, store_folder: str) -> bool:
    """Main-page basket: picture, quantity and remove per item, clear and plan. True if plan was clicked."""
    settings = finder.settings
    basket = st.session_state.basket
    with st.container(border=True, key="basket_panel"):
        title, count = st.columns([4, 1], vertical_alignment="center")
        title.subheader("Your basket")
        count.markdown(_badge("gray", f"{len(basket)} item{'s' if len(basket) != 1 else ''}"))
        note = st.session_state.get("basket_note")
        if note:
            ok, message = note
            (st.caption if ok else st.warning)(message)

        if not basket:
            st.caption("Your basket is empty. Use Add to basket on a result card.")
        for sku, entry in basket.items():
            qty_key = f"basket_qty_{sku}"
            st.session_state[qty_key] = entry["qty"]  # an add may have changed it since the widget last ran
            col_pic, col_name, col_qty, col_remove = st.columns([1, 4, 2, 1.2], vertical_alignment="center")
            _show_picture(col_pic, finder, store_folder, sku)
            col_name.markdown(f"**{entry['name']}**")
            col_qty.number_input(
                "Quantity",
                min_value=settings.basket_min_quantity,
                max_value=settings.basket_max_quantity,
                step=1,
                key=qty_key,
                on_change=_set_basket_quantity,
                args=(finder, sku),
            )
            col_remove.button("Remove", key=f"basket_remove_{sku}", type="tertiary",
                              on_click=_remove_from_basket, args=(sku,))

        col_plan, col_clear = st.columns([2, 1])
        plan = col_plan.button("Find route for basket", key="basket_plan", type="primary", use_container_width=True)
        if basket:
            col_clear.button("Clear basket", key="basket_clear", type="secondary",
                             on_click=_clear_basket, use_container_width=True)
    return plan


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


def _render_header() -> Any:
    """Top bar with title and subtitle; returns the slot for the model status chip."""
    with st.container(key="topbar"):
        left, right = st.columns([5, 2], vertical_alignment="center")
        left.title("Store Product Finder")
        left.caption("Find any product, see if it is in stock, and get the shortest walk to it across both floors.")
        return right.empty()


def _render_item_card(item: ItemResult, idx: int, finder: Orchestrator, store_folder: str) -> None:
    with st.container(border=True, height="stretch", key=f"card_{idx}"):
        body: Any = st.container()
        if item.sku:
            col_pic, body = st.columns([1, 2.4])
            _show_picture(col_pic, finder, store_folder, item.sku)
        with body:
            st.markdown(f"**{item.name or item.requested}**")
            st.markdown(_badge(*status_badge(item.status)))
            for line in card_lines(item):
                st.markdown(line)
            if item.reason:
                st.caption(item.reason)
            if item.sku and item.name:
                st.button(
                    "Add to basket",
                    key=f"add_item_{item.index}_{item.sku}",
                    on_click=_add_to_basket,
                    args=(finder, item.sku, item.name),
                )


def _render_route(answer: Answer, finder: Orchestrator) -> None:
    route = answer.route
    if route is None:
        return
    with st.container(border=True, key="route_panel"):
        st.subheader("Your route")
        walk_m = round(route.walking_distance)
        tile_walk, tile_floors = st.columns(2)
        tile_walk.metric("Walking distance", f"{walk_m} m")
        tile_floors.metric("Floor changes", route.floor_changes)
        st.markdown(f"about {walk_m} m of walking, {route.floor_changes} floor change(s)")

        rows = step_rows(route.steps)
        if rows:
            st.markdown("\n".join(f"{number}. {icon} {text}" for number, (icon, text) in enumerate(rows, start=1)))

        # One plain line per floor change, under the route
        for line in floor_change_lines(answer):
            st.markdown(line)

        # Every floor map stays visible, the floor of the first stop first
        segments = route_floor_segments(finder.dataset, answer)
        for fl in floor_display_order(finder.dataset, answer):
            st.markdown(f"#### Level {fl}")
            fig = draw_floor(finder.dataset, answer, fl)
            st.pyplot(fig)
            fl_stops = get_floor_stops(answer, fl)
            if fl_stops:
                stops_list = [f"{s_num}. {name} ({loc_str})" for s_num, sku, name, loc_str in fl_stops]
                st.caption(f"Stops on Level {fl}: {', '.join(stops_list)}")
            elif segments.get(fl):
                st.caption(f"No stops on Level {fl}; the route passes through this floor")
            else:
                st.caption(f"No route on Level {fl}")


def main() -> None:
    st.set_page_config(page_title="Store Product Finder", layout="wide", initial_sidebar_state="collapsed")
    st.markdown(CSS, unsafe_allow_html=True)
    chip_slot = _render_header()

    # Sidebar: only store and model settings
    with st.sidebar.expander("Store and model", expanded=False):
        store_folder = st.text_input("Store folder", value="data/store_demo")
        try:
            finder = get_finder(store_folder)
        except Exception as exc:  # noqa: BLE001
            finder = None
            load_error = exc
        if finder is not None:
            st.text(finder.model_label)
        show_details = st.checkbox("Show details", value=False)

    if finder is None:
        chip_slot.markdown(_badge("gray", "Store not loaded"))
        st.error(
            f"We couldn't open the store folder '{store_folder}'. Check the path under Store and model "
            "in the sidebar; the folder needs graph.json, products.csv, planogram.csv and inventory.csv."
        )
        with st.expander("Technical details"):
            st.code(str(load_error))
        return

    model_on = not isinstance(finder.client, NoModelClient)
    chip_slot.markdown(_badge("green" if model_on else "gray", f"AI model: {'on' if model_on else 'off'}"))

    # Session state tracking
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

    names = {p.sku: p.name for p in finder.dataset.products}

    # Search card: one search bar, hint, start point and step-free, then the paste-a-list section
    with st.container(border=True, key="search_card"):
        find_text = _render_search_bar(finder, store_folder)
        pick = st.session_state.pop("pending_pick", None)
        if pick and pick[0] == "product" and pick[1] in names:
            apply_suggestion(st.session_state, names[pick[1]])  # also shown in the paste box
        st.caption(SEARCH_HINT)

        start_options = _build_start_options(finder.dataset)
        options_map = {opt[0]: (opt[1], opt[2]) for opt in start_options}
        col_start, col_free = st.columns([3, 2], vertical_alignment="bottom")
        selected_label = col_start.selectbox("Start point", list(options_map.keys()), key="start_point")
        step_free = col_free.toggle(
            "Step-free route", value=False, key="step_free", help="Use only lifts and accessible connectors"
        )
        override_start, override_floor = options_map[selected_label]
        override_accessible: bool | None = True if step_free else None

        with st.expander("Type or paste a list instead", expanded=False):
            query_text = st.text_area(
                "Search query",
                value=st.session_state.query_input,
                placeholder=SEARCH_PLACEHOLDER,
                label_visibility="collapsed",
                height=110,
            )
            find_button = st.button("Find", type="primary", key="find")

    plan_clicked = _render_basket_panel(finder, store_folder)

    route_args = {"start": override_start, "floor": override_floor, "accessible_only": override_accessible}
    query_to_execute: str | None = None
    if pick and pick[0] == "search":
        query_to_execute = pick[1]
    elif find_text:
        query_to_execute = st.session_state.get("product_search_text", "")
    elif find_button:
        query_to_execute = query_text

    if pick and pick[0] == "product" and pick[1] in names:
        # A picked product runs its exact name through the pipeline, without the AI model
        try:
            ans = run_query(basket_finder_for(finder), names[pick[1]], **route_args)
            st.session_state.last_answer = ans
            st.session_state.session_id = ans.session_id
            st.session_state.answer_from_basket = True
        except Exception as exc:  # noqa: BLE001
            st.error(f"Search could not be completed: {exc}")
    elif query_to_execute is not None:
        stripped_query = query_to_execute.strip()
        if not stripped_query:
            st.info("Please enter a product name or item to search.")
            st.session_state.last_answer = None
        else:
            try:
                ans = run_query(finder, stripped_query, **route_args)
                st.session_state.last_answer = ans
                st.session_state.session_id = ans.session_id
                st.session_state.answer_from_basket = False
            except Exception as exc:  # noqa: BLE001
                st.error(f"Search could not be completed: {exc}")
    elif plan_clicked:
        try:
            ans = plan_basket(finder, st.session_state.basket, **route_args)
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
            with st.container(border=True, key="clarify"):
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

        # Item cards, two per row, equal height
        if last_answer.items:
            st.subheader("Items")
            items = last_answer.items
            for row_start in range(0, len(items), 2):
                cols = st.columns(2)
                for col, (offset, it) in zip(cols, enumerate(items[row_start:row_start + 2])):
                    with col:
                        _render_item_card(it, row_start + offset, finder, store_folder)

        _render_route(last_answer, finder)

        # Details trace
        if show_details and last_answer.trace:
            with st.expander("Execution Details", expanded=False):
                for ev in last_answer.trace:
                    ok_str = "OK" if ev.ok else "Failed"
                    note_str = f" - {ev.note}" if ev.note else ""
                    st.text(f"[{ev.stage}] {ok_str} ({ev.ms:.1f} ms){note_str}")

    with st.container(key="footer"):
        st.caption("Demo data: a synthetic two-floor store. Stock levels and locations are not real.")


if __name__ == "__main__":
    main()
