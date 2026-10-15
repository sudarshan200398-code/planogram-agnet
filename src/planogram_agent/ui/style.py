"""The page's one CSS block. Colours and font come from .streamlit/config.toml; this only shapes layout."""

CSS = """
<style>
.block-container { max-width: 1180px; padding-top: 3.75rem; padding-bottom: 2rem; }
.st-key-topbar { background: #FFFFFF; border: 1px solid #D9E0E3; border-radius: 0.75rem;
  padding: 0.85rem 1.25rem; margin-bottom: 0.5rem; }
.st-key-topbar h1 { font-size: 1.6rem; font-weight: 700; padding: 0; margin: 0; color: #0F5257; }
.st-key-topbar [data-testid="stCaptionContainer"] { margin-top: -0.25rem; font-size: 0.95rem; }
.st-key-search_card, [class*="st-key-card_"], .st-key-route_panel, .st-key-howto, .st-key-clarify {
  background: #FFFFFF; }
[class*="st-key-card_"] p { margin-bottom: 0.15rem; }
[data-testid="stMetric"] { background: #F5F7F8; border: 1px solid #D9E0E3; border-radius: 0.6rem;
  padding: 0.6rem 0.9rem; }
[data-testid="stMetricValue"] { font-size: 1.5rem; color: #0F5257; }
.st-key-footer { border-top: 1px solid #D9E0E3; margin-top: 1.5rem; padding-top: 0.5rem; }
</style>
"""
