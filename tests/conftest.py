import os
from pathlib import Path
import tempfile


TEST_DIR = Path(tempfile.mkdtemp(prefix="desktop-inventory-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_DIR / 'test.db').as_posix()}"
os.environ["JWT_SECRET"] = "test-only-secret-with-more-than-thirty-two-characters"
os.environ["CELERY_BROKER_URL"] = "memory://"
os.environ["CELERY_RESULT_BACKEND"] = "cache+memory://"
