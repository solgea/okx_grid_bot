# G9 — Demo Order Execution

This is an isolated, one-shot OKX Demo execution path.

## Safety contract

- `IS_DEMO=true` is mandatory.
- `DRY_RUN=false` is mandatory for the actual Demo submission.
- `G9_DEMO_CONFIRM=true` is mandatory.
- The dedicated G9 compose service is separate from the normal bot.
- The normal `docker-compose.yml` keeps `DRY_RUN=true`.
- G9 submits exactly one limit order and has no retry loop.
- No mainnet, withdrawal, account mutation, or grid/batch submission is supported.

## Configure

Keep credentials only in the local `.env` file:

```env
API_KEY=...
API_SECRET=...
PASSPHRASE=...
IS_DEMO=true
```

Do not commit `.env` or print credential values.

## Preflight

G9 fetches current instrument metadata, account state, and market data from OKX Demo, then requires `PreFlightState.AUTHORIZED` before submission.

The dedicated G9 process may temporarily disable the normal kill switch only inside that one-shot process. The regular bot configuration remains unchanged.

## Run

Build and run the isolated service:

```powershell
docker compose -f docker-compose.g9.yml build
docker compose -f docker-compose.g9.yml run --rm okx-grid-bot-g9
```

Expected successful output is a single JSON evidence line containing:

- gate
- mode
- symbol
- preflight
- exchange order id
- exchange status
- timestamp

A successful G9 run must contain a real OKX Demo `order_id`. CI/test success alone is not G9 PASS.