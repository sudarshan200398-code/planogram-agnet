import type { ReactNode } from "react";
import type { SearchItem } from "../api/types";
import { AlertIcon, CheckIcon, CrossCircleIcon, PinIcon, QuestionIcon } from "../components/icons";
import { Badge, Card } from "../components/ui";
import { formatLocation, formatPrice, stockLabel } from "../lib/format";
import { ProductImage } from "./ProductImage";

const TONE_ICON = { ok: <CheckIcon />, warn: <AlertIcon />, bad: <CrossCircleIcon />, neutral: <QuestionIcon /> };

/** One searched item: a product card, or a plain message when nothing usable was found. */
export function ResultCard({ item, action }: { item: SearchItem; action?: ReactNode }) {
  if (!item.sku || !item.name) {
    return (
      <Card className="sf-result sf-result--message" data-testid="result-card" data-status={item.status}>
        <div className="sf-result__body">
          <h3 className="sf-result__name">“{item.requested}”</h3>
          <p className="sf-result__note">
            {item.status === "needs_choice"
              ? "Choose which one you mean below."
              : item.status === "not_found"
                ? "We couldn't find this in this store. Try a different word."
                : "We couldn't check this item. Please try again."}
          </p>
        </div>
      </Card>
    );
  }

  const price = formatPrice(item.price);
  const stock = stockLabel(item.stock_status, item.in_stock);
  const place = formatLocation(item);
  const others = item.locations.slice(1).map((l) => formatLocation(l)).filter(Boolean);

  return (
    <Card className={`sf-result ${stock.tone === "bad" ? "is-out" : ""}`} data-testid="result-card" data-status={item.status}>
      <ProductImage imageUrl={item.image_url} name={item.name} />
      <div className="sf-result__body">
        <h3 className="sf-result__name">{item.name}</h3>
        <div className="sf-result__meta">
          {price ? <span className="sf-result__price">{price}</span> : null}
          <Badge tone={stock.tone} icon={TONE_ICON[stock.tone]}>
            {stock.text}
          </Badge>
        </div>
        {item.status === "not_placed" ? (
          <p className="sf-result__note">This product isn't on the shelves right now.</p>
        ) : place ? (
          <p className="sf-result__place">
            <PinIcon />
            <span>{place}</span>
          </p>
        ) : null}
        {others.length ? <p className="sf-result__note">Also at: {others.join("; ")}</p> : null}
        {item.quantity_requested > 1 ? <p className="sf-result__note">You asked for {item.quantity_requested}</p> : null}
        {action}
      </div>
    </Card>
  );
}
