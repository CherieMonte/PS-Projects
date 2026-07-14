import re, base64, json, datetime, urllib.request, urllib.error, os

# ── Date ──────────────────────────────────────────────────────────
now           = datetime.datetime.now()
run_date      = now.strftime("%Y-%m-%d")
run_date_long = now.strftime("%B %-d, %Y")

# ── Smartsheet budget pull ─────────────────────────────────────────
ss_token = os.environ.get("SMARTSHEET_TOKEN", "")
budget_data = {}

# Map Smartsheet Primary names → dashboard card keys
# Exact Smartsheet row names → dashboard card keys
# Source: Project Manager Dashboard > Project Hours At Risk widget
PROJECT_MAP = {
    "PER PS APP SM Services":                "genesys",  # Budget:500, Incurred:117.5
    "PER Lightning Bolt DevIQ 2026":         "oidc",     # Budget:480, Incurred:305.5
    "PER Atlanta DC Mobilization":           "atlanta",  # Budget:3379, Incurred:2226
    "PER Canadian CC Platform":              "canada",   # Budget:2210, Incurred:1603
    "PER Solliance Identity Server Rollout": "idp",      # Budget:260, Incurred:198
    "PER OC Multi-Region Active POC":        "ocwest",   # Budget:118, Incurred:22
}

