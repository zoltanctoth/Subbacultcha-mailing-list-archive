#!/usr/bin/env python3
"""Convert Subbacultcha mailing list HTML archives to clean Markdown files."""

import os
import re
import html
import glob

REPO_DIR = os.path.dirname(os.path.abspath(__file__))

# Windows-1252 C1 control codes that browsers interpret as printable chars
WIN1252_MAP = {
    132: '„',
    146: '\u2019',  # right single quote '
    148: '\u201D',  # right double quote "
    150: '–',       # en dash
}

# ISO-8859-2 chars that were misinterpreted as ISO-8859-1.
# In ISO-8859-2: 0xF5=ő, 0xD5=Ő, 0xFB=ű, 0xDB=Ű
# In ISO-8859-1: 0xF5=õ, 0xD5=Õ, 0xFB=û, 0xDB=Û
ISO2_FIXUP = {
    245: 'ő',   # &#245; õ → ő
    213: 'Ő',   # &#213; Õ → Ő
    251: 'ű',   # &#251; û → ű
    219: 'Ű',   # &#219; Û → Ű
}

# Combined: all numeric entities that need special handling before html.unescape
SPECIAL_NUMERIC = {**WIN1252_MAP, **ISO2_FIXUP}


def fix_numeric_entities(text):
    """Replace numeric HTML entities that need special handling."""
    def replacer(m):
        code = int(m.group(1))
        if code in SPECIAL_NUMERIC:
            return SPECIAL_NUMERIC[code]
        return m.group(0)
    return re.sub(r'&#(\d+);', replacer, text)


def convert_links(text):
    """Convert <A HREF="url">text</A> to markdown-style links or plain URLs."""
    def link_replacer(m):
        url = m.group(1)
        link_text = m.group(2).strip()
        # If link text is basically the URL, just output the URL
        if link_text.replace('http://', '').replace('https://', '').rstrip('/') == \
           url.replace('http://', '').replace('https://', '').rstrip('/'):
            return url
        # For mailto-style display text like "subbacultcha at freemail.hu"
        if 'mailman/listinfo' in url:
            return link_text
        return f'[{link_text}]({url})'
    return re.sub(r'<A HREF="([^"]*)"[^>]*>(.*?)</A>', link_replacer, text, flags=re.DOTALL)


def strip_header(text):
    """Remove the newsletter header boilerplate and subscribe/unsubscribe lines."""
    lines = text.split('\n')

    # Find the end of the header block.
    # Strategy: find the last "Írjatok le:" line (subscribe/unsubscribe),
    # then skip past it and any blank lines that follow.
    last_subscribe_idx = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('Írjatok le:') or stripped.startswith('Irjatok le:'):
            last_subscribe_idx = i
        # Also catch "Írjatok fel:" without a matching "le:" on a separate line
        if stripped.startswith('Írjatok fel:') or stripped.startswith('Irjatok fel:'):
            # Mark this but keep looking for "le:" which usually follows
            if last_subscribe_idx < 0:
                last_subscribe_idx = i

    if last_subscribe_idx >= 0:
        # Skip past subscribe lines, any mailto continuations, and blank lines
        start = last_subscribe_idx + 1
        while start < len(lines):
            stripped = lines[start].strip()
            # Skip blank lines, mailto URL continuations, and stray "subject=" lines
            if (stripped == '' or
                stripped.startswith('subject=') or
                stripped.startswith('mailto:') or
                stripped.startswith('Írjatok fel:') or
                stripped.startswith('Irjatok fel:')):
                start += 1
            else:
                break
        lines = lines[start:]
    else:
        # No subscribe lines found; try to strip asterisk/ASCII-art header
        # Find the header end: look for the first ___ separator or content line
        # after the banner (asterisks or ASCII art + dashes)
        header_end = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Skip asterisk lines, dash lines, ASCII art, and the SUBBACULTCHA/issue lines
            if (stripped == '' or
                re.match(r'^[\*]+$', stripped) or
                re.match(r'^[-]+$', stripped) or
                re.match(r'^[,\-\.\|\'\s_/\\]+$', stripped) or
                'SUBBACULTCHA' in stripped.upper() or
                'popkulturális megmondó' in stripped or
                'popkultur&#225;lis megmond' in stripped or
                re.match(r'^[IVX]+\.\s+évfolyam', stripped)):
                header_end = i + 1
            else:
                break
        if header_end > 0:
            lines = lines[header_end:]

    return '\n'.join(lines)


