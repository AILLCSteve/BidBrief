"""
BestPrep Excel Export - Comprehensive answer format with all fragments and footnotes.
"""
import io
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


class BestPrepExcelGenerator:
    """Generate exhaustive Excel report for BestPrep mode."""

    # Colors
    NAVY = "1E3A8A"
    BLUE = "5B7FCC"
    GREEN = "22C55E"
    GRAY = "F3F4F6"

    def __init__(self, analysis_result: dict, accumulator_data: dict):
        self.result = analysis_result
        self.accumulator = accumulator_data
        self.wb = Workbook()

    def generate(self) -> io.BytesIO:
        """Generate 5-sheet BestPrep report."""
        if 'Sheet' in self.wb.sheetnames:
            del self.wb['Sheet']

        self._create_summary_sheet()      # Sheet 1: Overview
        self._create_answers_sheet()      # Sheet 2: Synthesized Answers
        self._create_fragments_sheet()    # Sheet 3: All Fragments
        self._create_footnotes_sheet()    # Sheet 4: All Footnotes
        self._create_sources_sheet()      # Sheet 5: Page Index

        output = io.BytesIO()
        self.wb.save(output)
        output.seek(0)
        return output

    def _create_summary_sheet(self):
        """Sheet 1: Analysis summary and statistics."""
        ws = self.wb.create_sheet("Summary", 0)
        ws.column_dimensions['A'].width = 30
        ws.column_dimensions['B'].width = 50

        stats = self.accumulator.get('statistics', {})

        data = [
            ("BestPrep Analysis Summary", ""),
            ("", ""),
            ("Generated", datetime.now().strftime("%Y-%m-%d %H:%M")),
            ("", ""),
            ("Total Questions", stats.get('total_questions', 0)),
            ("Questions Answered", stats.get('questions_with_answers', 0)),
            ("Questions Synthesized", stats.get('questions_synthesized', 0)),
            ("Total Fragments Collected", stats.get('total_fragments', 0)),
            ("Total Footnotes Extracted", stats.get('total_footnotes', 0)),
            ("Windows Processed", stats.get('windows_processed', 0)),
            ("Avg Fragments/Question", f"{stats.get('avg_fragments_per_question', 0):.1f}"),
            ("Avg Footnotes/Question", f"{stats.get('avg_footnotes_per_question', 0):.1f}"),
        ]

        for row_idx, (label, value) in enumerate(data, 1):
            ws.cell(row_idx, 1, label)
            ws.cell(row_idx, 2, value)

        # Style header
        ws.cell(1, 1).font = Font(size=16, bold=True, color=self.NAVY)

    def _create_answers_sheet(self):
        """Sheet 2: Final synthesized answers."""
        ws = self.wb.create_sheet("Synthesized Answers", 1)

        headers = ["#", "Question", "Synthesized Answer", "Sources", "Fragments", "Footnotes"]
        col_widths = [5, 40, 80, 15, 10, 10]

        for col, (header, width) in enumerate(zip(headers, col_widths), 1):
            ws.cell(1, col, header)
            ws.cell(1, col).font = Font(bold=True, color="FFFFFF")
            ws.cell(1, col).fill = PatternFill("solid", fgColor=self.NAVY)
            ws.column_dimensions[get_column_letter(col)].width = width

        row = 2
        for qid, ca_data in self.accumulator.get('cumulative_answers', {}).items():
            ws.cell(row, 1, row - 1)
            ws.cell(row, 2, ca_data.get('question_text', ''))
            ws.cell(row, 2).alignment = Alignment(wrap_text=True, vertical='top')

            # Use synthesized answer if available, else concatenate fragments
            synthesized = ca_data.get('synthesized_answer')
            if not synthesized:
                fragments = ca_data.get('fragments', [])
                if fragments:
                    synthesized = "\n\n---\n\n".join([f.get('text', '') for f in fragments])
                else:
                    synthesized = "No answer found"

            ws.cell(row, 3, synthesized)
            ws.cell(row, 3).alignment = Alignment(wrap_text=True, vertical='top')
            ws.cell(row, 4, ', '.join(map(str, ca_data.get('all_pages', []))))
            ws.cell(row, 5, ca_data.get('fragment_count', 0))
            ws.cell(row, 6, ca_data.get('footnote_count', 0))

            # Dynamic row height based on answer length
            answer_len = len(synthesized) if synthesized else 0
            ws.row_dimensions[row].height = max(30, min(300, (answer_len // 80) * 15))

            row += 1

    def _create_fragments_sheet(self):
        """Sheet 3: All individual answer fragments."""
        ws = self.wb.create_sheet("All Fragments", 2)

        headers = ["Fragment ID", "Question ID", "Window", "Pages", "Confidence", "Expert", "Fragment Text"]
        col_widths = [12, 15, 8, 15, 10, 25, 80]

        for col, (header, width) in enumerate(zip(headers, col_widths), 1):
            ws.cell(1, col, header)
            ws.cell(1, col).font = Font(bold=True, color="FFFFFF")
            ws.cell(1, col).fill = PatternFill("solid", fgColor=self.BLUE)
            ws.column_dimensions[get_column_letter(col)].width = width

        row = 2
        for qid, ca_data in self.accumulator.get('cumulative_answers', {}).items():
            for frag in ca_data.get('fragments', []):
                ws.cell(row, 1, frag.get('fragment_id', ''))
                ws.cell(row, 2, qid)
                ws.cell(row, 3, frag.get('window_index', 0))
                ws.cell(row, 4, ', '.join(map(str, frag.get('pages', []))))
                ws.cell(row, 5, f"{frag.get('confidence', 0):.0%}")
                ws.cell(row, 6, frag.get('expert_name', ''))
                ws.cell(row, 7, frag.get('text', ''))
                ws.cell(row, 7).alignment = Alignment(wrap_text=True, vertical='top')
                row += 1

    def _create_footnotes_sheet(self):
        """Sheet 4: All individual footnotes with quotes."""
        ws = self.wb.create_sheet("All Footnotes", 3)

        headers = ["Footnote ID", "Question ID", "Page", "Quote", "Window", "Fragment ID"]
        col_widths = [12, 15, 8, 80, 8, 12]

        for col, (header, width) in enumerate(zip(headers, col_widths), 1):
            ws.cell(1, col, header)
            ws.cell(1, col).font = Font(bold=True, color="FFFFFF")
            ws.cell(1, col).fill = PatternFill("solid", fgColor=self.GREEN)
            ws.column_dimensions[get_column_letter(col)].width = width

        row = 2
        for qid, ca_data in self.accumulator.get('cumulative_answers', {}).items():
            for fn in ca_data.get('footnotes', []):
                ws.cell(row, 1, fn.get('footnote_id', ''))
                ws.cell(row, 2, qid)
                ws.cell(row, 3, fn.get('page', 0))
                ws.cell(row, 4, fn.get('quote', ''))
                ws.cell(row, 4).alignment = Alignment(wrap_text=True, vertical='top')
                ws.cell(row, 5, fn.get('window_index', 0))
                ws.cell(row, 6, fn.get('fragment_id', ''))
                row += 1

    def _create_sources_sheet(self):
        """Sheet 5: Page index showing which questions reference each page."""
        ws = self.wb.create_sheet("Page Index", 4)

        # Build page -> questions mapping
        page_map = {}
        for qid, ca_data in self.accumulator.get('cumulative_answers', {}).items():
            for page in ca_data.get('all_pages', []):
                if page not in page_map:
                    page_map[page] = []
                if qid not in page_map[page]:
                    page_map[page].append(qid)

        headers = ["Page", "Questions Referencing This Page", "Reference Count"]
        col_widths = [10, 80, 15]

        for col, (header, width) in enumerate(zip(headers, col_widths), 1):
            ws.cell(1, col, header)
            ws.cell(1, col).font = Font(bold=True, color="FFFFFF")
            ws.cell(1, col).fill = PatternFill("solid", fgColor=self.NAVY)
            ws.column_dimensions[get_column_letter(col)].width = width

        row = 2
        for page in sorted(page_map.keys()):
            ws.cell(row, 1, page)
            ws.cell(row, 2, ', '.join(page_map[page]))
            ws.cell(row, 2).alignment = Alignment(wrap_text=True)
            ws.cell(row, 3, len(page_map[page]))
            row += 1
