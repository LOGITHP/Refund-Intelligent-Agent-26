import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.minio_client import minio_storage
from app.db.database import Base, engine, ensure_schema_columns
from app.db.seed import seed_initial_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ecommerce_platform")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database schema...")
    Base.metadata.create_all(bind=engine)
    ensure_schema_columns(engine)
    logger.info("Ensuring MinIO buckets...")
    minio_storage.init_buckets()
    logger.info("Seeding initial catalog and test users...")
    seed_initial_data()
    yield
    logger.info("Shutting down e-commerce platform...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "storage_connected": minio_storage.available,
    }
