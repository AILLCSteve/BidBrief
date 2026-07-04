"""
Mobile-first sizing for every BidBrief Excel export.

The primary reader is the iOS app's QuickLook preview on a phone: wide desktop
columns force endless horizontal panning there. Desktop Excel users can resize
freely, so phone-friendly defaults cost nothing on desktop.

Applied by all generators (analysis dashboard, BestPrep, Smart Analysis,
CityScraper) right before the workbook is saved.
"""

from openpyxl.styles import Alignment

# Max column width (openpyxl width units ≈ characters). ~42 keeps two columns
# readable side-by-side on a phone in portrait without desktop feeling cramped.
MAX_COL_WIDTH = 42
DEFAULT_COL_WIDTH = 24


def mobile_optimize(wb):
    """Clamp column widths, wrap clamped columns, and set fit-to-width printing."""
    for ws in wb.worksheets:
        clamped_cols = set()
        for letter, dim in list(ws.column_dimensions.items()):
            if dim.width and dim.width > MAX_COL_WIDTH:
                dim.width = MAX_COL_WIDTH
                clamped_cols.add(letter)

        # Text that used to fit a wide column must wrap in the clamped one.
        for letter in clamped_cols:
            for cell in ws[letter]:
                if cell.value is None:
                    continue
                current = cell.alignment or Alignment()
                if not current.wrap_text:
                    cell.alignment = Alignment(
                        horizontal=current.horizontal,
                        vertical=current.vertical or 'top',
                        wrap_text=True,
                        indent=current.indent or 0,
                    )

        # Phone-friendly view + print defaults.
        ws.sheet_view.zoomScale = 100
        ws.page_setup.orientation = 'portrait'
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
    return wb
