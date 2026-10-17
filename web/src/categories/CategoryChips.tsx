import { useState } from "react";
import type { Category } from "../api/types";
import { QUICK_CATEGORY_COUNT } from "../config";
import { Sheet } from "../components/Sheet";
import { Chip, Skeleton } from "../components/ui";
import { quickCategories } from "./useCategories";
import "./categories.css";

/** Quick category chips; "More" opens every category in a sheet. */
export function CategoryChips({
  categories,
  selected,
  onSelect,
}: {
  categories: Category[] | null;
  selected: string | null;
  onSelect: (name: string | null) => void;
}) {
  const [allOpen, setAllOpen] = useState(false);
  if (categories === null) {
    return (
      <div className="sf-chips" aria-hidden="true">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} width="96px" height="36px" className="sf-chips__skeleton" />
        ))}
      </div>
    );
  }
  if (!categories.length) return null;
  const quick = quickCategories(categories, QUICK_CATEGORY_COUNT);
  const pick = (name: string) => onSelect(selected === name ? null : name);
  return (
    <nav aria-label="Browse by category">
      <div className="sf-chips">
        {quick.map((c) => (
          <Chip key={c.name} selected={selected === c.name} onClick={() => pick(c.name)}>
            {c.name}
          </Chip>
        ))}
        {categories.length > quick.length ? (
          <Chip onClick={() => setAllOpen(true)}>More categories</Chip>
        ) : null}
      </div>
      <Sheet open={allOpen} title="All categories" onClose={() => setAllOpen(false)}>
        <ul className="sf-category-list">
          {[...categories]
            .sort((a, b) => a.name.localeCompare(b.name))
            .map((c) => (
              <li key={c.name}>
                <button
                  type="button"
                  className="sf-category-list__item"
                  aria-pressed={selected === c.name}
                  onClick={() => {
                    setAllOpen(false);
                    pick(c.name);
                  }}
                >
                  <span>{c.name}</span>
                  <span className="sf-category-list__count">{c.product_count}</span>
                </button>
              </li>
            ))}
        </ul>
      </Sheet>
    </nav>
  );
}
