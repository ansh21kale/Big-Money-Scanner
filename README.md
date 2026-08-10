# Big Money Scanner V1

A starter real-time scanner for NIFTY 50 and BANKNIFTY options using Upstox Option Chain API.

## What it does
- Polls Upstox option-chain data.
- Calculates traded money = LTP × volume.
- Tracks local volume history to calculate volume spike.
- Calculates OI change and classifies:
  - Price ↑ + OI ↑ = Long Build-up
  - Price ↓ + OI ↑ = Short Build-up
  - Price ↑ + OI ↓ = Short Covering
  - Price ↓ + OI ↓ = Long Unwinding
- Calculates a normalized Big Money Score from 0–100.
- Shows ₹10Cr / ₹25Cr / ₹50Cr activity levels.
- Provides a mobile-friendly dashboard.

## Important
This is an analytics prototype, not an order-placement system and not a guarantee that activity belongs to a particular institution.

## Setup
1. Install Python 3.11+.
2. `pip install -r requirements.txt`
3. Copy `.env.example` to `.env`.
4. Put your Upstox access token in `UPSTOX_ACCESS_TOKEN`.
5. Run: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
6. Open `http://localhost:8000`

Upstox access tokens are sensitive. Do not put them in frontend JavaScript or commit `.env`.
