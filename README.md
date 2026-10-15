# cpanel-spam-filter-sync

Keep spam rules in one small YAML file and sync them to **cPanel server-side
email filters** with the UAPI `Email::store_filter` endpoint. Filtering then
runs on the mail server at delivery time, so it **uses no client resources**:
no IMAP polling, no desktop add-ins, and it works the same in every mail client.

## How it works
- `allow_domains`: a "From contains" filter that stops processing, so trusted senders are never moved.
- `from_contains`, `subject_contains`, `auth_fail_patterns`: OR-matched filters, split into chunks of `chunk` patterns, that save matches to the spam folder.
- Managed filters are named `<prefix> <n> <kind> <i>`. If a filter already exists it is updated, and the managed filters are moved to the top with `Email::reorder_filters`.
- Nothing is ever deleted. Managed filters that no longer appear in the rules are reported as STALE so you can review them by hand.

## Setup
    python -m venv .venv && . .venv/bin/activate
    pip install -r requirements.txt
    cp rules.example.yaml rules.yaml   # edit patterns and mailboxes
    export CPANEL_URL=https://cpanel.example.com:2083
    export CPANEL_USER=youruser
    read -rs CPANEL_API_TOKEN && export CPANEL_API_TOKEN   # env var only
    # optional: CPANEL_MAILBOXES=a@example.com,b@example.com  FILTER_PREFIX="custom spam"

## Usage
    python sync_filters.py --dry-run          # print the plan, make no API calls
    python sync_filters.py                    # apply
    python sync_filters.py -c other.yaml

## Tests
    pip install -r requirements-dev.txt && pytest -q   # all HTTP is mocked

License: MIT
