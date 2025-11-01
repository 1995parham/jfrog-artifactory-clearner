# JFrog Container Registry Cleaner

A minimal, readable Python tool to remove old Docker images from JFrog Artifactory Container Registry.

## Features

- Support for multiple repositories and images in a single configuration
- Specify repository/image combinations for fine-grained control
- Remove images older than a specified number of days
- Always keep a minimum number of recent tags per image
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
# Delete images older than this many days
days_old = 30

# Always keep at least this many recent tags per image
keep_minimum = 3

# Set to false to actually delete images (true = preview only)
dry_run = true
```

To clean a single image, just specify one:

```toml
images = ["docker-local/myapp"]
```

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
2. Parses the images list and groups by repository
3. For each repository/image combination:
   - Fetches all tags with their modification dates
   - Sorts tags by date (newest first)
   - Keeps the minimum number of recent tags (default: 3)
   - Deletes tags older than the specified days (default: 30)
4. Prints per-repository and overall summary statistics

## Safety Features

- Dry-run mode enabled by default
- Always keeps minimum number of recent tags per image
- Clear logging of all actions
- Error handling for network issues
