"""Probe candidate company boards before adding them to data/companies.csv.

For every candidate slug it tries Greenhouse, Lever and Ashby (public job-board APIs only,
1 request/second per host, with our User-Agent) and counts, per board found:
jobs in total, jobs open to India, and of those how many state a fresher-friendly level
(intern / fresher / junior, or at most 1 year) by today's rules, how many are senior/mid,
and how many state no level at all. No LLM; nothing is written to the database.

Usage: python -m scripts.probe_boards [--out data/board_candidates.csv]
"""

import argparse
import asyncio
import csv
import sys
from pathlib import Path

from scripts.check_slugs import ADAPTERS, CSV
from worker.http import PoliteClient
from worker.rules import rule_extract

# Companies that hire in India, many of them freshers, guessed by name; most slugs will 404.
CANDIDATES = """
phonepe swiggy zomato zepto blinkit flipkart myntra meesho nykaa lenskart urbancompany
dunzo rapido ola olaelectric ather cars24 spinny cardekho licious bigbasket udaan
jumbotail ninjacart dealshare purplle mamaearth boat sugarcosmetics firstcry
razorpay cashfree juspay setu jupiter slice fi epifi smallcase zerodha upstox angelone
paytmmoney coindcx coinswitch mobikwik bharatpe pinelabs payu billdesk policybazaar
acko digit insurancedekho navi kreditbee moneyview lendingkart open khatabook okcredit
jar indmoney scripbox kuvera stashfin uni onecard fampay junio
freshworks zoho chargebee postman browserstack hasura druva sprinklr thoughtspot
innovaccer icertis mindtickle leadsquared capillary whatfix yellowai haptik uniphore
gupshup exotel ozonetel kaleyra netcore moengage clevertap webengage wingify vwo
appsmith tooljet hoppscotch rocketlane everstage zluri toplyne springworks dyte 100ms
sprinto scrut darwinbox keka zimyo greythr pazcare plum loop onsurity
unacademy upgrad byjus vedantu physicswallah scaler interviewbit simplilearn greatlearning
eruditus emeritus classplus teachmint leverageedu cuemath toppr masaischool newtonschool
sharechat mohallatech dailyhunt verse inshorts pocketfm kukufm pratilipi glance roposo
dream11 dreamsports mpl games24x7 winzo nazara junglee zupee
practo pharmeasy 1mg tata1mg medibuddy healthifyme cultfit curefit innovaccer qure
niramai pristyncare mfine
delhivery shiprocket blackbuck rivigo porter shadowfax ecomexpress xpressbees loadshare
ofbusiness zetwerk moglix infra.market bizongo jumbotail
tekion highradius sigmoid fractal tigeranalytics mutualmobile mu-sigma latentview
gojek grab atlassian uber intuit adobe salesforce nutanix cohesity rubrik servicenow
confluent hashicorp cloudflare dropbox pinterest snowflake okta twilio
deliveryhero swiggyinstamart urbanladder pepperfry livspace homelane nobroker housing
magicbricks squareyards nestaway stanza zolo oyo makemytrip goibibo ixigo cleartrip
easemytrip yatra redbus
smartsheet conga enterpret cambiumnetworks zaimler ashahealth asha-health sanas workato toast
thoughtworks addepar canonical remotecom deel posthog getsimpl ultrahuman rupeek clear cleartax
kissht leena leenaai gong airtable mediaocean zeotap arcesium nference lambdatest testsigma
kapture hackerearth pubmatic eightfold eightfoldai gohighlevel highlevel zendesk sentry
mattermost automattic wise gitbook hightouch rudderstack chronosphere cohere sarvamai
krutrim ola-krutrim neysa jiohaptik truefoundry portkey composio maximai lyzr simplismart
""".split()


async def probe(client, ats: str, slug: str):
    mod = ADAPTERS[ats]
    try:
        data = await client.get_json(mod.url(slug))
    except Exception as e:  # a board that errors is reported, not fatal
        return {"ats": ats, "slug": slug, "error": type(e).__name__}
    if data is None:
        return None
    jobs = mod.parse(data, slug)
    if not jobs:
        return None
    india = [j for j in jobs if j.india_ok]
    fit = senior = unknown = 0
    for j in india:
        x = rule_extract(j.title, j.description_text or "")
        if x.seniority in ("intern", "fresher", "junior") or (
                x.min_exp_years is not None and x.min_exp_years <= 1):
            fit += 1
        elif x.seniority is None and x.min_exp_years is None:
            unknown += 1
        else:
            senior += 1
    return {"ats": ats, "slug": slug, "jobs": len(jobs), "india": len(india),
            "india_fresher_fit": fit, "india_mid_senior": senior, "india_no_level": unknown}


async def main(out: Path, only: list[str] | None = None) -> None:
    with open(CSV, encoding="utf-8") as f:
        have = {r["slug"].lower() for r in csv.DictReader(f)}
    pool = only or CANDIDATES
    slugs = [s for s in dict.fromkeys(pool) if s.lower() not in have]
    async with PoliteClient(retries=1, timeout=30) as client:
        found = await asyncio.gather(*(probe(client, ats, s) for s in slugs for ats in ADAPTERS))
    rows = sorted((r for r in found if r), key=lambda r: -r.get("india_fresher_fit", -1))
    cols = ["ats", "slug", "jobs", "india", "india_fresher_fit", "india_mid_senior",
            "india_no_level", "error"]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"probed {len(slugs)} slugs x {len(ADAPTERS)} boards; found {len(rows)}; wrote {out}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=CSV.parent / "board_candidates.csv")
    ap.add_argument("--slugs", nargs="*", help="probe only these slugs")
    a = ap.parse_args()
    asyncio.run(main(a.out, a.slugs))
