"""Product matching and fuzzy search using RapidFuzz."""
from __future__ import annotations

import re
import unicodedata
import weakref
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field
from rapidfuzz import fuzz

from .data_loader import Dataset
from .settings import Settings


class Candidate(BaseModel):
    sku: str
    name: str
    score: float


class MatchDecision(BaseModel):
    status: Literal["matched", "ambiguous", "not_found"]
    candidates: list[Candidate] = Field(default_factory=list)


def stem_word(w: str) -> str:
    """Simple English plural stemming."""
    if len(w) <= 3:
        return w
    if w.endswith("ies") and len(w) > 4:
        if w == "cookies":
            return "cookie"
        return w[:-3] + "y"
    if w.endswith("es") and len(w) > 4:
        if w.endswith(("shes", "ches", "sses", "xes", "zes")):
            return w[:-2]
        return w[:-1]
    if w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def normalize_text(text: str) -> str:
    """Normalize text: lowercase, remove accents, standardize unit spacing, remove punctuation, stem plurals."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    # Units spacing: e.g. "500g" -> "500 g", "2l" -> "2 l", "6pack" -> "6 pack"
    t = re.sub(r'(\d+)\s*(g|kg|ml|l|pack|cm|m)\b', r'\1 \2', t)
    # Remove punctuation, keeping alphanumerics
    t = re.sub(r'[^a-z0-9\s]', ' ', t)
    # Stem simple plurals
    words = [stem_word(w) for w in t.split()]
    return " ".join(words)


@dataclass
class IndexedProduct:
    sku: str
    name: str
    brand: str
    size: str
    norm_name: str
    norm_brand: str
    norm_size: str
    norm_keywords: list[str]
    candidate_texts: list[str]
    all_words: set[str]


class SearchIndex:
    """In-memory search index built once per dataset."""
    def __init__(self, dataset: Dataset):
        self.indexed: list[IndexedProduct] = []
        self.word_to_skus: dict[str, set[str]] = {}
        self.known_brands: set[str] = set()
        self.known_sizes: set[str] = set()
        self.norm_name_to_skus: dict[str, list[str]] = {}

        for p in dataset.products:
            n_name = normalize_text(p.name)
            self.norm_name_to_skus.setdefault(n_name, []).append(p.sku)
            n_brand = normalize_text(p.brand or "")
            n_size = normalize_text(p.size or "")
            n_cat = normalize_text(p.category or "")
            # Keywords excluding redundant category name
            n_kws = [normalize_text(k) for k in p.keywords if k and normalize_text(k) != n_cat]

            if n_brand:
                self.known_brands.add(n_brand)
            if n_size:
                self.known_sizes.add(n_size)

            c_texts = [n_name]
            if n_brand and n_name.startswith(n_brand):
                unbranded = n_name[len(n_brand):].strip()
                if unbranded:
                    c_texts.append(unbranded)

            for kw in n_kws:
                bks = " ".join([part for part in [n_brand, kw, n_size] if part])
                if bks:
                    c_texts.append(bks)
                ks = " ".join([part for part in [kw, n_size] if part])
                if ks:
                    c_texts.append(ks)
                c_texts.append(kw)

            # Deduplicate candidate texts preserving order
            seen_t: set[str] = set()
            dedup_texts: list[str] = []
            for t in c_texts:
                if t and t not in seen_t:
                    seen_t.add(t)
                    dedup_texts.append(t)

            all_w = set(n_name.split())
            if n_brand:
                all_w.update(n_brand.split())
            if n_size:
                all_w.update(n_size.split())
            for kw in n_kws:
                all_w.update(kw.split())

            for w in all_w:
                if len(w) > 1:
                    self.word_to_skus.setdefault(w, set()).add(p.sku)

            self.indexed.append(IndexedProduct(
                sku=p.sku,
                name=p.name,
                brand=p.brand or "",
                size=p.size or "",
                norm_name=n_name,
                norm_brand=n_brand,
                norm_size=n_size,
                norm_keywords=n_kws,
                candidate_texts=dedup_texts,
                all_words=all_w,
            ))


_DATASET_INDEX_CACHE: dict[int, tuple[weakref.ref[Dataset], SearchIndex]] = {}


def get_search_index(dataset: Dataset) -> SearchIndex:
    """Retrieve or build the SearchIndex for a dataset instance."""
    ds_id = id(dataset)
    if ds_id in _DATASET_INDEX_CACHE:
        stored_ref, index = _DATASET_INDEX_CACHE[ds_id]
        if stored_ref() is dataset:
            return index

    index = SearchIndex(dataset)

    def _cleanup(_ref: weakref.ref, key: int = ds_id) -> None:
        _DATASET_INDEX_CACHE.pop(key, None)

    _DATASET_INDEX_CACHE[ds_id] = (weakref.ref(dataset, _cleanup), index)
    return index


def clear_dataset_index_cache(dataset: Dataset | None = None) -> None:
    """Clear cached search index for a dataset, or all datasets if None."""
    if dataset is None:
        _DATASET_INDEX_CACHE.clear()
    else:
        _DATASET_INDEX_CACHE.pop(id(dataset), None)


_GENERIC_SIZE_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\s*[a-z]+\b")


def has_size_narrowing(norm_q: str, known_sizes: set[str]) -> bool:
    """Detect if normalized query specifies a size.

    Uses sizes found in data (known_sizes) and a generic pattern for a number
    followed by a unit word (digits, optional decimal, letters).
    """
    if _GENERIC_SIZE_PATTERN.search(norm_q):
        return True
    for s in known_sizes:
        if s and re.search(rf"\b{re.escape(s)}\b", norm_q):
            return True
    return False


def search_products(text: str, top_k: int, dataset: Dataset) -> list[Candidate]:
    """Search products using rapidfuzz, returning candidates scored between 0 and 1 (best first)."""
    norm_q = normalize_text(text)
    if not norm_q:
        return []

    index = get_search_index(dataset)
    q_words = norm_q.split()
    results: list[tuple[str, str, float]] = []

    # Detect if query specifies a size
    query_has_size = has_size_narrowing(norm_q, index.known_sizes)

    for p in index.indexed:
        # Check query words match in product words (exact or typo >= 80)
        matched_words = 0
        for qw in q_words:
            if qw in p.all_words or any(fuzz.ratio(qw, pw) >= 80 for pw in p.all_words):
                matched_words += 1

        if matched_words == 0:
            results.append((p.sku, p.name, 0.0))
            continue

        best_score = 0.0
        for cand_text in p.candidate_texts:
            cand_words = cand_text.split()
            # If query has multiple words, prevent single short keyword token_sort inflation
            if len(q_words) >= 2 and len(cand_words) == 1 and cand_text != norm_q:
                continue

            r1 = fuzz.ratio(norm_q, cand_text)
            r2 = fuzz.token_sort_ratio(norm_q, cand_text)
            score_cand = max(r1, r2)
            best_score = max(best_score, score_cand)

        # Penalize if some query words are completely missing from the product
        missing_count = len(q_words) - matched_words
        if missing_count > 0:
            best_score = best_score * (0.85 ** missing_count)

        # Size constraint: penalize if query specified a size and product has a different size
        if query_has_size and p.norm_size:
            if re.search(rf"\b{re.escape(p.norm_size)}\b", norm_q):
                pass
            else:
                best_score = best_score * 0.65

        final_score = round(min(1.0, best_score / 100.0), 4)
        results.append((p.sku, p.name, final_score))

    results.sort(key=lambda x: x[2], reverse=True)
    return [Candidate(sku=sku, name=name, score=score) for sku, name, score in results[:top_k]]


def decide_match(
    candidates: list[Candidate],
    settings: Settings,
    dataset: Dataset,
    query: str = "",
) -> MatchDecision:
    """Decide match status: matched, ambiguous, or not_found using settings thresholds."""
    if not candidates or candidates[0].score < settings.ask_threshold:
        return MatchDecision(status="not_found", candidates=[])

    # Ambiguous candidate pool: only items at or above ask_threshold, up to 3
    ambiguous_pool = [c for c in candidates if c.score >= settings.ask_threshold][:3]

    index = get_search_index(dataset)
    norm_q = normalize_text(query)

    # Exact full-name match check:
    # If the normalised query equals exactly one candidate's normalised full name,
    # the result is matched with that candidate, whatever the margin.
    # If two or more products share the same normalised name, it stays ambiguous.
    if norm_q and norm_q in index.norm_name_to_skus:
        exact_skus = index.norm_name_to_skus[norm_q]
        if len(exact_skus) == 1:
            exact_sku = exact_skus[0]
            exact_cand = next((c for c in candidates if c.sku == exact_sku), None)
            if exact_cand is None:
                p_match = next((p for p in dataset.products if p.sku == exact_sku), None)
                p_name = p_match.name if p_match else ""
                exact_cand = Candidate(sku=exact_sku, name=p_name, score=1.0)
            return MatchDecision(status="matched", candidates=[exact_cand])
        elif len(exact_skus) >= 2:
            return MatchDecision(status="ambiguous", candidates=ambiguous_pool)

    q_words = norm_q.split()

    # Data-driven generic words rule:
    # If the normalised query has no brand or size narrowing it, and 2 or more different products
    # contain its words in their names or keywords, the result is ambiguous.
    has_brand = False
    for b in index.known_brands:
        if b and b in norm_q:
            has_brand = True
            break

    has_size = has_size_narrowing(norm_q, index.known_sizes)

    if not has_brand and not has_size:
        matching_skus: set[str] = set()
        for w in q_words:
            if w in index.word_to_skus:
                matching_skus.update(index.word_to_skus[w])
        if len(matching_skus) >= 2:
            return MatchDecision(status="ambiguous", candidates=ambiguous_pool)

    top_score = candidates[0].score
    accept_th = settings.accept_threshold
    margin = settings.margin

    if top_score >= accept_th:
        if len(candidates) >= 2:
            second_score = candidates[1].score
            if (top_score - second_score) >= margin:
                return MatchDecision(status="matched", candidates=[candidates[0]])
            else:
                return MatchDecision(status="ambiguous", candidates=ambiguous_pool)
        else:
            return MatchDecision(status="matched", candidates=[candidates[0]])
    else:
        return MatchDecision(status="ambiguous", candidates=ambiguous_pool)
