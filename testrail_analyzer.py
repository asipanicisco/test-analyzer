import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import json
from collections import defaultdict
import re
import os
import csv
import time

# TestRail API Class
class TestRailAPI:
    def __init__(self, base_url, username, api_key):
        self.base_url = base_url.rstrip('/')
        self.auth = (username, api_key)
        self.headers = {'Content-Type': 'application/json'}
    
    def send_get(self, uri):
        """Send GET request to TestRail API"""
        url = f"{self.base_url}/index.php?/api/v2/{uri}"
        
        # Add timeout to prevent hanging
        try:
            response = requests.get(url, auth=self.auth, headers=self.headers, timeout=30)
        except requests.exceptions.Timeout:
            raise Exception(f"TestRail API timeout after 30 seconds for: {uri}")
        except requests.exceptions.ConnectionError:
            raise Exception(f"Connection error to TestRail API for: {uri}")
        
        if response.status_code != 200:
            raise Exception(f"TestRail API returned {response.status_code}: {response.text}")
        
        # Try to parse JSON response
        try:
            return response.json()
        except json.JSONDecodeError:
            raise Exception(f"Invalid JSON response from TestRail: {response.text[:200]}")
    
    def get_milestones(self, project_id):
        """Get all milestones for a project"""
        milestones = []
        offset = 0
        while True:
            try:
                response = self.send_get(f"get_milestones/{project_id}&offset={offset}")
                if isinstance(response, list):
                    if not response:  # Empty list means no more data
                        break
                    milestones.extend(response)
                    offset += len(response)
                    if len(response) < 250:  # Less than page size means last page
                        break
                else:
                    # Single response, not paginated
                    return response
            except:
                break
        return milestones
    
    def get_milestone(self, milestone_id):
        """Get a specific milestone"""
        return self.send_get(f"get_milestone/{milestone_id}")
    
    def get_plans(self, project_id):
        """Get all test plans for a project"""
        plans = []
        offset = 0
        while True:
            try:
                response = self.send_get(f"get_plans/{project_id}&offset={offset}")
                if isinstance(response, list):
                    if not response:  # Empty list means no more data
                        break
                    plans.extend(response)
                    offset += len(response)
                    if len(response) < 250:  # Less than page size means last page
                        break
                else:
                    # Single response, not paginated
                    return response
            except:
                break
        return plans
    
    def get_plan(self, plan_id):
        """Get a specific test plan"""
        return self.send_get(f"get_plan/{plan_id}")
    
    def get_runs(self, project_id):
        """Get all test runs for a project"""
        return self.send_get(f"get_runs/{project_id}")
    
    def get_run(self, run_id):
        """Get a specific test run"""
        return self.send_get(f"get_run/{run_id}")
    
    def get_tests(self, run_id):
        """Get all tests for a run"""
        return self.send_get(f"get_tests/{run_id}")
    
    def get_results_for_run(self, run_id, limit=None):
        """Get all results for a run with optional limit"""
        results = []
        offset = 0
        batch_size = 250  # TestRail's maximum limit per request
        
        try:
            while True:
                # Build the API call with pagination
                # TestRail doesn't allow limit > 250, so we must paginate
                current_limit = batch_size
                if limit:
                    remaining = limit - len(results)
                    if remaining <= 0:
                        break
                    if remaining < batch_size:
                        current_limit = remaining
                
                url_suffix = f"get_results_for_run/{run_id}&offset={offset}&limit={current_limit}"
                
                batch = self.send_get(url_suffix)
                
                if not batch or not isinstance(batch, list):
                    break
                    
                results.extend(batch)
                
                # If we got less than batch_size, we've reached the end
                if len(batch) < current_limit:
                    break
                    
                offset += len(batch)
                
                # Show progress for large result sets
                if offset > 0 and offset % 1000 == 0:
                    st.text(f"    Fetched {offset} results so far...")
                
                # Safety check
                if len(results) > 10000:
                    st.warning(f"Large number of results ({len(results)}) for run {run_id}. Stopping to prevent timeout.")
                    break
                    
        except Exception as e:
            st.error(f"Error fetching results for run {run_id}: {str(e)}")
            
        return results
    
    def get_sections(self, project_id, suite_id):
        """Get all sections for a suite"""
        return self.send_get(f"get_sections/{project_id}&suite_id={suite_id}")
    
    def get_cases(self, project_id, suite_id):
        """Get all test cases for a suite"""
        return self.send_get(f"get_cases/{project_id}&suite_id={suite_id}")

# Helper functions
def parse_build_date(milestone_name):
    """Extract date from milestone name - handles multiple date formats"""
    # Format 1: cs-17-2-202506022349-G9b920b73c087-rel-bricklaying (YYYYMMDDHHmm)
    # Format 2: switch-18-202506182240-G0100853be368-jenkins-banquette
    # Format 3: T-202506251848-G61bcac03e7e2-jenkins-anklet
    date_pattern1 = r'(\d{4})(\d{2})(\d{2})(\d{4})'
    match = re.search(date_pattern1, milestone_name)
    if match:
        year, month, day, time = match.groups()
        try:
            return datetime(int(year), int(month), int(day))
        except:
            pass
    
    # Format 4: Cisco_IOS_XE_Software_BLD_V1718_THROTTLE_LATEST_20250507_010754
    # Look for pattern with underscores: YYYYMMDD_HHmmss
    date_pattern2 = r'(\d{4})(\d{2})(\d{2})_(\d{6})'
    match = re.search(date_pattern2, milestone_name)
    if match:
        year, month, day, time = match.groups()
        try:
            return datetime(int(year), int(month), int(day))
        except:
            pass
    
    # Alternative formats: 2025-06-02 or 20250602
    date_pattern3 = r'(\d{4})[-]?(\d{2})[-]?(\d{2})'
    match = re.search(date_pattern3, milestone_name)
    if match:
        year, month, day = match.groups()
        try:
            return datetime(int(year), int(month), int(day))
        except:
            pass
    
    return None

def matches_release_pattern(milestone_name, release_milestone):
    """Check if milestone name matches the pattern for a given release"""
    ms_lower = milestone_name.lower()
    release_lower = release_milestone.lower()
    
    # CS-1: cs-17-2-202506022349-... (note: it's cs-17, not cs-1)
    if release_lower == 'cs-1':
        return ms_lower.startswith('cs-17-') and parse_build_date(milestone_name) is not None
    
    # switch-17 or switch-18: switch-XX-202506182240-...
    elif release_lower in ['switch-17', 'switch-18']:
        return ms_lower.startswith(release_lower + '-') and parse_build_date(milestone_name) is not None
    
    # Nightly: T-202506251848-...
    elif release_lower == 'nightly':
        return ms_lower.startswith('t-') and parse_build_date(milestone_name) is not None
    
    # Aurora2: Cisco_IOS_XE_Software_BLD_V1718_THROTTLE_LATEST_...
    # or: Cisco_IOS_XE_Software_BLD_V1715_THROTTLE_LATEST_...
    elif release_lower == 'aurora2':
        return ('cisco_ios_xe_software' in ms_lower and 
                ('bld_v17' in ms_lower or 'bld_v16' in ms_lower) and 
                parse_build_date(milestone_name) is not None)
    
    # Trunk: Use generic pattern matching
    elif release_lower == 'trunk':
        # For trunk, we'll need to know the pattern - for now, check if it has a date
        return parse_build_date(milestone_name) is not None
    
    # Default: look for release prefix
    return ms_lower.startswith(release_lower + '-') and parse_build_date(milestone_name) is not None

