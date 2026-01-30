"""
ClickHouse manager for handling connections and data operations
Enhanced with debugging statements and reconnection logic
FIXED: Removed column_names parameter from insert() calls
"""
import json
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

# Try to import clickhouse-connect, but handle if not available
try:
    from clickhouse_connect import get_client
    from clickhouse_connect.driver.client import Client
    CLICKHOUSE_AVAILABLE = True
except ImportError:
    # Create mock classes for type hints when clickhouse-connect is not available
    class Client:
        def command(self, sql):
            pass
        def insert(self, table, data):
            pass
        def close(self):
            pass
    def get_client(*args, **kwargs):
        return Client()
    CLICKHOUSE_AVAILABLE = False

class ClickHouseManager:
    """Manages ClickHouse connections and data operations for IMN"""
    
    def __init__(self, host: str = None, port: Optional[int] = None, database: str = None, 
                 username: str = None, password: str = None):
        """
        Initialize ClickHouse manager with connection parameters
        
        Args:
            host: ClickHouse server host
            port: ClickHouse server port
            database: Database name
            username: Username for authentication
            password: Password for authentication
        """
        self.host = host or os.environ.get('CLICKHOUSE_HOST', 'localhost')
        self.port = port or int(os.environ.get('CLICKHOUSE_PORT', 8123))
        self.database = database or os.environ.get('CLICKHOUSE_DATABASE', 'imn')
        self.username = username or os.environ.get('CLICKHOUSE_USERNAME', 'admin')
        self.password = password or os.environ.get('CLICKHOUSE_PASSWORD', '')
        
        self.client: Optional[Client] = None
        self.connected = False
        self._connection_attempts = 0
        self._last_error = None
        
        print(f"[ClickHouse] Initialized with config:")
        print(f"[ClickHouse]   Host: {self.host}")
        print(f"[ClickHouse]   Port: {self.port}")
        print(f"[ClickHouse]   Database: {self.database}")
        print(f"[ClickHouse]   Username: {self.username}")
        print(f"[ClickHouse]   Password: {'***' if self.password else '(empty)'}")
    
    def _safe_json_encode(self, value, default=None):
        """Safely encode value to JSON string"""
        if default is None:
            default = {}
        if isinstance(value, str):
            return value
        return json.dumps(value if value is not None else default)
    
    def ensure_connected(self) -> bool:
        """
        Ensure we're connected to ClickHouse, reconnect if necessary
        
        Returns:
            bool: True if connected, False otherwise
        """
        # If we think we're connected, test the connection
        if self.connected and self.client:
            try:
                # Simple ping query
                self.client.command("SELECT 1")
                return True
            except Exception as e:
                print(f"[ClickHouse] Connection test failed: {type(e).__name__}: {e}")
                print(f"[ClickHouse] Attempting to reconnect...")
                self.connected = False
        
        # If not connected, try to connect
        if not self.connected:
            success = self.connect()
            if not success:
                print(f"[ClickHouse] Reconnection failed after connection test failure")
            return success
        
        return False
        
    def connect(self) -> bool:
        """
        Establish connection to ClickHouse server
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        if not CLICKHOUSE_AVAILABLE:
            self._last_error = "clickhouse-connect library not available"
            print("[ClickHouse] ERROR: clickhouse-connect library not available")
            print("[ClickHouse] Install with: pip install clickhouse-connect")
            return False
        
        self._connection_attempts += 1
        print(f"[ClickHouse] Connection attempt #{self._connection_attempts}")
        print(f"[ClickHouse] Connecting to {self.host}:{self.port}/{self.database}...")
        
        try:
            # Create new client
            self.client = get_client(
                host=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                database=self.database
            )
            
            # Test the connection
            result = self.client.command("SELECT 1")
            print(f"[ClickHouse] Connection test query result: {result}")
            
            # Test database access
            version = self.client.command("SELECT version()")
            print(f"[ClickHouse] ClickHouse version: {version}")
            
            self.connected = True
            self._last_error = None
            print(f"[ClickHouse] ✓ Successfully connected to {self.host}:{self.port}/{self.database}")
            return True
            
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            self._last_error = error_msg
            print(f"[ClickHouse] ✗ Connection failed: {error_msg}")
            self.connected = False
            return False
    
    def initialize_tables(self) -> bool:
        """
        Initialize all required tables in ClickHouse
        
        Returns:
            bool: True if initialization successful, False otherwise
        """
        if not self.ensure_connected():
            print("[ClickHouse] Cannot initialize tables: Failed to connect")
            return False
        
        print("[ClickHouse] Starting table initialization...")
        
        try:
            # Import schema definitions
            from .clickhouse_schema import CREATE_TABLE_STATEMENTS
            
            print(f"[ClickHouse] Found {len(CREATE_TABLE_STATEMENTS)} table definitions")
            
            success_count = 0
            # Execute each table creation statement separately
            for i, statement in enumerate(CREATE_TABLE_STATEMENTS):
                try:
                    clean_statement = statement.strip()
                    if clean_statement:
                        # Extract table name for better logging
                        table_name = "unknown"
                        if "CREATE TABLE" in clean_statement or "CREATE MATERIALIZED VIEW" in clean_statement:
                            parts = clean_statement.split()
                            for j, part in enumerate(parts):
                                if part.upper() in ["TABLE", "VIEW"] and j + 2 < len(parts):
                                    # Skip "IF" "NOT" "EXISTS" keywords if present
                                    offset = 0
                                    while j + 2 + offset < len(parts) and parts[j + 2 + offset].upper() in ["IF", "NOT", "EXISTS"]:
                                        offset += 1
                                    if j + 2 + offset < len(parts):
                                        table_name = parts[j + 2 + offset]
                                    break
                        
                        print(f"[ClickHouse] [{i+1}/{len(CREATE_TABLE_STATEMENTS)}] Creating {table_name}...")
                        self.client.command(clean_statement)
                        success_count += 1
                        print(f"[ClickHouse] [{i+1}/{len(CREATE_TABLE_STATEMENTS)}] ✓ {table_name} created")
                except Exception as e:
                    print(f"[ClickHouse] [{i+1}/{len(CREATE_TABLE_STATEMENTS)}] ✗ Failed: {type(e).__name__}: {e}")
                    continue
            
            print(f"[ClickHouse] ✓ Table initialization completed ({success_count}/{len(CREATE_TABLE_STATEMENTS)} successful)")
            
            if self.ensure_connected():
                print("[ClickHouse] Connection still alive after table initialization")
            else:
                print("[ClickHouse] WARNING: Connection lost after table initialization!")
                
            return success_count > 0
            
        except Exception as e:
            print(f"[ClickHouse] ✗ Table initialization failed: {type(e).__name__}: {e}")
            return False
    
    def insert_measurement(self, data: Dict[str, Any]) -> bool:
        """
        Insert measurement result into ClickHouse
        
        Args:
            data: Dictionary containing measurement data
            
        Returns:
            bool: True if insertion successful, False otherwise
        """
        if not self.ensure_connected():
            print(f"[ClickHouse] Cannot insert measurement: Not connected")
            return False
        
        workflow_id = data.get('workflow_id', 'unknown')
        
        try:
            # Prepare data for insertion as a list of values in the correct order
            # This matches the table schema order
            insert_data = [(
                data.get('workflow_id', ''),
                data.get('agent_id', ''),
                data.get('module_name', ''),
                data.get('created_at', datetime.now(timezone.utc)),
                data.get('completed_at', datetime.now(timezone.utc)),
                self._safe_json_encode(data.get('measurement_data')),
                data.get('agent_hostname', ''),
                data.get('agent_name', ''),
                data.get('agent_pid', 0),
                data.get('system_machine', ''),
                data.get('system_node_name', ''),
                data.get('system_platform', ''),
                data.get('system_processor', ''),
                data.get('system_release', ''),
                data.get('system_version', ''),
                self._safe_json_encode(data.get('network_interfaces')),
                data.get('user_name', ''),
                data.get('user_uid', 0),
                data.get('user_gid', 0),
                data.get('user_home_dir', ''),
                data.get('user_shell', ''),
                self._safe_json_encode(data.get('request_data')),
                data.get('success', True)
            )]
            
            # Column names in the correct order
            column_names = [
                'workflow_id', 'agent_id', 'module_name', 'created_at', 'completed_at',
                'measurement_data', 'agent_hostname', 'agent_name', 'agent_pid',
                'system_machine', 'system_node_name', 'system_platform', 'system_processor',
                'system_release', 'system_version', 'network_interfaces', 'user_name',
                'user_uid', 'user_gid', 'user_home_dir', 'user_shell', 'request_data', 'success'
            ]
            
            # Insert with explicit column names and data as list of tuples
            self.client.insert('measurements', insert_data, column_names=column_names)
            print(f"[ClickHouse] ✓ Measurement inserted for workflow {workflow_id}")
            return True
            
        except Exception as e:
            print(f"[ClickHouse] ✗ Measurement insertion failed: {type(e).__name__}: {e}")
            print(f"[ClickHouse]   Workflow ID: {workflow_id}")
            self.connected = False
            self._last_error = str(e)
            return False
    
    def insert_heartbeat(self, data: Dict[str, Any]) -> bool:
        """
        Insert agent heartbeat into ClickHouse
        
        Args:
            data: Dictionary containing heartbeat data
            
        Returns:
            bool: True if insertion successful, False otherwise
        """
        if not self.ensure_connected():
            print(f"[ClickHouse] Cannot insert heartbeat: Not connected")
            return False
        
        agent_id = data.get('agent_id', 'unknown')
        
        try:
            # Prepare data for insertion as a list of values in the correct order
            # This matches the table schema order
            insert_data = [(
                data.get('agent_id', ''),
                data.get('agent_name', ''),
                data.get('hostname', ''),
                data.get('timestamp', datetime.now(timezone.utc)),
                data.get('alive', True),
                data.get('total_heartbeats', 0),
                data.get('load_avg_1m', 0.0),
                data.get('load_avg_5m', 0.0),
                data.get('load_avg_15m', 0.0),
                self._safe_json_encode(data.get('config'))
            )]
            
            # Column names in the correct order
            column_names = [
                'agent_id', 'agent_name', 'hostname', 'timestamp', 
                'alive', 'total_heartbeats', 'load_avg_1m', 'load_avg_5m', 
                'load_avg_15m', 'config'
            ]
            
            # Debug: Print the data we're trying to insert
            print(f"[ClickHouse] Preparing to insert heartbeat for agent {agent_id}")
            for i, (col_name, value) in enumerate(zip(column_names, insert_data[0])):
                print(f"[ClickHouse]   {col_name}: {type(value)} = {value}")
            
            # Insert with explicit column names and data as list of tuples
            self.client.insert('agent_heartbeats', insert_data, column_names=column_names)
            print(f"[ClickHouse] ✓ Heartbeat inserted for agent {agent_id}")
            return True
            
        except Exception as e:
            print(f"[ClickHouse] ✗ Heartbeat insertion failed: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            print(f"[ClickHouse]   Agent ID: {agent_id}")
            # Print the data that caused the error
            print(f"[ClickHouse]   Data that caused error: {data}")
            self.connected = False
            self._last_error = str(e)
            return False
    
    def insert_module_state(self, data: Dict[str, Any]) -> bool:
        """
        Insert module state transition into ClickHouse
        
        Args:
            data: Dictionary containing state transition data
            
        Returns:
            bool: True if insertion successful, False otherwise
        """
        if not self.ensure_connected():
            print(f"[ClickHouse] Cannot insert module state: Not connected")
            return False
        
        workflow_id = data.get('workflow_id', 'unknown')
        
        try:
            # Prepare data for insertion as a list of values in the correct order
            # This matches the table schema order
            insert_data = [(
                data.get('workflow_id', ''),
                data.get('agent_id', ''),
                data.get('module_name', ''),
                data.get('state', ''),
                data.get('timestamp', datetime.now(timezone.utc)),
                data.get('error_message', None),
                self._safe_json_encode(data.get('details'))
            )]
            
            # Column names in the correct order
            column_names = [
                'workflow_id', 'agent_id', 'module_name', 'state', 'timestamp',
                'error_message', 'details'
            ]
            
            # Insert with explicit column names and data as list of tuples
            self.client.insert('module_states', insert_data, column_names=column_names)
            print(f"[ClickHouse] ✓ Module state inserted for workflow {workflow_id}")
            return True
            
        except Exception as e:
            print(f"[ClickHouse] ✗ Module state insertion failed: {type(e).__name__}: {e}")
            print(f"[ClickHouse]   Workflow ID: {workflow_id}")
            self.connected = False
            self._last_error = str(e)
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current connection status and statistics
        
        Returns:
            Dictionary with connection status and info
        """
        status = {
            "available": CLICKHOUSE_AVAILABLE,
            "connected": self.connected,
            "client_exists": self.client is not None,
            "connection_attempts": self._connection_attempts,
            "last_error": self._last_error,
            "config": {
                "host": self.host,
                "port": self.port,
                "database": self.database,
                "username": self.username,
            }
        }
        
        # Test connection if we think we're connected
        if self.connected and self.client:
            try:
                result = self.client.command("SELECT version()")
                status["version"] = result
                status["connection_test"] = "passed"
            except Exception as e:
                status["connection_test"] = f"failed: {e}"
                status["connection_test_error"] = str(e)
        else:
            status["connection_test"] = "not_connected"
        
        return status
    
    def close(self):
        """Close ClickHouse connection"""
        if self.client:
            try:
                self.client.close()
                self.connected = False
                print("[ClickHouse] ✓ Connection closed")
            except Exception as e:
                print(f"[ClickHouse] ✗ Error closing connection: {type(e).__name__}: {e}")