"""Smoke test for OpenClaw bridge helpers."""

from d_brain.integrations.openclaw_bridge import handle_help, handle_status


def main() -> None:
    user_id = 123
    print("status:")
    print(handle_status(user_id))
    print("\nhelp:")
    print(handle_help(user_id))


if __name__ == "__main__":
    main()
