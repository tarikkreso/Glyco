from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

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
            if key and key not in __import__("os").environ:
                __import__("os").environ[key] = value


_load_env_file()

Base.metadata.create_all(bind=engine)


def _ensure_lightweight_schema_updates() -> None:
    """Apply tiny SQLite-safe updates for local demo databases."""
    inspector = inspect(engine)
    if "health_logs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("health_logs")}
    if "is_fasting" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE health_logs ADD COLUMN is_fasting BOOLEAN DEFAULT 1"))


_ensure_lightweight_schema_updates()
seed_demo_data()

app = FastAPI(title="Glyco API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex="https?://.*",
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
