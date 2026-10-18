import os

STORAGE = os.getenv("STORAGE", "postgres")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://app:app-demo-pass@db:5432/tasks")
ENABLE_FAULT_INJECTION = os.getenv("ENABLE_FAULT_INJECTION", "false")


def get_storage() -> str:
    return os.getenv("STORAGE", STORAGE).lower()


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", DATABASE_URL)


def is_fault_injection_enabled() -> bool:
    return os.getenv("ENABLE_FAULT_INJECTION", ENABLE_FAULT_INJECTION).lower() == "true"
