#!/usr/bin/env python3
"""Get precosbot logs from database and system logs."""
import sqlite3
import subprocess
import os

DB_PATH = r'E:\Code\Scripts\precosbot\precobot.db'

def get_database_logs():
    """Get logs from precobot database."""
    print("=" * 60)
    print("=== PRECOBOT DATABASE LOGS ===")
    print("=" * 60)
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(f"\nTables found: {[t[0] for t in tables]}")
        
        # Get schema for each table
        for table in tables:
            table_name = table[0]
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            print(f"\n--- {table_name} Schema ---")
            for col in columns:
                print(f"  {col[1]} ({col[2]})")
        
        # Get recent price history
        cursor.execute("SELECT * FROM price_history ORDER BY id DESC LIMIT 20")
        rows = cursor.fetchall()
        
        if rows:
            print(f"\n--- Last 20 Price History Records ({len(rows)} total) ---")
            # Get column names
            column_names = [desc[0] for desc in cursor.description]
            print(f"{'<' .join(column_names):<120}")
            for row in rows:
                print(f"{'<' .join(str(v) for v in row):<120}")
        
        # Get tracked products
        cursor.execute("SELECT * FROM tracked_products ORDER BY id DESC LIMIT 10")
        rows = cursor.fetchall()
        if rows:
            print(f"\n--- Tracked Products ({len(rows)} total) ---")
            column_names = [desc[0] for desc in cursor.description]
            print(f"{'<' .join(column_names):<80}")
            for row in rows:
                print(f"{'<' .join(str(v) for v in row):<80}")
        
        # Get user alerts
        cursor.execute("SELECT * FROM user_alerts ORDER BY id DESC LIMIT 10")
        rows = cursor.fetchall()
        if rows:
            print(f"\n--- User Alerts ({len(rows)} total) ---")
            column_names = [desc[0] for desc in cursor.description]
            print(f"{'<' .join(column_names):<80}")
            for row in rows:
                print(f"{'<' .join(str(v) for v in row):<80}")
        
        conn.close()
    except Exception as e:
        print(f"Database error: {e}")

def get_system_logs():
    """Get system logs from journalctl."""
    print("\n" + "=" * 60)
    print("=== PRECOBOT SYSTEM LOGS (journalctl) ===")
    print("=" * 60)
    
    try:
        # Try to get logs from the server
        result = subprocess.run(
            ['ssh', '-i', r'E:\Code\.ssh\oci_yvy', '-o', 'StrictHostKeyChecking=no',
             'ubuntu@137.131.159.91', 'sudo', 'journalctl', '-u', 'precosbot', '-n', '100', '--no-pager'],
            capture_output=True, text=True, timeout=30
        )
        
        if result.returncode == 0:
            print(result.stdout)
        else:
            print(f"SSH failed: {result.stderr}")
            print("Trying alternative method...")
            
            # Try to get logs via yvy jump host
            result = subprocess.run(
                ['ssh', 'yvy', 'sudo', 'journalctl', '-u', 'precosbot', '-n', '100', '--no-pager'],
                capture_output=True, text=True, timeout=30
            )
            
            if result.returncode == 0:
                print(result.stdout)
            else:
                print(f"SSH via yvy failed: {result.stderr}")
                
    except subprocess.TimeoutExpired:
        print("SSH command timed out")
    except Exception as e:
        print(f"Error getting system logs: {e}")

def get_service_status():
    """Get precosbot service status."""
    print("\n" + "=" * 60)
    print("=== PRECOBOT SERVICE STATUS ===")
    print("=" * 60)
    
    try:
        result = subprocess.run(
            ['ssh', 'yvy', 'sudo', 'systemctl', 'is-active', 'precosbot'],
            capture_output=True, text=True, timeout=10
        )
        print(f"Service status: {result.stdout.strip()}")
        
        # Get recent journalctl entries
        result = subprocess.run(
            ['ssh', 'yvy', 'sudo', 'journalctl', '-u', 'precosbot', '-n', '50', '--no-pager'],
            capture_output=True, text=True, timeout=30
        )
        
        if result.returncode == 0:
            print(result.stdout)
        else:
            print(f"journalctl failed: {result.stderr}")
            
    except subprocess.TimeoutExpired:
        print("SSH command timed out")
    except Exception as e:
        print(f"Error getting service status: {e}")

if __name__ == "__main__":
    get_database_logs()
    get_service_status()
    get_system_logs()
    print("\n" + "=" * 60)
    print("=== END OF PRECOBOT LOGS ===")
    print("=" * 60)
