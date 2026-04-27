import logging
import math
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError
from database import engine, get_db, Base
from models.customer import Customer
from schemas import CustomerResponse, PaginatedCustomerResponse, IngestResponse, HealthResponse
from services.ingestion import run_ingestion_pipeline
import models.customer  # noqa: F401 — registers model with Base

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("pipeline-service")

app = FastAPI(
    title="Customer Data Pipeline API",
    description="Ingests customer data from Flask mock server into PostgreSQL and exposes query endpoints.",
    version="1.0.0",
)

Base.metadata.create_all(bind=engine)
logger.info("Database tables verified / created.")


@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
def health(db: Session = Depends(get_db)):
    db_status = "healthy"
    db_error = None
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as e:
        db_status = "unhealthy"
        db_error = str(e)
        logger.error("Database health check failed: %s", e)

    status = "healthy" if db_status == "healthy" else "degraded"
    response = HealthResponse(status=status, database=db_status, database_error=db_error)
    logger.info("Health check: status=%s database=%s", status, db_status)
    return response


@app.post("/api/ingest", response_model=IngestResponse, tags=["Ingestion"])
async def ingest():
    logger.info("Ingestion triggered.")
    try:
        records_processed = run_ingestion_pipeline()
        logger.info("Ingestion complete: %d records processed.", records_processed)
        return IngestResponse(status="success", records_processed=records_processed)
    except Exception as e:
        logger.error("Ingestion failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/customers", response_model=PaginatedCustomerResponse, tags=["Customers"])
def get_customers(page: int = 1, limit: int = 10, db: Session = Depends(get_db)):
    if page < 1 or limit < 1:
        raise HTTPException(status_code=400, detail="page and limit must be positive integers")
    try:
        offset = (page - 1) * limit
        total = db.query(func.count(Customer.customer_id)).scalar()
        customers = db.query(Customer).offset(offset).limit(limit).all()
    except SQLAlchemyError as e:
        logger.error("DB error on GET /api/customers: %s", e)
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    total_pages = math.ceil(total / limit) if limit else 1
    logger.info("GET /api/customers page=%d limit=%d total=%d", page, limit, total)
    return PaginatedCustomerResponse(
        data=[CustomerResponse.model_validate(c) for c in customers],
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
        has_next=page < total_pages,
    )


@app.get("/api/customers/{customer_id}", response_model=CustomerResponse, tags=["Customers"])
def get_customer(customer_id: str, db: Session = Depends(get_db)):
    try:
        customer = db.query(Customer).filter(Customer.customer_id == customer_id).first()
    except SQLAlchemyError as e:
        logger.error("DB error on GET /api/customers/%s: %s", customer_id, e)
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    if not customer:
        logger.warning("Customer not found: %s", customer_id)
        raise HTTPException(status_code=404, detail="Customer not found")

    logger.info("GET /api/customers/%s", customer_id)
    return CustomerResponse.model_validate(customer)
