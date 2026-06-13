"""Auth CLI — Google sign-in (easy) or paste tokens (advanced)."""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from neosapien_mcp import constants
from neosapien_mcp.auth import store
from neosapien_mcp.auth.tokens import extract_uid_from_jwt, try_desktop_id_token


def _save(
    *,
    refresh_token: str,
    firebase_api_key: str,
    uid: str = "",
    email: str = "",
) -> None:
    store.save(
        store.StoredCredentials(
            refresh_token=refresh_token,
            firebase_api_key=firebase_api_key or constants.FIREBASE_API_KEY,
            uid=uid,
            email=email,
        )
    )
    print("Saved. Credentials are in your OS keychain (or encrypted fallback).")
    print(f"Fallback folder: {Path.home() / '.neo-recall'}")
    if email:
        print(f"Signed in as: {email}")
    elif uid:
        print(f"UID: {uid}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Connect NeoRecall to your Neo account (tokens never logged)."
    )
    parser.add_argument(
        "--google",
        action="store_true",
        help="Easiest: open browser, Sign in with Google, auto-save refresh token.",
    )
    parser.add_argument(
        "--from-desktop",
        action="store_true",
        help="Check Neo desktop config.json for a short-lived ID token (demo only).",
    )
    parser.add_argument("--manual", action="store_true", help="Paste API key + refresh token.")
    parser.add_argument("--clear", action="store_true", help="Remove stored credentials.")
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Seconds to wait for Google sign-in (default 180).",
    )
    args = parser.parse_args(argv)

    if args.clear:
        store.clear()
        print("Cleared stored credentials.")
        return

    if args.from_desktop:
        pair = try_desktop_id_token()
        if not pair:
            print(
                f"No usable authToken in {constants.NEO_DESKTOP_CONFIG}. Use --google instead.",
                file=sys.stderr,
            )
            sys.exit(1)
        _token, uid = pair
        print(
            f"Desktop ID token found for uid={uid}, but it expires in ~1 hour and "
            "is NOT a refresh token. Use --google for a lasting login."
        )
        return

    # Default path = Google browser login (best for non-technical users)
    if args.google or not args.manual:
        try:
            from neosapien_mcp.auth.google_login import run_google_login

            payload = run_google_login(timeout_sec=args.timeout)
            _save(
                refresh_token=payload["refresh_token"],
                firebase_api_key=payload.get("firebase_api_key") or constants.FIREBASE_API_KEY,
                uid=payload.get("uid") or "",
                email=payload.get("email") or "",
            )
            print("\nNext: point Claude / Cursor / Codex at the `neo-recall` command.")
            return
        except Exception as exc:  # noqa: BLE001
            if args.google:
                print(f"Google sign-in failed: {exc}", file=sys.stderr)
                sys.exit(1)
            print(f"Google sign-in unavailable ({exc}). Falling back to manual paste.\n")

    print("Manual credential paste")
    print("Paste values carefully. Nothing is printed back.")
    api_key = (
        getpass.getpass(
            f"Firebase web API key [default {constants.FIREBASE_API_KEY[:12]}…]: "
        ).strip()
        or constants.FIREBASE_API_KEY
    )
    refresh = getpass.getpass("Firebase refresh token: ").strip()
    email = input("Email (optional): ").strip()
    if not refresh:
        print("Refresh token is required.", file=sys.stderr)
        sys.exit(1)

    uid = ""
    if refresh.startswith("eyJ"):
        try:
            uid = extract_uid_from_jwt(refresh)
            print(
                "WARNING: that looks like an ID token, not a refresh token.",
                file=sys.stderr,
            )
        except Exception:
            pass

    _save(refresh_token=refresh, firebase_api_key=api_key, uid=uid, email=email)


if __name__ == "__main__":
    main()