def categorize_device(run_name):
    """Categorize device as single or stack"""
    run_name_upper = run_name.upper()
    
    # Check for stack indicators
    if any(indicator in run_name_upper for indicator in ['STACK', 'STK', 'STACKED']):
        return 'stack'
    # Check for single indicators
    elif any(indicator in run_name_upper for indicator in ['SINGLE', 'SNGL', 'STANDALONE', 'SWITCH-']):
        return 'single'
    
    # Additional patterns
    # If it contains Switch-[Letter]-[Model] pattern, it's usually single
    import re
    if re.match(r'Switch-[A-Z]-', run_name, re.IGNORECASE):
        return 'single'
    
    return 'unknown'

def extract_platform(run_name):
    """Extract platform from run name"""
    # Extended list of platforms including all Meraki switch models
    platforms = [
        # Meraki MS series
        'MS120', 'MS125', 'MS130', 'MS150', 'MS210', 'MS220', 'MS225', 'MS250', 
        'MS320', 'MS350', 'MS355', 'MS390', 'MS410', 'MS420', 'MS425', 'MS450',
        # Catalyst series
        'C9300', 'C9300L', 'C9300X', 'C9200', 'C9200L', 'C9200CX',
        'C9500', 'C9400', 'C9600', 'C9800',
        # Other potential platforms
        'C3850', 'C3650', 'C2960'
    ]
    
    # Check each platform in the run name
    for platform in platforms:
        if platform in run_name.upper():  # Case-insensitive matching
            return platform
    
    # If no known platform found, try to extract model number pattern
    # Look for patterns like MS-130, MS 130, etc.
    import re
    
    # Pattern for MS series with hyphen or space
    ms_pattern = r'MS[-\s]?(\d+)'
    match = re.search(ms_pattern, run_name, re.IGNORECASE)
    if match:
        return f'MS{match.group(1)}'
    
    # Pattern for C series
    c_pattern = r'C(\d{4}[A-Z]*)'
    match = re.search(c_pattern, run_name, re.IGNORECASE)
    if match:
        return f'C{match.group(1)}'
    
    return 'Unknown'

def save_build_data_to_csv(build_data, cache_dir, release_milestone):
    """Save build data to a single CSV file"""
    os.makedirs(cache_dir, exist_ok=True)
    
    # Create a safe filename
    safe_build_name = re.sub(r'[^\w\-_]', '_', build_data['name'])
    release_dir = os.path.join(cache_dir, release_milestone)
    os.makedirs(release_dir, exist_ok=True)
    
    csv_file = os.path.join(release_dir, f"{safe_build_name}.csv")
    
    with open(csv_file, 'w', newline='') as f:
        writer = csv.writer(f)
        
        # Write summary section
        writer.writerow(['SUMMARY'])
        writer.writerow(['metric', 'value'])
        writer.writerow(['name', build_data['name']])
        writer.writerow(['date', build_data['date']])
        writer.writerow(['passed', build_data['overall']['passed']])
        writer.writerow(['failed', build_data['overall']['failed']])
        writer.writerow(['error', build_data['overall'].get('error', 0)])
        writer.writerow(['blocked', build_data['overall']['blocked']])
        writer.writerow(['retest', build_data['overall']['retest']])
        writer.writerow(['skipped', build_data['overall']['skipped']])
        writer.writerow([])  # Empty row as separator
        
        # Write platform section
        writer.writerow(['PLATFORMS'])
        writer.writerow(['platform', 'device_type', 'passed', 'failed', 'error'])
        for platform, platform_data in build_data['platforms'].items():
            for device_type in ['single', 'stack']:
                writer.writerow([
                    platform,
                    device_type,
                    platform_data[device_type]['passed'],
                    platform_data[device_type]['failed'],
                    platform_data[device_type].get('error', 0)
                ])
        writer.writerow([])  # Empty row as separator
        
        # Write sections section
        writer.writerow(['SECTIONS'])
        writer.writerow(['platform', 'device_type', 'section', 'count'])
        for platform, platform_data in build_data['platforms'].items():
            for device_type in ['single', 'stack']:
                for section, count in platform_data[device_type]['sections'].items():
                    if count > 0:
                        writer.writerow([platform, device_type, section, count])
    
    return csv_file

def load_build_data_from_csv(csv_file):
    """Load build data from a single CSV file"""
    build_data = {
        'overall': {'passed': 0, 'failed': 0, 'error': 0, 'blocked': 0, 'retest': 0, 'skipped': 0},
        'platforms': defaultdict(lambda: {
            'single': {'passed': 0, 'failed': 0, 'error': 0, 'sections': defaultdict(int)},
            'stack': {'passed': 0, 'failed': 0, 'error': 0, 'sections': defaultdict(int)}
        })
    }
    
    current_section = None
    
    with open(csv_file, 'r') as f:
        reader = csv.reader(f)
        
        for row in reader:
            if not row:  # Skip empty rows
                continue
                
            # Check for section headers
            if row[0] == 'SUMMARY':
                current_section = 'summary'
                next(reader)  # Skip header row
                continue
            elif row[0] == 'PLATFORMS':
                current_section = 'platforms'
                next(reader)  # Skip header row
                continue
            elif row[0] == 'SECTIONS':
                current_section = 'sections'
                next(reader)  # Skip header row
                continue
            
            # Process data based on current section
            if current_section == 'summary':
                metric, value = row[0], row[1]
                if metric == 'name':
                    build_data['name'] = value
                elif metric == 'date':
                    build_data['date'] = value
                elif metric in ['passed', 'failed', 'error', 'blocked', 'retest', 'skipped']:
                    build_data['overall'][metric] = int(value)
                    
            elif current_section == 'platforms':
                if len(row) == 5:  # New format with error column
                    platform, device_type, passed, failed, error = row
                    build_data['platforms'][platform][device_type]['passed'] = int(passed)
                    build_data['platforms'][platform][device_type]['failed'] = int(failed)
                    build_data['platforms'][platform][device_type]['error'] = int(error)
                elif len(row) == 4:  # Old format without error column
                    platform, device_type, passed, failed = row
                    build_data['platforms'][platform][device_type]['passed'] = int(passed)
                    build_data['platforms'][platform][device_type]['failed'] = int(failed)
                    build_data['platforms'][platform][device_type]['error'] = 0
                
            elif current_section == 'sections':
                platform, device_type, section, count = row
                build_data['platforms'][platform][device_type]['sections'][section] = int(count)
    
    return build_data

