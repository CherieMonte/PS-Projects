import re, base64, json, datetime, urllib.request, urllib.error, os

# ── Date ──────────────────────────────────────────────────────────
now           = datetime.datetime.now()
run_date      = now.strftime("%Y-%m-%d")
run_date_long = now.strftime("%B %-d, %Y")

# ── Smartsheet budget pull ─────────────────────────────────────────
ss_token = os.environ.get("SMARTSHEET_TOKEN", "")
budget_data = {}

# Map Smartsheet Primary names → dashboard card keys
PROJECT_MAP = {
    "PER Atlanta DC Mobilization":           "atlanta",
    "PER Solliance Identity Server Rollout": "idp",
    "PER OC Multi-Region Active POC":        "ocwest",
    "PER Canadian CC Platform":              "canada",
    "PER Genesys":                           "genesys",
    "PER LDAP":                              "oidc",
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
    sheets = ss_get("sheets?includeAll=true")
    if sheets:
        # Find the budget/hours sheet
        target_sheet = None
        priority = ["budget - hours data", "project hours", "budgets - hours", "hours data"]
        sheet_list = sheets.get("data", [])
        print(f"Available sheets: {[s['name'] for s in sheet_list]}")

        for kw in priority:
            for s in sheet_list:
                if kw in s["name"].lower():
                    target_sheet = s
                    break
            if target_sheet:
                break

        # Fallback: first sheet with "hour" in name
        if not target_sheet:
            for s in sheet_list:
                if "hour" in s["name"].lower():
                    target_sheet = s
                    break

        if target_sheet:
            print(f"Using sheet: {target_sheet['name']} (ID: {target_sheet['id']})")
            sheet = ss_get(f"sheets/{target_sheet['id']}")

            if sheet:
                cols   = [c["title"] for c in sheet.get("columns", [])]
                print(f"Columns: {cols}")

                for row in sheet.get("rows", []):
                    cells = [c.get("displayValue") or c.get("value") for c in row.get("cells", [])]
                    if not cells:
                        continue
                    row_dict = dict(zip(cols, cells))
                    primary  = str(cells[0] or "")

                    # Match to our projects
                    matched_key = None
                    for map_name, key in PROJECT_MAP.items():
                        if map_name.lower() in primary.lower() or primary.lower() in map_name.lower():
                            matched_key = key
                            break

                    if matched_key:
                        # Find budget and incurred columns
                        budget   = None
                        incurred = None
                        on_budget = True
                        for col, val in row_dict.items():
                            col_l = col.lower()
                            if "budget" in col_l and "hour" in col_l and val:
                                try: budget = float(str(val).replace(",",""))
                                except: pass
                            if "incurred" in col_l and val:
                                try: incurred = float(str(val).replace(",",""))
                                except: pass
                            if "on budget" in col_l and val:
                                on_budget = str(val).lower() not in ["false","no","0","red"]

                        if budget and incurred is not None:
                            pct      = min(round((incurred / budget) * 100, 1), 100) if budget else 0
                            remaining = round(budget - incurred, 1)
                            status   = "ON BUDGET" if on_budget and pct < 90 else ("AT RISK" if pct < 100 else "OVER BUDGET")
                            color    = "#16a34a" if status == "ON BUDGET" else ("#d97706" if status == "AT RISK" else "#dc2626")
                            budget_data[matched_key] = {
                                "budget":    budget,
                                "incurred":  incurred,
                                "pct":       pct,
                                "remaining": remaining,
                                "status":    status,
                                "color":     color,
                                "source":    primary,
                            }
                            print(f"  {matched_key}: {incurred}/{budget} hrs ({pct}%) — {status}")
        else:
            print("WARNING: Could not find budget sheet")

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
for key, card_id in [('genesys', 'Genesys Deprecation'), ('oidc', 'OIDC Customer Migration')]:
    bar = budget_bar_html(key)
    if bar and card_id in html:
        # Insert before closing card-header div for each card
        # Find the card and insert budget bar before </div> that closes card-header
        pattern = rf'(card-title">[^<]*{re.escape(card_id)}.*?exec-detail">[^<]*</div>)'
        html = re.sub(pattern, lambda m: m.group(0) + bar, html, flags=re.DOTALL, count=1)

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
