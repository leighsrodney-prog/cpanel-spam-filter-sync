> **This project's home is now [github.com/globe-teck/cpanel-spam-filter-sync](https://github.com/globe-teck/cpanel-spam-filter-sync).** This copy stays up for existing links. Please open issues and pull requests there.

# cpanel-spam-filter-sync

Keep spam rules in one small YAML file and sync them to **cPanel server-side
email filters** with the UAPI `Email::store_filter` endpoint. Filtering then
runs on the mail server at delivery time, so it **uses no client resources**:
no IMAP polling, no desktop add-ins, and it works the same in every mail client.

## Why
Client-side rules only run when a mail client is open, and every client has its
own rule format. Server-side cPanel filters run for every message on delivery,
but editing dozens of them by hand in the web UI is slow and error-prone. This
tool treats the rules as code: one reviewed YAML file, a dry-run plan, and an
idempotent apply.

## Features
- One YAML file for allow-list domains, sender patterns, subject phrases and SPF/DKIM failure markers
- `--dry-run` prints the full plan and makes no API calls
- Idempotent: existing managed filters are updated in place, not duplicated
- Safe by design: nothing is ever deleted; stale managed filters are only reported
- API token read only from an environment variable, never from the config file
- Tests mock all HTTP, so they never touch a real server

## How it works
- `allow_domains`: a "From contains" filter that stops processing, so trusted senders are never moved.
- `from_contains`, `subject_contains`, `auth_fail_patterns`: OR-matched filters, split into chunks of `chunk` patterns, that save matches to the spam folder.
- Managed filters are named `<prefix> <n> <kind> <i>`. If a filter already exists it is updated, and the managed filters are moved to the top with `Email::reorder_filters`.
- Nothing is ever deleted. Managed filters that no longer appear in the rules are reported as STALE so you can review them by hand.

## Setup
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp rules.example.yaml rules.yaml   # edit patterns and mailboxes
export CPANEL_URL=https://cpanel.example.com:2083
export CPANEL_USER=youruser
read -rs CPANEL_API_TOKEN && export CPANEL_API_TOKEN   # env var only
# optional: CPANEL_MAILBOXES=a@example.com,b@example.com  FILTER_PREFIX="custom spam"
```

## Configuration
See [`rules.example.yaml`](rules.example.yaml). Keys:

| Key | Meaning |
|---|---|
| `mailboxes` | Mailboxes to manage (or set `CPANEL_MAILBOXES`) |
| `filter_prefix` | Prefix for managed filter names (or set `FILTER_PREFIX`) |
| `spam_folder` | Folder that matches are saved to |
| `allow_domains` | Trusted senders; matching mail stops processing |
| `from_contains` | Sender patterns sent to the spam folder |
| `subject_contains` | Subject phrases sent to the spam folder |
| `auth_fail_patterns` | Header markers such as `spf=fail` |
| `chunk` | Patterns per filter |

## Usage
```bash
python sync_filters.py --dry-run          # print the plan, make no API calls
python sync_filters.py                    # apply
python sync_filters.py -c other.yaml
```

## Tests
```bash
pip install -r requirements-dev.txt && pytest -q   # all HTTP is mocked
```

## Authorship

Built with AI coding assistance. I defined the requirements, ran the tests, and reviewed the changes.

## License

MIT. See [LICENSE](LICENSE).