def check_cached_builds(cache_dir, release_milestone, build_milestones):
    """Check which builds are already cached"""
    cached_builds = []
    uncached_builds = []
    
    release_dir = os.path.join(cache_dir, release_milestone)
    
    for build_ms in build_milestones:
        safe_build_name = re.sub(r'[^\w\-_]', '_', build_ms['name'])
        csv_file = os.path.join(release_dir, f"{safe_build_name}.csv")
        
        if os.path.exists(csv_file):
            cached_builds.append(build_ms)
        else:
            uncached_builds.append(build_ms)
    
    return cached_builds, uncached_builds

def calculate_status_percentages(passed, failed, error, blocked, retest, skipped):
    """Calculate percentages for all test statuses"""
    total = passed + failed + error + blocked + retest + skipped
    if total == 0:
        return 0, 0, 0, 0, 0
    
    pass_pct = (passed / total) * 100
    fail_pct = (failed / total) * 100
    error_pct = (error / total) * 100
    blocked_pct = (blocked / total) * 100
    skip_pct = (skipped / total) * 100
    
    return pass_pct, fail_pct, error_pct, blocked_pct, skip_pct

def calculate_pass_fail_percentage(passed, failed):
    """Calculate pass/fail percentages ignoring skipped"""
    total = passed + failed
    if total == 0:
        return 0, 0
    pass_pct = (passed / total) * 100
    fail_pct = (failed / total) * 100
    return pass_pct, fail_pct

# Streamlit App
st.set_page_config(page_title="TestRail Analysis Dashboard", layout="wide")

st.title("🧪 TestRail Test Results Analysis Dashboard")

