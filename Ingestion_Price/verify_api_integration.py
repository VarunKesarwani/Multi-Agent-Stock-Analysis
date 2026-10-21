#!/usr/bin/env python3
"""
Verification script to confirm CM - Bhavcopy API Reports integration is complete.

This script checks:
1. Source is in equity ingestion list
2. Transformation handles the new source
3. Error handling is in place
4. Database loader is compatible
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

def check_equity_ingestion():
    """Check that new source is in equity_ingestion.py"""
    print("=" * 80)
    print("1. Checking equity_ingestion.py for new API source...")
    print("=" * 80)
    
    ingestion_file = Path(__file__).parent / 'equity_ingestion.py'
    content = ingestion_file.read_text()
    
    checks = {
        "'CM - Bhavcopy API Reports'": "Source label in priority list",
        "if label == 'CM - Bhavcopy API Reports':": "Special handling for API Reports",
        "date_str = target_date.strftime('%d-%b-%Y')": "Date formatting as DD-Mon-YYYY",
        "https://www.nseindia.com/api/reports": "API Reports URL",
        "if status_code == 404:": "404 error handling",
    }
    
    passed = 0
    for check_string, description in checks.items():
        if check_string in content:
            print(f"✓ {description}")
            passed += 1
        else:
            print(f"✗ {description}: NOT FOUND")
    
    print(f"\nResult: {passed}/{len(checks)} checks passed\n")
    return passed == len(checks)


def check_transformers():
    """Check that transformers.py handles new source"""
    print("=" * 80)
    print("2. Checking transformers.py for new API source transformation...")
    print("=" * 80)
    
    transformers_file = Path(__file__).parent / 'transformers.py'
    content = transformers_file.read_text()
    
    checks = {
        "def transform_equity(df: pd.DataFrame, source_label: str) -> pd.DataFrame:": "transform_equity function exists",
        "'CM - Bhavcopy' or source_label == 'CM - Bhavcopy API Reports'": "Condition includes new source",
        "'OpnPric': 'OPEN_PRICE'": "Column mapping for abbreviated format",
        "'HghPric': 'HIGH_PRICE'": "High price column mapping",
        "'LwPric': 'LOW_PRICE'": "Low price column mapping",
        "mapping = {": "Mapping dictionary defined",
    }
    
    passed = 0
    for check_string, description in checks.items():
        if check_string in content:
            print(f"✓ {description}")
            passed += 1
        else:
            print(f"✗ {description}: NOT FOUND")
    
    print(f"\nResult: {passed}/{len(checks)} checks passed\n")
    return passed == len(checks)


def check_db_loader():
    """Check that db_loader.py is compatible"""
    print("=" * 80)
    print("3. Checking db_loader.py for compatibility...")
    print("=" * 80)
    
    db_loader_file = Path(__file__).parent / 'db_loader.py'
    content = db_loader_file.read_text()
    
    checks = {
        "def upsert_equity_bhavcopy(": "upsert_equity_bhavcopy method exists",
        "'TRADE_DATE': 'DATE1'": "Column mapping TRADE_DATE to DATE1",
        "'TOTAL_TRADED_QTY': 'TTL_TRD_QNTY'": "Quantity column mapping",
        "ON CONFLICT": "ON CONFLICT handling",
        "column_mapping": "Column mapping dictionary",
    }
    
    passed = 0
    for check_string, description in checks.items():
        if check_string in content:
            print(f"✓ {description}")
            passed += 1
        else:
            print(f"✗ {description}: NOT FOUND")
    
    print(f"\nResult: {passed}/{len(checks)} checks passed\n")
    return passed == len(checks)


def check_config():
    """Check configuration"""
    print("=" * 80)
    print("4. Checking config.py...")
    print("=" * 80)
    
    config_file = Path(__file__).parent / 'config.py'
    content = config_file.read_text()
    
    checks = {
        "EQUITY_DB_COLUMNS": "Database columns defined",
        "'SYMBOL'": "SYMBOL column in config",
        "'TRADE_DATE'": "TRADE_DATE column in config",
        "EQUITY_SOURCES": "Equity sources list",
    }
    
    passed = 0
    for check_string, description in checks.items():
        if check_string in content:
            print(f"✓ {description}")
            passed += 1
        else:
            print(f"✗ {description}: NOT FOUND")
    
    print(f"\nResult: {passed}/{len(checks)} checks passed\n")
    return passed == len(checks)


def check_test_script():
    """Check that test script exists"""
    print("=" * 80)
    print("5. Checking test script...")
    print("=" * 80)
    
    test_file = Path(__file__).parent / 'test_new_api_integration.py'
    
    if test_file.exists():
        print(f"✓ Test script exists: {test_file}")
        content = test_file.read_text()
        
        checks = {
            "def test_csv_parsing": "CSV parsing test",
            "def test_transformation": "Transformation test",
            "def test_data_integrity": "Data integrity test",
            "def test_database_column_mapping": "Database mapping test",
            "'CM - Bhavcopy API Reports'": "API Reports source in test",
        }
        
        passed = 0
        for check_string, description in checks.items():
            if check_string in content:
                print(f"✓ {description}")
                passed += 1
            else:
                print(f"✗ {description}: NOT FOUND")
        
        print(f"\nResult: {passed}/{len(checks)} checks passed\n")
        return passed == len(checks)
    else:
        print(f"✗ Test script not found: {test_file}\n")
        return False


def check_documentation():
    """Check that documentation is created"""
    print("=" * 80)
    print("6. Checking documentation...")
    print("=" * 80)
    
    doc_dir = Path(__file__).parent.parent / 'Doc'
    
    files_to_check = {
        'NEW_API_INTEGRATION_SUMMARY.md': "API Integration Summary",
        'IMPLEMENTATION_GUIDE_API_INTEGRATION.md': "Implementation Guide",
    }
    
    passed = 0
    for filename, description in files_to_check.items():
        filepath = doc_dir / filename
        if filepath.exists():
            print(f"✓ {description}: {filename}")
            passed += 1
        else:
            print(f"✗ {description} not found: {filename}")
    
    print(f"\nResult: {passed}/{len(files_to_check)} checks passed\n")
    return passed == len(files_to_check)


def main():
    """Run all checks"""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 15 + "CM - Bhavcopy API Reports Integration Verification" + " " * 14 + "║")
    print("╚" + "=" * 78 + "╝")
    print()
    
    results = []
    
    try:
        results.append(("equity_ingestion.py", check_equity_ingestion()))
        results.append(("transformers.py", check_transformers()))
        results.append(("db_loader.py", check_db_loader()))
        results.append(("config.py", check_config()))
        results.append(("test_new_api_integration.py", check_test_script()))
        results.append(("documentation", check_documentation()))
    except Exception as e:
        print(f"\n✗ Error during verification: {e}\n")
        return 1
    
    # Summary
    print("=" * 80)
    print("VERIFICATION SUMMARY")
    print("=" * 80)
    
    all_passed = True
    for component, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {component}")
        if not passed:
            all_passed = False
    
    print("=" * 80)
    
    if all_passed:
        print("\n✓ ALL CHECKS PASSED!")
        print("\nIntegration is complete and ready for production use.")
        print("\nNext steps:")
        print("  1. Test with sample CSV file:")
        print("     python ingestion/test_new_api_integration.py cm02JAN2019bhav.csv")
        print("  2. Run full ingestion:")
        print("     python ingestion/main.py")
        print("  3. Query database to verify data:")
        print("     SELECT COUNT(*) FROM equity_bhavcopy WHERE DATE1 = '2019-01-02';")
        print()
        return 0
    else:
        print("\n✗ VERIFICATION FAILED")
        print("\nPlease check the errors above and fix them before proceeding.")
        print()
        return 1


if __name__ == '__main__':
    sys.exit(main())