def ss_get(path):
    req = urllib.request.Request(
        f"https://api.smartsheet.com/2.0/{path}",
        headers={"Authorization": f"Bearer {ss_token}", "Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        print(f"Smartsheet error {e.code}: {e.read().decode()[:200]}")
        return None

if ss_token:
    print("Fetching Smartsheet budget data...")

    def fetch_budget(sheet_id, primary_col, budget_col, incurred_col, keys_to_fetch):
        """Fetch budget data for specific keys from a specific sheet."""
        sheet = ss_get(f"sheets/{sheet_id}")
        if not sheet:
            print(f"WARNING: Could not fetch sheet {sheet_id}")
            return
        cols = [c["title"] for c in sheet.get("columns", [])]
        for row in sheet.get("rows", []):
            cells    = [c.get("displayValue") or c.get("value") for c in row.get("cells", [])]
            if not cells:
                continue
            row_dict = dict(zip(cols, cells))
            primary  = str(row_dict.get(primary_col) or "").strip()
            if not primary:
                continue
            # Only process rows for the keys we want from this sheet
            matched_key = None
            for map_name, key in PROJECT_MAP.items():
                if primary.lower() == map_name.lower() and key in keys_to_fetch:
                    matched_key = key
                    break
            if matched_key and matched_key not in budget_data:
                try:
                    budget   = float(str(row_dict.get(budget_col)   or 0).replace(",",""))
                    incurred = float(str(row_dict.get(incurred_col) or 0).replace(",",""))
                    if not budget:
                        continue
                    pct       = min(round(incurred / budget * 100, 1), 100)
                    remaining = round(budget - incurred, 1)
                    status    = "ON BUDGET" if pct < 90 else ("AT RISK" if pct < 100 else "OVER BUDGET")
                    color     = "#16a34a" if status == "ON BUDGET" else ("#d97706" if status == "AT RISK" else "#dc2626")
                    budget_data[matched_key] = {
                        "budget": budget, "incurred": incurred, "pct": pct,
                        "remaining": remaining, "status": status, "color": color, "source": primary,
                    }
                    print(f"  {matched_key}: {incurred}/{budget} hrs ({pct}%) — {status}")
                except Exception as e:
                    print(f"  WARNING: Could not parse {primary}: {e}")

    # Genesys pulls from Hours Forecasting (has PER PS APP SM Services)
    fetch_budget(
        "176228980969348",          # Hours Forecasting
        "Projects",                 # primary column
        "Budget (Hours)",           # budget column
        "Incurred (Hours)",         # incurred column
        {"genesys"},                # only fetch genesys from this sheet
    )

    # All others pull from Mgmnt Project Percent Data
    # (confirmed has: PER Lightning Bolt DevIQ 2026, PER Atlanta DC Mobilization,
    #  PER Solliance Identity Server Rollout, PER OC Multi-Region Active POC)
    fetch_budget(
        "6854780065369988",         # Mgmnt Project Percent Data
        "Project",                  # primary column
        "Budget Hours",             # budget column
        "Total Incurred Hours",     # incurred column
        {"oidc", "atlanta", "idp", "ocwest", "canada"},
    )

print(f"Budget data found for: {list(budget_data.keys())}")

# ── Budget bar HTML ────────────────────────────────────────────────
def budget_bar_html(key):
    if key not in budget_data:
        return ""
    b = budget_data[key]
    return (
        f'\n      <div class="budget-bar-wrap">'
        f'\n        <div class="budget-bar-top">'
        f'\n          <span class="budget-dot" style="background:{b["color"]}"></span>'
        f'\n          <span class="budget-label">BUDGET HOURS &nbsp;·&nbsp; {b["status"]} &nbsp;·&nbsp; SMARTSHEET {run_date[5:]}</span>'
        f'\n          <span class="budget-used">{b["incurred"]:,.0f} / {b["budget"]:,.0f} hrs used</span>'
        f'\n        </div>'
        f'\n        <div class="budget-track">'
        f'\n          <div class="budget-fill" style="width:{b["pct"]}%;background:{b["color"]}"></div>'
        f'\n        </div>'
        f'\n        <div class="budget-sub">{b["remaining"]:,.0f} hrs remaining &nbsp;·&nbsp; {b["pct"]}% of budget consumed &nbsp;·&nbsp; Source: {b["source"]}</div>'
        f'\n      </div>'
    )

# ── Fetch Jonny's latest dashboard ────────────────────────────────
jonny_token = os.environ.get("JONNY_TOKEN", "")
jonny_html  = ""

if jonny_token:
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/JonnyBir/perfectserve-aws-exec-dashboard/contents/index.html",
            headers={
                "Authorization": f"token {jonny_token}",
                "Accept":        "application/vnd.github.v3+json",
            }
        )
        with urllib.request.urlopen(req) as r:
            d         = json.load(r)
            jonny_html = base64.b64decode(d["content"]).decode("utf-8")
        print(f"Fetched Jonny dashboard: {len(jonny_html)} chars")
    except Exception as e:
        print(f"WARNING: Could not fetch Jonny dashboard: {e}")

# ── Parse Jonny's 4 AWS cards ──────────────────────────────────────
def extract_card(block):
    def g(pattern, default=""):
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

    key_map = {'Atlanta': 'atlanta', 'Canada': 'canada', 'OC West': 'ocwest', 'IDP': 'idp'}
    key = next((v for k, v in key_map.items() if k in name), '')

    return dict(name=name, sub=sub, rag_class=rag_class, rag_label=rag_label,
                reason=reason, summary=summary, risks=risks, wins=wins,
                milestone=milestone, sources=sources, icon=icon, key=key)

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
    budget_html = budget_bar_html(c.get('key', ''))
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
        f'{budget_html}'
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

# ── Add budget bar CSS if not present ─────────────────────────────
budget_css = """
  /* ── Budget bar ── */
  .budget-bar-wrap { margin-top:14px; padding-top:12px; border-top:1px solid #f1f3f7; }
  .budget-bar-top  { display:flex; align-items:center; gap:6px; margin-bottom:6px; }
  .budget-dot      { width:8px; height:8px; border-radius:50%; flex-shrink:0; }
  .budget-label    { font-size:0.65rem; font-weight:700; text-transform:uppercase; letter-spacing:0.08em; color:#6b7280; flex:1; }
  .budget-used     { font-size:0.72rem; font-weight:600; color:#374151; }
  .budget-track    { background:#e5e7eb; border-radius:999px; height:6px; overflow:hidden; margin-bottom:5px; }
  .budget-fill     { height:100%; border-radius:999px; transition:width 0.3s ease; }
  .budget-sub      { font-size:0.68rem; color:#9ca3af; }
"""
if "budget-bar-wrap" not in html:
    html = html.replace("  /* ── Page footer ── */", budget_css + "\n  /* ── Page footer ── */")

# ── Update date ────────────────────────────────────────────────────
html = re.sub(r'<strong>\d{4}-\d{2}-\d{2}</strong>', f'<strong>{run_date}</strong>', html)
html = re.sub(
    r'PerfectServe Executive Dashboard · Scheduled 10:00 AM MT · [^<]+',
    f'PerfectServe Executive Dashboard · Scheduled 10:00 AM MT · {run_date_long}',
    html
)

# ── Add budget bars to Cherie's cards ─────────────────────────────
# Insert budget bar just before the exec-quote div in each card
# Using unique strings from each card's exec-quote as the insertion anchor
CHERIE_EXEC_QUOTES = {
    'genesys': 'Status as of 7/13/26',
    'oidc':    'Customer engagement is a growing concern',
}
for key, quote_anchor in CHERIE_EXEC_QUOTES.items():
    bar = budget_bar_html(key)
    if not bar:
        print(f'No budget data for {key} — skipping')
        continue
    pos = html.find(quote_anchor)
    if pos == -1:
        print(f'Could not find exec-quote anchor for {key}')
        continue
    # Walk back to find the opening of the exec-quote div
    div_start = html.rfind('<div class="exec-quote">', 0, pos)
    if div_start == -1:
        print(f'Could not find exec-quote div start for {key}')
        continue
    # Check if budget bar already exists just before this div
    preceding = html[div_start-300:div_start]
    if 'budget-bar-wrap' in preceding:
        # Replace existing budget bar
        bar_start = preceding.rfind('<div class="budget-bar-wrap">')
        abs_bar_start = div_start - 300 + bar_start
        bar_end = html.find('</div>', abs_bar_start + 100)
        # Find full closing of budget-bar-wrap
        bar_end = html.find('</div>', bar_end + 1) + len('</div>')
        html = html[:abs_bar_start] + bar.strip() + '\n      ' + html[bar_end:]
        print(f'Budget bar updated for {key}')
    else:
        # Insert budget bar right before exec-quote div
        html = html[:div_start] + bar + '\n        ' + html[div_start:]
        print(f'Budget bar inserted for {key}')

# ── Replace Jonny's cards ──────────────────────────────────────────
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
        print('WARNING: Could not find AWS card-grid section')

# ── Write updated file ─────────────────────────────────────────────
with open('index.html', 'w') as f:
    f.write(html)
print(f'Dashboard written — {run_date_long}')
