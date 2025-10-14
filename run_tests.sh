#!/bin/bash
# Test Suite Setup and Validation Script
# Run this to install dependencies and validate test suite

set -e  # Exit on error

echo "=========================================="
echo "QTC API Test Suite Setup"
echo "=========================================="
echo ""

# Check Python version
echo "Checking Python version..."
python3 --version
echo ""

# Install test dependencies
echo "Installing test dependencies..."
pip3 install pytest pytest-asyncio pytest-cov
echo ""

# Verify installations
echo "Verifying pytest installation..."
python3 -m pytest --version
echo ""

# Collect tests
echo "=========================================="
echo "Collecting test cases..."
echo "=========================================="
python3 -m pytest --collect-only
echo ""

# Run tests
echo "=========================================="
echo "Running test suite..."
echo "=========================================="
python3 -m pytest tests/ -v --tb=short
echo ""

# Generate coverage report
echo "=========================================="
echo "Generating coverage report..."
echo "=========================================="
python3 -m pytest tests/ --cov=app.api.middleware --cov=app.api.server --cov-report=term --cov-report=html
echo ""

echo "=========================================="
echo "Test suite validation complete!"
echo "=========================================="
echo ""
echo "Results:"
echo "  - HTML coverage report: htmlcov/index.html"
echo "  - Run specific tests: pytest tests/test_middleware.py"
echo "  - Run with verbose: pytest -v"
echo ""
echo "Next steps:"
echo "  1. Review coverage report"
echo "  2. Run integration tests"
echo "  3. Validate all tests pass"
echo "  4. Set up CI/CD pipeline"
echo ""
