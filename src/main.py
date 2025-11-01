#!/usr/bin/env python3

"""
JFrog Container Registry Cleaner
Removes old Docker images from JFrog Artifactory based on age.
"""

import os
import sys
import tomllib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


@dataclass
class ImageTag:
    """Represents a Docker image tag with metadata."""

    tag: str
    path: str
    modified: str


class JFrogCleaner:
    """Clean old images from JFrog Container Registry."""

    def __init__(self, url: str, username: str, password: str, repository: str):
        """
        Initialize JFrog cleaner.
        """
        self.url = url.rstrip("/")
        self.repository = repository
        self.session = requests.Session()
        self.session.auth = (username, password)
        self.session.headers.update({"Content-Type": "application/json"})

    def get_images(self) -> list[str]:
        """Get list of all images in the repository."""
        api_url = f"{self.url}/api/docker/{self.repository}/v2/_catalog"

        try:
            response = self.session.get(api_url)
            response.raise_for_status()
            data = response.json()
            return data.get("repositories", [])
        except requests.exceptions.RequestException as e:
            console.print(f"[red]Error fetching images: {e}[/red]")
            return []

    def get_image_tags(self, image_name: str) -> list[ImageTag]:
        """Get all tags for a specific image with metadata."""
        api_url = f"{self.url}/api/storage/{self.repository}/{image_name}"

        try:
            response = self.session.get(api_url, params={"list": "", "deep": "1"})
            response.raise_for_status()
            data = response.json()

            tags = []
            for file_info in data.get("files", []):
                if file_info["uri"].endswith("/manifest.json"):
                    tag_path = file_info["uri"].strip("/").split("/")[0]
                    tags.append(
                        ImageTag(
                            tag=tag_path,
                            path=f"{image_name}/{tag_path}",
                            modified=file_info.get("lastModified"),
                        )
                    )

            return tags
        except requests.exceptions.RequestException as e:
            console.print(f"[red]Error fetching tags for {image_name}: {e}[/red]")
            return []

    def delete_image_tag(self, image_path: str, dry_run: bool = True) -> bool:
        """
        Delete a specific image tag.

        Args:
            image_path: Full path to image tag (e.g., 'myimage/v1.0.0')
            dry_run: If True, only simulate deletion

        Returns:
            True if deleted successfully (or would be deleted in dry-run)
        """
        delete_url = f"{self.url}/{self.repository}/{image_path}"

        if dry_run:
            console.print(f"  [yellow]Would delete: {image_path}[/yellow]")
            return True

        try:
            response = self.session.delete(delete_url)
            response.raise_for_status()
            console.print(f"  [green]✓ Deleted: {image_path}[/green]")
            return True
        except requests.exceptions.RequestException as e:
            console.print(f"  [red]✗ Error deleting {image_path}: {e}[/red]")
            return False

    def clean_old_images(
        self,
        days_old: int = 30,
        dry_run: bool = True,
        keep_minimum: int = 3,
        include_images=None,
        exclude_images=None,
    ) -> dict[str, int]:
        """
        Remove images older than specified days.
        Args:
            days_old: Delete images older than this many days
            dry_run: If True, only simulate deletions
            keep_minimum: Always keep at least this many recent tags per image

        Returns:
            dictionary with statistics (checked, deleted, kept, errors)
        """

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
        stats = {"checked": 0, "deleted": 0, "kept": 0, "errors": 0}

        console.print(
            f"[cyan]Cleaning images older than {days_old} days (before {cutoff_date.date()})[/cyan]"
        )
        mode_color = "yellow" if dry_run else "red bold"
        console.print(
            f"Mode: [{mode_color}]{'DRY RUN' if dry_run else 'LIVE DELETION'}[/{mode_color}]"
        )
        console.print(
            f"[cyan]Keeping minimum {keep_minimum} recent tags per image[/cyan]\n"
        )

        images = self.get_images()

        if include_images:
            images = [i for i in images if i in include_images]

        if exclude_images:
            images = [i for i in images if i not in exclude_images]

        for image_name in images:
            console.print(
                f"\n[bold blue]Processing image:[/bold blue] [white]{image_name}[/white]"
            )
            tags = self.get_image_tags(image_name)

            if not tags:
                console.print("  [dim]No tags found[/dim]")
                continue

            # Sort by modification date (newest first)
            tags.sort(key=lambda x: x.modified, reverse=True)

            # Keep minimum number of recent tags
            tags_to_check = tags[keep_minimum:]
            kept_count = len(tags) - len(tags_to_check)

            console.print(
                f"  [dim]Found {len(tags)} tags, keeping {kept_count} most recent[/dim]"
            )

            for tag_info in tags_to_check:
                stats["checked"] += 1
                tag_date = datetime.fromisoformat(
                    tag_info.modified.replace("Z", "+00:00")
                )

                if tag_date < cutoff_date:
                    success = self.delete_image_tag(tag_info.path, dry_run)
                    if success:
                        stats["deleted"] += 1
                    else:
                        stats["errors"] += 1
                else:
                    stats["kept"] += 1

        return stats


