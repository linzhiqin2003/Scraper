"""Unified storage module for all scrapers."""

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Union

from rich.console import Console

from .browser import DEFAULT_DATA_DIR

console = Console()


class JSONStorage:
    """JSON file storage for scraped data."""

    def __init__(self, source: str = "default", output_dir: Optional[Path] = None):
        """Initialize JSON storage.

        Args:
            source: Source name for default directory.
            output_dir: Custom output directory (overrides source).
        """
        if output_dir:
            self.output_dir = output_dir
        else:
            self.output_dir = DEFAULT_DATA_DIR / source / "exports"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def create_folder(self, folder_name: str) -> Path:
        """Create a subfolder in the output directory.

        Args:
            folder_name: Name of the subfolder to create.

        Returns:
            Path to the created folder.
        """
        folder_path = self.output_dir / folder_name
        folder_path.mkdir(parents=True, exist_ok=True)
        return folder_path

    def save(
        self,
        data: Any,
        filename: str,
        description: str = "data",
        silent: bool = False,
    ) -> Path:
        """Save data to JSON file.

        Args:
            data: Data to save (Pydantic models, dicts, or lists).
            filename: Output filename.
            description: Description for console output.
            silent: Suppress console output.

        Returns:
            Path to saved file.
        """
        filepath = self.output_dir / filename

        # Convert Pydantic models to dicts
        if isinstance(data, list):
            if data and hasattr(data[0], "model_dump"):
                export_data = [item.model_dump(mode="json") for item in data]
            else:
                export_data = data
        elif hasattr(data, "model_dump"):
            export_data = data.model_dump(mode="json")
        else:
            export_data = data

        self._write_json(filepath, export_data)

        if not silent:
            count = len(data) if isinstance(data, list) else 1
            console.print(f"[green]Saved {count} {description} to {filepath}[/green]")

        return filepath

    def save_to_folder(
        self,
        folder: Path,
        data: Any,
        filename: str,
        description: str = "data",
        silent: bool = False,
    ) -> Path:
        """Save data to a specific folder.

        Args:
            folder: Target folder path.
            data: Data to save.
            filename: Output filename.
            description: Description for console output.
            silent: Suppress console output.

        Returns:
            Path to saved file.
        """
        filepath = folder / filename

        if isinstance(data, list) and data and hasattr(data[0], "model_dump"):
            export_data = [item.model_dump(mode="json") for item in data]
        elif hasattr(data, "model_dump"):
            export_data = data.model_dump(mode="json")
        else:
            export_data = data

        self._write_json(filepath, export_data)

        if not silent:
            count = len(data) if isinstance(data, list) else 1
            console.print(f"[green]Saved {count} {description} to {filepath}[/green]")

        return filepath

    def load(self, filename: str) -> Optional[Any]:
        """Load data from JSON file.

        Args:
            filename: Input filename.

        Returns:
            Loaded data or None if file doesn't exist.
        """
        filepath = self.output_dir / filename
        return self._read_json(filepath)

    def generate_filename(self, prefix: str, suffix: str = "") -> str:
        """Generate timestamped filename.

        Args:
            prefix: Filename prefix.
            suffix: Optional suffix before extension.

        Returns:
            Generated filename.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if suffix:
            return f"{prefix}_{suffix}_{timestamp}.json"
        return f"{prefix}_{timestamp}.json"

    def _write_json(self, filepath: Path, data: Any) -> None:
        """Write data to JSON file."""
        filepath.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str)
        )

    def _read_json(self, filepath: Path) -> Optional[Any]:
        """Read data from JSON file."""
        if not filepath.exists():
            return None
        return json.loads(filepath.read_text())


class CSVStorage:
    """CSV file storage for scraped data."""

    def __init__(self, source: str = "default", output_dir: Optional[Path] = None):
        """Initialize CSV storage.

        Args:
            source: Source name for default directory.
            output_dir: Custom output directory (overrides source).
        """
        if output_dir:
            self.output_dir = output_dir
        else:
            self.output_dir = DEFAULT_DATA_DIR / source / "exports"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        data: List[Any],
        filename: str,
        flatten_nested: bool = True,
        silent: bool = False,
    ) -> Path:
        """Save data to CSV file.

        Args:
            data: List of data items (Pydantic models or dicts).
            filename: Output filename.
            flatten_nested: Flatten nested dicts (e.g., author.name -> author_name).
            silent: Suppress console output.

        Returns:
            Path to saved file.
        """
        filepath = self.output_dir / filename

        if not data:
            if not silent:
                console.print("[yellow]No data to save[/yellow]")
            return filepath

        # Convert to dicts
        rows = []
        for item in data:
            if hasattr(item, "model_dump"):
                row = item.model_dump(mode="json")
            else:
                row = dict(item)

            if flatten_nested:
                row = self._flatten_dict(row)

            rows.append(row)

        # Write CSV
        if rows:
            fieldnames = list(rows[0].keys())
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

        if not silent:
            console.print(f"[green]Saved {len(data)} items to {filepath}[/green]")

        return filepath

    def _flatten_dict(self, d: dict, parent_key: str = "", sep: str = "_") -> dict:
        """Flatten nested dictionary.

        Args:
            d: Dictionary to flatten.
            parent_key: Prefix for flattened keys.
            sep: Separator between parent and child keys.

        Returns:
            Flattened dictionary.
        """
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep).items())
            elif isinstance(v, list):
                # Convert lists to comma-separated strings
                items.append((new_key, ", ".join(str(x) for x in v)))
            else:
                items.append((new_key, v))
        return dict(items)


class DataManager:
    """High-level data management with deduplication."""

    def __init__(self, source: str = "default", output_dir: Optional[Path] = None):
        """Initialize data manager.

        Args:
            source: Source name for default directory.
            output_dir: Custom output directory.
        """
        self.json_storage = JSONStorage(source, output_dir)
        self.csv_storage = CSVStorage(source, output_dir)
        self._seen_ids: set = set()

    def add_items(
        self,
        items: List[Any],
        id_field: str = "id",
    ) -> List[Any]:
        """Add items with deduplication.

        Args:
            items: Items to add.
            id_field: Field name to use for deduplication.

        Returns:
            List of newly added items (not duplicates).
        """
        new_items = []
        for item in items:
            if hasattr(item, id_field):
                item_id = getattr(item, id_field)
            elif isinstance(item, dict):
                item_id = item.get(id_field)
            else:
                item_id = str(item)

            if item_id not in self._seen_ids:
                self._seen_ids.add(item_id)
                new_items.append(item)

        return new_items

    def export_json(self, data: Any, filename: str) -> Path:
        """Export data to JSON."""
        return self.json_storage.save(data, filename)

    def export_csv(self, data: List[Any], filename: str) -> Path:
        """Export data to CSV."""
        return self.csv_storage.save(data, filename)
