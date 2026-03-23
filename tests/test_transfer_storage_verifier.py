import json
import os
import tempfile
import unittest

from framework.transfer_storage_verifier import TransferStorageVerifier


def _buffer_payload(payload):
    return {
        "stream": {
            "type": "Buffer",
            "data": list(json.dumps(payload).encode("utf-8")),
        }
    }


def _build_transfer_report(report_path, *, failures=None):
    payload = {
        "collection": {"info": {"name": "06_consumer_transfer"}},
        "run": {
            "executions": [
                {
                    "item": {"name": "Start Transfer Process"},
                    "cursor": {"started": "2026-03-22T18:00:00.000Z"},
                    "response": _buffer_payload({"@id": "tp-123"}),
                },
                {
                    "item": {"name": "Resolve Current Transfer Destination"},
                    "response": _buffer_payload(
                        [
                            {
                                "@id": "tp-123",
                                "dataDestination": {
                                    "type": "AmazonS3",
                                    "bucketName": "demo-conn-consumer",
                                },
                            }
                        ]
                    ),
                },
            ],
            "failures": failures or [],
        },
    }
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)


def _build_transfer_report_without_cursor(report_path, *, created_at):
    payload = {
        "collection": {"info": {"name": "06_consumer_transfer"}},
        "run": {
            "executions": [
                {
                    "item": {"name": "Start Transfer Process"},
                    "cursor": {},
                    "response": _buffer_payload({"@id": "tp-123", "createdAt": created_at}),
                },
                {
                    "item": {"name": "Resolve Current Transfer Destination"},
                    "response": _buffer_payload(
                        [
                            {
                                "@id": "tp-123",
                                "dataDestination": {
                                    "type": "AmazonS3",
                                    "bucketName": "demo-conn-consumer",
                                },
                            }
                        ]
                    ),
                },
            ],
            "failures": [],
        },
    }
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)


class TransferStorageVerifierTests(unittest.TestCase):
    def test_verify_consumer_transfer_persistence_marks_pending_without_baseline(self):
        verifier = TransferStorageVerifier(poll_attempts=1, poll_interval_seconds=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = os.path.join(tmpdir, "reports")
            os.makedirs(report_dir, exist_ok=True)
            _build_transfer_report(os.path.join(report_dir, "06_consumer_transfer.json"))

            result = verifier.verify_consumer_transfer_persistence(
                "conn-provider",
                "conn-consumer",
                report_dir,
                before_snapshot=None,
            )

        self.assertEqual(result["status"], "skipped")
        self.assertIn("baseline", result["reason"])

    def test_verify_consumer_transfer_persistence_detects_new_object_after_retry(self):
        verifier = TransferStorageVerifier(poll_attempts=2, poll_interval_seconds=0)
        snapshots = [
            {},
            {
                "transfers/object.csv": {
                    "etag": "etag-1",
                    "size": 128,
                    "last_modified": "2026-03-22T18:00:02+00:00",
                }
            },
        ]
        verifier.capture_consumer_bucket_snapshot = lambda connector, bucket: snapshots.pop(0)

        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = os.path.join(tmpdir, "reports")
            os.makedirs(report_dir, exist_ok=True)
            _build_transfer_report(os.path.join(report_dir, "06_consumer_transfer.json"))

            result = verifier.verify_consumer_transfer_persistence(
                "conn-provider",
                "conn-consumer",
                report_dir,
                before_snapshot={},
                experiment_dir=tmpdir,
            )

            artifact_path = result["artifact_path"]

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["bucket_name"], "demo-conn-consumer")
        self.assertEqual(result["matched_objects"][0]["object_name"], "transfers/object.csv")
        self.assertTrue(artifact_path.endswith("storage_checks/conn-provider__conn-consumer.json"))

    def test_verify_consumer_transfer_persistence_fails_when_transfer_report_already_failed(self):
        verifier = TransferStorageVerifier(poll_attempts=1, poll_interval_seconds=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = os.path.join(tmpdir, "reports")
            os.makedirs(report_dir, exist_ok=True)
            _build_transfer_report(
                os.path.join(report_dir, "06_consumer_transfer.json"),
                failures=[
                    {
                        "source": {"name": "Check Transfer Status"},
                        "error": {
                            "test": "Transfer reached a successful state",
                            "message": "expected STARTED but got TERMINATED",
                        },
                    }
                ],
            )

            result = verifier.verify_consumer_transfer_persistence(
                "conn-provider",
                "conn-consumer",
                report_dir,
                before_snapshot={},
            )

        self.assertEqual(result["status"], "failed")
        self.assertIn("assertion failures", result["reason"])
        self.assertEqual(result["report_failures"][0]["source"], "Check Transfer Status")

    def test_verify_consumer_transfer_persistence_uses_created_at_when_cursor_started_is_missing(self):
        verifier = TransferStorageVerifier(poll_attempts=1, poll_interval_seconds=0)
        verifier.capture_consumer_bucket_snapshot = lambda connector, bucket: {
            "todos": {
                "etag": "etag-same",
                "size": 83,
                "last_modified": "2026-03-23T13:45:40+00:00",
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = os.path.join(tmpdir, "reports")
            os.makedirs(report_dir, exist_ok=True)
            _build_transfer_report_without_cursor(
                os.path.join(report_dir, "06_consumer_transfer.json"),
                created_at=1774273535000,
            )

            result = verifier.verify_consumer_transfer_persistence(
                "conn-provider",
                "conn-consumer",
                report_dir,
                before_snapshot={
                    "todos": {
                        "etag": "etag-same",
                        "size": 83,
                        "last_modified": "2026-03-23T12:00:00+00:00",
                    }
                },
            )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["matched_objects"][0]["reason"], "modified_after_transfer_start")
        self.assertEqual(result["transfer_started_at"], "2026-03-23T13:45:35+00:00")


if __name__ == "__main__":
    unittest.main()
