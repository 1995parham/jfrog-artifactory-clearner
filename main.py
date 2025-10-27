#!/usr/bin/env python3

"""
JFrog Container Registry Cleaner
Removes old Docker images from JFrog Artifactory based on age.
"""

import sys
import tomllib
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import requests


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
            print(f"Error fetching images: {e}")
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
            print(f"Error fetching tags for {image_name}: {e}")
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
            print(f"  [DRY RUN] Would delete: {image_path}")
            return True

        try:
            response = self.session.delete(delete_url)
            response.raise_for_status()
            print(f"  Deleted: {image_path}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"  Error deleting {image_path}: {e}")
            return False

    def clean_old_images(
        self, days_old: int = 30, dry_run: bool = True, keep_minimum: int = 3
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
        cutoff_date = datetime.now() - timedelta(days=days_old)
        stats = {"checked": 0, "deleted": 0, "kept": 0, "errors": 0}

        print(
            f"Cleaning images older than {days_old} days (before {cutoff_date.date()})"
        )
        print(f"Mode: {'DRY RUN' if dry_run else 'LIVE DELETION'}")
        print(f"Keeping minimum {keep_minimum} recent tags per image\n")

        images = self.get_images()

        for image_name in images:
            print(f"Processing image: {image_name}")
            tags = self.get_image_tags(image_name)

            if not tags:
                print(f"  No tags found\n")
                continue

            # Sort by modification date (newest first)
            tags.sort(key=lambda x: x.modified, reverse=True)

            # Keep minimum number of recent tags
            tags_to_check = tags[keep_minimum:]
            kept_count = len(tags) - len(tags_to_check)

            print(f"  Found {len(tags)} tags, keeping {kept_count} most recent")

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

            print()

        return stats


def main():
    config_path = Path(__file__).parent / "config.toml"

    if not config_path.exists():
        print(f"Error: Configuration file not found at {config_path}")
        print("Please copy config.toml and update with your settings.")
        sys.exit(1)

    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    jfrog_config = config.get("jfrog", {})
    cleanup_config = config.get("cleanup", {})

    jfrog_url = jfrog_config.get("url")
    jfrog_username = jfrog_config.get("username")
    jfrog_password = jfrog_config.get("password")
    repositories = jfrog_config.get("repositories", [])
    days_old = cleanup_config.get("days_old", 30)
    keep_minimum = cleanup_config.get("keep_minimum", 3)
    dry_run = cleanup_config.get("dry_run", True)

    if not all([jfrog_url, jfrog_username, jfrog_password]):
        print("Error: Missing required configuration in config.toml!")
        print(
            "Please ensure [jfrog] section has: url, username, password, repositories"
        )
        sys.exit(1)

    if not repositories:
        print("Error: No repositories specified in config.toml!")
        print("Please add repositories list in [jfrog] section")
        sys.exit(1)

    total_stats = {"checked": 0, "deleted": 0, "kept": 0, "errors": 0}

    print(f"Processing {len(repositories)} repository/repositories\n")

    for repo in repositories:
        print("=" * 60)
        print(f"Repository: {repo}")
        print("=" * 60)

        cleaner = JFrogCleaner(jfrog_url, jfrog_username, jfrog_password, repo)
        stats = cleaner.clean_old_images(
            days_old=days_old, dry_run=dry_run, keep_minimum=keep_minimum
        )

        # Accumulate stats
        for key in total_stats:
            total_stats[key] += stats[key]

        print()

    print("=" * 60)
    print("Overall Summary:")
    print(f"  Repositories processed: {len(repositories)}")
    print(f"  Images checked: {total_stats['checked']}")
    print(f"  Images deleted: {total_stats['deleted']}")
    print(f"  Images kept: {total_stats['kept']}")
    print(f"  Errors: {total_stats['errors']}")
    print("=" * 60)

    if dry_run:
        print(
            "\nThis was a DRY RUN. Set dry_run=false in config.toml to actually delete images."
        )


if __name__ == "__main__":
    main()
