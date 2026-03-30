#!/usr/bin/env python3
"""
Database migration script for GovUpdate API v7 to v8
Adds new tables, indexes, and migrates API keys to hashed format
"""

import sqlite3
import os
import sys
import hashlib
from datetime import datetime, timezone

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "govupdate.db")


def hash_api_key(key: str) -> str:
    """Hash API key using SHA256"""
    return hashlib.sha256(key.encode()).hexdigest()


def backup_database():
    """Create a backup of the database"""
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return False

    backup_path = DB_PATH + f".backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    try:
        import shutil
        shutil.copy2(DB_PATH, backup_path)
        print(f"[OK] Database backed up to: {backup_path}")
        return True
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        return False


def migrate_database():
    """Migrate database to v8 schema"""
    print("\n" + "=" * 60)
    print("GovUpdate API - Database Migration v7 → v8")
    print("=" * 60 + "\n")

    if not backup_database():
        print("\n❌ Migration aborted - backup failed")
        return False

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        print("📊 Current database status:")

        # Check existing tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"   Tables: {', '.join(tables)}")

        # Check if already migrated
        cursor.execute("PRAGMA table_info(api_keys)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'key_hash' in columns:
            print("\n⚠️  Database already migrated to v8 schema")
            print("   No migration needed.")
            conn.close()
            return True

        print("\n🔄 Starting migration...\n")

        # Step 1: Create new api_keys table with hash support
        print("1️⃣  Migrating API keys to hashed format...")

        # Get existing API keys
        cursor.execute("SELECT * FROM api_keys")
        old_keys = cursor.fetchall()

        print(f"   Found {len(old_keys)} existing API keys")

        # Rename old table
        cursor.execute("ALTER TABLE api_keys RENAME TO api_keys_old")

        # Create new table
        cursor.execute("""
            CREATE TABLE api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_hash TEXT NOT NULL UNIQUE,
                key_prefix TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                rate_limit_per_minute INTEGER DEFAULT 60,
                rate_limit_per_hour INTEGER DEFAULT 1000,
                requests_count INTEGER DEFAULT 0,
                last_used TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                expires_at TEXT
            )
        """)

        # Migrate data - WARNING: Can't recover unhashed keys!
        print("   ⚠️  WARNING: Old API keys cannot be recovered after migration")
        print("   A new admin key will be generated")

        # Only migrate metadata, generate new keys
        for old_key in old_keys:
            if old_key['name'] == 'admin':
                print(f"   Skipping admin key (will be regenerated)")
                continue

            # For non-admin keys, we can't migrate since we don't have the original key
            # We'll create a placeholder that needs to be regenerated
            key_hash = hash_api_key(f"MIGRATED_{old_key['id']}")  # Placeholder hash
            key_prefix = "govup_[REGENERATE]..."

            cursor.execute("""
                INSERT INTO api_keys
                (key_hash, key_prefix, name, description, rate_limit_per_minute,
                 rate_limit_per_hour, requests_count, last_used, created_at, is_active, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """, (
                key_hash,
                key_prefix,
                old_key['name'] + "_NEEDS_REGENERATION",
                (old_key['description'] or '') + " [MIGRATED - REGENERATE KEY]",
                old_key['rate_limit_per_minute'],
                old_key['rate_limit_per_hour'],
                old_key['requests_count'],
                old_key['last_used'],
                old_key['created_at'],
                old_key['expires_at']
            ))

        print(f"   ✅ API keys migrated (old keys deactivated, need regeneration)")

        # Step 2: Create attachments table
        print("\n2️⃣  Creating attachments table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                update_id TEXT NOT NULL,
                url TEXT NOT NULL,
                filename TEXT,
                file_type TEXT,
                size_bytes INTEGER,
                fetched INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (update_id) REFERENCES updates(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_attachments_update_id ON attachments(update_id)")
        print("   ✅ Attachments table created")

        # Step 3: Update webhooks table with foreign key
        print("\n3️⃣  Updating webhooks table...")

        # Check if webhooks table exists
        if 'webhooks' in tables:
            cursor.execute("SELECT * FROM webhooks")
            old_webhooks = cursor.fetchall()

            cursor.execute("DROP TABLE IF EXISTS webhooks")

            cursor.execute("""
                CREATE TABLE webhooks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    name TEXT NOT NULL,
                    site_filter TEXT,
                    type_filter TEXT,
                    category_filter TEXT,
                    api_key_id INTEGER NOT NULL,
                    events TEXT DEFAULT 'new',
                    retry_count INTEGER DEFAULT 3,
                    is_active INTEGER DEFAULT 1,
                    last_triggered TEXT,
                    last_success TEXT,
                    last_failure TEXT,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (api_key_id) REFERENCES api_keys(id) ON DELETE CASCADE
                )
            """)

            # Migrate webhooks - link to first active api_key
            cursor.execute("SELECT id FROM api_keys WHERE is_active = 1 LIMIT 1")
            first_key = cursor.fetchone()

            if first_key and old_webhooks:
                for wh in old_webhooks:
                    cursor.execute("""
                        INSERT INTO webhooks
                        (url, name, site_filter, type_filter, category_filter, api_key_id,
                         events, retry_count, is_active, last_triggered, last_success,
                         last_failure, success_count, failure_count, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        wh['url'], wh['name'], wh.get('site_filter'), wh.get('type_filter'),
                        wh.get('category_filter'), first_key[0], wh.get('events', 'new'),
                        wh.get('retry_count', 3), wh.get('is_active', 1),
                        wh.get('last_triggered'), wh.get('last_success'), wh.get('last_failure'),
                        wh.get('success_count', 0), wh.get('failure_count', 0), wh.get('created_at')
                    ))

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_webhooks_active ON webhooks(is_active)")
            print(f"   ✅ Webhooks table updated ({len(old_webhooks)} webhooks migrated)")
        else:
            cursor.execute("""
                CREATE TABLE webhooks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    name TEXT NOT NULL,
                    site_filter TEXT,
                    type_filter TEXT,
                    category_filter TEXT,
                    api_key_id INTEGER NOT NULL,
                    events TEXT DEFAULT 'new',
                    retry_count INTEGER DEFAULT 3,
                    is_active INTEGER DEFAULT 1,
                    last_triggered TEXT,
                    last_success TEXT,
                    last_failure TEXT,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (api_key_id) REFERENCES api_keys(id) ON DELETE CASCADE
                )
            """)
            print("   ✅ Webhooks table created")

        # Step 4: Update email_subscriptions table
        print("\n4️⃣  Updating email subscriptions table...")

        if 'email_subscriptions' in tables:
            cursor.execute("SELECT * FROM email_subscriptions")
            old_subs = cursor.fetchall()

            cursor.execute("DROP TABLE IF EXISTS email_subscriptions")

            cursor.execute("""
                CREATE TABLE email_subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    name TEXT,
                    site_filter TEXT,
                    type_filter TEXT,
                    category_filter TEXT,
                    api_key_id INTEGER NOT NULL,
                    frequency TEXT DEFAULT 'daily',
                    is_active INTEGER DEFAULT 1,
                    last_sent TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (api_key_id) REFERENCES api_keys(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("SELECT id FROM api_keys WHERE is_active = 1 LIMIT 1")
            first_key = cursor.fetchone()

            if first_key and old_subs:
                for sub in old_subs:
                    cursor.execute("""
                        INSERT INTO email_subscriptions
                        (email, name, site_filter, type_filter, category_filter, api_key_id,
                         frequency, is_active, last_sent, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        sub['email'], sub.get('name'), sub.get('site_filter'),
                        sub.get('type_filter'), sub.get('category_filter'), first_key[0],
                        sub.get('frequency', 'daily'), sub.get('is_active', 1),
                        sub.get('last_sent'), sub.get('created_at')
                    ))

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_email_subs_active ON email_subscriptions(is_active)")
            print(f"   ✅ Email subscriptions updated ({len(old_subs)} subscriptions migrated)")
        else:
            cursor.execute("""
                CREATE TABLE email_subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    name TEXT,
                    site_filter TEXT,
                    type_filter TEXT,
                    category_filter TEXT,
                    api_key_id INTEGER NOT NULL,
                    frequency TEXT DEFAULT 'daily',
                    is_active INTEGER DEFAULT 1,
                    last_sent TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (api_key_id) REFERENCES api_keys(id) ON DELETE CASCADE
                )
            """)
            print("   ✅ Email subscriptions table created")

        # Step 5: Add new indexes
        print("\n5️⃣  Adding new indexes...")
        new_indexes = [
            "CREATE INDEX IF NOT EXISTS idx_updates_created_at ON updates(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_updates_site_date ON updates(site, date)"
        ]

        for idx in new_indexes:
            cursor.execute(idx)

        print("   ✅ New indexes created")

        # Step 6: Drop old api_keys table
        print("\n6️⃣  Cleaning up...")
        cursor.execute("DROP TABLE IF EXISTS api_keys_old")
        print("   ✅ Old tables removed")

        # Commit all changes
        conn.commit()

        print("\n" + "=" * 60)
        print("✅ Migration completed successfully!")
        print("=" * 60)

        print("\n📋 Post-migration tasks:")
        print("   1. Run the v8 API - it will create a new admin key")
        print("   2. Regenerate any other API keys that were migrated")
        print("   3. Update webhook and email subscription configurations if needed")
        print("   4. Test all endpoints with new API keys")

        conn.close()
        return True

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()

        if conn:
            conn.rollback()
            conn.close()

        return False


if __name__ == "__main__":
    print("\nWARNING: This will modify your database. A backup will be created automatically.")
    response = input("Continue? (yes/no): ")

    if response.lower() in ['yes', 'y']:
        success = migrate_database()
        sys.exit(0 if success else 1)
    else:
        print("Migration cancelled.")
        sys.exit(0)
