import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api/client";
import { StoreSelector } from "./app/StoreSelector";
import { ThemeToggle } from "./app/ThemeToggle";
import { BrowseResults } from "./categories/BrowseResults";
import { CategoryChips } from "./categories/CategoryChips";
import { useBrowse } from "./categories/useBrowse";
import { useCategories } from "./categories/useCategories";
import { StoreIcon } from "./components/icons";
import { Sheet } from "./components/Sheet";
import { Toast, type ToastMessage } from "./components/Toast";
import { EmptyState, ErrorState, Skeleton } from "./components/ui";
import { friendlyError } from "./lib/errors";
import { formatLocation } from "./lib/format";
import { addAllMessage, type NewItem } from "./list/list";
import { AddAllButton, AddToListButton, ListButton, ShoppingList } from "./list/ShoppingList";
import { useBasketRoute } from "./list/useBasketRoute";
import { useShoppingList } from "./list/useShoppingList";
import type { ProductLike } from "./results/ProductCard";
import { Results, ResultsSkeleton } from "./results/Results";
import { useStartPoint } from "./route/useStartPoint";
import { SearchBar } from "./search/SearchBar";
import { useSearch } from "./search/useSearch";
import { useStoreSelection } from "./stores/useStoreSelection";
import { LIST_MAX_ITEMS } from "./config";
import { useTheme } from "./theme/theme";
import { useVoice } from "./voice/useVoice";
import { VoiceButton } from "./voice/VoiceButton";
import "./app/app.css";

const isStoreGone = (e: unknown) => e instanceof ApiError && e.code === "STORE_NOT_FOUND";

