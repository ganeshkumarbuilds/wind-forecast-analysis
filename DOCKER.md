# WindScope containers

## Prerequisites

- Docker Desktop with its Linux container engine running.
- Docker Compose v2 (`docker compose`).
- The backend image uses Python 3.14, matching the project's current runtime.

No Elexon API credentials or database are required by the current application.

## Build and start

From the project root in PowerShell:

```powershell
docker compose up --build -d
```

Open the dashboard at **http://localhost:8080**. The backend health endpoint is also published at **http://localhost:8000/api/v1/health**.

## Request routing

The production frontend is served by unprivileged Nginx on port 8080. Browser requests to `/api/...` are reverse-proxied by Nginx to the Compose service `backend:8000`, preserving the path; for example, `/api/v1/health` is forwarded to `http://backend:8000/api/v1/health`. Both services share Compose's private network. This same-origin browser request does not require permissive CORS configuration.

The Vite development server also proxies `/api` to `http://localhost:8000`; this is separate from the production Nginx proxy. `VITE_API_BASE_URL` (in `frontend/.env.example`) is an optional Vite build-time override for deployments that call a separately hosted API. Leave it blank when using the Nginx proxy. It must contain no secrets because Vite values are embedded in public browser assets. Direct cross-origin hosting may require an explicit, restricted backend CORS policy; none is enabled by default.

## Operations

```powershell
# Follow logs
docker compose logs -f

# Inspect service state and health
docker compose ps

# Stop and remove containers and the Compose network
docker compose down

# Rebuild images after changing source or configuration
docker compose up --build -d
```

The Compose file supports these optional host-port variables:

| Variable | Default | Purpose |
| --- | ---: | --- |
| `FRONTEND_PORT` | `8080` | Host port for the dashboard |
| `BACKEND_PORT` | `8000` | Host port for direct backend access |

Set them in the shell before `docker compose`, or in a local Compose `.env` file. Do not commit credentials there. The current backend does not require runtime configuration for Elexon access.

## Known limitations

- The dashboard still reports forecast accuracy as blocked. WINDFOR units and interval semantics and an approved comparison grain remain unverified; containerization does not change that.
- The applicable purchasing cutoff remains a caller-supplied business input.
- Elexon network access is required when an analysis is requested; containers do not cache historical responses.
- This Compose setup is intended for local evaluation and as a reproducible build. Production hosting still needs TLS termination, domain and operational configuration (including resource limits, monitoring and a deployment-specific secret/configuration review). No production deployment platform is configured here.
