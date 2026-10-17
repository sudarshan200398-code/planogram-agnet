import { CheckIcon, ListIcon, MinusIcon, PlusIcon, TrashIcon, WalkIcon } from "../components/icons";
import { Button, EmptyState, ErrorState, IconButton, Skeleton } from "../components/ui";
import { QTY_MAX, QTY_MIN } from "../config";
import { friendlyError } from "../lib/errors";
import { ProductImage } from "../results/ProductImage";
import { RouteSteps } from "../route/RouteSteps";
import type { ListItem, NewItem } from "./list";
import type { RouteState } from "./useBasketRoute";
import "./list.css";

export function listLabel(count: number) {
  return `Shopping list, ${count === 0 ? "empty" : count === 1 ? "1 item" : `${count} items`}`;
}

/** Header button that opens the list, with the number of products. */
export function ListButton({ count, onClick }: { count: number; onClick: () => void }) {
  return (
    <button type="button" className="sf-list-button" aria-label={listLabel(count)} onClick={onClick}>
      <ListIcon />
      <span className="sf-list-button__word" aria-hidden="true">
        List
      </span>
      {count ? (
        <span className="sf-list-button__count" aria-hidden="true">
          {count}
        </span>
      ) : null}
    </button>
  );
}

/** "Add to list" on a product card; once added it says so and opens the list. */
export function AddToListButton({
  item,
  inList,
  full,
  onAdd,
  onOpen,
}: {
  item: NewItem;
  inList: boolean;
  full: boolean;
  onAdd: (item: NewItem) => void;
  onOpen: () => void;
}) {
  if (inList) {
    return (
      <Button variant="secondary" className="sf-add is-added" aria-label={`${item.name} is in your list. Open list`} onClick={onOpen}>
        <CheckIcon /> In your list
      </Button>
    );
  }
  return (
    <Button variant="secondary" className="sf-add" aria-label={`Add ${item.name} to list`} disabled={full} onClick={() => onAdd(item)}>
      <PlusIcon /> {full ? "List full" : "Add to list"}
    </Button>
  );
}

function Stepper({ item, onChange }: { item: ListItem; onChange: (qty: number) => void }) {
  return (
    <div className="sf-stepper" role="group" aria-label={`Quantity of ${item.name}`}>
      <IconButton label={`One fewer ${item.name}`} disabled={item.qty <= QTY_MIN} onClick={() => onChange(item.qty - 1)}>
        <MinusIcon />
      </IconButton>
      <output className="sf-stepper__value" aria-live="polite">
        {item.qty}
      </output>
      <IconButton label={`One more ${item.name}`} disabled={item.qty >= QTY_MAX} onClick={() => onChange(item.qty + 1)}>
        <PlusIcon />
      </IconButton>
    </div>
  );
}

/** The list inside its sheet: items with steppers, then "Find my route" and the route. */
export function ShoppingList({
  items,
  route,
  onQty,
  onRemove,
  onFindRoute,
}: {
  items: ListItem[];
  route: RouteState;
  onQty: (sku: string, qty: number) => void;
  onRemove: (sku: string) => void;
  onFindRoute: () => void;
}) {
  if (!items.length) {
    return (
      <EmptyState title="Your list is empty" icon={<ListIcon />}>
        Tap “Add to list” on any product, then find the shortest route to all of them.
      </EmptyState>
    );
  }
  return (
    <div className="sf-list">
      <ul className="sf-list__items">
        {items.map((i) => (
          <li key={i.sku} className="sf-list__item">
            <ProductImage imageUrl={i.image_url} name={i.name} size={44} />
            <div className="sf-list__text">
              <span className="sf-list__name">{i.name}</span>
              {i.place ? <span className="sf-list__place">{i.place}</span> : null}
            </div>
            <div className="sf-list__controls">
              <Stepper item={i} onChange={(q) => onQty(i.sku, q)} />
              <IconButton label={`Remove ${i.name}`} className="sf-list__remove" onClick={() => onRemove(i.sku)}>
                <TrashIcon />
              </IconButton>
            </div>
          </li>
        ))}
      </ul>
      <Button className="sf-list__find" onClick={onFindRoute} disabled={route.status === "loading"} aria-busy={route.status === "loading"}>
        <WalkIcon /> {route.status === "loading" ? "Finding your route…" : "Find my route"}
      </Button>
      {route.status === "loading" ? (
        <div className="sf-list__loading" aria-label="Loading route">
          <Skeleton height="1.25rem" width="50%" />
          <Skeleton height="3rem" />
          <Skeleton height="1rem" />
          <Skeleton height="1rem" />
        </div>
      ) : null}
      {route.status === "error" ? <ErrorState {...friendlyError(route.error)} onRetry={onFindRoute} /> : null}
      {route.status === "done" ? (
        <>
          {route.response.messages.map((m) => (
            <p key={m} className="sf-message">
              {m}
            </p>
          ))}
          {route.response.route ? (
            <RouteSteps route={route.response.route} storeId={route.response.store_id} defaultOpen />
          ) : (
            <p className="sf-message">We couldn't make a route for this list.</p>
          )}
        </>
      ) : null}
    </div>
  );
}
