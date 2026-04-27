from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime


class CustomerResponse(BaseModel):
    customer_id: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    address: Optional[str] = None
    date_of_birth: Optional[date] = None
    account_balance: Optional[float] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PaginatedCustomerResponse(BaseModel):
    data: List[CustomerResponse]
    total: int
    page: int
    limit: int
    total_pages: int
    has_next: bool


class IngestResponse(BaseModel):
    status: str
    records_processed: int


class HealthResponse(BaseModel):
    status: str
    database: str
    database_error: Optional[str] = None
