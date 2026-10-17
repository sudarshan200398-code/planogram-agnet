import { CrossCircleIcon, StoreIcon } from "../components/icons";
import { Button, Card } from "../components/ui";

/** What a not-found card needs to know about the stores. */
export interface NotFoundInfo {
  storeName: string;
  /** Another store to try, or null (only one store, or it was already checked). */
  otherStoreName: string | null;
  /** The other store was checked for this search and does not sell it either. */
  checkedBoth: boolean;
  onCheckOther: () => void;
}

/** "Not sold at <store>", with a button to try the other store (only on tap, never by itself). */
export function NotFoundCard({ text, info }: { text: string; info: NotFoundInfo }) {
  return (
    <Card className="sf-result sf-result--message sf-not-found" data-testid="result-card" data-status="not_found">
      <span className="sf-not-found__icon" aria-hidden="true">
        <CrossCircleIcon />
      </span>
      <div className="sf-result__body">
        <h3 className="sf-result__name">“{text}”</h3>
        <p className="sf-not-found__where">{info.checkedBoth ? "Not found in either store" : `Not sold at ${info.storeName}`}</p>
        <p className="sf-result__note">Try a different word{info.checkedBoth ? "." : ", or check the other store."}</p>
        {info.otherStoreName && !info.checkedBoth ? (
          <div className="sf-result__actions">
            <Button variant="secondary" onClick={info.onCheckOther}>
              <StoreIcon /> Check {info.otherStoreName}
            </Button>
          </div>
        ) : null}
      </div>
    </Card>
  );
}
