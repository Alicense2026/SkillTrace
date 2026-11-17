from __future__ import annotations

import argparse
from pathlib import Path

from docx import Document
from docx.document import Document as DocumentObject
from docx.table import Table
from docx.text.paragraph import Paragraph


def iter_blocks(doc: DocumentObject):
    for child in doc.element.body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, doc)
        elif child.tag.endswith("}tbl"):
            yield Table(child, doc)


def paragraph_text(paragraph: Paragraph) -> str:
    style = paragraph.style.name if paragraph.style else ""
    text = paragraph.text.strip()
    if not text:
        return ""
    return f"[{style}] {text}"


def table_text(table: Table, index: int) -> str:
    lines = [f"[TABLE {index}]"]
    for row_index, row in enumerate(table.rows, start=1):
        cells = []
        for cell in row.cells:
            value = " ".join(cell.text.split())
            cells.append(value)
        lines.append(f"R{row_index}: " + " | ".join(cells))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--out")
    args = parser.parse_args()

    path = Path(args.input)
    doc = Document(path)
    table_index = 0
    blocks: list[str] = []
    for block in iter_blocks(doc):
        if isinstance(block, Paragraph):
            text = paragraph_text(block)
            if text:
                blocks.append(text)
        elif isinstance(block, Table):
            table_index += 1
            blocks.append(table_text(block, table_index))

    output = "\n".join(
        [
            f"FILE: {path}",
            f"PARAGRAPHS: {len(doc.paragraphs)}",
            f"TABLES: {len(doc.tables)}",
            f"INLINE_SHAPES: {len(doc.inline_shapes)}",
            *blocks,
        ]
    )
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
