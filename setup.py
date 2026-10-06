"""py2app build for PixProRefsel.app -- use build.sh, which also signs and installs."""

from setuptools import setup

VERSION = "1.6.0"

setup(
    name="PixProRefsel",
    app=["main.py"],
    options={"py2app": {
        "argv_emulation": False,
        "iconfile": "PixProRefsel.icns",
        "plist": {
            "CFBundleName": "PixProRefsel",
            "CFBundleDisplayName": "PixProRefsel",
            "CFBundleIdentifier": "com.timmccoy.pixprorefsel",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSMinimumSystemVersion": "13.0",
            "NSHighResolutionCapable": True,
            "LSUIElement": True,
            "NSAppleEventsUsageDescription":
                "PixProRefsel controls Pixelmator Pro to shrink or grow your selection.",
            "NSHumanReadableCopyright": "Copyright © 2026 Tim McCoy. All rights reserved.",
        },
    }},
    setup_requires=["py2app"],
)
