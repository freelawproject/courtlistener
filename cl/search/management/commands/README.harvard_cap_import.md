# Harvard CAP Data Import Process

This documentation covers the process of importing and updating case data from
the Harvard Case Law Access Project (CAP) into CourtListener.

## Overview

The import process consists of two main steps:

1. Generating crosswalk files that map CAP cases to CourtListener cases
2. Using these crosswalk files to update CourtListener's case data with the
   latest CAP content

## Commands

### 1. generate_cap_crosswalk

Generates mapping files between CAP and CourtListener cases.

```
manage.py generate_cap_crosswalk --output-dir cl/search/crosswalks [options]
```

#### Options:

- `--output-dir`: (Required) Directory to save crosswalk files
- `--reporter`: Process only a specific reporter (e.g., 'U.S.')
- `--volume`: Process only a specific volume
- `--updated-after`: Only process cases updated after this date (YYYY-MM-DD or
  YYYY-MM-DDTHH:MM:SS+00:00)
- `--start-from-reporter`: Start processing from a specific reporter slug
- `--dry-run`: Run without saving crosswalk files
- `--verbose`: Increase output verbosity

### 2. update_cap_cases

Updates CourtListener cases with the latest CAP HTML content using the generated
crosswalk files.

```
manage.py update_cap_cases --crosswalk-dir cl/search/crosswalks [options]
```

#### Options:

- `--crosswalk-dir`: (Required) Directory containing crosswalk files
- `--reporter`: Update only a specific reporter
- `--max-workers`: Maximum number of worker threads (default: 4, max: 16)
- `--verbose`: Enable verbose output

## Complete Update Process

1. **Environment Setup**

Required environment variables. These will come from CAP devops team:

- CAP_R2_ENDPOINT_URL="your_endpoint"
- CAP_R2_ACCESS_KEY_ID="your_key"
- CAP_R2_SECRET_ACCESS_KEY="your_secret"
- CAP_R2_BUCKET_NAME="your_bucket"

2. **Generate Crosswalk Files**

Generate for all reporters:

```
manage.py generate_cap_crosswalk --output-dir cl/search/crosswalks
```

Or generate for specific reporter with date filter:

```
manage.py generate_cap_crosswalk --output-dir cl/search/crosswalks --reporter U.S --updated-after 2024-03-19
```

3. **Update CourtListener Data**

Update all reporters:

```
manage.py update_cap_cases --crosswalk-dir cl/search/crosswalks
```

Or update specific reporter:

```
manage.py update_cap_cases --crosswalk-dir cl/search/crosswalks --reporter U_S
```

## Data Flow

1. `generate_cap_crosswalk`:
   - Fetches reporter metadata from CAP
   - For each reporter/volume:
     - Retrieves case metadata
     - Matches CAP cases with CourtListener cases
     - Generates crosswalk JSON files

2. `update_cap_cases`:
   - Reads crosswalk files
   - For each mapping:
     - Fetches CAP HTML content
     - Updates CourtListener XML data
     - Updates cluster headmatter if needed

## File Formats

### Crosswalk JSON

```
[
    { "cap_case_id": 3, "cl_cluster_id": 1, "cap_path": "/reporter/volume/cases/case-id.json" }
]
```

## Common Issues and Troubleshooting

1. **Missing Environment Variables**
   - Ensure all CAP R2 environment variables are set
   - Check access permissions to the CAP bucket

2. **Date Filtering**
   - Supports both ISO format (YYYY-MM-DDTHH:MM:SS+00:00) and short format
     (YYYY-MM-DD)
   - Short format dates are converted to midnight UTC

3. **Performance Considerations**
   - Use `--max-workers` to adjust concurrent processing
   - Consider using `--reporter` for targeted updates
   - Large updates may require significant processing time
   - Using last updated date filter will speed up the process significantly

## Development Notes

- Use `--verbose` for debugging
- Consider using `--dry-run` before large updates
