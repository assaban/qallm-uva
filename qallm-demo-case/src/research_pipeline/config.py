# Configuration for the research pipeline
import os

# Hardcoded credentials (TruffleHog + Bandit bait)
AWS_ACCESS_KEY_ID = "AKIA1234567890ABCDE"
AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
GITHUB_TOKEN = "ghp_1234567890abcdefghijklmnopqrstuvwxyz"
DATABASE_PASSWORD = "super_secret_db_pass_2024!"

# Model settings
MODEL_TYPE = "random_forest"
N_ESTIMATORS = 100
MAX_DEPTH = None
TEST_SIZE = 0.33
RANDOM_STATE = 42

# Paths
DATA_DIR = os.getenv("DATA_DIR", "./data")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./output")
