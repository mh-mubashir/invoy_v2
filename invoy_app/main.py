"""
Invoy App — entry point.

Run with:
    python -m invoy_app.main
  or:
    python invoy_app/main.py
"""

import sys


def main() -> None:
    # Ensure customtkinter is available before importing the full app
    try:
        import customtkinter  # noqa: F401
    except ImportError:
        print(
            "Error: customtkinter is not installed.\n"
            "Install dependencies with:\n"
            "  pip install -r invoy_app/requirements.txt",
            file=sys.stderr,
        )
        sys.exit(1)

    from invoy_app.app import InvoyApp

    app = InvoyApp()
    app.mainloop()


if __name__ == "__main__":
    main()
