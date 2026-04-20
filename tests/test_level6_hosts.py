import unittest
from unittest import mock

from validation.orchestration import hosts


class Level6HostsTests(unittest.TestCase):
    def test_connector_hosts_resolve_returns_unresolved_hosts(self):
        unresolved = hosts.connector_hosts_resolve(
            ["conn-a", "conn-b"],
            domain="example.local",
            resolver=mock.Mock(side_effect=[OSError("missing"), "127.0.0.1"]),
        )

        self.assertEqual(unresolved, ["conn-a.example.local"])

    def test_connector_hosts_resolve_skips_when_domain_is_missing(self):
        resolver = mock.Mock()

        unresolved = hosts.connector_hosts_resolve(
            ["conn-a"],
            domain="",
            resolver=resolver,
        )

        self.assertEqual(unresolved, [])
        resolver.assert_not_called()

    def test_ensure_connector_hosts_updates_hosts_before_resolution_failure(self):
        config_adapter = mock.Mock()
        config_adapter.generate_connector_hosts.return_value = [
            "127.0.0.1 conn-a.example.local",
            "127.0.0.1 conn-b.example.local",
        ]
        infrastructure_adapter = mock.Mock()

        with self.assertRaisesRegex(RuntimeError, "Connector hostnames do not resolve locally"):
            hosts.ensure_connector_hosts(
                ["conn-a", "conn-b"],
                config_adapter=config_adapter,
                infrastructure_adapter=infrastructure_adapter,
                domain="example.local",
                resolver=mock.Mock(side_effect=OSError("Name or service not known")),
            )

        infrastructure_adapter.manage_hosts_entries.assert_called_once_with(
            [
                "127.0.0.1 conn-a.example.local",
                "127.0.0.1 conn-b.example.local",
            ],
            header_comment="# Dataspace Connector Hosts",
        )


if __name__ == "__main__":
    unittest.main()
