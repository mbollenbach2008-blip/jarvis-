"""Diagnose: durchsucht den öffentlichen JS-Code der Schulmanager-Web-App nach dem API-Format."""
import re, urllib.request
BASE = "https://login.schulmanager-online.de"
def get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read().decode("utf-8", "replace")
html = get(BASE + "/")
files = re.findall(r'src="([^"]+\.js)"', html)
seen = set()
patterns = ["api/calls", "moduleName", "endpointName", "bundleVersion", "get-actual-lessons", "get-homework", "get-letters", "get-exams", "requests:"]
queue = list(files)
while queue and len(seen) < 60:
    f = queue.pop(0)
    if f in seen: continue
    seen.add(f)
    try: js = get(f"{BASE}/{f.lstrip('/')}" if not f.startswith("http") else f)
    except Exception as e: print("ERR", f, e); continue
    for c in re.findall(r'["\'](?:\./)?(chunk-[A-Z0-9]+\.js)["\']', js):
        c = "static/" + c
        if c not in seen: queue.append(c)
    for p in patterns:
        for i, m in enumerate(re.finditer(re.escape(p), js)):
            if i >= 3: break
            print(f"== {f} [{p}] ..." + js[max(0, m.start()-200):m.end()+200].replace("\n", " ") + "...")
print("Dateien:", len(seen))
