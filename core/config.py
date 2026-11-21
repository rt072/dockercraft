import os


class Settings:
    PROJECT_NAME = "Container Optimizer"
    VERSION = "0.1.0"
    ANALYSIS_MAX_SIZE = 1024 * 1024  # 1 MB
    ALLOWED_EXTENSIONS = {".txt", ".Dockerfile", ".dockerfile"}


settings = Settings()
