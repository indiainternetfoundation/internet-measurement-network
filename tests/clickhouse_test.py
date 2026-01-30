#!/usr/bin/env python3
"""
Test script to verify ClickHouse integration
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

def test_clickhouse_import():
    """Test that ClickHouse manager can be imported"""
    try:
        from server.olap.clickhouse_manager import ClickHouseManager
        print("✓ ClickHouseManager imported successfully")
        return True
    except ImportError as e:
        print(f"✗ Failed to import ClickHouseManager: {e}")
        return False

def test_clickhouse_connection():
    """Test ClickHouse connection"""
    try:
        from server.olap.clickhouse_manager import ClickHouseManager, CLICKHOUSE_AVAILABLE
        
        if not CLICKHOUSE_AVAILABLE:
            print("⚠ ClickHouse not available (clickhouse-connect not installed)")
            return True
            
        # Create manager with localhost settings
        manager = ClickHouseManager(
            host="localhost",
            port=8123,
            database="imn",
            username="admin",
            password=""
        )
        
        # Test connection
        if manager.connect():
            print("✓ ClickHouse connection successful")
            
            # Test table initialization
            if manager.initialize_tables():
                print("✓ ClickHouse tables initialized successfully")
            else:
                print("✗ Failed to initialize ClickHouse tables")
                
            manager.close()
            return True
        else:
            print("✗ Failed to connect to ClickHouse")
            return False
            
    except Exception as e:
        print(f"✗ Error testing ClickHouse connection: {e}")
        return False

if __name__ == "__main__":
    print("Testing ClickHouse integration...")
    
    success = True
    success &= test_clickhouse_import()
    success &= test_clickhouse_connection()
    
    if success:
        print("\n✓ All ClickHouse tests passed!")
        sys.exit(0)
    else:
        print("\n✗ Some ClickHouse tests failed!")
        sys.exit(1)