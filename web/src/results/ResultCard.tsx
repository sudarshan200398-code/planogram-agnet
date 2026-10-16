import type { ReactNode } from "react";
import type { SearchItem } from "../api/types";
import { Card } from "../components/ui";
import { ProductCard } from "./ProductCard";

/** One searched item: a product card, or a plain message when nothing usable was found. */
export function ResultCard({ item, action }: { item: SearchItem; action?: ReactNode }) {
  if (!item.sku || !item.name) {
    return (
      <Card className="sf-result sf-result--message" data-testid="result-card" data-status={item.status}>
        <div className="sf-result__body">
          <h3 className="sf-result__name">“{item.requested}”</h3>
          <p className="sf-result__note">
            {item.status === "needs_choice"
              ? "Choose which one you mean."
              : item.status === "not_found"
                ? "We couldn't find this in this store. Try a different word."
                : "We couldn't check this item. Please try again."}
          </p>
        </div>
      </Card>
    );
  }
  const notes = (
    <>
      {item.status === "not_placed" ? <p className="sf-result__note">This product isn't on the shelves right now.</p> : null}
      {item.quantity_requested > 1 ? <p className="sf-result__note">You asked for {item.quantity_requested}</p> : null}
    </>
  );
  return <ProductCard product={{ ...item, name: item.name }} notes={notes} action={action} status={item.status} />;
}
