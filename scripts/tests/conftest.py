import os
import sys

# Antes de importar seed_config: fecha fija, sin RDS y sin credenciales reales.
os.environ["SEED_REFERENCE_DATE"] = "2026-11-09"
os.environ["STAGE"] = "test"
for k in ("DB_HOST", "DB_PASSWORD", "DB_PASS", "AWS_PROFILE"):
    os.environ.pop(k, None)
os.environ.update(AWS_ACCESS_KEY_ID="testing", AWS_SECRET_ACCESS_KEY="testing", AWS_SESSION_TOKEN="testing", AWS_DEFAULT_REGION="us-east-1")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
