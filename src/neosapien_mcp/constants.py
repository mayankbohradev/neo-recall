"""Hosts and paths — no private secrets.

Firebase web API key is a public client identifier (ships in NeoSapien.app).
Security is enforced by Firebase Auth + Firestore rules, not by hiding this key.
"""

FIREBASE_PROJECT_ID = "neo-app-prod"
FIREBASE_API_KEY = "AIzaSyAfNEhywrk9sEIJ2F1wwZ_TAGAJcOOLwkg"
FIREBASE_AUTH_DOMAIN = "neo-app-prod.firebaseapp.com"
FIREBASE_APP_ID = "1:654544939696:web:13100c98d0be3ca609a975"
FIREBASE_STORAGE_BUCKET = "neo-app-prod.firebasestorage.app"
FIREBASE_MESSAGING_SENDER_ID = "654544939696"

FIRESTORE_BASE = (
    f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}"
    "/databases/(default)/documents"
)
BACKEND_BASE = "https://neo-backend-v2.api.neosapien.xyz"
SECURE_TOKEN_URL = "https://securetoken.googleapis.com/v1/token"

# Desktop piggyback (macOS NeoSapien app) — ID token only, expires ~hourly
NEO_DESKTOP_CONFIG = "~/Library/Application Support/neosapien/config.json"

KEYRING_SERVICE = "neo-recall"
CACHE_TTL_SECONDS = 600  # 10 minutes
PAGE_SIZE = 300
TOKEN_SAFETY_MARGIN_SECONDS = 120

# Local Google sign-in helper (use localhost — authorized in Firebase by default)
AUTH_HELPER_HOST = "localhost"
AUTH_HELPER_PORT = 8765
