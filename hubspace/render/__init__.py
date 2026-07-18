"""HTML rendering: markdown, data tables, and served-page chrome."""
from .columns import _detect_col_types, _fmt_cell
from .markdown import _inline, _render_md, _add_outline
from .tabular import _rows_to_table, _render_csv, _render_xlsx
from .page import (
    _favicon_href, _inject_into_html, _render_lineage_html, _CSS, _PAGE,
    _LINEAGE_ORDER, _LINEAGE_LABELS, _BACKLINKS_CSS, _DOC_CHROME_CSS, _DOC_PRINT_BTN,
    doc_menu, DOC_PDF_ITEM,
)
from .draw import draw_page_html
