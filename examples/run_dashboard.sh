#!/usr/bin/env bash
# Launch the Streamlit dashboard.
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${PORT:-8501}"
echo "[run_dashboard] starting Streamlit on port ${PORT}"
exec streamlit run qrp_platform/dashboard/app.py --server.port "${PORT}" --server.address 0.0.0.0