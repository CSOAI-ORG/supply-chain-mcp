import os
import sys
import unittest

# Ensure shared auth middleware is available
sys.path.insert(0, os.path.expanduser("~/clawd/meok-labs-engine/shared"))
os.chdir(os.path.dirname(os.path.abspath(__file__)) + "/..")


class TestMCPImport(unittest.TestCase):
    def test_import_server(self):
        """Server module must import without errors."""
        import server  # noqa: F401

    def test_mcp_or_server_object_exists(self):
        """FastMCP servers export 'mcp'; low-level servers export 'server'."""
        import server as srv
        self.assertTrue(
            hasattr(srv, "mcp") or hasattr(srv, "server"),
            "Expected 'mcp' or 'server' object in server.py",
        )


class TestAuthMiddleware(unittest.TestCase):
    def test_check_access_allows_empty_key_as_free_tier(self):
        """Empty API key maps to FREE tier and is allowed."""
        from auth_middleware import check_access, Tier
        allowed, msg, tier = check_access("")
        self.assertTrue(allowed)
        self.assertEqual(tier, Tier.FREE)
        self.assertIsInstance(msg, str)

    def test_check_access_returns_tuple(self):
        """check_access must return a 3-tuple."""
        from auth_middleware import check_access
        result = check_access("")
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)


if __name__ == "__main__":
    unittest.main()