# Sidebar for credentials and inputs
with st.sidebar:
    st.header("Configuration")
    
    testrail_url = st.text_input("TestRail URL", value="https://testrail.ikarem.io/", help="Your TestRail instance URL")
    username = st.text_input("Username", value="autobot@msperfect.meraki.net", help="Your TestRail username (email)")
    api_key = st.text_input("API Key", type="password", help="Your TestRail API key")
    
    # Hardcoded project ID
    project_id = 9
    st.info(f"Project ID: {project_id}")
    
    # Predefined milestones dropdown
    milestone_options = ["CS-1", "switch-17", "switch-18", "Nightly", "Aurora2", "Trunk"]
    release_milestone = st.selectbox("Release Milestone", milestone_options, help="Select the release milestone to analyze")
    
    # Option to enable/disable section analysis
    fetch_sections = st.checkbox("Fetch detailed section information", value=False, 
                                help="Enable to see which test sections are failing most. This will increase processing time significantly.")
    
    # Option to skip result fetching if API doesn't support it
    force_summary_only = st.checkbox("Use summary data only (faster)", value=False,
                                    help="Skip fetching individual test results and use only summary statistics")
    
    # Cache directory
    cache_dir = st.text_input("Cache Directory", value="./testrail_cache", 
                             help="Directory to store cached CSV files")
    
    use_cache = st.checkbox("Use cached data if available", value=True,
                           help="Load previously fetched data from CSV files")
    
    if st.button("Fetch Data", type="primary"):
        if not all([testrail_url, username, api_key, release_milestone]):
            st.error("Please fill in all fields")
        else:
            with st.spinner("Fetching data from TestRail..."):
                try:
                    # Initialize API
                    api = TestRailAPI(testrail_url, username, api_key)
                    
                    # Get all milestones and find the release milestone
                    milestones_response = api.get_milestones(project_id)
                    
                    # Check response format
                    if isinstance(milestones_response, dict):
                        if 'error' in milestones_response:
                            st.error(f"API Error: {milestones_response['error']}")
                            raise Exception(milestones_response['error'])
                        elif 'milestones' in milestones_response:
                            milestones = milestones_response['milestones']
                        else:
                            milestones = milestones_response.get('result', milestones_response.get('data', []))
                            if not isinstance(milestones, list):
                                raise Exception(f"Cannot find milestones list in response")
                    elif isinstance(milestones_response, list):
                        milestones = milestones_response
                    else:
                        raise Exception("Invalid API response format")
                    
                    release_ms = None
                    matching_milestones = []
                    
                    # Find all milestones with the matching name
                    for ms in milestones:
                        if isinstance(ms, dict) and ms.get('name') == release_milestone:
                            matching_milestones.append(ms)
                    
                    if not matching_milestones:
                        st.error(f"Release milestone '{release_milestone}' not found")
                        st.info(f"Available milestones: {', '.join([m.get('name', 'Unknown') for m in milestones if isinstance(m, dict)])}")
                    else:
                        # If multiple milestones with same name, prefer the one with children
                        if len(matching_milestones) > 1:
                            matching_milestones.sort(key=lambda x: len(x.get('milestones', [])), reverse=True)
                        
                        # Use the first one (which should have the most children after sorting)
                        release_ms = matching_milestones[0]
                        st.success(f"Found release milestone: {release_ms['name']} (ID: {release_ms['id']})")
                        
                        # Get sub-milestones (build milestones) from the release milestone
                        build_milestones = []
                        
                        # First check if the milestone already has children in the initial response
                        if 'milestones' in release_ms and isinstance(release_ms.get('milestones'), list):
                            child_milestones = release_ms['milestones']
                            if len(child_milestones) > 0:
                                for child_ms in child_milestones:
                                    if isinstance(child_ms, dict):
                                        ms_name = child_ms.get('name', '')
                                        build_date = parse_build_date(ms_name)
                                        if build_date:
                                            child_ms['build_date'] = build_date
                                            build_milestones.append(child_ms)
                        
                        # If no children found in initial response, try the get_milestone API
                        if not build_milestones:
                            try:
                                milestone_details = api.get_milestone(release_ms['id'])
                                
                                # The API returns child milestones in the 'milestones' array
                                if 'milestones' in milestone_details:
                                    child_milestones = milestone_details['milestones']
                                    if isinstance(child_milestones, list) and len(child_milestones) > 0:
                                        for child_ms in child_milestones:
                                            if isinstance(child_ms, dict):
                                                ms_name = child_ms.get('name', '')
                                                build_date = parse_build_date(ms_name)
                                                if build_date:
                                                    child_ms['build_date'] = build_date
                                                    build_milestones.append(child_ms)
                                    
                            except Exception as e:
                                st.error(f"Error getting milestone details: {str(e)}")
                        
                        # Final fallback: look through all milestones for children
                        if not build_milestones:
                            for ms in milestones:
                                if isinstance(ms, dict) and ms.get('parent_id') == release_ms['id']:
                                    ms_name = ms.get('name', '')
                                    build_date = parse_build_date(ms_name)
                                    if build_date:
                                        ms['build_date'] = build_date
                                        build_milestones.append(ms)
                        
                        # Sort by date and get last 5
                        build_milestones.sort(key=lambda x: x['build_date'], reverse=True)
                        build_milestones = build_milestones[:5]
                        
                        if not build_milestones:
                            st.warning(f"No build milestones found under '{release_milestone}'")
                            st.stop()
                        
                        # Check for cached builds
                        cached_builds = []
                        uncached_builds = build_milestones
                        
                        if use_cache:
                            cached_builds, uncached_builds = check_cached_builds(cache_dir, release_milestone, build_milestones)
                            
                            if cached_builds:
                                st.success(f"Found {len(cached_builds)} cached builds")
                            if uncached_builds:
                                st.info(f"Need to fetch data for {len(uncached_builds)} builds")
                        
                        # Collect data for each build
                        all_data = {
                            'release': release_milestone,
                            'builds': [],
                            'fetch_sections': fetch_sections  # Store the setting
                        }
                        
                        # Load cached builds first
                        for build_ms in cached_builds:
                            safe_build_name = re.sub(r'[^\w\-_]', '_', build_ms['name'])
                            csv_file = os.path.join(cache_dir, release_milestone, f"{safe_build_name}.csv")
                            
                            with st.spinner(f"Loading cached data for {build_ms['name'][:40]}..."):
                                build_data = load_build_data_from_csv(csv_file)
                                all_data['builds'].append(build_data)
                        
                        # Process uncached builds
                        if uncached_builds:
                            progress_bar = st.progress(0)
                            status_text = st.empty()
                            
                            for idx, build_ms in enumerate(uncached_builds):
                                build_name = build_ms['name']
                                status_text.text(f"Processing build: {build_name[:60]}...")
                                progress_bar.progress((idx + 1) / len(uncached_builds))
                                
                                build_data = {
                                    'name': build_name,
                                    'date': build_ms['build_date'].strftime('%Y-%m-%d'),
                                    'overall': {'passed': 0, 'failed': 0, 'error': 0, 'blocked': 0, 'retest': 0, 'skipped': 0},
                                    'platforms': defaultdict(lambda: {
                                        'single': {'passed': 0, 'failed': 0, 'error': 0, 'sections': defaultdict(int)},
                                        'stack': {'passed': 0, 'failed': 0, 'error': 0, 'sections': defaultdict(int)}
                                    })
                                }
                                
                                # Get plans for this milestone
                                try:
                                    # Get ALL plans once and filter
                                    if 'all_plans_cache' not in st.session_state:
                                        with st.spinner("Fetching all plans (one-time operation)..."):
                                            plans_response = api.get_plans(project_id)
                                            
                                            # Handle different response formats
                                            if isinstance(plans_response, dict):
                                                if 'plans' in plans_response:
                                                    plans = plans_response['plans']
                                                elif 'result' in plans_response:
                                                    plans = plans_response['result']
                                                elif 'data' in plans_response:
                                                    plans = plans_response['data']
                                                else:
                                                    plans = []
                                            elif isinstance(plans_response, list):
                                                plans = plans_response
                                            else:
                                                plans = []
                                            
                                            st.session_state['all_plans_cache'] = plans
                                    else:
                                        plans = st.session_state['all_plans_cache']
                                    
                                    # Filter plans for this milestone
                                    milestone_plans = [p for p in plans if isinstance(p, dict) and p.get('milestone_id') == build_ms['id']]
                                    
                                    if not milestone_plans:
                                        continue
                                        
                                except Exception as e:
                                    st.warning(f"Error getting plans for build {build_ms['name']}: {str(e)}")
                                    continue
                                
                                # Process plans with progress tracking
                                plan_progress = st.progress(0)
                                for plan_idx, plan in enumerate(milestone_plans):
                                    plan_progress.progress((plan_idx + 1) / len(milestone_plans))
                                    
                                    try:
                                        plan_details = api.get_plan(plan['id'])
                                        
                                        # Process each run in the plan
                                        total_runs = sum(len(entry.get('runs', [])) for entry in plan_details.get('entries', []))
                                        run_count = 0
                                        
                                        for entry in plan_details.get('entries', []):
                                            for run in entry.get('runs', []):
                                                run_count += 1
                                                run_name = run.get('name', '')
                                                run_id = run.get('id')
                                                
                                                platform = extract_platform(run_name)
                                                device_type = categorize_device(run_name)
                                                
                                                # Get results for this run
                                                try:
                                                    # First, get run details to see how many tests it has
                                                    run_details = api.get_run(run_id)
                                                    
                                                    # Calculate total test count including custom statuses
                                                    passed = run_details.get('passed_count', 0)
                                                    failed = run_details.get('failed_count', 0)
                                                    blocked = run_details.get('blocked_count', 0)
                                                    retest = run_details.get('retest_count', 0)
                                                    untested = run_details.get('untested_count', 0)
                                                    
                                                    # Custom statuses (based on your mapping)
                                                    # custom_status1_count=7 (skip), custom_status2_count=26 (error)
                                                    skip = run_details.get('custom_status1_count', 0)
                                                    error = run_details.get('custom_status2_count', 0)
                                                    
                                                    test_count = passed + failed + blocked + retest + untested + skip + error
                                                    executed_count = passed + failed + blocked + retest + skip + error
                                                    
                                                    # If no tests or all untested, skip this run
                                                    if test_count == 0 or executed_count == 0:
                                                        continue
                                                    
                                                    # Try to fetch detailed results first
                                                    results_fetched = False
                                                    results = []
                                                    
                                                    # Skip result fetching if force_summary_only is enabled
                                                    if force_summary_only:
                                                        results_fetched = False
                                                    # Increase the threshold for fetching detailed results
                                                    elif executed_count < 10000:  # Increased from 5000
                                                        try:
                                                            start_time = time.time()
                                                            with st.spinner(f"  Fetching {executed_count} test results..."):
                                                                results = api.get_results_for_run(run_id)
                                                            
                                                            fetch_time = time.time() - start_time
                                                            
                                                            # Check if we got results
                                                            if results and len(results) > 0:
                                                                results_fetched = True
                                                            else:
                                                                # No results returned
                                                                results = []
                                                                results_fetched = False
                                                                    
                                                            if len(results) > 0:
                                                                results_fetched = True
                                                                
                                                                # Reset counts to process from actual results
                                                                build_data_temp = {
                                                                    'passed': 0, 'failed': 0, 'blocked': 0, 
                                                                    'retest': 0, 'skipped': 0, 'error': 0
                                                                }
                                                                
                                                                # Process actual results
                                                                for result in results:
                                                                    if not isinstance(result, dict):
                                                                        continue
                                                                    
                                                                    status = result.get('status_id', 0)
                                                                    
                                                                    if status == 1:  # Passed
                                                                        build_data_temp['passed'] += 1
                                                                    elif status == 5:  # Failed
                                                                        build_data_temp['failed'] += 1
                                                                    elif status == 6:  # Error (custom)
                                                                        build_data_temp['error'] += 1
                                                                    elif status == 7:  # Skip (custom)
                                                                        build_data_temp['skipped'] += 1
                                                                    elif status == 2:  # Blocked
                                                                        build_data_temp['blocked'] += 1
                                                                    elif status == 4:  # Retest
                                                                        build_data_temp['retest'] += 1
                                                                    elif status == 3:  # Untested
                                                                        build_data_temp['skipped'] += 1
                                                                
                                                                # Update main counts from actual results
                                                                build_data['overall']['passed'] += build_data_temp['passed']
                                                                build_data['overall']['failed'] += build_data_temp['failed']
                                                                build_data['overall']['error'] += build_data_temp['error']
                                                                build_data['overall']['blocked'] += build_data_temp['blocked']
                                                                build_data['overall']['retest'] += build_data_temp['retest']
                                                                build_data['overall']['skipped'] += build_data_temp['skipped']
                                                                
                                                                if platform != 'Unknown' and device_type in ['single', 'stack']:
                                                                    build_data['platforms'][platform][device_type]['passed'] += build_data_temp['passed']
                                                                    build_data['platforms'][platform][device_type]['failed'] += build_data_temp['failed']
                                                                    build_data['platforms'][platform][device_type]['error'] += build_data_temp['error']
                                                                
                                                                # Handle section mapping after processing results
                                                                if fetch_sections and (build_data_temp['failed'] + build_data_temp['error']) > 0 and platform != 'Unknown' and device_type in ['single', 'stack']:
                                                                    try:
                                                                        if run.get('suite_id'):
                                                                            # Step 1: Get all tests for this run (maps test_id to case_id)
                                                                            tests = api.get_tests(run_id)
                                                                            test_to_case = {test['id']: test['case_id'] for test in tests if isinstance(test, dict) and test.get('id') and test.get('case_id')}
                                                                            
                                                                            # Step 2: Get all cases for this suite (maps case_id to section_id)
                                                                            cases = api.get_cases(project_id, run['suite_id'])
                                                                            case_to_section_id = {case['id']: case['section_id'] for case in cases if isinstance(case, dict) and case.get('id') and case.get('section_id')}
                                                                            
                                                                            # Step 3: Get all sections for this suite (maps section_id to section_name)
                                                                            sections = api.get_sections(project_id, run['suite_id'])
                                                                            section_id_to_name = {section['id']: section['name'] for section in sections if isinstance(section, dict) and section.get('id') and section.get('name')}
                                                                            
                                                                            # Step 4: Process failed/error results and map to sections
                                                                            sections_found = False
                                                                            section_counts = defaultdict(int)
                                                                            
                                                                            for result in results:
                                                                                if isinstance(result, dict) and result.get('status_id') in [5, 6]:  # Failed or Error
                                                                                    test_id = result.get('test_id')
                                                                                    
                                                                                    # Map test_id -> case_id -> section_id -> section_name
                                                                                    if test_id and test_id in test_to_case:
                                                                                        case_id = test_to_case[test_id]
                                                                                        if case_id in case_to_section_id:
                                                                                            section_id = case_to_section_id[case_id]
                                                                                            if section_id in section_id_to_name:
                                                                                                section_name = section_id_to_name[section_id]
                                                                                                section_counts[section_name] += 1
                                                                                                sections_found = True
                                                                            
                                                                            # Add section counts to build data
                                                                            if sections_found:
                                                                                for section_name, count in section_counts.items():
                                                                                    build_data['platforms'][platform][device_type]['sections'][section_name] += count
                                                                            else:
                                                                                build_data['platforms'][platform][device_type]['sections']['Failed to map sections'] += build_data_temp['failed'] + build_data_temp['error']
                                                                        else:
                                                                            build_data['platforms'][platform][device_type]['sections']['No Suite ID'] += build_data_temp['failed'] + build_data_temp['error']
                                                                    except Exception as e:
                                                                        build_data['platforms'][platform][device_type]['sections'][f'Mapping Error: {str(e)[:50]}'] += build_data_temp['failed'] + build_data_temp['error']
                                                                elif not fetch_sections and (build_data_temp['failed'] + build_data_temp['error']) > 0 and platform != 'Unknown' and device_type in ['single', 'stack']:
                                                                    build_data['platforms'][platform][device_type]['sections']['Section details not fetched'] += build_data_temp['failed'] + build_data_temp['error']
                                                                    
                                                        except Exception as e:
                                                            pass
                                                    else:
                                                        pass
                                                    
                                                    # If we didn't get results, use summary data
                                                    if not results_fetched:
                                                        build_data['overall']['passed'] += passed
                                                        build_data['overall']['failed'] += failed
                                                        build_data['overall']['error'] += error
                                                        build_data['overall']['blocked'] += blocked
                                                        build_data['overall']['retest'] += retest
                                                        build_data['overall']['skipped'] += untested + skip
                                                        
                                                        if platform != 'Unknown' and device_type in ['single', 'stack']:
                                                            build_data['platforms'][platform][device_type]['passed'] += passed
                                                            build_data['platforms'][platform][device_type]['failed'] += failed
                                                            build_data['platforms'][platform][device_type]['error'] += error
                                                            
                                                            if (failed + error) > 0:
                                                                if fetch_sections:
                                                                    # Try to provide some section breakdown even without detailed results
                                                                    # Check if we can get test information from the run
                                                                    try:
                                                                        if run.get('suite_id'):
                                                                            # Try to get suite structure
                                                                            sections = api.get_sections(project_id, run['suite_id'])
                                                                            if sections and len(sections) > 0:
                                                                                # Distribute failures proportionally across sections
                                                                                section_names = [s['name'] for s in sections if isinstance(s, dict) and s.get('name')]
                                                                                if len(section_names) > 0:
                                                                                    failures_per_section = (failed + error) // len(section_names)
                                                                                    remainder = (failed + error) % len(section_names)
                                                                                    
                                                                                    for i, section_name in enumerate(section_names[:5]):  # Top 5 sections
                                                                                        count = failures_per_section + (1 if i < remainder else 0)
                                                                                        if count > 0:
                                                                                            build_data['platforms'][platform][device_type]['sections'][f"{section_name} (estimated)"] += count
                                                                                else:
                                                                                    build_data['platforms'][platform][device_type]['sections']['Summary data - no valid sections found'] += failed + error
                                                                            else:
                                                                                build_data['platforms'][platform][device_type]['sections']['Summary data - no sections found'] += failed + error
                                                                        else:
                                                                            build_data['platforms'][platform][device_type]['sections']['Summary data - no suite information'] += failed + error
                                                                    except Exception as e:
                                                                        build_data['platforms'][platform][device_type]['sections']['Summary data - section details not available'] += failed + error
                                                                else:
                                                                    build_data['platforms'][platform][device_type]['sections']['Summary data - details not available'] += failed + error
                                                    
                                                except Exception as e:
                                                    st.warning(f"  Error processing run {run_name}: {str(e)}")
                                                    continue
                                                    
                                    except Exception as e:
                                        st.warning(f"Error processing plan {plan.get('name', 'Unknown')}: {str(e)}")
                                        continue
                                
                                plan_progress.progress(1.0)
                                
                                all_data['builds'].append(build_data)
                                
                                # Save to cache
                                save_build_data_to_csv(build_data, cache_dir, release_milestone)
                            
                            if uncached_builds:
                                progress_bar.progress(1.0)
                                status_text.text("Data fetched successfully!")
                        
                        # Store in session state
                        st.session_state['testrail_data'] = all_data
                        st.success(f"Analysis complete! Loaded {len(cached_builds)} cached builds and fetched {len(uncached_builds)} new builds.")
                        
                except Exception as e:
                    st.error(f"Error: {str(e)}")

