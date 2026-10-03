# G9 — Demo Order Execution

This is an isolated, one-shot OKX Demo execution path.

## Safety contract

- `IS_DEMO=true` is mandatory.
- `DRY_RUN=false` is mandatory for the actual Demo submission.
- `G9_DEMO_CONFIRM=true` is mandatory.
- The dedicated G9 compose service is separate from the normal bot.
- The normal `docker-compose.yml` keeps `DRY_RUN=true`.
- G9 submits exactly one limit order and has no retry loop.
- After submission G9 reads the real order state with `fetch_order` and cancels the order if it is still working. Cancellation is not an order submission; G9 never submits a second order and never auto-closes a position.
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
- order_id
- submit_status (status in the submit response, often empty)
- status (verified with `fetch_order`)
- filled, position_size
- cleanup
- timestamp

`cleanup` values: `CANCELED` (cancel confirmed), `NOT_NEEDED` (already canceled/expired/rejected), `FILLED_POSITION_OPEN` (order filled; close the Demo position manually, a warning is printed to stderr), `FAILED` (order may still be open; the run exits non-zero and the order must be canceled manually in the OKX Demo UI).

A successful G9 run must contain a real OKX Demo `order_id`. CI/test success alone is not G9 PASS.