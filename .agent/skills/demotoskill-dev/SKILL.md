---
name: demotoskill-dev
description: >-
  Developer procedures, commands, and workflows for building, testing, and demonstrating DemoToSkill.
  Use when starting backend, frontend, or demo app services, running Gemma 4 smoke tests, or testing ablation mutations.
---

# DemoToSkill Developer Runbook

This skill provides step-by-step instructions for operating and developing the DemoToSkill codebase.

---

## 1. Environment Setup

### Backend (Python 3.11+)
```bash
# In Hacktoberfest-Goa root
python -m venv venv
.\venv\Scripts\activate       # Windows PowerShell
pip install -r backend/requirements.txt
playwright install chromium
```

### Frontend (Node 18+)
```bash
cd frontend
npm install
```

### Configuration (`.env`)
Ensure `.env` exists in the repository root:
```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMMA_MODEL=gemma-4-26b-a4b-it
GEMMA_REPAIR_MODEL=gemma-4-31b-it
PORT=8000
FRONTEND_PORT=5173
DEMO_APP_PORT=8080
```

---

## 2. Running Services

### A. Start the Target Demo App
Runs the ScholarshipPortal on port 8080:
```powershell
python -m http.server 8080 --directory demo_app
```
- Standard mode: `http://localhost:8080/`
- Mutated mode: `http://localhost:8080/?v=2`

### B. Start the FastAPI Backend
Runs with automatic reload on port 8000:
```powershell
cd backend
uvicorn app.main:app --reload --port 8000
```
- Swagger Docs: `http://localhost:8000/docs`
- SSE Endpoints: `http://localhost:8000/api/record/events`, `/api/compile/{id}/events`, `/api/run/{id}/events`

### C. Start the Frontend Dashboard
```powershell
cd frontend
npm run dev
```
Dashboard opens at `http://localhost:5173`.

---

## 3. Critical Verification & Smoke Tests

### Gemma 4 Multimodal Smoke Test (Hour 0:00 - 0:45)
Run before building further to ensure Google GenAI API credentials and Gemma 4 model support are active:
```powershell
python scripts/smoke_test_gemma.py
```
This verifies:
1. Valid API key connection.
2. Capability to ingest a base64/local image screenshot.
3. Successful generation and parsing of valid JSON output.

### Running the Ablation Benchmark
Generates the comparison table proving Gemma 4 Set-of-Marks performance against rule-based/BM25 baseline:
```powershell
python scripts/ablation.py
```
Outputs the ablation metrics table to console and `specs/ablation_results.json`.

