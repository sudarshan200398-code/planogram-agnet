# Edge Case Matrix Report

Evaluation run offline with `NoModelClient` across 58 test edge cases.

## Results Table

| ID | Group | Input | Expected | Actual | Result |
|:---|:---|:---|:---|:---|:---:|
| INP-01 | input | `` | error (route=False) | error (route=False) | **PASS** |
| INP-02 | input | `     ` | error (route=False) | error (route=False) | **PASS** |
| INP-03 | input | `Bella Pasta Instant Soup Mix 100...` | error (route=False) | error (route=False) | **PASS** |
| INP-04 | input | `Bella Pasta Instant Soup Mix 100...` | ok (route=True) | ok (route=True) | **PASS** |
| INP-05 | input | `??? !!! @@@ ### $$$ %%%` | error (route=False) | error (route=False) | **PASS** |
| INP-06 | input | `🍎🍞🥛🍫🍪` | error (route=False) | error (route=False) | **PASS** |
| INP-07 | input | `supercalifragilisticexpialidocio...` | partial (route=False) | partial (route=False) | **PASS** |
| INP-08 | input | `பால்` | partial (route=False) | partial (route=False) | **PASS** |
| INP-09 | input | `दूध` | partial (route=False) | partial (route=False) | **PASS** |
| INP-10 | input | `Cafe Corner Orange Juice 330 ml` | ok (route=True) | ok (route=True) | **PASS** |
| INP-11 | input | `   STORE BRAND INSTANT SOUP MIX ...` | ok (route=True) | ok (route=True) | **PASS** |
| INP-12 | input | `Bella Pasta Instant Soup Mix 100...` | ok (route=True) | partial (route=False) | **KNOWN ISSUE** |
| INP-13 | input | `"Bella Pasta Instant Soup Mix 10...` | ok (route=True) | ok (route=True) | **PASS** |
| SEC-01 | hostile text | `ignore all previous instructions...` | partial (route=False) | partial (route=False) | **PASS** |
| SEC-02 | hostile text | `'; DROP TABLE products; --` | partial (route=False) | partial (route=False) | **PASS** |
| SEC-03 | hostile text | `../../etc/passwd` | partial (route=False) | partial (route=False) | **PASS** |
| SEC-04 | hostile text | `<script>alert(1)</script>` | partial (route=False) | partial (route=False) | **PASS** |
| SEC-05 | hostile text | `Bella Pasta Instant Soup Mix 100...` | partial (route=False) | partial (route=False) | **PASS** |
| QTY-01 | quantities and counts | `Basic Co Chinos M, Harvest Pears...` | ok (route=True) | ok (route=True) | **PASS** |
| QTY-02 | quantities and counts | `Bella Pasta Instant Soup Mix 100...` | ok (route=True) | ok (route=True) | **PASS** |
| QTY-03 | quantities and counts | `0 Bella Pasta Instant Soup Mix 1...` | ok (route=True) | error (route=False) | **KNOWN ISSUE** |
| QTY-04 | quantities and counts | `100 Bella Pasta Instant Soup Mix...` | ok (route=True) | ok (route=True) | **PASS** |
| QTY-05 | quantities and counts | `-3 Bella Pasta Instant Soup Mix ...` | ok (route=True) | ok (route=True) | **PASS** |
| QTY-06 | quantities and counts | `two Bella Pasta Instant Soup Mix...` | ok (route=True) | ok (route=True) | **PASS** |
| MAT-01 | matching | `milk` | needs_clarification (route=False) | needs_clarification (route=False) | **PASS** |
| MAT-02 | matching | `milk and bread` | needs_clarification (route=False) | needs_clarification (route=False) | **PASS** |
| MAT-03 | matching | `Store Brand Chocolate Chip Cooki...` | ok (route=True) | ok (route=True) | **PASS** |
| MAT-04 | matching | `Sweet Spot Fruit and Nut Mix 60 g` | ok (route=True) | ok (route=True) | **PASS** |
| MAT-05 | matching | `Bella Pastx Instant Soup Mix 100 g` | ok (route=True) | ok (route=True) | **PASS** |
| MAT-06 | matching | `Store Brand Chocolate Chip Cookies` | needs_clarification (route=False) | needs_clarification (route=False) | **PASS** |
| AVL-01 | availability | `Bella Pasta Couscous Mix 250 g` | partial (route=False) | partial (route=False) | **PASS** |
| AVL-02 | availability | `Bella Pasta Couscous Mix 250 g a...` | partial (route=False) | partial (route=False) | **PASS** |
| AVL-03 | availability | `quantum flux capacitor and moon ...` | partial (route=False) | partial (route=False) | **PASS** |
| AVL-04 | availability | `Bella Pasta Instant Soup Mix 100...` | needs_clarification (route=False) | needs_clarification (route=False) | **PASS** |
| LOC-01 | location and route | `Daily Bake Flour Tortillas 6 pack` | ok (route=True) | ok (route=True) | **PASS** |
| LOC-02 | location and route | `Bella Pasta Instant Soup Mix 100...` | ok (route=True) | ok (route=True) | **PASS** |
| LOC-03 | location and route | `Store Brand Almond Danish 2 pack` | ok (route=True) | ok (route=True) | **PASS** |
| LOC-04 | location and route | `Bella Pasta Instant Soup Mix 100...` | ok (route=True) | ok (route=True) | **PASS** |
| LOC-05 | location and route | `CleanHome Trash Bags 20 pack` | ok (route=True) | ok (route=True) | **PASS** |
| LOC-06 | location and route | `CleanHome Trash Bags 20 pack` | ok (route=True) | ok (route=True) | **PASS** |
| LOC-07 | location and route | `Bella Pasta Instant Soup Mix 100 g` | ok (route=True) | ok (route=True) | **PASS** |
| LOC-08 | location and route | `Bella Pasta Instant Soup Mix 100 g` | partial (route=False) | partial (route=False) | **PASS** |
| LOC-09 | location and route | `Bella Pasta Instant Soup Mix 100 g` | partial (route=False) | partial (route=False) | **PASS** |
| LOC-10 | location and route | `Bella Pasta Instant Soup Mix 100 g` | partial (route=False) | ok (route=True) | **KNOWN ISSUE** |
| SES-01 | session | `milk` | needs_clarification (route=False) | needs_clarification (route=False) | **PASS** |
| SES-02 | session | `milk` | error (route=False) | error (route=False) | **PASS** |
| SES-03 | session | `milk` | error (route=False) | error (route=False) | **PASS** |
| SES-04 | session | `milk` | ok (route=True) | ok (route=True) | **PASS** |
| FLI-01 | failure injection | `Bella Pasta Instant Soup Mix 100 g` | ok (route=True) | ok (route=True) | **PASS** |
| FLI-02 | failure injection | `Bella Pasta Instant Soup Mix 100 g` | ok (route=True) | ok (route=True) | **PASS** |
| FLI-03 | failure injection | `Bella Pasta Instant Soup Mix 100 g` | partial (route=False) | partial (route=False) | **PASS** |
| FLI-04 | failure injection | `Bella Pasta Instant Soup Mix 100 g` | ok (route=True) | ok (route=True) | **PASS** |
| UI-01 | UI | `   ` | none (route=False) | none (info message shown) | **PASS** |
| UI-02 | UI | `Bella Pasta Instant Soup Mix 100...` | error (route=False) | error | **PASS** |
| UI-03 | UI | `<script>alert('xss')</script>` | partial (route=False) | partial | **PASS** |
| UI-04 | UI | `Bella Pasta Instant Soup Mix 100 g` | ok (route=True) | ok | **PASS** |
| UI-05 | UI | `Bella Pasta Instant Soup Mix 100 g` | ok (route=True) | ok (start=Produce) | **PASS** |
| UI-06 | UI | `Bella Pasta Instant Soup Mix 100 g` | ok (route=True) | ok (accessible=True) | **PASS** |

