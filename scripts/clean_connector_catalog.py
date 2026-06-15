#!/usr/bin/env python3
"""Clean accumulated test-junk offers from the vm-distributed connectors.

The federated catalog grows with every Level 6 / UI run (qa-ui-*, contract-ui-*,
asset-e2e-*, kafka-edc-asset-*, old contract-pt5-mh-*). The federated catalog
cache is capped (~100 datasets), so once enough junk accumulates the fresh
model / e2e / kafka assets fall outside the cap and discovery/negotiation fail.

This removes junk CONTRACT DEFINITIONS (which is what makes an asset appear as a
dataset/offer in the catalog) and, with --assets, the junk assets+policies too.
It PRESERVES the seeded AI Model Hub assets (company-flares-*, model-flares-*,
company-mobility-*, dataset-flares-*) and their policies/contracts.

Usage:
  python3 scripts/clean_connector_catalog.py            # dry-run (shows targets)
  python3 scripts/clean_connector_catalog.py --apply    # delete contract defs
  python3 scripts/clean_connector_catalog.py --apply --assets   # also assets+policies
  python3 scripts/clean_connector_catalog.py --connectors conn-org2-pionera

Review the dry-run output before using --apply. Deletions are irreversible and
hit the shared dataspace connectors.
"""
import argparse
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = "https://org1.pionera.oeg.fi.upm.es/auth/realms/pionera/protocol/openid-connect/token"
CRED_DIR = "deployers/inesdata/deployments/DEV/vm-distributed/pionera/connectors"
HOSTS = {
    "conn-org2-pionera": "org2.pionera.oeg.fi.upm.es",
    "conn-org3-pionera": "org3.pionera.oeg.fi.upm.es",
}
JUNK_PREFIXES = (
    "qa-ui-", "asset-e2e-", "kafka-edc-asset-", "test-", "asset-crud-", "todos-",
    "e2e-", "contract-e2e-", "policy-e2e-", "contract-crud-", "policy-crud-",
    "contract-ui-", "policy-ui-", "contract-pt5-mh-", "policy-pt5-mh-",
    "pt5-mh-", "asset-ui-", "policy-test-", "contract-test",
)
# Exact ids of the BROAD wildcard seed offers. These contract definitions use an
# empty/all assetsSelector and expose ~100 assets each, bloating the federated
# catalog (MBs/25s -> INESData UI ERR_ABORTED). Removed by exact id so the NARROW
# seed offers (e.g. contractdef-flares-subtask2, which MH-LING needs for consumer
# discovery) are preserved.
JUNK_EXACT = {
    "contract-seed-city", "contract-seed-company",
    "policy-seed-city", "policy-seed-company",
}
# Preserve the seeded model/dataset assets AND their narrow offers (so MH-LING's
# dataset-flares-subtask2 stays discoverable). Only JUNK_EXACT broad offers go.
KEEP_PREFIXES = (
    "company-flares", "model-flares", "company-mobility", "dataset-flares",
    "contract-seed-", "policy-seed-", "contractdef-flares", "policy-flares",
)
EDC_CTX = {"@context": {"@vocab": "https://w3id.org/edc/v0.0.1/ns/"}}
_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def is_junk(identifier: str) -> bool:
    identifier = str(identifier or "")
    # Broad wildcard seed offers are removed by exact id even though their prefix
    # (contract-seed-/policy-seed-) is otherwise preserved.
    if identifier in JUNK_EXACT:
        return True
    if any(identifier.startswith(k) for k in KEEP_PREFIXES):
        return False
    return any(identifier.startswith(j) for j in JUNK_PREFIXES)


def token(conn: str) -> str:
    cu = json.load(open(f"{CRED_DIR}/{conn}/credentials.json"))["connector_user"]
    data = urllib.parse.urlencode({
        "grant_type": "password", "client_id": "dataspace-users",
        "username": cu["user"], "password": cu["passwd"],
    }).encode()
    return json.load(urllib.request.urlopen(
        urllib.request.Request(TOKEN_URL, data=data), timeout=20, context=_ctx))["access_token"]


def query(host: str, tok: str, kind: str):
    body = json.dumps({**EDC_CTX, "@type": "QuerySpec", "limit": 10000}).encode()
    req = urllib.request.Request(
        f"https://{host}/management/v3/{kind}/request", data=body,
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=120, context=_ctx))


def delete(host: str, tok: str, kind: str, ident: str) -> str:
    req = urllib.request.Request(
        f"https://{host}/management/v3/{kind}/{urllib.parse.quote(ident, safe='')}",
        headers={"Authorization": f"Bearer {tok}"}, method="DELETE")
    try:
        urllib.request.urlopen(req, timeout=30, context=_ctx)
        return "ok"
    except urllib.error.HTTPError as exc:
        return str(exc.code)
    except Exception as exc:  # noqa: BLE001
        return f"err:{exc}"


def cdef_asset(cd: dict) -> str:
    sel = cd.get("assetsSelector") or cd.get("https://w3id.org/edc/v0.0.1/ns/assetsSelector") or []
    if isinstance(sel, dict):
        sel = [sel]
    for crit in sel:
        val = crit.get("operandRight") or crit.get("https://w3id.org/edc/v0.0.1/ns/operandRight")
        if val:
            return str(val)
    return ""


def run(conns, apply: bool, assets: bool):
    for conn in conns:
        host = HOSTS[conn]
        tok = token(conn)
        print(f"\n=== {conn} ({host}) {'APPLY' if apply else 'DRY-RUN'} ===")
        cds = query(host, tok, "contractdefinitions")
        targets = []
        for cd in cds:
            cid = cd.get("@id") or cd.get("id")
            if is_junk(cid) or is_junk(cdef_asset(cd)):
                targets.append(cid)
        print(f"contract-definitions: {len(cds)} total, {len(targets)} junk")
        codes = {}
        for cid in targets:
            res = delete(host, tok, "contractdefinitions", cid) if apply else "DRY"
            codes[res] = codes.get(res, 0) + 1
        print(f"  result: {codes}")
        if assets:
            for kind in ("policydefinitions", "assets"):
                items = query(host, tok, kind)
                tg = [(i.get("@id") or i.get("id")) for i in items if is_junk(i.get("@id") or i.get("id"))]
                print(f"{kind}: {len(items)} total, {len(tg)} junk")
                codes = {}
                for ident in tg:
                    res = delete(host, tok, kind, ident) if apply else "DRY"
                    codes[res] = codes.get(res, 0) + 1
                print(f"  result: {codes}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually delete (default: dry-run)")
    ap.add_argument("--assets", action="store_true", help="also delete junk policies+assets")
    ap.add_argument("--connectors", default=",".join(HOSTS), help="comma list")
    args = ap.parse_args()
    run([c.strip() for c in args.connectors.split(",") if c.strip()], args.apply, args.assets)


if __name__ == "__main__":
    main()