# Main content area
if 'testrail_data' in st.session_state:
    data = st.session_state['testrail_data']
    
    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        build_options = ['all'] + [b['name'] for b in data['builds']]
        selected_build = st.selectbox("Filter by Build", build_options)
    
    with col2:
        # Get all platforms
        all_platforms = set()
        for build in data['builds']:
            all_platforms.update(build['platforms'].keys())
        platform_options = ['all'] + sorted(list(all_platforms))
        selected_platform = st.selectbox("Filter by Platform", platform_options)
    
    with col3:
        view_mode = st.radio("View Mode", ['Table', 'Graph'], horizontal=True)
    
    # Filter data based on selections
    filtered_builds = data['builds']
    if selected_build != 'all':
        filtered_builds = [b for b in filtered_builds if b['name'] == selected_build]
    
    # Overall Summary
    st.header("📊 Overall Test Results Summary")
    
    # Calculate overall metrics with all status percentages
    overall_metrics = []
    for build in filtered_builds:
        pass_pct, fail_pct, error_pct, blocked_pct, skip_pct = calculate_status_percentages(
            build['overall']['passed'], 
            build['overall']['failed'],
            build['overall'].get('error', 0),
            build['overall']['blocked'],
            build['overall']['retest'],
            build['overall']['skipped']
        )
        overall_metrics.append({
            'Build': build['name'],  # Full build name, no truncation
            'Date': build['date'],
            'Pass %': round(pass_pct, 2),
            'Fail %': round(fail_pct, 2),
            'Error %': round(error_pct, 2),
            'Blocked %': round(blocked_pct, 2),
            'Skip %': round(skip_pct, 2),
            'Total Tests': sum([
                build['overall']['passed'],
                build['overall']['failed'],
                build['overall'].get('error', 0),
                build['overall']['blocked'],
                build['overall']['retest'],
                build['overall']['skipped']
            ])
        })
    
    if view_mode == 'Table':
        # Display table with horizontal scroll for long build names
        st.dataframe(pd.DataFrame(overall_metrics), use_container_width=True)
    else:
        # Create line chart for all status trends
        fig = go.Figure()
        
        df_metrics = pd.DataFrame(overall_metrics)
        
        # Add traces for each status
        fig.add_trace(go.Scatter(
            x=df_metrics['Build'],  # Using full build names
            y=df_metrics['Pass %'],
            mode='lines+markers',
            name='Pass %',
            line=dict(color='green', width=3),
            marker=dict(size=8)
        ))
        fig.add_trace(go.Scatter(
            x=df_metrics['Build'],
            y=df_metrics['Fail %'],
            mode='lines+markers',
            name='Fail %',
            line=dict(color='red', width=3),
            marker=dict(size=8)
        ))
        fig.add_trace(go.Scatter(
            x=df_metrics['Build'],
            y=df_metrics['Error %'],
            mode='lines+markers',
            name='Error %',
            line=dict(color='orange', width=3),
            marker=dict(size=8)
        ))
        fig.add_trace(go.Scatter(
            x=df_metrics['Build'],
            y=df_metrics['Blocked %'],
            mode='lines+markers',
            name='Blocked %',
            line=dict(color='purple', width=3),
            marker=dict(size=8)
        ))
        fig.add_trace(go.Scatter(
            x=df_metrics['Build'],
            y=df_metrics['Skip %'],
            mode='lines+markers',
            name='Skip %',
            line=dict(color='blue', width=3),
            marker=dict(size=8)
        ))
        
        fig.update_layout(
            title='Test Status Percentage Trend by Build',
            xaxis_title='Build',
            yaxis_title='Percentage',
            hovermode='x unified',
            xaxis=dict(
                tickangle=-45,  # Angle the x-axis labels for better readability
                automargin=True  # Automatically adjust margins
            ),
            height=600,  # Make chart taller to accommodate angled labels
            margin=dict(b=150)  # Extra bottom margin for labels
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Platform Analysis
    st.header("🖥️ Platform Analysis")
    
    # Create filters for platform analysis
    col1_pa, col2_pa = st.columns(2)
    
    with col1_pa:
        # Build dropdown for platform analysis
        pa_build_options = ['All Builds'] + [b['name'] for b in data['builds']]
        selected_pa_build = st.selectbox("Select Build for Platform Analysis", pa_build_options, key="pa_build")
    
    with col2_pa:
        # Get platforms based on selected build
        if selected_pa_build == 'All Builds':
            # Get all unique platforms across all builds
            available_platforms = set()
            for build in data['builds']:
                available_platforms.update(build['platforms'].keys())
        else:
            # Get platforms only from selected build
            selected_build_data = next((b for b in data['builds'] if b['name'] == selected_pa_build), None)
            if selected_build_data:
                available_platforms = set(selected_build_data['platforms'].keys())
            else:
                available_platforms = set()
        
        pa_platform_options = ['All Platforms'] + sorted(list(available_platforms))
        selected_pa_platform = st.selectbox("Select Platform", pa_platform_options, key="pa_platform")
    
    # Filter builds for platform analysis
    if selected_pa_build == 'All Builds':
        pa_filtered_builds = data['builds']
    else:
        pa_filtered_builds = [b for b in data['builds'] if b['name'] == selected_pa_build]
    
    # Aggregate platform data with detailed status information
    platform_data = defaultdict(lambda: {
        'single': {'passed': 0, 'failed': 0, 'error': 0, 'blocked': 0, 'retest': 0, 'skipped': 0, 'sections': defaultdict(int)},
        'stack': {'passed': 0, 'failed': 0, 'error': 0, 'blocked': 0, 'retest': 0, 'skipped': 0, 'sections': defaultdict(int)},
        'builds': set()  # Track which builds contributed to this data
    })
    
    for build in pa_filtered_builds:
        for platform, data_item in build['platforms'].items():
            if selected_pa_platform == 'All Platforms' or platform == selected_pa_platform:
                platform_data[platform]['builds'].add(build['name'])
                for device_type in ['single', 'stack']:
                    platform_data[platform][device_type]['passed'] += data_item[device_type]['passed']
                    platform_data[platform][device_type]['failed'] += data_item[device_type]['failed']
                    platform_data[platform][device_type]['error'] += data_item[device_type].get('error', 0)
                    # Estimate blocked/retest/skipped from overall data (proportionally)
                    total_platform_tests = (data_item[device_type]['passed'] + 
                                          data_item[device_type]['failed'] + 
                                          data_item[device_type].get('error', 0))
                    total_build_tests = (build['overall']['passed'] + 
                                       build['overall']['failed'] + 
                                       build['overall'].get('error', 0))
                    
                    if total_build_tests > 0 and total_platform_tests > 0:
                        ratio = total_platform_tests / total_build_tests
                        platform_data[platform][device_type]['blocked'] += int(build['overall']['blocked'] * ratio)
                        platform_data[platform][device_type]['retest'] += int(build['overall']['retest'] * ratio)
                        platform_data[platform][device_type]['skipped'] += int(build['overall']['skipped'] * ratio)
                    
                    for section, count in data_item[device_type]['sections'].items():
                        platform_data[platform][device_type]['sections'][section] += count
    
    # Create platform summary with all status percentages
    platform_summary = []
    for platform, data in platform_data.items():
        # Calculate percentages for single device
        single_total = (data['single']['passed'] + data['single']['failed'] + data['single']['error'] +
                       data['single']['blocked'] + data['single']['retest'] + data['single']['skipped'])
        if single_total > 0:
            single_pass_pct = round((data['single']['passed'] / single_total) * 100, 2)
            single_fail_pct = round((data['single']['failed'] / single_total) * 100, 2)
            single_error_pct = round((data['single']['error'] / single_total) * 100, 2)
            single_blocked_pct = round((data['single']['blocked'] / single_total) * 100, 2)
            single_skip_pct = round((data['single']['skipped'] / single_total) * 100, 2)
        else:
            single_pass_pct = single_fail_pct = single_error_pct = single_blocked_pct = single_skip_pct = 0
        
        # Calculate percentages for stack device
        stack_total = (data['stack']['passed'] + data['stack']['failed'] + data['stack']['error'] +
                      data['stack']['blocked'] + data['stack']['retest'] + data['stack']['skipped'])
        if stack_total > 0:
            stack_pass_pct = round((data['stack']['passed'] / stack_total) * 100, 2)
            stack_fail_pct = round((data['stack']['failed'] / stack_total) * 100, 2)
            stack_error_pct = round((data['stack']['error'] / stack_total) * 100, 2)
            stack_blocked_pct = round((data['stack']['blocked'] / stack_total) * 100, 2)
            stack_skip_pct = round((data['stack']['skipped'] / stack_total) * 100, 2)
        else:
            stack_pass_pct = stack_fail_pct = stack_error_pct = stack_blocked_pct = stack_skip_pct = 0
        
        # Get top failing sections
        single_top_sections = sorted(data['single']['sections'].items(), key=lambda x: x[1], reverse=True)[:3]
        stack_top_sections = sorted(data['stack']['sections'].items(), key=lambda x: x[1], reverse=True)[:3]
        
        platform_summary.append({
            'Platform': platform,
            'Single Pass %': single_pass_pct,
            'Single Fail %': single_fail_pct,
            'Single Error %': single_error_pct,
            'Single Blocked %': single_blocked_pct,
            'Single Skip %': single_skip_pct,
            'Single Total': single_total,
            'Stack Pass %': stack_pass_pct,
            'Stack Fail %': stack_fail_pct,
            'Stack Error %': stack_error_pct,
            'Stack Blocked %': stack_blocked_pct,
            'Stack Skip %': stack_skip_pct,
            'Stack Total': stack_total,
            'Builds': len(data['builds']),
            'Top Failing Sections (Single)': ', '.join([f"{s[0]} ({s[1]})" for s in single_top_sections]) if single_top_sections else 'N/A',
            'Top Failing Sections (Stack)': ', '.join([f"{s[0]} ({s[1]})" for s in stack_top_sections]) if stack_top_sections else 'N/A'
        })
    
    if view_mode == 'Table':
        # Create a more detailed table view
        if platform_summary:
            df = pd.DataFrame(platform_summary)
            
            # Show build info if filtering by specific build
            if selected_pa_build != 'All Builds':
                st.info(f"Showing platform data for build: {selected_pa_build}")
            else:
                st.info(f"Showing aggregated data across {len(pa_filtered_builds)} builds")
            
            # Display the dataframe with custom formatting
            st.dataframe(
                df[[
                    'Platform',
                    'Single Pass %', 'Single Fail %', 'Single Error %', 'Single Blocked %', 'Single Skip %', 'Single Total',
                    'Stack Pass %', 'Stack Fail %', 'Stack Error %', 'Stack Blocked %', 'Stack Skip %', 'Stack Total',
                    'Top Failing Sections (Single)', 'Top Failing Sections (Stack)'
                ]],
                use_container_width=True
            )
        else:
            st.warning("No platform data found for the selected filters.")
    else:
        # Create grouped bar chart
        if platform_summary:
            df_platform = pd.DataFrame(platform_summary)
            
            # Create subplots for single and stack
            from plotly.subplots import make_subplots
            
            fig = make_subplots(
                rows=2, cols=1,
                subplot_titles=('Single Device Status Distribution', 'Stack Device Status Distribution'),
                vertical_spacing=0.15
            )
            
            # Single device bars
            fig.add_trace(go.Bar(
                name='Pass %',
                x=df_platform['Platform'],
                y=df_platform['Single Pass %'],
                marker_color='green',
                showlegend=True,
                legendgroup='pass'
            ), row=1, col=1)
            
            fig.add_trace(go.Bar(
                name='Fail %',
                x=df_platform['Platform'],
                y=df_platform['Single Fail %'],
                marker_color='red',
                showlegend=True,
                legendgroup='fail'
            ), row=1, col=1)
            
            fig.add_trace(go.Bar(
                name='Error %',
                x=df_platform['Platform'],
                y=df_platform['Single Error %'],
                marker_color='orange',
                showlegend=True,
                legendgroup='error'
            ), row=1, col=1)
            
            fig.add_trace(go.Bar(
                name='Blocked %',
                x=df_platform['Platform'],
                y=df_platform['Single Blocked %'],
                marker_color='purple',
                showlegend=True,
                legendgroup='blocked'
            ), row=1, col=1)
            
            fig.add_trace(go.Bar(
                name='Skip %',
                x=df_platform['Platform'],
                y=df_platform['Single Skip %'],
                marker_color='blue',
                showlegend=True,
                legendgroup='skip'
            ), row=1, col=1)
            
            # Stack device bars
            fig.add_trace(go.Bar(
                name='Pass %',
                x=df_platform['Platform'],
                y=df_platform['Stack Pass %'],
                marker_color='green',
                showlegend=False,
                legendgroup='pass'
            ), row=2, col=1)
            
            fig.add_trace(go.Bar(
                name='Fail %',
                x=df_platform['Platform'],
                y=df_platform['Stack Fail %'],
                marker_color='red',
                showlegend=False,
                legendgroup='fail'
            ), row=2, col=1)
            
            fig.add_trace(go.Bar(
                name='Error %',
                x=df_platform['Platform'],
                y=df_platform['Stack Error %'],
                marker_color='orange',
                showlegend=False,
                legendgroup='error'
            ), row=2, col=1)
            
            fig.add_trace(go.Bar(
                name='Blocked %',
                x=df_platform['Platform'],
                y=df_platform['Stack Blocked %'],
                marker_color='purple',
                showlegend=False,
                legendgroup='blocked'
            ), row=2, col=1)
            
            fig.add_trace(go.Bar(
                name='Skip %',
                x=df_platform['Platform'],
                y=df_platform['Stack Skip %'],
                marker_color='blue',
                showlegend=False,
                legendgroup='skip'
            ), row=2, col=1)
            
            # Update layout
            title = f'Platform Status Distribution'
            if selected_pa_build != 'All Builds':
                title += f' for {selected_pa_build}'
            
            fig.update_layout(
                title=title,
                barmode='group',
                height=800,
                showlegend=True,
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                )
            )
            
            fig.update_xaxes(title_text="Platform", row=2, col=1)
            fig.update_yaxes(title_text="Percentage", row=1, col=1)
            fig.update_yaxes(title_text="Percentage", row=2, col=1)
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No platform data found for the selected filters.")
    
    # Detailed Section Analysis
    st.header("📑 Top Failing Sections Analysis")
    
    if 'fetch_sections' in data and not data['fetch_sections']:
        st.info("Section analysis was disabled for faster processing. Enable 'Fetch detailed section information' when fetching data to see which test sections are failing.")
    
    # Aggregate all failing sections
    all_sections = defaultdict(int)
    for build in filtered_builds:
        for platform, data_item in build['platforms'].items():
            if selected_platform == 'all' or platform == selected_platform:
                for device_type in ['single', 'stack']:
                    for section, count in data_item[device_type]['sections'].items():
                        all_sections[section] += count
    
    # Get top 10 failing sections
    top_sections = sorted(all_sections.items(), key=lambda x: x[1], reverse=True)[:10]
    
    if top_sections:
        if view_mode == 'Table':
            section_df = pd.DataFrame(top_sections, columns=['Section', 'Failure Count'])
            st.dataframe(section_df, use_container_width=True)
        else:
            # Create horizontal bar chart
            fig = px.bar(
                x=[s[1] for s in top_sections],
                y=[s[0] for s in top_sections],
                orientation='h',
                labels={'x': 'Failure Count', 'y': 'Section'},
                title='Top 10 Failing Sections'
            )
            fig.update_traces(marker_color='indianred')
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No failing sections found in the selected data.")
    
    # Build Comparison
    if len(filtered_builds) > 1:
        st.header("🔄 Build Comparison")
        
        # Create comparison data with percentages
        comparison_data = []
        for build in filtered_builds:
            total_passed = build['overall']['passed']
            total_failed = build['overall']['failed']
            total_error = build['overall'].get('error', 0)
            total_blocked = build['overall']['blocked']
            total_retest = build['overall']['retest']
            total_skipped = build['overall']['skipped']
            total = total_passed + total_failed + total_error + total_blocked + total_retest + total_skipped
            
            if total > 0:
                comparison_data.append({
                    'Build': build['name'],  # Full build name
                    'Pass %': round((total_passed / total * 100), 2),
                    'Fail %': round((total_failed / total * 100), 2),
                    'Error %': round((total_error / total * 100), 2),
                    'Blocked %': round((total_blocked / total * 100), 2),
                    'Skip %': round((total_skipped / total * 100), 2),
                    'Total Tests': total
                })
        
        # Create stacked bar chart with percentages
        df_comp = pd.DataFrame(comparison_data)
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            name='Pass %',
            x=df_comp['Build'],
            y=df_comp['Pass %'],
            marker_color='green',
            text=df_comp['Pass %'],
            textposition='inside'
        ))
        fig.add_trace(go.Bar(
            name='Fail %',
            x=df_comp['Build'],
            y=df_comp['Fail %'],
            marker_color='red',
            text=df_comp['Fail %'],
            textposition='inside'
        ))
        fig.add_trace(go.Bar(
            name='Error %',
            x=df_comp['Build'],
            y=df_comp['Error %'],
            marker_color='orange',
            text=df_comp['Error %'],
            textposition='inside'
        ))
        fig.add_trace(go.Bar(
            name='Blocked %',
            x=df_comp['Build'],
            y=df_comp['Blocked %'],
            marker_color='purple',
            text=df_comp['Blocked %'],
            textposition='inside'
        ))
        fig.add_trace(go.Bar(
            name='Skip %',
            x=df_comp['Build'],
            y=df_comp['Skip %'],
            marker_color='blue',
            text=df_comp['Skip %'],
            textposition='inside'
        ))
        
        fig.update_layout(
            title='Test Results Percentage by Build',
            xaxis_title='Build',
            yaxis_title='Percentage',
            barmode='stack',
            xaxis=dict(
                tickangle=-45,  # Angle the x-axis labels
                automargin=True
            ),
            height=700,  # Taller chart
            margin=dict(b=200),  # Extra bottom margin
            yaxis=dict(range=[0, 100])  # Set y-axis to 0-100%
        )
        st.plotly_chart(fig, use_container_width=True)

else:
    st.info("👈 Please enter your TestRail credentials in the sidebar and click 'Fetch Data' to start.")
    
    st.markdown("""
    ### How to use this dashboard:
    1. Enter your TestRail URL (e.g., https://yourcompany.testrail.io)
    2. Enter your username (email) and API key
    3. Select a release milestone from the dropdown
    4. Click 'Fetch Data' to load the test results
    
    **Available Milestones:**
    - CS-1
    - switch-17
    - switch-18
    - Nightly
    - Aurora2
    - Trunk
    
    The dashboard will show:
    - Overall pass/fail/error/skip percentages for each build
    - Platform-specific analysis (single vs stack devices)
    - Most failing test sections
    - Trends and comparisons across builds
    """)
