# Sentra Backend API & Audit Engine

FastAPI-powered satellite audit backend for detecting non-existent public infrastructure projects, parsing tender documents, executing computer vision change detection, and generating evidence reports.

---

## Tech Stack & Architecture

- **Framework**: FastAPI (Python 3.11) + Uvicorn
- **Parsing**: Groq LLM API + PyMuPDF / Tesseract OCR
- **Geocoding**: OpenStreetMap Nominatim / Custom fallback
- **Satellite Provider**: Esri Wayback Imagery API
- **Computer Vision**: OpenCV + SciPy + NumPy (SSIM, NDVI/NDWI, Spectral Change Detection)
- **Reporting**: Jinja2 HTML Evidence Cards + JSON Store

---

## Local Development Setup

### Prerequisites

- Python 3.11+
- Tesseract OCR (`apt install tesseract-ocr` or `brew install tesseract`)

### Installation

```bash
# Navigate to backend directory
cd backend

# Install dependencies
pip install -r requirements.txt

# Create .env file (copy from root .env.example)
cp ../.env.example .env
```

### Running the API Server

```bash
# Using main.py CLI
python main.py serve

# Or directly with Uvicorn
uvicorn src.api.app:app --host 127.0.0.1 --port 8050 --reload
```

The API will be available at:
- **Base URL**: `http://127.0.0.1:8050`
- **Interactive Swagger Docs**: `http://127.0.0.1:8050/docs`
- **ReDoc API Documentation**: `http://127.0.0.1:8050/redoc`

---

## CLI Tools (`main.py`)

The backend includes a command-line interface for running audits and managing data without the web server:

```bash
# Run demonstration audits on pre-configured sample tenders
python main.py demo

# Audit a specific tender file
python main.py audit --file data/sample_tenders/tender_001_ghost_road.txt

# Batch-scan raw tender documents in data/raw_tenders/
python main.py scan

# Clear all stored audit records and generated evidence cards
python main.py clear
```

---

## Running Tests

Execute the backend test suite with `pytest`:

```bash
python -m pytest tests/ -v
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | None | API key for Groq LLM tender parsing |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Allowed frontend origins for CORS |
| `SENTRA_HOST` | `0.0.0.0` | API bind address |
| `SENTRA_PORT` | `8050` | API listen port |

---

## Docker Containerization

To build and run the backend container independently:

```bash
# Build Docker image
docker build -t sentra-backend .

# Run container
docker run -d -p 8050:8050 --env-file ../.env -v $(pwd)/data:/app/data --name sentra-api sentra-backend
```
