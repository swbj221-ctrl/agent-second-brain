"""Dev check: ensure help handler import wiring is valid."""

from d_brain.bot.handlers.telegram_ux import cmd_help  # noqa: F401


def main() -> int:
    print("help_import_check_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
