#!/usr/bin/env python3
"""Launch the Pose2OSC app from the project root."""

from __future__ import annotations

from multiprocessing import freeze_support

from pose2osc.app import main


if __name__ == "__main__":
    freeze_support()
    raise SystemExit(main())
