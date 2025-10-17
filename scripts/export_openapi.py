"""Script to export OpenAPI specification from FastAPI app."""

import json
from pathlib import Path

from token_bowl_chat_server.server import create_app


def export_openapi_spec():
    """Export OpenAPI specification to openapi.json."""
    # Create app instance
    app = create_app()

    # Get OpenAPI schema
    openapi_schema = app.openapi()

    # Get project root directory
    project_root = Path(__file__).parent.parent
    output_path = project_root / "openapi.json"

    # Write to file with pretty formatting
    with open(output_path, "w") as f:
        json.dump(openapi_schema, f, indent=2)

    print(f"OpenAPI specification exported to: {output_path}")
    print(f"Total endpoints: {len([p for p in openapi_schema.get('paths', {}).values()])}")


if __name__ == "__main__":
    export_openapi_spec()
