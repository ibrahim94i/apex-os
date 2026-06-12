# APEX Price Feed EA (MetaTrader 4)

Timer-based price stream to APEX backend — **every 5 seconds**.

## Install

1. Copy `ApexPriceFeed.mq4` to:
   ```
   MetaTrader 4/MQL4/Experts/
   ```
2. Compile in MetaEditor (F7).
3. MT4 → **Tools → Options → Expert Advisors**:
   - Enable *Allow automated trading*
   - Enable *Allow WebRequest for listed URL*
   - Add:
     ```
     https://apex-os-production-9adc.up.railway.app
     ```
4. Attach EA to **XAUUSD** chart (or gold symbol with same quotes).
5. Set inputs:
   - `InpApiKey` = your `METATRADER_API_KEY`
   - `InpApexSymbol` = `XAUUSD`

## Verify

- Chart comment: `APEX OK | HTTP 200`
- Backend: `GET /api/v1/prices/status` → `connected: true`

## Notes

- Uses `OnTimer` only — **not** `OnTick`.
- Sends UTC time as `YYYY.MM.DD HH:MM:SS` (backend-compatible).
- Does not place trades or affect APEX signals.
