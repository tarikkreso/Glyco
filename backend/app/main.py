from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.db.database import Base, engine
from app.services.seed import seed_demo_data


def _load_env_file() -> None:
    """Load simple .env files before settings-dependent modules are used."""
    backend_dir = Path(__file__).resolve().parents[1]
    project_dir = backend_dir.parent
    for env_path in (project_dir / ".env", backend_dir / ".env"):
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                __import__("os").environ[key] = value


_load_env_file()

Base.metadata.create_all(bind=engine)
seed_demo_data()

app = FastAPI(title="Glyco API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(router, prefix="/v1")


@app.get("/")
def root() -> dict[str, str]:
    """Return a small API root health payload."""
    return {"status": "ok", "product": "Glyco API", "docs": "/docs"}


@app.get("/health")
def health() -> dict[str, str]:
    """Return application health for tests and local checks."""
    return {"status": "ok", "product": "Glyco"}
