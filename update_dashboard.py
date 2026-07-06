import re, base64, json, datetime, urllib.request, urllib.error, os

# ── Date ──────────────────────────────────────────────────────────
now           = datetime.datetime.now()
run_date      = now.strftime('%Y-%m-%d')
run_date_long = now.strftime('%B %-d, %Y')

# ── Fetch Jonny's latest dashboard ────────────────────────────────
jonny_token = os.environ.get('JONNY_TOKEN', '')
jonny_html  = ''

if jonny_token:
    try:
        req = urllib.request.Request(
            'https://api.github.com/repos/JonnyBir/perfectserve-aws-exec-dashboard/contents/index.html',
            headers={
                'Authorization': f'token {jonny_token}',
                'Accept': 'application/vnd.github.v3+json',
            }
        )
        with urllib.request.urlopen(req) as r:
            d = json.load(r)
            jonny_html = base64.b64decode(d['content']).decode('utf-8')
        print(f'Fetched Jonny dashboard: {len(jonny_html)} chars')
    except Exception as e:
        print(f'WARNING: Could not fetch Jonny dashboard: {e}')

# ── Parse Jonny's 4 AWS cards ──────────────────────────────────────
def extract_card(block):
    def g(pattern, default=''):
        m = re.search(pattern, block, re.DOTALL)
        return m.group(1).strip() if m else default

    name      = g(r'class="card-name"[^>]*>(.*?)</div>')
    sub       = g(r'class="card-sub"[^>]*>(.*?)</div>')
    reason    = g(r'class="rag-reason"[^>]*>(.*?)</div>')
    summary   = g(r'class="exec-summary"[^>]*>(.*?)</div>')
    milestone = g(r'class="milestone-value"[^>]*>(.*?)</span>')
    milestone = re.sub(r'&#x[^;]+;', lambda m: {
        '&#x1F3C1;': '🏁', '&#x2014;': '—', '&#x2192;': '→'
    }.get(m.group(0), ''), milestone).strip()

    if   'rag-red'   in block: rag_class, rag_label = 'rag-red',    'Off Track'
    elif 'rag-green' in block: rag_class, rag_label = 'rag-green',  'On Track'
    else:                      rag_class, rag_label = 'rag-yellow', 'At Risk'

    risks   = re.findall(r'&#x26A0;&#xFE0F;\s*(.*?)</li>', block, re.DOTALL)
    wins    = re.findall(r'&#x2705;\s*(.*?)</li>', block, re.DOTALL)
    sources = re.findall(r'<a href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)

    icons = {'Atlanta': '🏗️', 'Canada': '🇨🇦', 'OC West': '🌐', 'IDP': '🛑'}
    icon  = next((v for k, v in icons.items() if k in name), '📋')

    return dict(name=name, sub=sub, rag_class=rag_class, rag_label=rag_label,
                reason=reason, summary=summary, risks=risks, wins=wins,
                milestone=milestone, sources=sources, icon=icon)

def render_card(c):
    risks_html = ''.join(
        f'<div class="item"><span class="item-icon">⚠️</span><span>{r.strip()}</span></div>'
        for r in c['risks']
    )
    wins_html = ''.join(
        f'<div class="item"><span class="item-icon">✅</span><span>{w.strip()}</span></div>'
        for w in c['wins']
    )
    sources_html = ''.join(
        f'<a href="{url}" class="source-link" target="_blank">📋 {label.strip()}</a>'
        for url, label in c['sources']
    )
    return (
        '\n    <div class="project-card">'
        '\n      <div class="card-header">'
        '\n        <div class="card-header-top">'
        '\n          <div>'
        f'\n            <div class="card-title">{c["icon"]} {c["name"]}</div>'
        f'\n            <div class="card-subtitle">{c["sub"]}</div>'
        '\n          </div>'
        f'\n          <span class="rag-pill {c["rag_class"]}"><span class="dot"></span> {c["rag_label"]}</span>'
        '\n        </div>'
        f'\n        <div class="exec-quote">{c["reason"]}</div>'
        f'\n        <div class="exec-detail">{c["summary"]}</div>'
        '\n      </div>'
        '\n      <div class="card-body">'
        '\n        <div class="card-col">'
        '\n          <div class="col-label">Key Risks &amp; Blockers</div>'
        f'\n          <div class="item-list">{risks_html}</div>'
        '\n        </div>'
        '\n        <div class="card-col">'
        '\n          <div class="col-label">Recent Progress</div>'
        f'\n          <div class="item-list">{wins_html}</div>'
        '\n        </div>'
        '\n      </div>'
        '\n      <div class="card-footer">'
        '\n        <div class="milestone-wrap">'
        '\n          <span class="milestone-badge">· Next:</span>'
        f'\n          <span class="milestone-text">{c["milestone"]}</span>'
        '\n        </div>'
        f'\n        <div class="source-links">{sources_html}</div>'
        '\n      </div>'
        '\n    </div>'
    )

# ── Read current index.html ────────────────────────────────────────
with open('index.html', 'r') as f:
    html = f.read()

# ── Update date ────────────────────────────────────────────────────
html = re.sub(r'<strong>\d{4}-\d{2}-\d{2}</strong>', f'<strong>{run_date}</strong>', html)
html = re.sub(
    r'PerfectServe Executive Dashboard · Scheduled 10:00 AM MT · [^<]+',
    f'PerfectServe Executive Dashboard · Scheduled 10:00 AM MT · {run_date_long}',
    html
)

# ── Replace Jonny's cards if we got his data ───────────────────────
if jonny_html:
    card_blocks    = re.split(r'<div class="card">', jonny_html)
    jonny_cards    = [extract_card(b) for b in card_blocks[1:5]]
    aws_cards_html = '\n'.join(render_card(c) for c in jonny_cards)

    old_section = re.search(
        r'(// AWS Platform.*?Jonny Bir.*?PM.*?</div>\s*<div class="card-grid">)(.*?)(</div><!-- /card-grid -->)',
        html, re.DOTALL
    )
    if old_section:
        html = (html[:old_section.start()]
                + old_section.group(1) + '\n' + aws_cards_html + '\n  '
                + old_section.group(3)
                + html[old_section.end():])
        print('Jonny cards updated successfully')
    else:
        print('WARNING: Could not find AWS card-grid section to replace')

# ── Write updated file ─────────────────────────────────────────────
with open('index.html', 'w') as f:
    f.write(html)
print(f'Dashboard written — {run_date_long}')
