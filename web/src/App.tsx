import { useEffect, useState } from "react";
import { ApiError } from "./api/client";
import { StoreSelector } from "./app/StoreSelector";
import { ThemeToggle } from "./app/ThemeToggle";
import { BrowseResults } from "./categories/BrowseResults";
import { CategoryChips } from "./categories/CategoryChips";
import { useBrowse } from "./categories/useBrowse";
import { useCategories } from "./categories/useCategories";
import { StoreIcon } from "./components/icons";
import { EmptyState, ErrorState, Skeleton } from "./components/ui";
import { friendlyError } from "./lib/errors";
import { Results, ResultsSkeleton } from "./results/Results";
import { SearchBar } from "./search/SearchBar";
import { useSearch } from "./search/useSearch";
import { useStoreSelection } from "./stores/useStoreSelection";
import { useTheme } from "./theme/theme";
import "./app/app.css";

const isStoreGone = (e: unknown) => e instanceof ApiError && e.code === "STORE_NOT_FOUND";

export function App() {
  const theme = useTheme();
  const stores = useStoreSelection();
  const { state: search, search: runSearch, reset: resetSearch } = useSearch(stores.storeId);
  const categories = useCategories(stores.storeId);
  const browse = useBrowse(stores.storeId);
  const [text, setText] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  // 404 STORE_NOT_FOUND from a search or a category: the chosen store is gone, so use the first store.
  const failure = search.status === "error" ? search.error : browse.state.status === "error" ? browse.state.error : null;
  const { resetToFirst } = stores;
  useEffect(() => {
    if (isStoreGone(failure)) {
      resetToFirst();
      setNotice("That store isn't available any more, so we've switched to the first store.");
    }
  }, [failure, resetToFirst]);

  const doSearch = (t: string) => {
    browse.open(null);
    void runSearch(t);
  };
  const selectedCategory = browse.state.status === "idle" ? null : browse.state.category;

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
          <StoreSelector
            stores={stores.state.stores}
            value={stores.storeId}
            onChange={(id) => {
              setNotice(null);
              setText("");
              stores.selectStore(id);
            }}
          />
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
            <SearchBar
              storeId={stores.storeId}
              text={text}
              onTextChange={setText}
              onSearch={doSearch}
              disabled={!stores.storeId}
              busy={search.status === "loading"}
            />
            <CategoryChips
              categories={categories}
              selected={selectedCategory}
              onSelect={(name) => {
                resetSearch();
                browse.open(name);
              }}
            />
            {notice ? (
              <p className="sf-notice" role="status">
                {notice}
              </p>
            ) : null}
            <section className="sf-section" aria-live="polite" aria-label="Results">
              {browse.state.status !== "idle" ? (
                <BrowseResults state={browse.state} onMore={browse.more} onRetry={() => browse.open(selectedCategory)} />
              ) : (
                <>
                  {search.status === "loading" ? <ResultsSkeleton /> : null}
                  {search.status === "done" ? <Results response={search.response} text={search.text} /> : null}
                  {search.status === "error" && !isStoreGone(search.error) ? (
                    <ErrorState {...friendlyError(search.error)} onRetry={() => runSearch(search.text)} />
                  ) : null}
                  {search.status === "idle" ? (
                    <EmptyState title="What are you looking for?" icon={<StoreIcon />}>
                      Search for one product or a whole list, like “milk, bread and crayons”, or pick a category.
                    </EmptyState>
                  ) : null}
                </>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
