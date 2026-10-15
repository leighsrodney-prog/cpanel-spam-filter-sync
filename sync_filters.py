#!/usr/bin/env python3
"""Sync YAML spam rules into cPanel server-side email filters via UAPI.

Configuration (environment variables override the YAML config):
  CPANEL_URL        Base URL, e.g. https://cpanel.example.com:2083
  CPANEL_USER       cPanel account username
  CPANEL_API_TOKEN  cPanel API token (env var only, never in config)
  CPANEL_MAILBOXES  Comma-separated mailboxes (overrides `mailboxes` in rules)
  FILTER_PREFIX     Prefix for managed filter names (default "custom spam")

Filters are created/updated with Email::store_filter. Existing filters are
never deleted; stale managed filters are only reported.
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

import yaml

DEFAULT_PREFIX = "custom spam"


def load_rules(path):
    with open(path) as fh:
        rules = yaml.safe_load(fh) or {}
    for key in ("allow_domains", "from_contains", "subject_contains", "auth_fail_patterns"):
        rules.setdefault(key, [])
    rules.setdefault("chunk", 6)
    rules.setdefault("spam_folder", ".spam")
    return rules


def get_config(rules, env=None):
    env = os.environ if env is None else env
    mailboxes = env.get("CPANEL_MAILBOXES")
    mailboxes = [m.strip() for m in mailboxes.split(",") if m.strip()] if mailboxes else rules.get("mailboxes", [])
    return {
        "url": (env.get("CPANEL_URL") or rules.get("cpanel_url") or "").rstrip("/"),
        "user": env.get("CPANEL_USER") or rules.get("cpanel_user") or "",
        "token": env.get("CPANEL_API_TOKEN", ""),
        "mailboxes": mailboxes,
        "prefix": env.get("FILTER_PREFIX") or rules.get("filter_prefix") or DEFAULT_PREFIX,
    }


def chunks(items, n):
    return [items[i:i + n] for i in range(0, len(items), n)]


def plan(rules, prefix=DEFAULT_PREFIX):
    """Return [(filter_name, [(part, match, value)], (action, dest))]."""
    filters = []
    if rules["allow_domains"]:
        filters.append((f"{prefix} 0 allow",
                        [("$header_from:", "contains", d) for d in rules["allow_domains"]],
                        ("finish", "")))
    n = 1
    for kind, part, vals in [("from", "$header_from:", rules["from_contains"]),
                             ("subject", "$header_subject:", rules["subject_contains"]),
                             ("auth", "$h_Authentication-Results:", rules["auth_fail_patterns"])]:
        for i, c in enumerate(chunks(vals, rules["chunk"])):
            filters.append((f"{prefix} {n} {kind} {i + 1}",
                            [(part, "contains", v) for v in c],
                            ("save", rules["spam_folder"])))
            n += 1
    return filters


def build_params(account, name, rules, action, existing):
    if action[0] not in ("finish", "save"):
        raise ValueError(f"unsupported action {action[0]}")
    p = {"account": account, "filtername": name}
    if name in existing:
        p["oldfiltername"] = name
    for i, (part, match, val) in enumerate(rules, 1):
        p[f"part{i}"], p[f"match{i}"], p[f"val{i}"] = part, match, val
        if i < len(rules):
            p[f"opt{i}"] = "or"
    p["action1"] = action[0]
    if action[1]:
        p["dest1"] = action[1]
    return p


def uapi(cfg, fn, params):
    data = urllib.parse.urlencode(params, doseq=True).encode()
    req = urllib.request.Request(
        f"{cfg['url']}/execute/{fn}", data=data,
        headers={"Authorization": f"cpanel {cfg['user']}:{cfg['token']}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def sync(cfg, rules, dry_run=False, call=uapi, out=print):
    filters = plan(rules, cfg["prefix"])
    for acct in cfg["mailboxes"]:
        out(f"== {acct}")
        for name, rs, act in filters:
            out(f"  {name}: {act[0]} {act[1]} <- {[r[2] for r in rs]}")
        if dry_run:
            continue
        existing = [f["filtername"] for f in (call(cfg, "Email/list_filters", {"account": acct})["data"] or [])]
        for name, rs, act in filters:
            r = call(cfg, "Email/store_filter", build_params(acct, name, rs, act, existing))
            out(f"  store {name}: status={r['status']} errors={r['errors']}")
        ours = [f[0] for f in filters]
        stale = [e for e in existing if e.startswith(cfg["prefix"]) and e not in ours]
        if stale:
            out(f"  STALE (not deleted; review manually): {stale}")
        cur = [f["filtername"] for f in (call(cfg, "Email/list_filters", {"account": acct})["data"] or [])]
        order = ours + [x for x in cur if x not in ours]
        params = {"mailbox": acct, **{f"filter{i}": x for i, x in enumerate(order, 1)}}
        r = call(cfg, "Email/reorder_filters", params)
        out(f"  reorder: status={r['status']} errors={r['errors']}")
    return filters


def main(argv=None):
    ap = argparse.ArgumentParser(description="Sync YAML spam rules into cPanel email filters (UAPI Email::store_filter).")
    ap.add_argument("-c", "--rules", default=os.environ.get("RULES_FILE", "rules.yaml"), help="rules YAML file (default: rules.yaml or $RULES_FILE)")
    ap.add_argument("--dry-run", action="store_true", help="print the planned filters without calling the API")
    args = ap.parse_args(argv)
    rules = load_rules(args.rules)
    cfg = get_config(rules)
    if not cfg["mailboxes"]:
        sys.exit("no mailboxes configured (rules `mailboxes` or CPANEL_MAILBOXES)")
    if not args.dry_run and not (cfg["url"] and cfg["user"] and cfg["token"]):
        sys.exit("CPANEL_URL, CPANEL_USER and CPANEL_API_TOKEN must be set")
    sync(cfg, rules, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
