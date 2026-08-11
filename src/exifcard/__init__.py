"""exifcard: render a photo and its EXIF metadata into a finished card image."""

import pillow_heif

# Registered once, at import: HEIC is both an input the tool reads and an output
# it writes, so every entry point needs Pillow to know the format.
pillow_heif.register_heif_opener()

__version__ = "0.1.0"
