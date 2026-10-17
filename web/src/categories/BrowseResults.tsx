import { Button, ErrorState } from "../components/ui";
import { friendlyError } from "../lib/errors";
import { ProductCard } from "../results/ProductCard";
import { ResultsSkeleton } from "../results/Results";
import type { ReactNode } from "react";
import type { Product } from "../api/types";
import type { BrowseState } from "./useBrowse";

/** Products in one category, with "Show more" while there are more pages. */
export function BrowseResults({
  state,
  onMore,
  onRetry,
  action,
}: {
  state: BrowseState;
  onMore: () => void;
  onRetry: () => void;
  action?: (p: Product) => ReactNode;
}) {
  if (state.status === "loading") return <ResultsSkeleton />;
  if (state.status === "error") return <ErrorState {...friendlyError(state.error)} onRetry={onRetry} />;
  if (state.status !== "done") return null;
  return (
    <div className="sf-results-wrap">
      <h2 className="sf-results__heading">
        {state.category} <span className="sf-results__count">({state.total})</span>
      </h2>
      <div className="sf-results">
        {state.items.map((p) => (
          <ProductCard key={p.sku} product={p} action={action?.(p)} />
        ))}
      </div>
      {state.page < state.pages ? (
        <Button variant="secondary" onClick={onMore} disabled={state.loadingMore}>
          {state.loadingMore ? "Loading…" : `Show more (${state.total - state.items.length} left)`}
        </Button>
      ) : null}
    </div>
  );
}