def main():
    config_path = Path(__file__).parent / "config.toml"

    if not config_path.exists():
        console.print(
            f"[red]Error: Configuration file not found at {config_path}[/red]"
        )
        console.print("Please copy config.toml and update with your settings.")
        sys.exit(1)

    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    jfrog_config = config.get("jfrog", {})
    cleanup_config = config.get("cleanup", {})

    jfrog_url = jfrog_config.get("url")
    jfrog_username = os.path.expandvars(jfrog_config.get("username", ""))
    jfrog_password = os.path.expandvars(jfrog_config.get("password", ""))
    images = jfrog_config.get("images", [])

    days_old = cleanup_config.get("days_old", 30)
    keep_minimum = cleanup_config.get("keep_minimum", 3)
    dry_run = cleanup_config.get("dry_run", True)

    if not all([jfrog_url, jfrog_username, jfrog_password]):
        console.print(
            "[red]Error: Missing required configuration in config.toml![/red]"
        )
        console.print(
            "Please ensure [jfrog] section has: url, username, password, images"
        )
        sys.exit(1)

    if not images:
        console.print("[red]Error: No images specified in config.toml![/red]")
        console.print(
            "Please add images list in [jfrog] section (format: repository/image-name)"
        )
        sys.exit(1)

    # Parse and group images by repository
    repo_images = {}
    for image_spec in images:
        if "/" not in image_spec:
            console.print(f"[red]Error: Invalid image format '{image_spec}'![/red]")
            console.print(
                "Expected format: repository/image-name (e.g., 'docker-local/myapp')"
            )
            sys.exit(1)

        parts = image_spec.split("/", 1)
        repo = parts[0]
        image_name = parts[1]

        if repo not in repo_images:
            repo_images[repo] = []
        repo_images[repo].append(image_name)

    total_stats = {"checked": 0, "deleted": 0, "kept": 0, "errors": 0}

    console.print(
        f"\n[bold magenta]Processing {len(repo_images)} repository/repositories with {len(images)} image(s)[/bold magenta]\n"
    )

    for repo, image_list in repo_images.items():
        console.print(
            Panel(
                f"[bold cyan]{repo}[/bold cyan]\nImages: [white]{', '.join(image_list)}[/white]",
                title="Repository",
                border_style="cyan",
            )
        )

        cleaner = JFrogCleaner(jfrog_url, jfrog_username, jfrog_password, repo)
        stats = cleaner.clean_old_images(
            days_old=days_old,
            dry_run=dry_run,
            keep_minimum=keep_minimum,
            include_images=image_list,
            exclude_images=None,
        )

        for key in total_stats:
            total_stats[key] += stats[key]

        console.print()

    table = Table(
        title="Overall Summary",
        border_style="green",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Metric", style="cyan", justify="left")
    table.add_column("Count", style="white", justify="right")

    table.add_row("Repositories processed", str(len(repo_images)))
    table.add_row("Images checked", str(total_stats["checked"]))
    table.add_row(
        "Images deleted",
        (
            f"[yellow]{total_stats['deleted']}[/yellow]"
            if dry_run
            else f"[red]{total_stats['deleted']}[/red]"
        ),
    )
    table.add_row("Images kept", f"[green]{total_stats['kept']}[/green]")
    table.add_row(
        "Errors",
        f"[red]{total_stats['errors']}[/red]" if total_stats["errors"] > 0 else "0",
    )

    console.print("\n")
    console.print(table)

    if dry_run:
        console.print(
            "\n[yellow bold]⚠ This was a DRY RUN. Set dry_run=false in config.toml to actually delete images.[/yellow bold]"
        )


if __name__ == "__main__":
    main()
