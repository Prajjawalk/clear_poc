"""Minimal TiTiler server with default COG endpoints."""
import os
from pathlib import Path
from fastapi import FastAPI
from titiler.core.factory import TilerFactory
from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers

# Base directory for raster files (not used in this minimal example)
RASTER_BASE_DIR = Path(__file__).parent / "assets" / "cogs"

# Create custom FastAPI app
app = FastAPI(
    title="TiTiler - Minimal COG Server",
    description="Minimal dynamic raster tile server",
)

# Add exception handlers
add_exception_handlers(app, DEFAULT_STATUS_CODES)

# Create and include the COG router
cog = TilerFactory()
app.include_router(cog.router, prefix="/cog")

if __name__ == "__main__":
    import uvicorn
    # Configuration
    host = os.getenv("TITILER_HOST", "127.0.0.1")
    port = int(os.getenv("TITILER_PORT", "8001"))
    print(f"TiTiler COG directory: {RASTER_BASE_DIR}")
    print(f"\nUsage:")
    print(f"  Info:      http://{host}:{port}/cog/info?url=https://example.com/file.tif")
    print(f"  Tiles:     http://{host}:{port}/cog/tiles/{{z}}/{{x}}/{{y}}?url=https://example.com/file.tif")

    # Run TiTiler
    uvicorn.run(
        "titiler_server:app",
        host=host,
        port=port,
        log_level="info",
        reload=True,  # Enable auto-reload during development
    )