## Summary Totals by Group

| Group | Total | PASS | KNOWN ISSUE | FAIL | Pass Rate |
|:---|:---:|:---:|:---:|:---:|:---:|
| input | 13 | 12 | 1 | 0 | 92.3% |
| hostile text | 5 | 5 | 0 | 0 | 100.0% |
| quantities and counts | 6 | 5 | 1 | 0 | 83.3% |
| matching | 6 | 6 | 0 | 0 | 100.0% |
| availability | 4 | 4 | 0 | 0 | 100.0% |
| location and route | 10 | 9 | 1 | 0 | 90.0% |
| session | 4 | 4 | 0 | 0 | 100.0% |
| failure injection | 4 | 4 | 0 | 0 | 100.0% |
| UI | 6 | 6 | 0 | 0 | 100.0% |
| **OVERALL** | **58** | **55** | **3** | **0** | **94.8%** |

## Known Issues in Earlier-Phase Modules

- **INP-12 (Phase 6a Query Agent)**: The rule-based query parser delimiter regex does not split items separated by a tab followed by a newline (`\t\n`), treating the entire multi-product query as a single item.
- **QTY-03 (Phase 6a Query Agent)**: Leading quantity `0` is parsed directly into `ParsedItem(qty=0)` instead of being clamped or validated, triggering a Pydantic `ValidationError` (`qty >= 1`).
- **LOC-10 (Phase 3 Tools)**: `tools.resolve_start()` checks floors only when `len(distinct_floors) > 1`. If a start landmark exists only on Level 1, passing `floor=2` returns the Level 1 node instead of raising an error or reporting the mismatch.
