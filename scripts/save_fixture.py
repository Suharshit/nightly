"""Save a trimmed real API response as a fixture: python -m scripts.save_fixture ats slug [n]."""
import json
import sys

import httpx

from worker.sources import ashby, greenhouse, lever

ADAPTERS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}

ats, slug = sys.argv[1], sys.argv[2]
n = int(sys.argv[3]) if len(sys.argv) > 3 else 4
r = httpx.get(ADAPTERS[ats].url(slug), headers={"User-Agent": "nightly-jobs/0.1"}, timeout=60)
r.raise_for_status()
data = r.json()
if isinstance(data, list):
    data = data[:n]
else:
    data["jobs"] = data["jobs"][:n]
    for j in data["jobs"]:  # keep fixtures small
        for k in ("content", "descriptionHtml"):
            if k in j:
                j[k] = j[k][:3000]
        if "descriptionPlain" in j:
            j["descriptionPlain"] = j["descriptionPlain"][:1500]
path = f"tests/fixtures/{ats}_{slug}.json"
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
print(path, len(data if isinstance(data, list) else data["jobs"]))