export function App() {
  const theme = useTheme();
  const stores = useStoreSelection();
  const { state: search, search: runSearch, answer, reset: resetSearch } = useSearch(stores.storeId);
  const categories = useCategories(stores.storeId);
  const browse = useBrowse(stores.storeId);
  const [text, setText] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const list = useShoppingList(stores.storeId);
  const basket = useBasketRoute(stores.storeId);
  const [listOpen, setListOpen] = useState(false);
  const openList = useCallback(() => setListOpen(true), []);
  const closeList = useCallback(() => setListOpen(false), []);
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const closeToast = useCallback(() => setToast(null), []);
  // A start point said in a search ("I'm at produce, …") is kept for the list route of this store.
  const startPoint = useStartPoint(stores.storeId);
  const searchResponse = search.status === "done" ? search.response : null;
  const { detect: detectStart } = startPoint;
  useEffect(() => {
    if (searchResponse) void detectStart(searchResponse);
  }, [searchResponse, detectStart]);
  const startLabel = startPoint.start?.label ?? null;
  // A route is only shown for the list and start it was made from; changing either clears it.
  const { clear: clearRoute } = basket;
  useEffect(() => clearRoute(), [list.items, startLabel, clearRoute]);
  const voice = useVoice(setText);
  // When speech ends, hand the words back to the shopper to check before searching.
  useEffect(() => {
    if (voice.status === "heard") searchInput.current?.focus();
  }, [voice.status]);

  // 404 STORE_NOT_FOUND from a search or a category: the chosen store is gone, so use the first store.
  const failure = search.status === "error" ? search.error : browse.state.status === "error" ? browse.state.error : null;
  const { resetToFirst } = stores;
  useEffect(() => {
    if (isStoreGone(failure)) {
      resetToFirst();
      setNotice("That store isn't available any more, so we've switched to the first store.");
    }
  }, [failure, resetToFirst]);

  // "Check <other store>" on a not-found card: switch store, then run the same search there once.
  const [crossCheck, setCrossCheck] = useState<{ text: string; to: string; ran: boolean } | null>(null);
  const otherStore = stores.state.status === "ready" ? (stores.state.stores.find((s) => s.id !== stores.storeId) ?? null) : null;
  const checkOtherStore = (t: string) => {
    if (!otherStore) return;
    setCrossCheck({ text: t, to: otherStore.id, ran: false });
    setText(t);
    setNotice(null);
    browse.open(null);
    stores.selectStore(otherStore.id); // URL and storage; the old store's search is cancelled
  };
  useEffect(() => {
    if (crossCheck && !crossCheck.ran && stores.storeId === crossCheck.to) {
      setCrossCheck({ ...crossCheck, ran: true });
      void runSearch(crossCheck.text);
    }
  }, [crossCheck, stores.storeId, runSearch]);
  const checkedBoth = !!crossCheck?.ran && stores.storeId === crossCheck.to && search.status === "done" && search.text === crossCheck.text;

  // An empty box means "no search": cancel it and drop its results and route (the shopping list is separate).
  const changeText = (t: string) => {
    setText(t);
    if (!t.trim()) {
      resetSearch();
      setCrossCheck(null);
    }
  };

  const doSearch = (t: string) => {
    setCrossCheck(null);
    browse.open(null);
    void runSearch(t);
  };
  const selectedCategory = browse.state.status === "idle" ? null : browse.state.category;
  const inList = new Set(list.items.map((i) => i.sku));
  const addAction = (p: ProductLike & { sku: string | null }) => {
    if (!p.sku) return null;
    const item: NewItem = { sku: p.sku, name: p.name, image_url: p.image_url, place: formatLocation(p) };
    const add = (n: NewItem) => {
      list.add(n);
      const nowFull = list.items.length + 1 >= LIST_MAX_ITEMS;
      setToast({
        id: Date.now(),
        text: nowFull ? `Added ${n.name}. Your list is now full (${LIST_MAX_ITEMS} products).` : `Added ${n.name} to your list`,
        action: { label: "Open list", run: openList },
      });
    };
    return <AddToListButton item={item} inList={inList.has(p.sku)} full={list.full} onAdd={add} onOpen={openList} />;
  };
  // "Add all to list" when a list search found 2 or more products in stock; the rest are skipped.
  const searchItems = searchResponse?.items ?? [];
  const inStock = searchItems.filter((i) => i.status === "available" && i.sku && i.name);
  const addAll = () => {
    const result = list.addMany(
      inStock.map((i) => ({ sku: i.sku!, name: i.name!, image_url: i.image_url, place: formatLocation(i), qty: i.quantity_requested })),
    );
    setToast({ id: Date.now(), text: addAllMessage(result, searchItems.length - inStock.length), action: { label: "Open list", run: openList } });
  };

  return (
    <div className="sf-app">
      <header className="sf-header">
        <div className="sf-header__row">
          <p className="sf-brand">
            <span className="sf-brand__mark" aria-hidden="true">S</span>
            SuperFind <span className="sf-brand__ai">AI</span>
          </p>
          <div className="sf-header__actions">
            <ListButton count={list.items.length} onClick={openList} />
            <ThemeToggle preference={theme.preference} onChange={theme.setPreference} />
          </div>
        </div>
        {stores.state.status === "ready" ? (
          <StoreSelector
            stores={stores.state.stores}
            value={stores.storeId}
            onChange={(id) => {
              setNotice(null);
              setText("");
              setCrossCheck(null);
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
            <div className="sf-search-block">
              <SearchBar
                storeId={stores.storeId}
                text={text}
                onTextChange={changeText}
                onSearch={doSearch}
                disabled={!stores.storeId}
                busy={search.status === "loading"}
                inputRef={searchInput}
                trailing={
                  voice.supported ? (
                    <VoiceButton listening={voice.listening} onStart={voice.start} onStop={voice.stop} disabled={!stores.storeId} />
                  ) : null
                }
              />
              {voice.supported ? (
                <p className="sf-voice-status" role="status">
                  {voice.message}
                </p>
              ) : null}
            </div>
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
                <BrowseResults
                  state={browse.state}
                  onMore={browse.more}
                  onRetry={() => browse.open(selectedCategory)}
                  action={addAction}
                />
              ) : (
                <>
                  {search.status === "loading" ? <ResultsSkeleton /> : null}
                  {search.status === "done" ? (
                    <Results
                      response={search.response}
                      text={search.text}
                      answering={search.answering}
                      notice={search.notice}
                      onAnswer={(i, sku) => void answer(i, sku)}
                      action={(item) => addAction({ ...item, name: item.name ?? item.requested })}
                      addAll={inStock.length >= 2 ? <AddAllButton full={list.full} onAdd={addAll} /> : null}
                      notFound={{
                        storeName: stores.current?.name ?? "this store",
                        otherStoreName: otherStore?.name ?? null,
                        checkedBoth,
                        onCheckOther: () => checkOtherStore(search.text),
                      }}
                    />
                  ) : null}
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

      <Toast message={toast} onClose={closeToast} />

      <Sheet open={listOpen} title="Shopping list" onClose={closeList}>
        <ShoppingList
          items={list.items}
          route={basket.state}
          start={startPoint.start}
          onQty={list.setQty}
          onRemove={list.remove}
          onFindRoute={() => void basket.find(list.items, startLabel)}
          onResetStart={startPoint.reset}
        />
      </Sheet>
    </div>
  );
}
