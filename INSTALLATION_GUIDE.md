# Installation & Deployment Guide

## 🎯 Prerequisites

- Python 3.8+
- Ollama installed and running
- pip package manager
- 2GB free disk space (for Qwen3 8B model)

---

## 📦 Step 1: Install Dependencies

### Option A: Fresh Installation

```bash
# Navigate to project directory
cd c:\Users\honey\denz-backend

# Install all requirements
pip install -r requirements.txt
```

### Option B: Upgrade Existing Installation

```bash
# Install new web search packages
pip install duckduckgo-search httpx

# Or update all requirements
pip install -r requirements.txt --upgrade
```

---

## 🤖 Step 2: Setup Ollama Model

### Pull Qwen3 8B Model

```bash
ollama pull qwen3:8b
```

**Output will show**:
```
pulling manifest
pulling 2bd447ae6782... 100% ▕███████████████████████████████████████████████▏ 8.0 GB
pulling 82551e91d439... 100% ▕███████████████████████████████████████████████▏ 1.2 MB
pulling f02d4cc4f975... 100% ▕███████████████████████████████████████████████▏ 7.3 KB
pulling 2e0493f67d0c... 100% ▕███████████████████████████████████████████████▏ 59 B
pulling bebeac3d2f04... 100% ▕███████████████████████████████████████████████▏ 409 B
digests: sha256:24e... sha256:f49... sha256:dd1... sha256:33c... sha256:83c...
```

### Verify Model Installation

```bash
ollama list
# Should show: qwen3:8b          8.0 GB         4 hours ago
```

---

## 🔧 Step 3: Environment Configuration

### Option A: Using .env File (Recommended)

Create `.env` in project root:

```env
# Ollama Configuration
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b
OLLAMA_TIMEOUT=15

# Weather API (optional)
WEATHER_API_KEY=your_openweather_api_key_here

# Server Configuration (optional)
FLASK_ENV=production
DEBUG=False
```

### Option B: Using Environment Variables

```bash
# Windows (PowerShell)
$env:OLLAMA_URL = "http://localhost:11434"
$env:OLLAMA_MODEL = "qwen3:8b"
$env:OLLAMA_TIMEOUT = "15"

# Windows (Command Prompt)
set OLLAMA_URL=http://localhost:11434
set OLLAMA_MODEL=qwen3:8b
set OLLAMA_TIMEOUT=15

# Linux/Mac
export OLLAMA_URL=http://localhost:11434
export OLLAMA_MODEL=qwen3:8b
export OLLAMA_TIMEOUT=15
```

---

## 🚀 Step 4: Start the Application

### Step 4A: Start Ollama (if not running)

**Windows**:
```bash
ollama serve
# Running on http://localhost:11434
```

**Linux/Mac**:
```bash
ollama serve
```

**Note**: Leave this terminal running in the background

### Step 4B: Start Flask Backend

In a new terminal:

```bash
cd c:\Users\honey\denz-backend

# Activate virtual environment (if using one)
.\venv\Scripts\Activate.ps1

# Start the app
python denz.py
```

**Expected Output**:
```
🚀 Warming up Ollama...
   Attempt 1/10: Checking Ollama at http://localhost:11434
   ✅ Ollama is running. Available models: ['qwen3:8b', 'llama3.1:8b']
   ✅ Model 'qwen3:8b' pulled successfully
   🚀 Making warmup request to load model into memory...
   ✅ Ollama Ready!
   
 * Running on http://127.0.0.1:5000
 * Debug mode: off
```

---

## ✅ Step 5: Verify Installation

### Test 1: Check Health

```bash
curl http://localhost:5000/api/health

# Expected response:
{
  "status": "healthy",
  "service": "DENZ",
  "version": "3D-ULTRA-AI-FASTEST",
  "ollama": {
    "connected": true,
    "model": "qwen3:8b",
    "ready": true,
    "models": ["qwen3:8b", "llama3.1:8b"]
  }
}
```

### Test 2: Test Weather Query

```bash
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the weather?", "session_id": "test1"}'

# Should respond with routing.intent: "weather"
```

### Test 3: Test Location Query

```bash
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the capital of India?", "session_id": "test2"}'

# Should respond with routing.intent: "location"
```

### Test 4: Test Web Search

```bash
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the latest news on AI?", "session_id": "test3"}'

# Should respond with web_search.performed: true
```

### Test 5: Test General Chat

```bash
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Explain machine learning", "session_id": "test4"}'

# Should respond normally without web search
```

---

## 📊 Performance Benchmark

After installation, you should see response times like:

