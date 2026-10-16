import { useState } from "react";
import { SEARCH_MAX_CHARS } from "../config";
import { SearchIcon } from "../components/icons";
import { Button } from "../components/ui";
import "./search.css";

/** The one search bar: a product, or a whole list with a start point ("milk, bread and crayons, I'm at produce"). */
export function SearchForm({ onSearch, disabled, busy }: { onSearch: (text: string) => void; disabled?: boolean; busy?: boolean }) {
  const [text, setText] = useState("");
  return (
    <form
      role="search"
      className="sf-search"
      onSubmit={(e) => {
        e.preventDefault();
        if (text.trim()) onSearch(text);
      }}
    >
      <label className="sf-search__field">
        <span className="visually-hidden">Search products</span>
        <SearchIcon className="sf-search__icon" />
        <input
          className="sf-search__input"
          type="search"
          name="q"
          value={text}
          maxLength={SEARCH_MAX_CHARS}
          placeholder="Try milk, or a list: bread and crayons"
          autoComplete="off"
          enterKeyHint="search"
          disabled={disabled}
          onChange={(e) => setText(e.target.value)}
        />
      </label>
      <Button type="submit" disabled={disabled || busy || !text.trim()}>
        Search
      </Button>
    </form>
  );
}
