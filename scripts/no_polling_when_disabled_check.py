"""Verify d_brain does not import or start polling when Telegram is disabled."""

import asyncio
import os
import sys


def main() -> None:
    os.environ["D_BRAIN_TELEGRAM_DISABLED"] = "1"
    import d_brain.__main__ as entry

    asyncio.run(entry.main())
    if "d_brain.bot.main" in sys.modules:
        raise SystemExit("Polling module imported while telegram_disabled=True.")
    print("ok: polling not started (telegram_disabled=True)")


if __name__ == "__main__":
    main()
