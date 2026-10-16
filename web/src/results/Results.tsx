import type { ReactNode } from "react";
import type { SearchItem, SearchResponse } from "../api/types";
import { SearchIcon } from "../components/icons";
import { Card, EmptyState, Skeleton } from "../components/ui";
import { RouteSteps } from "../route/RouteSteps";
import { ClarifyPanel } from "../search/ClarifyPanel";
import { ResultCard } from "./ResultCard";
import "./results.css";

export function ResultsSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="sf-results" aria-busy="true" aria-label="Loading results">
      {Array.from({ length: count }, (_, i) => (
        <Card key={i} className="sf-result">
          <Skeleton width="72px" height="72px" />
          <div className="sf-result__body" style={{ flex: 1 }}>
            <Skeleton width="70%" height="1.1rem" />
            <Skeleton width="40%" />
            <Skeleton width="85%" />
          </div>
        </Card>
      ))}
    </div>
  );
}

/** Messages, the pending question (if any) and result cards for one search response. */
export function Results({
  response,
  text,
  answering = null,
  notice = null,
  onAnswer,
  action,
}: {
  response: SearchResponse;
  text: string;
  answering?: string | null;
  notice?: string | null;
  onAnswer?: (itemIndex: number, sku: string) => void;
  action?: (item: SearchItem) => ReactNode;
}) {
  if (!response.items.length) {
    return (
      <EmptyState title="No results" icon={<SearchIcon />}>
        {response.messages[0] ?? "Try a product name, like milk or bread."}
      </EmptyState>
    );
  }
  return (
    <div className="sf-results-wrap">
      <h2 className="sf-results__heading">
        Results for “{text}”
      </h2>
      {notice ? (
        <p className="sf-message" role="status">
          {notice}
        </p>
      ) : null}
      {response.question && onAnswer ? (
        <ClarifyPanel question={response.question} answering={answering} onAnswer={onAnswer} />
      ) : null}
      {response.messages.length ? (
        <div className="sf-messages">
          {response.messages.map((m) => (
            <p key={m} className="sf-message">
              {m}
            </p>
          ))}
        </div>
      ) : null}
      <div className="sf-results">
        {response.items.map((item) => (
          <ResultCard key={`${item.index}-${item.sku ?? item.requested}`} item={item} action={item.sku ? action?.(item) : undefined} />
        ))}
      </div>
      {response.route ? <RouteSteps route={response.route} /> : null}
    </div>
  );
}
