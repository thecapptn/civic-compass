# Deploying Civic Compass

Two stages. Tonight is stage one: the Dell, LAN only, demonstration data. Stage two is the
public beta laptop, and it has its own prerequisites at the bottom that are **not** satisfied yet.

---

## Stage 1 — Home server (tonight)

### Push to GitHub

From wherever you unzipped this, with the git history already in place:

```bash
cd civic-compass
gh repo create thecapptn/civic-compass --public --source=. --remote=origin --push
```

Or create it in the web UI and:

```bash
git remote add origin git@github.com:thecapptn/civic-compass.git
git branch -M main
git push -u origin main
```

Nothing sensitive is committed. `.env` is gitignored and the only credential in the tree is the
literal string `demo-ops-token`, which is a placeholder the compose file overrides.

### Install on the Dell

```bash
ssh steve@10.0.0.202
git clone https://github.com/thecapptn/civic-compass.git
cd civic-compass

printf 'CIVIC_COMPASS_OPS_TOKEN=%s\n' "$(openssl rand -hex 24)" > .env

docker compose up -d --build
docker compose logs -f           # ctrl-C once you see uvicorn listening
```

### Reach it

| From | URL |
|---|---|
| Your desktop, same router | `http://10.0.0.202:6021` |
| Your phone, off network | `http://<dell-tailscale-name>:6021` |
| Operations console | `http://10.0.0.202:6021/ops?token=<the token from .env>` |

Add it to Homepage alongside the rest of the fleet. Health endpoint for the widget is
`/healthz`.

### Pulling changes later

```bash
cd civic-compass && git pull && docker compose up -d --build
```

The database lives in `./data` on a mounted volume, so rebuilds do not touch it. The container
seeds only when the database is empty, so a restart will not revert anything you have changed
through the operations console. To deliberately start over: `docker compose down && rm -rf data
&& docker compose up -d`.

---

## About the demonstration data

The dataset is anchored to a fixed set of intervals — a primary that has just finished with
results, a special election a few weeks out, a general a couple of months out — and is shifted
forward by whole weeks when it is seeded, so it never ages into a site that reports it is unsure
of everything. Whole weeks, so elections stay on Tuesdays.

One consequence worth knowing: if you re-seed months from now, the elections move forward again.
They are demonstration elections and never actually arrive. That is the right behaviour for a
demo and the wrong behaviour for real data, which is why real ingestion will not use this path.

To look at the site as it would appear on some other date, without touching the data:

```bash
CIVIC_COMPASS_NOW=2026-12-20T12:00:00+00:00 docker compose up
```

That is also what the test suite uses to keep its assertions about expiry deterministic.

---

## Stage 2 — Public beta laptop

**Do not expose this yet.** Three things are missing, and the first is the one that matters.

### 1. Search engine exclusion — blocking

A demonstration election site indexed by Google is precisely the harm the whole design guards
against. Someone searches for their polling place, lands on invented data, and the banner is the
only thing between them and a wrong answer. Banners get skimmed.

Before anything is publicly reachable it needs `X-Robots-Tag: noindex, nofollow` sitewide and a
`robots.txt` disallow. Neither exists in the code yet.

### 2. Rate limiting — blocking

Every route is an unauthenticated database read. `/report` is an open POST that writes. Cloudflare
absorbs the crude case; per-IP limits on `/resolve` and `/report` handle the rest.

### 3. Access control on the operations console

The token is a query parameter, so it lands in logs and browser history. Put Cloudflare Access in
front of `/ops` and treat the token as a second layer rather than the door.

### Network shape

- **Cloudflare Tunnel, not port forwarding.** The laptop dials out; no inbound ports, your home
  IP never appears in DNS.
- **The beta laptop does not join your tailnet.** A public-facing box on your personal tailnet
  bridges the internet into your LAN. Separate VLAN or guest network, no route to the Dell. If you
  want remote admin, use a second tailnet or SSH behind its own tunnel with Access in front.
- **Invite-gated to start.** Cloudflare Access with an email allowlist, so "beta users" means
  people you invited rather than anyone who finds the URL. Open it up once real data flows behind
  at least one jurisdiction.

None of this applies to the Dell install above, which stays LAN and Tailscale only.
