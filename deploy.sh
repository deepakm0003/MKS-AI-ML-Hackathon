#!/bin/bash
# Quick deployment script for college GPU server

set -e

echo "=== Celeris Control Tower - Deployment Script ==="
echo

# 1. Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 not found. Install Python 3.11+ first."
    exit 1
fi
echo "✓ Python 3 found: $(python3 --version)"

# 2. Install Python dependencies
echo
echo "Installing Python dependencies..."
pip install -q -r requirements.txt
echo "✓ Dependencies installed"

# 3. Run pipeline
echo
echo "Running pipeline (generates all outputs, ~5 min)..."
python3 run_pipeline.py
echo "✓ Pipeline complete"

# 4. Build frontend
echo
echo "Building frontend..."
cd dashboard
if ! command -v npm &> /dev/null; then
    echo "WARNING: npm not found. Skipping frontend build."
    echo "The API will work but the UI won't be served."
    cd ..
else
    npm install
    npm run build
    cd ..
    echo "✓ Frontend built → dashboard/dist/"
fi

# 5. Start server
echo
echo "=== Starting server ==="
echo "API + Dashboard will be available at:"
echo
echo "  http://$(hostname -I | awk '{print $1}'):8000"
echo
echo "Press Ctrl+C to stop"
echo
python3 -m uvicorn api.app:app --host 0.0.0.0 --port 8000
