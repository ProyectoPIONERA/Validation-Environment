import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from deployers.shared.lib.cluster_runtime import (
    DEFAULT_K3S_KUBECONFIG,
    build_cluster_runtime,
    normalize_cluster_type,
)


class SharedClusterRuntimeTests(unittest.TestCase):
    def test_local_defaults_to_minikube(self):
        self.assertEqual(normalize_cluster_type(topology="local"), "minikube")
        self.assertEqual(build_cluster_runtime(topology="local")["cluster_type"], "minikube")

    def test_vm_single_preserves_minikube_default_until_k3s_is_validated(self):
        runtime = build_cluster_runtime(topology="vm-single")

        self.assertEqual(runtime["cluster_type"], "minikube")
        self.assertEqual(runtime["k3s_kubeconfig"], DEFAULT_K3S_KUBECONFIG)

    def test_vm_single_can_opt_into_k3s(self):
        runtime = build_cluster_runtime(
            {
                "CLUSTER_TYPE": "k3s",
                "K3S_KUBECONFIG": "/custom/k3s.yaml",
            },
            topology="vm-single",
        )

        self.assertEqual(runtime["cluster_type"], "k3s")
        self.assertEqual(runtime["k3s_kubeconfig"], "/custom/k3s.yaml")

    def test_vm_distributed_defaults_to_k3s_runtime(self):
        self.assertEqual(build_cluster_runtime(topology="vm-distributed")["cluster_type"], "k3s")

    def test_unsupported_cluster_runtime_fails_fast(self):
        with self.assertRaisesRegex(ValueError, "Unsupported cluster runtime"):
            normalize_cluster_type("kind", topology="vm-single")


if __name__ == "__main__":
    unittest.main()
