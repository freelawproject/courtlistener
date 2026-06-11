import re
import os

def markdown_to_html(md_content):
    # Standard HTML wrapper with premium styling
    html_template = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Integration Proposal: U.S. Code Link Service</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
    <style>
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #24292f;
            max-width: 850px;
            margin: 40px auto;
            padding: 0 20px;
            background-color: #ffffff;
        }
        h1, h2, h3, h4 {
            color: #1f2328;
            font-weight: 600;
            margin-top: 24px;
            margin-bottom: 16px;
            line-height: 1.25;
        }
        h1 { font-size: 2em; border-bottom: 1px solid #d0d7de; padding-bottom: .3em; }
        h2 { font-size: 1.5em; border-bottom: 1px solid #d0d7de; padding-bottom: .3em; }
        h3 { font-size: 1.25em; }
        h4 { font-size: 1em; }
        p, ul, ol, table, pre {
            margin-top: 0;
            margin-bottom: 16px;
        }
        a {
            color: #0969da;
            text-decoration: none;
        }
        a:hover {
            text-decoration: underline;
        }
        ul, ol {
            padding-left: 2em;
        }
        li {
            margin-top: 0.25em;
        }
        code {
            padding: .2em .4em;
            margin: 0;
            font-size: 85%;
            white-space: break-spaces;
            background-color: rgba(175,184,193,0.2);
            border-radius: 6px;
            font-family: 'JetBrains Mono', monospace;
        }
        pre {
            padding: 16px;
            overflow: auto;
            font-size: 85%;
            line-height: 1.45;
            background-color: #f6f8fa;
            border-radius: 6px;
            font-family: 'JetBrains Mono', monospace;
        }
        pre code {
            background-color: transparent;
            padding: 0;
            font-size: 100%;
        }
        table {
            border-spacing: 0;
            border-collapse: collapse;
            width: 100%;
            margin-top: 20px;
            margin-bottom: 20px;
        }
        table th, table td {
            padding: 6px 13px;
            border: 1px solid #d0d7de;
        }
        table tr {
            background-color: #ffffff;
            border-top: 1px solid #hsla(210,18%,87%,1);
        }
        table tr:nth-child(even) {
            background-color: #f6f8fa;
        }
        table th {
            font-weight: 600;
            background-color: #f0f2f5;
        }
        hr {
            height: .25em;
            padding: 0;
            margin: 24px 0;
            background-color: #d0d7de;
            border: 0;
        }
        .alert {
            padding: 16px;
            margin-bottom: 16px;
            border-left: .25em solid;
            border-radius: 6px;
        }
        .alert-important {
            background-color: #fcf8e3;
            border-color: #f0ad4e;
            color: #8a6d3b;
        }
        .alert p {
            margin: 0;
        }
        .alert-title {
            font-weight: 600;
            margin-bottom: 4px;
        }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <script>mermaid.initialize({startOnLoad:true, theme: 'neutral'});</script>
</head>
<body>
    {content}
</body>
</html>
"""

    lines = md_content.split('\n')
    html_lines = []
    
    in_code_block = False
    code_block_content = []
    code_lang = ""
    
    in_list = False
    in_table = False
    table_headers = []
    table_rows = []
    
    in_alert = False
    alert_type = ""
    alert_lines = []

    for line in lines:
        # 1. Code Block Handling
        if line.strip().startswith('```'):
            if in_code_block:
                in_code_block = False
                content_str = '\n'.join(code_block_content)
                if code_lang == 'mermaid':
                    html_lines.append(f'<div class="mermaid">\n{content_str}\n</div>')
                else:
                    html_lines.append(f'<pre><code class="language-{code_lang}">{html.escape(content_str)}</code></pre>')
                code_block_content = []
            else:
                in_code_block = True
                code_lang = line.strip()[3:].strip()
            continue

        if in_code_block:
            code_block_content.append(line)
            continue

        # 2. Alert Box Handling (Blockquotes with > [!TYPE])
        if line.strip().startswith('>'):
            content = line.strip()[1:].strip()
            if not in_alert:
                in_alert = True
                alert_lines = []
                if content.startswith('[!'):
                    match = re.match(r'^\[!(IMPORTANT|WARNING|NOTE|TIP|CAUTION)\]', content)
                    if match:
                        alert_type = match.group(1).lower()
                        content = content[match.end():].strip()
                    else:
                        alert_type = "note"
                else:
                    alert_type = "note"
            
            if content:
                alert_lines.append(content)
            continue
        elif in_alert and not line.strip().startswith('>'):
            in_alert = False
            # Render Alert block
            title = alert_type.upper()
            body = ' '.join(alert_lines)
            # Apply inline styling rules
            body = inline_formatting(body)
            html_lines.append(f'<div class="alert alert-important"><div class="alert-title">{title}</div><p>{body}</p></div>')

        # 3. List Handling
        is_bullet = line.strip().startswith('* ') or line.strip().startswith('- ')
        if is_bullet:
            if not in_list:
                html_lines.append('<ul>')
                in_list = True
            item_text = line.strip()[2:]
            html_lines.append(f'  <li>{inline_formatting(item_text)}</li>')
            continue
        elif in_list and not is_bullet and line.strip() != "":
            # Check if this is an indented bullet (nested list)
            if line.startswith('    * ') or line.startswith('    - '):
                item_text = line.strip()[2:]
                html_lines.append(f'  <ul><li>{inline_formatting(item_text)}</li></ul>')
                continue
            elif line.startswith('  * ') or line.startswith('  - '):
                item_text = line.strip()[2:]
                html_lines.append(f'  <ul><li>{inline_formatting(item_text)}</li></ul>')
                continue
            else:
                html_lines.append('</ul>')
                in_list = False
        elif in_list and line.strip() == "":
            html_lines.append('</ul>')
            in_list = False

        # 4. Table Handling
        if line.strip().startswith('|'):
            in_table = True
            parts = [p.strip() for p in line.split('|')[1:-1]]
            # Check if separator row
            if all(re.match(r'^:?-+:?$', p) for p in parts):
                continue
            
            if not table_headers:
                table_headers = parts
            else:
                table_rows.append(parts)
            continue
        elif in_table and not line.strip().startswith('|'):
            in_table = False
            # Render Table
            table_html = ['<table>', '  <thead>', '    <tr>']
            for h in table_headers:
                table_html.append(f'      <th>{inline_formatting(h)}</th>')
            table_html.extend(['    </tr>', '  </thead>', '  <tbody>'])
            for row in table_rows:
                table_html.append('    <tr>')
                for cell in row:
                    table_html.append(f'      <td>{inline_formatting(cell)}</td>')
                table_html.append('    </tr>')
            table_html.extend(['  </tbody>', '</table>'])
            html_lines.append('\n'.join(table_html))
            table_headers = []
            table_rows = []

        # 5. Header Handling
        if line.startswith('# '):
            html_lines.append(f'<h1>{inline_formatting(line[2:])}</h1>')
        elif line.startswith('## '):
            html_lines.append(f'<h2>{inline_formatting(line[3:])}</h2>')
        elif line.startswith('### '):
            html_lines.append(f'<h3>{inline_formatting(line[4:])}</h3>')
        elif line.startswith('#### '):
            html_lines.append(f'<h4>{inline_formatting(line[5:])}</h4>')
        elif line.strip() == '---':
            html_lines.append('<hr>')
        elif line.strip() != "":
            # Plain paragraph
            html_lines.append(f'<p>{inline_formatting(line)}</p>')

    content_html = '\n'.join(html_lines)
    return html_template.replace('{content}', content_html)

import html
def inline_formatting(text):
    # Escape HTML characters first to avoid conflict, except we allow our own tags
    text = html.escape(text)
    
    # Restore escaped characters that might be needed in markdown or links
    # Bold formatting **text**
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
    # Inline code `code`
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)
    
    # Markdown links [text](url)
    # URL needs to decode amp and other chars
    def make_link(match):
        label = match.group(1)
        url = html.unescape(match.group(2))
        return f'<a href="{url}">{label}</a>'
        
    text = re.sub(r'\[(.*?)\]\((.*?)\)', make_link, text)
    return text

if __name__ == "__main__":
    proposal_path = "/home/brian/.gemini/antigravity/brain/399fe7d1-4717-4519-b16e-9ff042c4512c/integration_proposal.md"
    output_path = "/home/brian/.gemini/antigravity/scratch/courtlistener/integration_proposal.html"
    
    if os.path.exists(proposal_path):
        with open(proposal_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
        
        html_content = markdown_to_html(md_content)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        print(f"SUCCESS: Generated HTML at {output_path}")
    else:
        print("ERROR: Proposal markdown file not found.")
