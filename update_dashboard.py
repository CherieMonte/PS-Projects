import re, base64, json, datetime, urllib.request, urllib.error, os

# ── Date ─────────────────────────────────────────────────────────
now           = datetime.datetime.now()
run_date      = now.strftime("%Y-%m-%d")
run_date_long = now.strftime("%B %-d, %Y")
run_date_mm_dd = now.strftime("%m-%d")

# ── Smartsheet budget pull ────────────────────────────────────────
ss_token = os.environ.get("SMARTSHEET_TOKEN", "")

# Maps exact Smartsheet project names to card keys
PROJECT_MAP = {
    "PER PS APP SM Services":                "genesys",
    "PER Lightning Bolt DevIQ 2026":         "oidc",
    "PER Atlanta DC Mobilization":           "atlanta",
    "PER Canadian CC Platform":              "canada",
    "PER Solliance Identity Server Rollout": "idp",
    "PER OC Multi-Region Active POC":        "ocwest",
}

budget_data = {}

def ss_get(path):
    req = urllib.request.Request(
        f"https://api.smartsheet.com/2.0/{path}",
        headers={"Authorization": f"Bearer {ss_token}", "Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    except Exception as e:
        print(f"Smartsheet error: {e}")
        return None

def parse_budget_row(row_dict, primary_col, budget_col, incurred_col):
    try:
        primary  = str(row_dict.get(primary_col) or "").strip()
        budget   = float(str(row_dict.get(budget_col)   or 0).replace(",",""))
        incurred = float(str(row_dict.get(incurred_col) or 0).replace(",",""))
        return primary, budget, incurred
    except:
        return None, 0, 0

if ss_token:
    print("Fetching Smartsheet data...")

    # Sheet 1: Hours Forecasting — has PER PS APP SM Services (genesys)
    sheet1 = ss_get("sheets/176228980969348")
    if sheet1:
        cols = [c["title"] for c in sheet1.get("columns", [])]
        for row in sheet1.get("rows", []):
            cells    = [c.get("displayValue") or c.get("value") for c in row.get("cells", [])]
            row_dict = dict(zip(cols, cells))
            primary, budget, incurred = parse_budget_row(row_dict, "Projects", "Budget (Hours)", "Incurred (Hours)")
            key = PROJECT_MAP.get(primary)
            if key and key not in budget_data and budget > 0:
                pct = min(round(incurred/budget*100, 1), 100)
                budget_data[key] = {"budget": budget, "incurred": incurred, "pct": pct,
                    "remaining": round(budget-incurred,1),
                    "status": "ON BUDGET" if pct < 90 else ("AT RISK" if pct < 100 else "OVER BUDGET"),
                    "color": "#16a34a" if pct < 90 else ("#d97706" if pct < 100 else "#dc2626"),
                    "source": primary}
                print(f"  {key}: {incurred}/{budget} hrs ({pct}%)")

    # Sheet 2: Mgmnt Project Percent Data — has Lightning Bolt and others
    sheet2 = ss_get("sheets/6854780065369988")
    if sheet2:
        cols = [c["title"] for c in sheet2.get("columns", [])]
        for row in sheet2.get("rows", []):
            cells    = [c.get("displayValue") or c.get("value") for c in row.get("cells", [])]
            row_dict = dict(zip(cols, cells))
            primary, budget, incurred = parse_budget_row(row_dict, "Project", "Budget Hours", "Total Incurred Hours")
            key = PROJECT_MAP.get(primary)
            if key and key not in budget_data and budget > 0:
                pct = min(round(incurred/budget*100, 1), 100)
                budget_data[key] = {"budget": budget, "incurred": incurred, "pct": pct,
                    "remaining": round(budget-incurred,1),
                    "status": "ON BUDGET" if pct < 90 else ("AT RISK" if pct < 100 else "OVER BUDGET"),
                    "color": "#16a34a" if pct < 90 else ("#d97706" if pct < 100 else "#dc2626"),
                    "source": primary}
                print(f"  {key}: {incurred}/{budget} hrs ({pct}%)")

    print(f"Budget data: {list(budget_data.keys())}")

# ── Budget bar HTML ───────────────────────────────────────────────
def make_bar(key):
    if key not in budget_data:
        return ""
    b = budget_data[key]
    return (
        f'\n        <div class="budget-bar-wrap">'
        f'<div class="budget-bar-top">'
        f'<span class="budget-dot" style="background:{b["color"]}"></span>'
        f'<span class="budget-label">BUDGET HOURS &nbsp;·&nbsp; {b["status"]} &nbsp;·&nbsp; SMARTSHEET {run_date_mm_dd}</span>'
        f'<span class="budget-used">{b["incurred"]:,.0f} / {b["budget"]:,.0f} hrs used</span>'
        f'</div>'
        f'<div class="budget-track"><div class="budget-fill" style="width:{b["pct"]}%;background:{b["color"]}"></div></div>'
        f'<div class="budget-sub">{b["remaining"]:,.0f} hrs remaining &nbsp;·&nbsp; {b["pct"]}% of budget consumed &nbsp;·&nbsp; Source: {b["source"]}</div>'
        f'</div>'
    )

# ── Fetch Jonny\'s latest dashboard ─────────────────────────────
jonny_token = os.environ.get("JONNY_TOKEN", "")
jonny_html  = ""
if jonny_token:
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/JonnyBir/perfectserve-aws-exec-dashboard/contents/index.html",
            headers={"Authorization": f"token {jonny_token}", "Accept": "application/vnd.github.v3+json"}
        )
        with urllib.request.urlopen(req) as r:
            jonny_html = base64.b64decode(json.load(r)["content"]).decode("utf-8")
        print(f"Fetched Jonny dashboard: {len(jonny_html)} chars")
    except Exception as e:
        print(f"WARNING: Could not fetch Jonny dashboard: {e}")

# ── Parse Jonny\'s 4 AWS cards ────────────────────────────────────
def extract_card(block):
    def g(pattern, default=""):
        m = re.search(pattern, block, re.DOTALL)
        return m.group(1).strip() if m else default
    name      = g(r'class="card-name"[^>]*>(.*?)</div>')
    sub       = g(r'class="card-sub"[^>]*>(.*?)</div>')
    reason    = g(r'class="rag-reason"[^>]*>(.*?)</div>')
    summary   = g(r'class="exec-summary"[^>]*>(.*?)</div>')
    milestone = g(r'class="milestone-value"[^>]*>(.*?)</span>')
    milestone = re.sub(r'&#x[^;]+;', lambda m: {'&#x1F3C1;':'🏁','&#x2014;':'—','&#x2192;':'→'}.get(m.group(0), ''), milestone).strip()
    if   'rag-red'   in block: rag_class, rag_label = 'rag-red',    'Off Track'
    elif 'rag-green' in block: rag_class, rag_label = 'rag-green',  'On Track'
    else:                      rag_class, rag_label = 'rag-yellow', 'At Risk'
    risks   = re.findall(r'&#x26A0;&#xFE0F;\s*(.*?)</li>', block, re.DOTALL)
    wins    = re.findall(r'&#x2705;\s*(.*?)</li>', block, re.DOTALL)
    sources = re.findall(r'<a href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
    icons   = {'Atlanta':'🏗️','Canada':'🇨🇦','OC West':'🌐','IDP':'🛑'}
    icon    = next((v for k,v in icons.items() if k in name), '📋')
    key_map = {'Atlanta':'atlanta','Canada':'canada','OC West':'ocwest','IDP':'idp'}
    key     = next((v for k,v in key_map.items() if k in name), '')
    return dict(name=name, sub=sub, rag_class=rag_class, rag_label=rag_label,
                reason=reason, summary=summary, risks=risks, wins=wins,
                milestone=milestone, sources=sources, icon=icon, key=key)

def render_card(c):
    risks_html   = ''.join(f'<div class="item"><span class="item-icon">⚠️</span><span>{r.strip()}</span></div>' for r in c['risks'])
    wins_html    = ''.join(f'<div class="item"><span class="item-icon">✅</span><span>{w.strip()}</span></div>' for w in c['wins'])
    sources_html = ''.join(f'<a href="{url}" class="source-link" target="_blank">📋 {label.strip()}</a>' for url,label in c['sources'])
    budget_bar   = make_bar(c.get('key', ''))
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
        f'\n      <div class="card-footer">{budget_bar}'
        '\n        <div class="milestone-wrap">'
        '\n          <span class="milestone-badge">· Next:</span>'
        f'\n          <span class="milestone-text">{c["milestone"]}</span>'
        '\n        </div>'
        f'\n        <div class="source-links">{sources_html}</div>'
        '\n      </div>'
        '\n    </div>'
    )

# ── Read current index.html ───────────────────────────────────────
with open("index.html", "r") as f:
    html = f.read()

# ── Update date ───────────────────────────────────────────────────
html = re.sub(r'<strong>\d{4}-\d{2}-\d{2}</strong>', f'<strong>{run_date}</strong>', html)
html = re.sub(
    r'PerfectServe Executive Dashboard · Scheduled 10:00 AM MT · [^<]+',
    f'PerfectServe Executive Dashboard · Scheduled 10:00 AM MT · {run_date_long}',
    html
)

# ── Update budget bars for Cherie\'s cards ────────────────────────
# Find each card footer and replace/insert budget bar
CHERIE_CARDS = [
    ('Genesys Deprecation → Twilio',   'genesys'),
    ('LDAP → OIDC Customer Migration', 'oidc'),
]

# Map cards to their footers
cards   = [m.start() for m in re.finditer(r'<div class="project-card">', html)]
footers = [m.start() for m in re.finditer(r'<div class="card-footer">', html)]
card_footer_map = {}
for card_pos in cards:
    title_m = re.search(r'card-title">(.*?)</div>', html[card_pos:card_pos+500], re.DOTALL)
    title   = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else ''
    footer  = next((f for f in footers if f > card_pos), None)
    card_footer_map[title] = footer

for card_title, budget_key in CHERIE_CARDS:
    matched = next((t for t in card_footer_map if card_title in t), None)
    if not matched or not card_footer_map[matched]:
        print(f"WARNING: Could not find card/footer for {card_title}")
        continue
    footer_pos = card_footer_map[matched]
    insert_at  = footer_pos + len('<div class="card-footer">')
    bar        = make_bar(budget_key)
    if not bar:
        print(f"No budget data for {budget_key} — skipping bar update")
        continue
    # Remove existing budget bar if present
    after_footer = html[insert_at:insert_at+1000]
    if 'budget-bar-wrap' in after_footer:
        html = html[:insert_at] + re.sub(r'\n\s*<div class="budget-bar-wrap">.*?</div>', '', after_footer[:1000], count=1, flags=re.DOTALL) + html[insert_at+1000:]
        # Recalculate after removal
        footers   = [m.start() for m in re.finditer(r'<div class="card-footer">', html)]
        cards     = [m.start() for m in re.finditer(r'<div class="project-card">', html)]
        card_footer_map = {}
        for cp in cards:
            tm = re.search(r'card-title">(.*?)</div>', html[cp:cp+500], re.DOTALL)
            t  = re.sub(r'<[^>]+>', '', tm.group(1)).strip() if tm else ''
            card_footer_map[t] = next((f for f in footers if f > cp), None)
        footer_pos = card_footer_map.get(matched)
        if not footer_pos:
            continue
        insert_at = footer_pos + len('<div class="card-footer">')
    html = html[:insert_at] + bar + html[insert_at:]
    print(f"Budget bar updated for {card_title}")

# ── Replace Jonny\'s cards ─────────────────────────────────────────
if jonny_html:
    card_blocks    = re.split(r'<div class="card">', jonny_html)
    jonny_cards    = [extract_card(b) for b in card_blocks[1:5]]
    aws_cards_html = '\n'.join(render_card(c) for c in jonny_cards)
    old_section = re.search(
        r'(// AWS Platform.*?Jonny Bir.*?PM.*?</div>\s*<div class="card-grid">)(.*?)(</div><!-- /card-grid -->)',
        html, re.DOTALL
    )
    if old_section:
        html = html[:old_section.start()] + old_section.group(1) + '\n' + aws_cards_html + '\n  ' + old_section.group(3) + html[old_section.end():]
        print('Jonny cards updated')

# ── Write ────────────────────────────────────────────────────────
with open("index.html", "w") as f:
    f.write(html)
print(f'Dashboard written — {run_date_long}')
