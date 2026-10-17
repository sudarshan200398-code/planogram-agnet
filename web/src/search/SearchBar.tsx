import { useId, useState, type ReactNode, type Ref } from "react";
import { SEARCH_MAX_CHARS } from "../config";
import { CloseIcon, SearchIcon } from "../components/icons";
import { Button, IconButton } from "../components/ui";
import { stockLabel } from "../lib/format";
import { useSuggestions } from "./useSuggestions";
import "./search.css";

/**
 * The one search bar (a combobox). Typing shows suggestions; picking one searches that exact product.
 * Submitting searches everything typed, so lists and start points ("milk, bread, I'm at produce") work.
 */
export function SearchBar({
  storeId,
  text,
  onTextChange,
  onSearch,
  disabled,
  busy,
  trailing,
  inputRef,
}: {
  storeId: string | null;
  text: string;
  onTextChange: (t: string) => void;
  onSearch: (t: string) => void;
  disabled?: boolean;
  busy?: boolean;
  trailing?: ReactNode;
  inputRef?: Ref<HTMLInputElement>;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const { suggestions } = useSuggestions(storeId, text, open);
  const listId = useId();
  const showList = open && suggestions.length > 0;

  const submit = (value: string) => {
    setOpen(false);
    setActive(-1);
    if (value.trim()) onSearch(value);
  };

  return (
    <form
      role="search"
      className="sf-search"
      onSubmit={(e) => {
        e.preventDefault();
        const picked = active >= 0 ? suggestions[active] : undefined;
        if (picked) onTextChange(picked.name);
        submit(picked ? picked.name : text);
      }}
    >
      <div className={`sf-search__field ${trailing ? "has-trailing" : ""}`}>
        <SearchIcon className="sf-search__icon" />
        <input
          ref={inputRef}
          className="sf-search__input"
          type="search"
          name="q"
          role="combobox"
          aria-label="Search products"
          aria-autocomplete="list"
          aria-expanded={showList}
          aria-controls={listId}
          aria-activedescendant={showList && active >= 0 ? `${listId}-${active}` : undefined}
          value={text}
          maxLength={SEARCH_MAX_CHARS}
          placeholder="Search a product, or a list: milk, bread and crayons"
          autoComplete="off"
          enterKeyHint="search"
          disabled={disabled}
          onChange={(e) => {
            onTextChange(e.target.value);
            setOpen(true);
            setActive(-1);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => window.setTimeout(() => setOpen(false), 150)}
          onKeyDown={(e) => {
            // Escape closes the suggestions; with none showing, it empties the box (which returns home).
            if (e.key === "Escape" && !showList && text) {
              e.preventDefault();
              onTextChange("");
              return;
            }
            if (!showList) return;
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((i) => Math.min(suggestions.length - 1, i + 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((i) => Math.max(-1, i - 1));
            } else if (e.key === "Escape") {
              setOpen(false);
              setActive(-1);
            }
          }}
        />
        <span className="sf-search__actions">
          {text ? (
            <IconButton label="Clear search" className="sf-search__clear" onClick={(e) => {
                onTextChange("");
                setActive(-1);
                e.currentTarget.closest(".sf-search__field")?.querySelector("input")?.focus();
              }}>
              <CloseIcon />
            </IconButton>
          ) : null}
          {trailing}
        </span>
        <ul id={listId} role="listbox" aria-label="Suggestions" className="sf-suggest" hidden={!showList}>
          {suggestions.map((s, i) => {
            const stock = stockLabel(s.stock_status, null);
            return (
              <li
                key={s.sku}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === active}
                className={`sf-suggest__item ${i === active ? "is-active" : ""}`}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onTextChange(s.name);
                  submit(s.name);
                }}
              >
                <span className="sf-suggest__name">{s.name}</span>
                <span className="sf-suggest__meta">
                  {s.places.join(" / ") || "No shelf location"} · {stock.text}
                </span>
              </li>
            );
          })}
        </ul>
      </div>
      <Button type="submit" disabled={disabled || busy || !text.trim()}>
        Search
      </Button>
    </form>
  );
}