def convert_html_to_md(html_content):
    """Extract and convert the article content from a pipermail HTML file."""
    # Extract content between beginarticle/endarticle markers
    match = re.search(
        r'<!--beginarticle-->\s*<PRE>(.*?)</PRE>\s*<!--endarticle-->',
        html_content, re.DOTALL
    )
    if not match:
        return None

    content = match.group(1)

    # Fix double-encoded entities: &amp;Otilde; → Ő, &amp;otilde; → ő, etc.
    content = content.replace('&amp;Otilde;', 'Ő')
    content = content.replace('&amp;otilde;', 'ő')
    content = content.replace('&amp;Ucirc;', 'Ű')
    content = content.replace('&amp;ucirc;', 'ű')

    # Convert HTML links to plain URLs / markdown links
    content = convert_links(content)

    # Fix special numeric entities (Windows-1252 + ISO-8859-2 corrections)
    content = fix_numeric_entities(content)

    # Unescape all remaining standard HTML entities (&#233; → é, &quot; → ", etc.)
    content = html.unescape(content)

    # Post-unescape: fix any remaining ISO-8859-2 chars that came from named entities
    # (e.g. &otilde; → õ should be ő)
    content = content.replace('õ', 'ő')
    content = content.replace('Õ', 'Ő')
    content = content.replace('û', 'ű')
    content = content.replace('Û', 'Ű')

    # Strip the newsletter header/subscribe boilerplate
    content = strip_header(content)

    # Strip leading/trailing whitespace
    content = content.strip()

    return content


def process_file(html_path, output_dir):
    """Process a single HTML file and write the markdown output."""
    with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
        html_content = f.read()

    md_content = convert_html_to_md(html_content)
    if md_content is None:
        return False

    basename = os.path.splitext(os.path.basename(html_path))[0]
    md_path = os.path.join(output_dir, f'{basename}.md')

    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content + '\n')

    return True


def main():
    import sys

    # Allow processing a single file for testing
    if len(sys.argv) > 1 and sys.argv[1] == '--single':
        html_path = sys.argv[2]
        with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
            html_content = f.read()
        md = convert_html_to_md(html_content)
        if md:
            print(md)
        else:
            print("No article content found.", file=sys.stderr)
        return

    # Process all newsletter HTML files
    output_base = os.path.join(REPO_DIR, 'markdown')
    total = 0
    converted = 0

    # Find all month directories (YYYY-Month pattern)
    for entry in sorted(os.listdir(REPO_DIR)):
        dir_path = os.path.join(REPO_DIR, entry)
        if not os.path.isdir(dir_path):
            continue
        if not re.match(r'\d{4}-\w+', entry):
            continue

        # Find numbered HTML files (the actual newsletters)
        html_files = sorted(glob.glob(os.path.join(dir_path, '[0-9]*.html')))
        if not html_files:
            continue

        out_dir = os.path.join(output_base, entry)
        os.makedirs(out_dir, exist_ok=True)

        for html_file in html_files:
            total += 1
            if process_file(html_file, out_dir):
                converted += 1
                print(f'  ✓ {entry}/{os.path.basename(html_file)} → .md')
            else:
                print(f'  ✗ {entry}/{os.path.basename(html_file)} (no article found)')

    print(f'\nDone: {converted}/{total} files converted.')
    print(f'Output: {output_base}/')


if __name__ == '__main__':
    main()
