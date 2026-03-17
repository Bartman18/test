"""
Root conftest.py — applies to ALL tests under tests/

Sets dummy AWS credentials and region at module load time — BEFORE any
Lambda handler module is imported. boto3 raises botocore.exceptions.NoRegionError
at module-import time even when all clients are later mocked, because the
client objects (e.g. boto3.client("sns")) are instantiated at the top level
of each handler module. Setting these env vars here (outside any fixture)
ensures they are present before pytest ever collects or imports a test file.
"""
import os

# Dummy region and credentials for boto3 / moto — never reach real AWS
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")
