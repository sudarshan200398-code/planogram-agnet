import type { Question } from "../api/types";
import { QuestionIcon } from "../components/icons";
import { Card } from "../components/ui";
import { ProductImage } from "../results/ProductImage";

/** "Which milk did you mean?" with one tappable option per product. */
export function ClarifyPanel({
  question,
  answering,
  onAnswer,
}: {
  question: Question;
  answering: string | null;
  onAnswer: (itemIndex: number, sku: string) => void;
}) {
  return (
    <Card className="sf-clarify" aria-labelledby="sf-clarify-title">
      <h2 id="sf-clarify-title" className="sf-clarify__title">
        <QuestionIcon />
        Which “{question.item_text}” did you mean?
      </h2>
      <ul className="sf-clarify__options">
        {question.options.map((o) => (
          <li key={o.sku}>
            <button
              type="button"
              className="sf-option"
              disabled={answering !== null}
              aria-busy={answering === o.sku}
              onClick={() => onAnswer(question.item_index, o.sku)}
            >
              <ProductImage imageUrl={o.image_url} name={o.name} size={44} />
              <span className="sf-option__text">
                <span className="sf-option__name">{o.name}</span>
                <span className="sf-option__places">{o.places.join(" / ") || "No shelf location"}</span>
              </span>
              {answering === o.sku ? <span className="sf-option__busy">Choosing…</span> : null}
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
