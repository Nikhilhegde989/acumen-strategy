import logging
import math
import sys
import json
from flask import Flask, jsonify, request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("mock-server")

app = Flask(__name__)

try:
    with open('data/customers.json', 'r') as f:
        customers = json.load(f)
    logger.info("Loaded %d customers from customers.json.", len(customers))
except (FileNotFoundError, json.JSONDecodeError) as e:
    logger.error("Failed to load customers.json: %s", e)
    sys.exit(1)


@app.route('/api/health', methods=['GET'])
def health():
    logger.info("Health check requested.")
    return jsonify({"status": "healthy", "total_customers": len(customers)})


@app.route('/api/customers', methods=['GET'])
def get_customers():
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
    except ValueError:
        return jsonify({"error": "page and limit must be integers"}), 400

    if page < 1 or limit < 1:
        return jsonify({"error": "page and limit must be positive integers"}), 400

    start = (page - 1) * limit
    end = start + limit
    total = len(customers)
    total_pages = math.ceil(total / limit)

    logger.info("GET /api/customers page=%d limit=%d", page, limit)
    return jsonify({
        "data": customers[start:end],
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "has_next": page < total_pages,
    })


@app.route('/api/customers/<customer_id>', methods=['GET'])
def get_customer(customer_id):
    customer = next((c for c in customers if c['customer_id'] == customer_id), None)
    if not customer:
        logger.warning("Customer not found: %s", customer_id)
        return jsonify({"error": "Customer not found"}), 404
    logger.info("GET /api/customers/%s", customer_id)
    return jsonify(customer)


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found"}), 404


@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "Method not allowed"}), 405


@app.errorhandler(500)
def internal_error(e):
    logger.error("Internal server error: %s", e)
    return jsonify({"error": "Internal server error"}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
