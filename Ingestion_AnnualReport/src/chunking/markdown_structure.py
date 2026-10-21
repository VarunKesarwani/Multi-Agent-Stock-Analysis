"""Shared Markdown structure extraction from the annual-report notebook."""

import re


def clean_heading(text):
    """
    Remove common Markdown formatting from heading text.
    Example:
        **About Tata Steel** -> About Tata Steel
    """
    text = text.strip()

    text = re.sub(r"^\*\*(.*?)\*\*$", r"\1", text)
    text = re.sub(r"^__(.*?)__$", r"\1", text)

    return text.strip()


def parse_markdown_structure(markdown_content):
    """
    Parse Markdown into RAG-friendly structured blocks.

    Block types:
        - text
        - table

    Each content block contains:
        - section       -> latest H1
        - heading       -> nearest heading
        - heading_level -> Markdown level of nearest heading
        - text

    Heading blocks themselves are not returned.
    """

    lines = markdown_content.splitlines()

    blocks = []

    current_section = None
    current_heading = None
    current_heading_level = None

    current_text = []

    def flush_text():

        nonlocal current_text

        if not current_text:
            return

        text = "\n".join(current_text).strip()

        if not text:
            current_text = []
            return

        blocks.append(
            {
                "type": "text",
                "section": current_section,
                "heading": current_heading,
                "heading_level": current_heading_level,
                "text": text,
            }
        )

        current_text = []

    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # ---------------------------------------------------------
        # Empty line
        # ---------------------------------------------------------
        if not line:
            if current_text:
                current_text.append("")

            i += 1
            continue

        # ---------------------------------------------------------
        # Heading
        # ---------------------------------------------------------
        heading_match = re.match(r"^(#{1,6})\s+(.*)$", line)

        if heading_match:
            flush_text()

            level = len(heading_match.group(1))
            heading = clean_heading(heading_match.group(2))

            # H1 becomes the main section
            if level == 1:
                current_section = heading
                current_heading = heading
                current_heading_level = level

            else:
                current_heading = heading
                current_heading_level = level

            i += 1
            continue

        # ---------------------------------------------------------
        # Markdown table
        # ---------------------------------------------------------
        is_table = (
            line.startswith("|")
            and i + 1 < len(lines)
            and re.match(r"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?$", lines[i + 1].strip())
        )

        if is_table:
            flush_text()

            table_lines = []

            while i < len(lines):
                table_line = lines[i].strip()

                if not table_line.startswith("|"):
                    break

                table_lines.append(table_line)

                i += 1

            table_text = "\n".join(table_lines)

            blocks.append(
                {
                    "type": "table",
                    "section": current_section,
                    "heading": current_heading,
                    "heading_level": current_heading_level,
                    "text": table_text,
                }
            )

            continue

        # ---------------------------------------------------------
        # Normal text
        # ---------------------------------------------------------
        current_text.append(line)

        i += 1

    # Flush remaining text
    flush_text()

    return blocks
