import { useEffect, useState } from "react";
import { ApiError } from "./api/client";
import { StoreSelector } from "./app/StoreSelector";
import { ThemeToggle } from "./app/ThemeToggle";
import { EmptyState, ErrorState, Skeleton } from "./components/ui";
import { StoreIcon } from "./components/icons";
import { friendlyError } from "./lib/errors";
import { Results, ResultsSkeleton } from "./results/Results";
import { SearchForm } from "./search/SearchForm";
import { useSearch } from "./search/useSearch";
import { useStoreSelection } from "./stores/useStoreSelection";
import { useTheme } from "./theme/theme";
import "./app/app.css";

export function App() {
  const theme = useTheme();
  const stores = useStoreSelection();
  const { state: search, search: runSearch } = useSearch(stores.storeId);
  const [notice, setNotice] = useState<string | null>(null);

  // 404 STORE_NOT_FOUND: the chosen store is gone, so fall back to the first store.
  const searchError = search.status === "error" ? search.error : null;
  const { resetToFirst } = stores;
  useEffect(() => {
    if (searchError instanceof ApiError && searchError.code === "STORE_NOT_FOUND") {
      resetToFirst();
      setNotice("That store isn't available any more, so we've switched to the first store.");
    }
  }, [searchError, resetToFirst]);

  return (
    <div className="sf-app">
      <header className="sf-header">
        <div className="sf-header__row">
          <p className="sf-brand">
            <span className="sf-brand__mark" aria-hidden="true">S</span>
            SuperFind <span className="sf-brand__ai">AI</span>
          </p>
          <ThemeToggle preference={theme.preference} onChange={theme.setPreference} />
        </div>
        {stores.state.status === "ready" ? (
          <StoreSelector stores={stores.state.stores} value={stores.storeId} onChange={(id) => (setNotice(null), stores.selectStore(id))} />
        ) : stores.state.status === "loading" ? (
          <Skeleton height="44px" />
        ) : null}
      </header>

      <main className="sf-main">
        {stores.state.status === "error" ? (
          <ErrorState {...friendlyError(stores.state.error)} onRetry={stores.retry} />
        ) : (
          <>
            <h1 className="sf-title">{stores.current ? `Find anything in ${stores.current.name}` : "Find anything in the store"}</h1>
            <SearchForm disabled={!stores.storeId} busy={search.status === "loading"} onSearch={runSearch} />
            {notice ? (
              <p className="sf-notice" role="status">
                {notice}
              </p>
            ) : null}
            <section className="sf-section" aria-live="polite" aria-label="Search results">
              {search.status === "loading" ? <ResultsSkeleton /> : null}
              {search.status === "done" ? <Results response={search.response} text={search.text} /> : null}
              {search.status === "error" && !(search.error instanceof ApiError && search.error.code === "STORE_NOT_FOUND") ? (
                <ErrorState {...friendlyError(search.error)} onRetry={() => runSearch(search.text)} />
              ) : null}
              {search.status === "idle" ? (
                <EmptyState title="What are you looking for?" icon={<StoreIcon />}>
                  Search for one product or a whole list, like “milk, bread and crayons”.
                </EmptyState>
              ) : null}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
