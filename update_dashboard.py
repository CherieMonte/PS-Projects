import re, base64, json, datetime, urllib.request, urllib.error, os

# ── Date ─────────────────────────────────────────────────────────
now            = datetime.datetime.now()
run_date       = now.strftime("%Y-%m-%d")
run_date_long  = now.strftime("%B %-d, %Y")
run_date_mm_dd = now.strftime("%m-%d")

# ── Smartsheet ───────────────────────────────────────────────────
ss_token = os.environ.get("SMARTSHEET_TOKEN", "")

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

def ingest_sheet(sheet, primary_col, budget_col, incurred_col):
    if not sheet:
        return
    cols = [c["title"] for c in sheet.get("columns", [])]
    for row in sheet.get("rows", []):
        cells    = [c.get("displayValue") or c.get("value") for c in row.get("cells", [])]
        row_dict = dict(zip(cols, cells))
        primary  = str(row_dict.get(primary_col) or "").strip()
        key      = PROJECT_MAP.get(primary)
        if key and key not in budget_data:
            try:
                budget   = float(str(row_dict.get(budget_col)   or 0).replace(",",""))
                incurred = float(str(row_dict.get(incurred_col) or 0).replace(",",""))
                if not budget:
                    continue
                pct       = min(round(incurred / budget * 100, 1), 100)
                remaining = round(budget - incurred, 1)
                status    = "ON BUDGET" if pct < 90 else ("AT RISK" if pct < 100 else "OVER BUDGET")
                color     = "#16a34a" if pct < 90 else ("#d97706" if pct < 100 else "#dc2626")
                budget_data[key] = dict(budget=budget, incurred=incurred, pct=pct,
                    remaining=remaining, status=status, color=color, source=primary)
                print(f"  {key}: {incurred}/{budget} hrs ({pct}%) — {status}")
            except Exception as e:
                print(f"  WARNING {primary}: {e}")

if ss_token:
    print("Fetching Smartsheet data...")
    ingest_sheet(ss_get("sheets/176228980969348"), "Projects",  "Budget (Hours)",    "Incurred (Hours)")
    ingest_sheet(ss_get("sheets/6854780065369988"), "Project",  "Budget Hours",      "Total Incurred Hours")
    print(f"Budget data for: {list(budget_data.keys())}")

# ── Build budget bar HTML ─────────────────────────────────────────
def make_bar(key):
    if key not in budget_data:
        return f'<!-- BUDGET_BAR_{key.upper()}_START --><!-- BUDGET_BAR_{key.upper()}_END -->'
    b = budget_data[key]
    return (
        f'<!-- BUDGET_BAR_{key.upper()}_START -->'
        f'<div class="budget-bar-wrap">'
        f'<div class="budget-bar-top">'
        f'<span class="budget-dot" style="background:{b["color"]}"></span>'
        f'<span class="budget-label">BUDGET HOURS &nbsp;·&nbsp; {b["status"]} &nbsp;·&nbsp; SMARTSHEET {run_date_mm_dd}</span>'
        f'<span class="budget-used">{b["incurred"]:,.0f} / {b["budget"]:,.0f} hrs used</span>'
        f'</div>'
        f'<div class="budget-track"><div class="budget-fill" style="width:{b["pct"]}%;background:{b["color"]}"></div></div>'
        f'<div class="budget-sub">{b["remaining"]:,.0f} hrs remaining &nbsp;·&nbsp; {b["pct"]}% of budget consumed &nbsp;·&nbsp; Source: {b["source"]}</div>'
        f'</div>'
        f'<!-- BUDGET_BAR_{key.upper()}_END -->'
    )

# ── Fetch Jonny's dashboard ───────────────────────────────────────
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
        print(f"Fetched Jonny: {len(jonny_html)} chars")
    except Exception as e:
        print(f"WARNING Jonny: {e}")

# ── Parse Jonny's cards ───────────────────────────────────────────
def extract_card(block):
    def g(p, d=""):
        m = re.search(p, block, re.DOTALL)
        return m.group(1).strip() if m else d
    name      = g(r'class="card-name"[^>]*>(.*?)</div>')
    sub       = g(r'class="card-sub"[^>]*>(.*?)</div>')
    reason    = g(r'class="rag-reason"[^>]*>(.*?)</div>')
    summary   = g(r'class="exec-summary"[^>]*>(.*?)</div>')
    milestone = g(r'class="milestone-value"[^>]*>(.*?)</span>')
    milestone = re.sub(r'&#x[^;]+;', lambda m: {'&#x1F3C1;':'🏁','&#x2014;':'—','&#x2192;':'→'}.get(m.group(0),''), milestone).strip()
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
    sources_html = ''.join(f'<a href="{u}" class="source-link" target="_blank">📋 {l.strip()}</a>' for u,l in c['sources'])
    bar          = make_bar(c.get('key',''))
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
        f'\n      <div class="card-footer">{bar}'
        '\n        <div class="milestone-wrap">'
        '\n          <span class="milestone-badge">· Next:</span>'
        f'\n          <span class="milestone-text">{c["milestone"]}</span>'
        '\n        </div>'
        f'\n        <div class="source-links">{sources_html}</div>'
        '\n      </div>'
        '\n    </div>'
    )

# ── Read index.html ───────────────────────────────────────────────
with open("index.html", "r") as f:
    html = f.read()

# ── Update date ───────────────────────────────────────────────────
html = re.sub(r'<strong>\d{4}-\d{2}-\d{2}</strong>', f'<strong>{run_date}</strong>', html)
html = re.sub(
    r'PerfectServe Executive Dashboard · Scheduled 10:00 AM MT · [^<]+',
    f'PerfectServe Executive Dashboard · Scheduled 10:00 AM MT · {run_date_long}',
    html
)

# ── Replace budget bars using sentinels (safe, idempotent) ────────
for key in ['genesys', 'oidc']:
    new_bar = make_bar(key)
    pattern = f'<!-- BUDGET_BAR_{key.upper()}_START -->.*?<!-- BUDGET_BAR_{key.upper()}_END -->'
    if re.search(pattern, html, re.DOTALL):
        html = re.sub(pattern, new_bar, html, flags=re.DOTALL)
        print(f"Updated budget bar: {key}")
    else:
        print(f"WARNING: No sentinel found for {key}")

# ── Replace Jonny's AWS cards ─────────────────────────────────────
if jonny_html:
    card_blocks    = re.split(r'<div class="card">', jonny_html)
    jonny_cards    = [extract_card(b) for b in card_blocks[1:5]]
    aws_cards_html = '\n'.join(render_card(c) for c in jonny_cards)
    old_section    = re.search(
        r'(// AWS Platform.*?Jonny Bir.*?PM.*?</div>\s*<div class="card-grid">)(.*?)(</div><!-- /card-grid -->)',
        html, re.DOTALL
    )
    if old_section:
        html = html[:old_section.start()] + old_section.group(1) + '\n' + aws_cards_html + '\n  ' + old_section.group(3) + html[old_section.end():]
        print('Jonny cards updated')
    else:
        print('WARNING: Could not find Jonny card-grid section')

# ── Write ─────────────────────────────────────────────────────────
with open("index.html", "w") as f:
    f.write(html)
print(f'Done — {run_date_long}')
