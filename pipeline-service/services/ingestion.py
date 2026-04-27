import logging
import time
import dlt
import requests
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation

logger = logging.getLogger("pipeline-service.ingestion")

FLASK_URL = os.getenv("FLASK_URL", "http://mock-server:5000")


def fetch_all_customers():
    all_records = []
    page = 1
    limit = 100
    logger.info("Fetching customers from Flask: %s", FLASK_URL)

    while True:
        try:
            response = requests.get(
                f"{FLASK_URL}/api/customers",
                params={"page": page, "limit": limit},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.ConnectionError:
            raise RuntimeError(f"Cannot connect to Flask service at {FLASK_URL}")
        except requests.exceptions.Timeout:
            raise RuntimeError(f"Flask service timed out on page {page}")
        except requests.exceptions.HTTPError as e:
            raise RuntimeError(f"Flask service returned error: {e}")
        except ValueError:
            raise RuntimeError("Flask service returned invalid JSON")

        records = data.get("data", [])
        if not records:
            break

        for record in records:
            try:
                if record.get("date_of_birth"):
                    record["date_of_birth"] = datetime.strptime(
                        record["date_of_birth"], "%Y-%m-%d"
                    ).date()
                if record.get("created_at"):
                    record["created_at"] = datetime.fromisoformat(record["created_at"])
                if record.get("account_balance") is not None:
                    record["account_balance"] = Decimal(str(record["account_balance"]))
            except (ValueError, InvalidOperation) as e:
                raise RuntimeError(f"Data conversion error for customer {record.get('customer_id')}: {e}")

        all_records.extend(records)
        logger.info("Fetched page %d — %d records so far.", page, len(all_records))

        total = data.get("total", 0)
        if len(all_records) >= total or len(records) < limit:
            break

        page += 1

    logger.info("Fetch complete: %d total records retrieved.", len(all_records))
    return all_records


@dlt.resource(name="customers", write_disposition="merge", primary_key="customer_id")
def customers_resource(records):
    yield from records


def run_ingestion_pipeline():
    start = time.time()
    records = fetch_all_customers()

    pipeline = dlt.pipeline(
        pipeline_name="customer_pipeline",
        destination="postgres",
        dataset_name="public"
    )

    try:
        pipeline.run(customers_resource(records))
    except Exception as e:
        raise RuntimeError(f"dlt pipeline failed: {e}")

    elapsed = round(time.time() - start, 2)
    logger.info("dlt pipeline finished: %d records upserted in %ss.", len(records), elapsed)
    return len(records)
