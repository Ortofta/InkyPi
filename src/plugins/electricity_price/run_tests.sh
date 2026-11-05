#!/bin/bash

# Test runner script for Electricity Price plugin
# Run this from the project root directory

echo "Running Electricity Price plugin tests..."
echo "=========================================="

# Activate virtual environment and run tests
source venv/bin/activate

# Run the comprehensive test suite
python -m pytest src/plugins/electricity_price/test_electricity_price_comprehensive.py -v

echo ""
echo "Test run completed!"
echo ""
echo "To run specific tests:"
echo "  python -m pytest src/plugins/electricity_price/test_electricity_price_comprehensive.py::TestElectricityPrice::test_method_name -v"
echo ""
echo "To run with coverage:"
echo "  python -m pytest --cov=src/plugins/electricity_price --cov-report=term-missing src/plugins/electricity_price/test_electricity_price_comprehensive.py"
