import json, urllib.request, os

ss_token = os.environ.get("SMARTSHEET_TOKEN", "")

def ss_get(path):
    req = urllib.request.Request(
        f"https://api.smartsheet.com/2.0/{path}",
        headers={"Authorization": f"Bearer {ss_token}"}
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)

print("=== Budget - Hours Data sheet (6866540340137860) ===")
sheet = ss_get("sheets/6866540340137860")
cols = [c["title"] for c in sheet.get("columns", [])]
print(f"Columns: {cols}")
print("\nAll rows (Primary column):")
for row in sheet.get("rows", []):
    cells = [c.get("displayValue") or c.get("value") for c in row.get("cells", [])]
    if cells and cells[0]:
        print(f"  {json.dumps(dict(zip(cols, cells)))}")

print("\n=== Mgmnt Project Percent Data (6854780065369988) — all rows ===")
sheet2 = ss_get("sheets/6854780065369988")
cols2 = [c["title"] for c in sheet2.get("columns", [])]
print(f"Columns: {cols2}")
for row in sheet2.get("rows", []):
    cells = [c.get("displayValue") or c.get("value") for c in row.get("cells", [])]
    if cells and cells[0]:
        print(f"  {json.dumps(dict(zip(cols2, cells)))}")
