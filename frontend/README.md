# Sentra Frontend Dashboard

React 19 + TypeScript + Vite single-page dashboard for the Sentra AI Infrastructure Audit Platform.

---

## Tech Stack

- **Framework**: React 19 + TypeScript 5
- **Build Tool**: Vite 8 with Hot Module Replacement (HMR)
- **Styling**: Tailwind CSS v4
- **Maps**: Leaflet + React-Leaflet
- **Linter**: Oxlint

---

## Local Development Setup

### Prerequisites

- Node.js 20+
- npm 10+

### Installation

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install
```

### Running Development Server

```bash
npm run dev
```

The app will start at `http://localhost:5173`.

> **Note**: In development mode, Vite automatically proxies API requests (`/api` and `/reports`) to `http://localhost:8050` (configurable in `vite.config.ts`).

---

## Environment Variables

Create `.env.local` in the `frontend` directory if pointing to a non-local backend:

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_URL` | `http://localhost:8050` | Base URL of the Sentra FastAPI backend |

---

## Scripts

```bash
# Start development server
npm run dev

# Run TypeScript type check and build static production bundle
npm run build

# Run linter
npm run lint

# Preview production build locally
npm run preview
```

---

## Docker Deployment (Nginx)

To build and run the frontend production static container independently:

```bash
# Build Docker image
docker build --build-arg VITE_API_URL=http://your-backend-api:8050 -t sentra-frontend .

# Run container
docker run -d -p 80:80 --name sentra-web sentra-frontend
```

The container uses Nginx to serve static files built into `dist/` and handle client-side routing.
