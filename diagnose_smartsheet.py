#!/usr/bin/env python3
"""Smartsheet diagnostic — run this in GitHub Actions to see all sheet/row data"""
import json, urllib.request, urllib.error, os

ss_token = os.environ.get("SMARTSHEET_TOKEN", "")
if not ss_token:
    print("ERROR: No SMARTSHEET_TOKEN")
    exit(1)

def ss_get(path):
    req = urllib.request.Request(
        f"https://api.smartsheet.com/2.0/{path}",
        headers={"Authorization": f"Bearer {ss_token}", "Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        print(f"ERROR {e.code}: {e.read().decode()[:500]}")
        return None

print("=== LISTING ALL SHEETS ===")
sheets = ss_get("sheets?includeAll=true")
if not sheets:
    exit(1)

for s in sheets.get("data", []):
    print(f"  [{s['id']}] {s['name']}")

print("\n=== CHECKING EACH SHEET FOR PROJECT DATA ===")
targets = ["PER PS APP SM Services", "PER Lightning Bolt DevIQ 2026",
           "PER Atlanta DC Mobilization", "PER Solliance Identity Server Rollout",
           "PER OC Multi-Region Active POC", "PER Canadian CC Platform"]

for s in sheets.get("data", []):
    sheet = ss_get(f"sheets/{s['id']}")
    if not sheet:
        continue
    cols = [c["title"] for c in sheet.get("columns", [])]
    rows = sheet.get("rows", [])
    
    # Check if this sheet has any of our projects
    found_projects = []
    for row in rows:
        cells = [c.get("displayValue") or c.get("value") for c in row.get("cells", [])]
        primary = str(cells[0] if cells else "")
        for t in targets:
            if t.lower() in primary.lower() or primary.lower() in t.lower():
                found_projects.append(primary)
                break
    
    if found_projects:
        print(f"\nSHEET: {s['name']} (ID: {s['id']})")
        print(f"  Columns: {cols}")
        print(f"  Matching projects: {found_projects}")
        # Print full rows for matches
        for row in rows:
            cells = [c.get("displayValue") or c.get("value") for c in row.get("cells", [])]
            primary = str(cells[0] if cells else "")
            for t in targets:
                if t.lower() in primary.lower() or primary.lower() in t.lower():
                    row_dict = dict(zip(cols, cells))
                    print(f"  ROW: {json.dumps(row_dict)}")
                    break

print("\n=== DONE ===")
