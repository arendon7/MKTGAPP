"""Single source of truth for BINARIO Marketing product versioning."""

__version__ = "0.9.0.dev1"
MACOS_SHORT_VERSION = "0.9.0"
MACOS_BUNDLE_VERSION = "3"

# Releases remain fail-closed until the reconstructed product reaches a certified gate.
RELEASE_READY = False
RELEASE_TAG: str | None = None
