import type { ReactNode } from "react";
import type { Location, StockStatus } from "../api/types";
import { AlertIcon, CheckIcon, CrossCircleIcon, PinIcon, QuestionIcon } from "../components/icons";
import { Badge, Card } from "../components/ui";
import { formatLocation, formatPrice, stockLabel } from "../lib/format";
import { ProductImage } from "./ProductImage";

const TONE_ICON = { ok: <CheckIcon />, warn: <AlertIcon />, bad: <CrossCircleIcon />, neutral: <QuestionIcon /> };

/** The fields a product card needs; both Product (browse) and SearchItem (search) have them. */
export interface ProductLike {
  name: string;
  image_url: string | null;
  price: number | null;
  stock_status: StockStatus | string | null;
  in_stock: number | null;
  floor: number | null;
  zone: string | null;
  bay: string | null;
  shelf: number | null;
  locations: Location[];
}

export function ProductCard({
  product,
  notes,
  action,
  status,
}: {
  product: ProductLike;
  notes?: ReactNode;
  action?: ReactNode;
  status?: string;
}) {
  const price = formatPrice(product.price);
  const stock = stockLabel(product.stock_status as StockStatus | null, product.in_stock);
  const place = formatLocation(product);
  const others = product.locations.slice(1).map((l) => formatLocation(l)).filter(Boolean);

  return (
    <Card className={`sf-result ${stock.tone === "bad" ? "is-out" : ""}`} data-testid="result-card" data-status={status}>
      <ProductImage imageUrl={product.image_url} name={product.name} />
      <div className="sf-result__body">
        <h3 className="sf-result__name">{product.name}</h3>
        <div className="sf-result__meta">
          {price ? <span className="sf-result__price">{price}</span> : null}
          <Badge tone={stock.tone} icon={TONE_ICON[stock.tone]}>
            {stock.text}
          </Badge>
        </div>
        {place ? (
          <p className="sf-result__place">
            <PinIcon />
            <span>{place}</span>
          </p>
        ) : null}
        {others.length ? <p className="sf-result__note">Also at: {others.join("; ")}</p> : null}
        {notes}
        {action ? <div className="sf-result__actions">{action}</div> : null}
      </div>
    </Card>
  );
}
