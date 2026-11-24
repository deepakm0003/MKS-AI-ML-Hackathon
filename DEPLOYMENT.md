# Deployment Guide — Celeris Control Tower

## Prerequisites on the server
- Python 3.11+
- Node.js 18+ (for building the frontend)
- Git

## Step 1: Clone and setup on the server

```bash
# SSH into your GPU server
ssh your_username@server_address

# Clone the repo
git clone https://github.com/deepakm0003/mks-celeris-demand-forecasting.git
cd mks-celeris-demand-forecasting

# Install Python dependencies
pip install -r requirements.txt

# Run the pipeline to generate all outputs (roughly 40-60 minutes: it includes the 6-cutoff backtest)
python run_pipeline.py

# Verify outputs exist
ls -lh outputs/final/
# Should show submission.csv, forecast_detail.csv, etc.
```

## Step 2: Build the frontend

```bash
cd dashboard
npm install
npm run build
# Creates dashboard/dist/ with optimized static files
cd ..
```

## Step 3: Run the API (serves both API and frontend)

Create a startup script `start_server.sh`:

```bash
#!/bin/bash
cd /path/to/celeris-control-tower
uvicorn api.app:app --host 0.0.0.0 --port 8000 &
echo "API running on http://your-server-ip:8000"
echo "Dashboard at http://your-server-ip:8000"
```

Make it executable and run:

```bash
chmod +x start_server.sh
./start_server.sh
```

## Step 4: Serve the frontend via the API

Nothing to add: `api/app.py` already serves `dashboard/dist` when it exists. Notes:

* The static / SPA routes are registered **after** every API router, so `/scenario/*`, `/meta/filters`
  and the other API routes are never answered with `index.html`. An unknown API path returns a JSON 404.
* The built dashboard calls `/api/<route>`. The API strips that prefix itself, so the same build works
  behind nginx (which strips it too, Option 3) and when uvicorn serves everything on port 8000.
* Files are only served from inside `dashboard/dist`.

Restart the server and visit `http://your-server-ip:8000`

---

## Option 2: Use Docker (Production-grade)

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python run_pipeline.py
EXPOSE 8000
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run:

```bash
docker build -t celeris-control-tower .
docker run -d -p 8000:8000 celeris-control-tower
```

---

## Option 3: nginx reverse proxy (for custom domain)

If your college server has nginx:

```nginx
server {
    listen 80;
    server_name your-domain.edu;
    
    location /api/ {
        proxy_pass http://localhost:8000/;
    }
    
    location / {
        root /path/to/celeris-control-tower/dashboard/dist;
        try_files $uri $uri/ /index.html;
    }
}
```

---

## Firewall / Port opening

Ask your college IT to open port 8000 (or 80 if using nginx) for external access.

---

## Share with judges

Once deployed, share:
- **Live URL**: `http://your-server-ip:8000` or `http://your-domain.edu`
- **GitHub repo**: https://github.com/deepakm0003/mks-celeris-demand-forecasting
- **Demo video** (optional but recommended): 2-minute walkthrough

---

## Troubleshooting

**API returns 503 "not generated yet"**
→ Run `python run_pipeline.py` on the server

**Frontend shows blank page**
→ Check `dashboard/dist/index.html` exists and contains `<script src="/assets/index-*.js">`

**CORS errors**
→ Add to `api/app.py`:
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"])
```

**Port 8000 not accessible**
→ Check firewall: `sudo ufw allow 8000` or ask IT admin

---

## Keeping it running (production)

Use `systemd` service or `screen`:

```bash
# Option A: screen (simple)
screen -S celeris
./start_server.sh
# Press Ctrl+A, then D to detach

# Option B: systemd service
sudo nano /etc/systemd/system/celeris.service
# (see systemd template below)
sudo systemctl enable celeris
sudo systemctl start celeris
```

### systemd service template

```ini
[Unit]
Description=Celeris Control Tower API
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/celeris-control-tower
ExecStart=/usr/bin/python3 -m uvicorn api.app:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```