```
Test Case                    Expected Time   Model Used
─────────────────────────────────────────────────────
Weather Query                500ms          Weather API
Location Query               50ms           Local Lookup
Web Search Query             2-3s           Web + Ollama
General Chat                 3-5s           Ollama (qwen3)
First Startup                ~30s           Model Loading
Subsequent Requests          <5s            Cache Hit
```

---

## 🐛 Troubleshooting Installation

### Issue: "Ollama connection refused"

**Solution**:
```bash
# Verify Ollama is running
ollama list

# If not running, start it
ollama serve

# Check if port 11434 is accessible
curl http://localhost:11434/api/tags
```

### Issue: "Model qwen3:8b not found"

**Solution**:
```bash
# Pull the model
ollama pull qwen3:8b

# Verify
ollama list | grep qwen3
```

### Issue: "duckduckgo_search import error"

**Solution**:
```bash
# Reinstall the package
pip uninstall duckduckgo-search -y
pip install duckduckgo-search==3.9.10
```

### Issue: "Port 5000 already in use"

**Solution**:
```python
# In denz.py, change the port:
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False)  # Use 5001 instead
```

### Issue: "Out of memory" error

**Solution**:
- Qwen3 8B requires ~8GB RAM
- Close other applications
- Consider using smaller model: `ollama pull mistral:latest`

---

## 🚢 Production Deployment

### Using Gunicorn (Recommended)

```bash
# Install gunicorn (if not already)
pip install gunicorn

# Run with gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 denz:app

# Or with more workers for high traffic
gunicorn -w 8 -b 0.0.0.0:5000 --worker-class sync denz:app
```

### Using Docker

Create `Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Expose port
EXPOSE 5000

# Run application
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "denz:app"]
```

Build and run:
```bash
# Build image
docker build -t denz-backend .

# Run container
docker run -p 5000:5000 \
  -e OLLAMA_URL=http://host.docker.internal:11434 \
  denz-backend
```

### Using Systemd (Linux)

Create `/etc/systemd/system/denz.service`:
```ini
[Unit]
Description=DENZ AI Backend
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/home/denz-backend
ExecStart=/usr/bin/python3 /home/denz-backend/denz.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Start service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable denz
sudo systemctl start denz
sudo systemctl status denz
```

---

## 📈 Performance Optimization

### 1. Enable Caching

Already enabled by default. Verify in logs:
```
🚀 In-memory weather cache hit for Shimla
📦 DB weather cache hit for Delhi
```

### 2. Adjust Model Timeout

Edit `.env`:
```env
# For slower systems
OLLAMA_TIMEOUT=30

# For faster systems
OLLAMA_TIMEOUT=10
```

### 3. Monitor Resource Usage

```bash
# Check Ollama memory usage
ps aux | grep ollama

# Monitor system resources
top  # Linux/Mac
Get-Process python  # Windows
```

### 4. Database Optimization

Clean old cache entries:
```bash
# Use Flask shell
python
>>> from denz import app, db, WeatherCache, ChatMessage
>>> with app.app_context():
>>>     db.session.query(WeatherCache).delete()
>>>     db.session.commit()
```

---

## 🔄 Updating to Newer Versions

### Update Requirements

```bash
pip install -r requirements.txt --upgrade
```

### Update Ollama Models

```bash
# Pull latest version
ollama pull qwen3:8b

# Or switch to newer model
ollama pull qwen3:11b
```

### Update Code

```bash
# If using git
git pull origin main

# Restart application
# Press Ctrl+C to stop
python denz.py
```

---

## 📚 Next Steps

1. **Frontend Integration**: Update your frontend to use new routing info
2. **API Documentation**: Generate docs with: `pip install flask-swagger-ui`
3. **Monitoring**: Setup logs to file for production
4. **Backup**: Regular database backups for chat history
5. **Rate Limiting**: Add rate limiting for production

---

## 🆘 Support

If you encounter issues:

1. **Check logs**: Look at console output and error messages
2. **Test endpoints**: Use curl/Postman to test individually
3. **Verify services**: Ensure Ollama and Flask are running
4. **Review configs**: Check .env and environment variables
5. **Check documentation**: See IMPROVEMENTS_SUMMARY.md and ROUTER_QUICK_REFERENCE.md

---

## ✨ Successful Installation Checklist

- [ ] Python 3.8+ installed
- [ ] Ollama running with qwen3:8b model
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Environment variables configured
- [ ] Flask app starts without errors
- [ ] Health check endpoint responds
- [ ] Weather query works
- [ ] Location query works
- [ ] Web search query works
- [ ] Chat works

---

*Installation completed! Your DENZ backend is ready to use.* 🎉

For issues or questions, check the troubleshooting section or review the detailed documentation files.
