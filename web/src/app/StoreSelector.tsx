import type { StoreSummary } from "../api/types";

/** Store picker: a native select, which is the most usable control on phones and with screen readers. */
export function StoreSelector({
  stores,
  value,
  onChange,
}: {
  stores: StoreSummary[];
  value: string | null;
  onChange: (id: string) => void;
}) {
  return (
    <label className="sf-store">
      <span className="sf-store__label">Store</span>
      <select className="sf-store__select" value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
        {stores.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </select>
    </label>
  );
}
