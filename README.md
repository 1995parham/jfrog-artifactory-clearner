# JFrog Container Registry Cleaner

A minimal, readable Python tool to remove old Docker images from JFrog Artifactory Container Registry.

## Features

- Support for multiple repositories and images in a single configuration
- Specify repository/image combinations for fine-grained control
- Per-image configuration for `days_old` and `keep_minimum` settings
- Remove images older than a specified number of days
- Always keep a minimum number of recent tags per image
- Configuration review table displayed at startup
- Dry-run mode to preview deletions before executing
- Simple TOML-based configuration
- Clear logging and summary statistics

## Requirements

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) package manager

## Installation

1. Install uv if you haven't already:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. Clone or download this project

3. Install dependencies:

```bash
uv sync
```

## Configuration

1. Copy the example configuration:

```bash
cp config.toml.example config.toml
```

2. Edit `config.toml` with your JFrog credentials:

```toml
# JFrog Artifactory Configuration
[jfrog]
url = "https://your-company.jfrog.io/artifactory"
username = "your-username"
password = "your-password-or-api-token"

# List of images to clean in the format: repository/image-name
# You can specify images from different repositories
images = ["docker-local/image1", "docker-local/image2", "docker-prod/production-app"]

# Cleanup Configuration
[cleanup]
# Default settings for all images (can be overridden per-image below)
# Delete images older than this many days
days_old = 30

# Always keep at least this many recent tags per image
keep_minimum = 3

# Set to false to actually delete images (true = preview only)
dry_run = true
```

### Per-Image Configuration

You can override `days_old` and `keep_minimum` for specific images:

```toml
# Keep production images longer with more tags
[[image_config]]
image = "docker-local/critical-app"
days_old = 60
keep_minimum = 5

# Clean dev images more aggressively
[[image_config]]
image = "docker-local/dev-app"
days_old = 7
keep_minimum = 2
```

The tool will display a configuration table at startup showing the settings for each image.

## Usage

### Dry Run (Preview)

By default, the tool runs in dry-run mode to show what would be deleted:

```bash
uv run main.py
```

### Live Deletion

To actually delete images, set `dry_run = false` in your `config.toml` file:

```toml
[cleanup]
dry_run = false
```

Then run:

```bash
uv run main.py
```

## How It Works

1. Connects to JFrog Artifactory using provided credentials
2. Displays a configuration table showing settings for each image
3. Parses the images list and groups by repository
4. For each repository/image combination:
   - Applies the image-specific or default cleanup settings
   - Fetches all tags with their modification dates
   - Sorts tags by date (newest first)
   - Keeps the minimum number of recent tags (per-image or default: 3)
   - Deletes tags older than the specified days (per-image or default: 30)
5. Prints per-repository and overall summary statistics

## Safety Features

- Dry-run mode enabled by default
- Always keeps minimum number of recent tags per image
- Per-image configuration for fine-grained control
- Configuration review table displayed at startup
- Clear logging of all actions with per-image settings
- Error handling for network issues
