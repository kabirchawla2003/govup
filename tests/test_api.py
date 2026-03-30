# Comprehensive test suite for GovUpdate API v8.0

import pytest
import sys
import os
from datetime import datetime, timezone

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from fastapi.testclient import TestClient

# Import with error handling
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("main", os.path.join(os.path.dirname(__file__), '..', 'src', 'main-v8-improved.py'))
    main_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main_module)
    app = main_module.app
    generate_api_key = main_module.generate_api_key
    hash_api_key = main_module.hash_api_key
    get_db_sync = main_module.get_db_sync
    SITES = main_module.SITES
except Exception as e:
    print(f"Error importing main module: {e}")
    raise

client = TestClient(app)


@pytest.fixture(scope="module")
def test_api_key():
    """Create a test API key"""
    with get_db_sync() as conn:
        test_key = generate_api_key()
        key_hash = hash_api_key(test_key)
        key_prefix = test_key[:15] + "..."

        conn.execute("""
            INSERT INTO api_keys
            (key_hash, key_prefix, name, description, rate_limit_per_minute, rate_limit_per_hour, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (key_hash, key_prefix, "test_key", "Test API key", 100, 5000, 1))
        conn.commit()

    yield test_key

    # Cleanup
    with get_db_sync() as conn:
        conn.execute("DELETE FROM api_keys WHERE name = 'test_key'")
        conn.commit()


class TestAuthentication:
    """Test API authentication and security"""

    def test_root_endpoint_no_auth(self):
        """Root endpoint should work without auth"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "GovUpdate API"
        assert data["version"] == "8.0 - Enhanced Edition"
        assert data["total_sites"] >= 55

    def test_updates_requires_api_key(self):
        """Updates endpoint should require API key"""
        response = client.get("/api/updates")
        assert response.status_code == 401
        assert "API key is required" in response.json()["detail"]

    def test_updates_with_invalid_key(self):
        """Invalid API key should be rejected"""
        response = client.get("/api/updates", headers={"X-API-Key": "invalid_key"})
        assert response.status_code == 403
        assert "Invalid API key" in response.json()["detail"]

    def test_updates_with_valid_key(self, test_api_key):
        """Valid API key should work"""
        response = client.get("/api/updates", headers={"X-API-Key": test_api_key})
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert data["success"] == True


class TestUpdatesEndpoint:
    """Test the /api/updates endpoint"""

    def test_get_updates_basic(self, test_api_key):
        """Test basic updates retrieval"""
        response = client.get("/api/updates", headers={"X-API-Key": test_api_key})
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "count" in data
        assert "total" in data
        assert isinstance(data["data"], list)

    def test_get_updates_with_limit(self, test_api_key):
        """Test pagination with limit"""
        response = client.get("/api/updates?limit=10", headers={"X-API-Key": test_api_key})
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 10
        assert len(data["data"]) <= 10

    def test_get_updates_with_offset(self, test_api_key):
        """Test pagination with offset"""
        response = client.get("/api/updates?limit=5&offset=5", headers={"X-API-Key": test_api_key})
        assert response.status_code == 200
        data = response.json()
        assert data["offset"] == 5

    def test_get_updates_filter_by_site(self, test_api_key):
        """Test filtering by site"""
        response = client.get("/api/updates?site=sebi", headers={"X-API-Key": test_api_key})
        assert response.status_code == 200
        data = response.json()
        for update in data["data"]:
            assert update["site"] == "sebi"

    def test_get_updates_filter_by_date(self, test_api_key):
        """Test filtering by date"""
        since_date = "2026-01-01"
        response = client.get(f"/api/updates?since={since_date}", headers={"X-API-Key": test_api_key})
        assert response.status_code == 200
        data = response.json()
        for update in data["data"]:
            assert update["date"] >= since_date

    def test_get_updates_search(self, test_api_key):
        """Test full-text search"""
        response = client.get("/api/updates?search=circular", headers={"X-API-Key": test_api_key})
        assert response.status_code == 200
        data = response.json()
        # Some results should contain 'circular' in title or summary
        if len(data["data"]) > 0:
            found = any("circular" in str(u.get("title", "")).lower() or
                       "circular" in str(u.get("summary", "")).lower()
                       for u in data["data"])
            assert found

    def test_get_updates_invalid_limit(self, test_api_key):
        """Test invalid limit values"""
        response = client.get("/api/updates?limit=1000", headers={"X-API-Key": test_api_key})
        assert response.status_code == 422  # Validation error


class TestSingleUpdate:
    """Test the /api/updates/{id} endpoint"""

    def test_get_nonexistent_update(self, test_api_key):
        """Test retrieving non-existent update"""
        response = client.get("/api/updates/nonexistent-id", headers={"X-API-Key": test_api_key})
        assert response.status_code == 404

    def test_get_update_by_id(self, test_api_key):
        """Test retrieving update by ID"""
        # First, get any update
        list_response = client.get("/api/updates?limit=1", headers={"X-API-Key": test_api_key})
        if list_response.json()["count"] > 0:
            update_id = list_response.json()["data"][0]["id"]

            # Get that specific update
            response = client.get(f"/api/updates/{update_id}", headers={"X-API-Key": test_api_key})
            assert response.status_code == 200
            data = response.json()
            assert data["success"] == True
            assert data["data"]["id"] == update_id
            assert "attachments" in data["data"]


class TestManualEntry:
    """Test manual update creation"""

    def test_manual_entry_valid(self, test_api_key):
        """Test creating valid manual update"""
        unique_url = f"https://example.com/test/{datetime.now(timezone.utc).timestamp()}"
        payload = {
            "site": "sebi",
            "title": "Test Manual Circular Entry",
            "url": unique_url,
            "type": "circular",
            "category": "testing",
            "date": "2026-03-05",
            "content": "This is a test manual entry",
            "priority": "normal"
        }

        response = client.post("/api/manual", json=payload, headers={"X-API-Key": test_api_key})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "id" in data["data"]

    def test_manual_entry_duplicate_url(self, test_api_key):
        """Test creating duplicate manual update"""
        unique_url = f"https://example.com/test-dup/{datetime.now(timezone.utc).timestamp()}"
        payload = {
            "site": "sebi",
            "title": "Duplicate Test",
            "url": unique_url,
            "type": "circular"
        }

        # First creation should succeed
        response1 = client.post("/api/manual", json=payload, headers={"X-API-Key": test_api_key})
        assert response1.status_code == 200

        # Second creation should fail
        response2 = client.post("/api/manual", json=payload, headers={"X-API-Key": test_api_key})
        assert response2.status_code == 409

    def test_manual_entry_invalid_site(self, test_api_key):
        """Test creating manual update with invalid site"""
        payload = {
            "site": "invalid_site",
            "title": "Test",
            "url": "https://example.com/test",
            "type": "circular"
        }

        response = client.post("/api/manual", json=payload, headers={"X-API-Key": test_api_key})
        assert response.status_code == 422  # Validation error

    def test_manual_entry_missing_required_fields(self, test_api_key):
        """Test creating manual update without required fields"""
        payload = {
            "site": "sebi"
            # Missing title and url
        }

        response = client.post("/api/manual", json=payload, headers={"X-API-Key": test_api_key})
        assert response.status_code == 422


class TestAPIKeyManagement:
    """Test API key creation and management"""

    def test_list_api_keys(self, test_api_key):
        """Test listing API keys"""
        response = client.get("/api/keys", headers={"X-API-Key": test_api_key})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_create_api_key(self, test_api_key):
        """Test creating new API key"""
        payload = {
            "name": "test_created_key",
            "description": "Key created during testing",
            "rate_limit_per_minute": 50,
            "rate_limit_per_hour": 1000
        }

        response = client.post("/api/keys", json=payload, headers={"X-API-Key": test_api_key})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "key" in data["data"]
        assert data["data"]["key"].startswith("govup_")

        # Cleanup
        with get_db_sync() as conn:
            conn.execute("DELETE FROM api_keys WHERE name = 'test_created_key'")
            conn.commit()


class TestWebhooks:
    """Test webhook management"""

    def test_list_webhooks(self, test_api_key):
        """Test listing webhooks"""
        response = client.get("/api/webhooks", headers={"X-API-Key": test_api_key})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "data" in data

    def test_create_webhook(self, test_api_key):
        """Test creating a webhook"""
        payload = {
            "url": "https://example.com/webhook",
            "name": "test_webhook",
            "site_filter": "sebi",
            "type_filter": "circular",
            "retry_count": 3
        }

        response = client.post("/api/webhooks", json=payload, headers={"X-API-Key": test_api_key})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True

        # Cleanup
        with get_db_sync() as conn:
            conn.execute("DELETE FROM webhooks WHERE name = 'test_webhook'")
            conn.commit()


class TestEmailSubscriptions:
    """Test email subscription management"""

    def test_list_email_subscriptions(self, test_api_key):
        """Test listing email subscriptions"""
        response = client.get("/api/email-subscriptions", headers={"X-API-Key": test_api_key})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "data" in data

    def test_create_email_subscription(self, test_api_key):
        """Test creating email subscription"""
        payload = {
            "email": "test@example.com",
            "name": "Test User",
            "frequency": "daily",
            "site_filter": "sebi"
        }

        response = client.post("/api/email-subscriptions", json=payload, headers={"X-API-Key": test_api_key})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True

        # Cleanup
        with get_db_sync() as conn:
            conn.execute("DELETE FROM email_subscriptions WHERE email = 'test@example.com'")
            conn.commit()


class TestScrapingLogs:
    """Test scraping logs endpoint"""

    def test_get_scraping_logs(self, test_api_key):
        """Test retrieving scraping logs"""
        response = client.get("/api/scraping-logs", headers={"X-API-Key": test_api_key})
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_get_scraping_logs_filter_by_site(self, test_api_key):
        """Test filtering scraping logs by site"""
        response = client.get("/api/scraping-logs?site=sebi", headers={"X-API-Key": test_api_key})
        assert response.status_code == 200
        data = response.json()
        for log in data["data"]:
            assert log["site"] == "sebi"

    def test_get_scraping_logs_filter_by_status(self, test_api_key):
        """Test filtering scraping logs by status"""
        response = client.get("/api/scraping-logs?status=success", headers={"X-API-Key": test_api_key})
        assert response.status_code == 200
        data = response.json()
        for log in data["data"]:
            assert log["status"] == "success"


class TestStatus:
    """Test status endpoint"""

    def test_get_status(self, test_api_key):
        """Test status endpoint"""
        response = client.get("/api/status", headers={"X-API-Key": test_api_key})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "database" in data
        assert "api_keys" in data
        assert "webhooks" in data
        assert "rate_limits" in data
        assert data["version"] == "8.0 - Enhanced"


class TestRateLimiting:
    """Test rate limiting functionality"""

    def test_rate_limit_headers(self, test_api_key):
        """Test that rate limit headers are present"""
        response = client.get("/api/updates", headers={"X-API-Key": test_api_key})
        assert "X-RateLimit-Request-Limit-Minute" in response.headers
        assert "X-RateLimit-Request-Limit-Hour" in response.headers


class TestDataSources:
    """Test that all data sources are configured"""

    def test_all_sites_configured(self):
        """Test that we have all expected sites"""
        assert len(SITES) >= 55, f"Expected at least 55 sites, got {len(SITES)}"

    def test_new_sources_added(self):
        """Test that new sources are marked"""
        new_sources = [key for key, site in SITES.items() if site.get("new_source")]
        assert len(new_sources) >= 20, f"Expected at least 20 new sources, got {len(new_sources)}"

    def test_critical_sites_present(self):
        """Test that critical sites are present"""
        critical_sites = ["sebi", "rbi", "nse", "bse", "amfi", "npci", "epfo", "icai"]
        for site in critical_sites:
            assert site in SITES, f"Critical site {site} is missing"

    def test_all_sites_have_required_fields(self):
        """Test that all sites have required configuration"""
        for key, site in SITES.items():
            assert "name" in site, f"Site {key} missing 'name'"
            assert "category" in site, f"Site {key} missing 'category'"
            assert "urls" in site, f"Site {key} missing 'urls'"
            assert isinstance(site["urls"], list), f"Site {key} urls should be a list"
            assert len(site["urls"]) > 0, f"Site {key} has no URLs"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
