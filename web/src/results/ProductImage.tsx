import { useState } from "react";
import { imageSrc } from "../api/client";
import { initialsOf } from "../lib/format";

/** Lazy-loaded product picture; if it fails to load, a tile with the product's initials takes its place. */
export function ProductImage({ imageUrl, name, size = 72 }: { imageUrl: string | null | undefined; name: string; size?: number }) {
  const [failed, setFailed] = useState(false);
  if (!imageUrl || failed) {
    return (
      <span className="sf-thumb sf-thumb--fallback" style={{ width: size, height: size }} aria-hidden="true" data-testid="image-fallback">
        {initialsOf(name)}
      </span>
    );
  }
  return (
    <img
      className="sf-thumb"
      src={imageSrc(imageUrl)}
      alt=""
      width={size}
      height={size}
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
    />
  );
}
