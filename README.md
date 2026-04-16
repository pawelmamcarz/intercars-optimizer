# INTERCARS — Silnik Optymalizacji Portfela Zamówień

Multi-criteria order portfolio optimiser powered by **HiGHS** solver.
REST API (FastAPI) + interactive dashboard for supply-chain allocation across Central Europe.

![CI](https://github.com/pawelmamcarz/flow-procurement/actions/workflows/ci.yml/badge.svg) [![codecov](https://codecov.io/gh/pawelmamcarz/flow-procurement/graph/badge.svg)](https://codecov.io/gh/pawelmamcarz/flow-procurement) ![Python](https://img.shields.io/badge/python-3.11+-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688) ![HiGHS](https://img.shields.io/badge/solver-HiGHS-D4A843)

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  3. Decision Layer   REST JSON API (/api/v1/*)          │
├─────────────────────────────────────────────────────────┤
│  2. Optimisation     HiGHS LP / MIP solver              │
├─────────────────────────────────────────────────────────┤
│  1. Data Layer       EWM integration + demo dataset     │
└─────────────────────────────────────────────────────────┘
```

## Quick start

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open **http://localhost:8000** → graphical dashboard auto-loads.

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/optimize` | POST | Core optimisation (custom data) |
| `/api/v1/optimize/demo` | GET | Optimisation with built-in demo |
| `/api/v1/dashboard` | POST | Pareto front + radar profiles |
| `/api/v1/dashboard/demo` | GET | Dashboard with demo data |
| `/api/v1/stealth` | POST | Raw solver diagnostics |
| `/api/v1/stealth/demo` | GET | Stealth with demo data |
| `/api/v1/weights/defaults` | GET/PUT | Live weight tuning |
| `/docs` | GET | Swagger UI |

## Mathematical model

**Objective (minimisation):**

```
min Σ [ λ·w_c·ĉ + (1-λ)·w_t·t̂ + w_r·(1-r̂) + w_e·(1-ê) ] · x
```

**Solver modes:**
- **Continuous** — `scipy.optimize.linprog(method='highs')` — fractional allocation
- **MIP** — PuLP + HiGHS — binary supplier selection

## Demo dataset

8 suppliers (TRW, Bosch, LuMag, KraftPol, Brembo, GreenFilter, SK Automotive, RapidStock) ×
12 auto-parts indices × 5 Polish warehouse regions.
