"""Single source of truth for BINARIO Marketing product versioning."""

__version__ = "0.9.0"
MACOS_SHORT_VERSION = "0.9.0"
MACOS_BUNDLE_VERSION = "3"

# Wave 96 freezes release identity before physical UAT. This is source intent only:
# it does not grant operational, release, publication, or production authority.
RELEASE_READY = True
RELEASE_TAG: str | None = "v0.9.0"
