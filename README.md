# TestRail Test Results Analysis Dashboard

A comprehensive Streamlit-based dashboard for analyzing TestRail test results across multiple builds, platforms, and test configurations.

## Features

- **Multi-Build Analysis**: Analyze test results across the last 5 builds of a release
- **Platform-Specific Metrics**: Track performance across different hardware platforms (MS series, Catalyst series)
- **Device Type Comparison**: Compare single vs. stack device configurations
- **Test Status Tracking**: Monitor 5 different test statuses (Pass, Fail, Error, Blocked, Skip)
- **Section-Level Analysis**: Identify which test sections are failing most frequently
- **Data Caching**: Local CSV caching for faster subsequent loads
- **Interactive Visualizations**: Toggle between table and graph views

## Prerequisites

- Python 3.7+
- TestRail instance with API access
- TestRail API key

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd testrail-dashboard
```

2. Install required dependencies:
```bash
pip install streamlit requests pandas plotly
```

## Configuration

### TestRail API Setup

1. Log into your TestRail instance
2. Go to **My Settings** → **API Keys**
3. Generate a new API key or use an existing one
4. Note your TestRail URL (e.g., `https://yourcompany.testrail.io/`)

### Project Configuration

The dashboard is currently configured for:
- **Project ID**: 9 (hardcoded)
- **Supported Release Milestones**:
  - CS-1
  - switch-17
  - switch-18
  - Nightly
  - Aurora2
  - Trunk

To modify these settings, edit the relevant sections in the code.

## Usage

1. Run the Streamlit dashboard:
```bash
streamlit run testrail_dashboard.py
```

2. In the sidebar, enter:
   - TestRail URL
   - Username (email)
   - API Key
   - Select a Release Milestone

3. Configure options:
   - **Fetch detailed section information**: Enable to see which test sections are failing (slower)
   - **Use summary data only**: Skip fetching individual test results (faster)
   - **Use cached data**: Load previously fetched data from CSV files

4. Click **Fetch Data** to load test results

## Dashboard Sections

### 1. Overall Test Results Summary
- Shows pass/fail/error/blocked/skip percentages for each build
- Available in both table and line graph views
- Displays full build names with dates

### 2. Platform Analysis
- Filter by specific build or view all builds
- Filter by specific platform or view all platforms
- Shows test status distribution for single and stack configurations
- Identifies top failing sections per platform

### 3. Top Failing Sections Analysis
- Aggregates failures across all selected builds
- Shows which test sections have the most failures
- Requires "Fetch detailed section information" to be enabled

### 4. Build Comparison
- Stacked bar chart showing test status distribution
- Compares multiple builds side-by-side
- Shows percentages for easy comparison

## Supported Platforms

### Meraki MS Series
- MS120, MS125, MS130, MS150
- MS210, MS220, MS225, MS250
- MS320, MS350, MS355, MS390
- MS410, MS420, MS425, MS450

### Catalyst Series
- C9300, C9300L, C9300X
- C9200, C9200L, C9200CX
- C9500, C9400, C9600, C9800
- C3850, C3650, C2960

## Data Caching

The dashboard caches fetched data in CSV files to improve performance:
- Default cache directory: `./testrail_cache`
- Cache structure: `./testrail_cache/{release_milestone}/{build_name}.csv`
- Each CSV contains summary data, platform breakdowns, and section information

To clear the cache, simply delete the cache directory.

## Troubleshooting

### "No results returned for run" warnings
- TestRail may not be storing individual test results
- Your API key may not have permission to access test results
- Try enabling "Use summary data only" checkbox

### "Summary data - section details not available"
- Individual test results are not available from the API
- Section analysis requires individual test results to map failures to sections
- This is a TestRail configuration/permission issue

### Platform not detected
- Check if the run name contains the platform identifier
- The platform extraction looks for patterns like "MS350", "C9300", etc.
- Platforms are case-insensitive

### API Timeout errors
- Large test runs may take time to fetch
- Consider using the cache feature
- Enable "Use summary data only" for faster loading

## Limitations

1. **Section Analysis**: Requires individual test results from TestRail API
2. **Project ID**: Currently hardcoded to project ID 9
3. **Build Limit**: Shows only the last 5 builds per release
4. **API Rate Limits**: Subject to TestRail API rate limiting

## Contributing

To add support for new platforms:
1. Edit the `extract_platform()` function
2. Add platform identifiers to the `platforms` list

To add new release milestones:
1. Edit the `milestone_options` list in the sidebar
2. Update the `matches_release_pattern()` function if needed

## License

[Your License Here]

## Support

For issues related to:
- **TestRail API**: Contact your TestRail administrator
- **Dashboard bugs**: Open an issue in this repository
- **Feature requests**: Submit a pull request or open an issue
