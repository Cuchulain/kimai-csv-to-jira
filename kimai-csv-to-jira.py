import csv
import re
import os
import requests
import argparse
import json
import pytz
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
from datetime import datetime

def process_csv(file_path, column_names, task_regex):
    records = []
    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            # Extract the task ID from the description using the provided regex
            description = row[column_names['description']]
            match = re.match(task_regex, description)
            if match:
                task_id = match.group(1)
                task_description = match.group(3)

                # Doba trvání je již v sekundách
                time_spent_seconds = int(row[column_names['duration']])

                # Datum a čas začátku úkolu kombinovaný ze sloupců 'Datum' a 'Od'
                date = row[column_names['date']]
                time = row[column_names['time']]

                # Kombinování Datum a Od do jednoho datetime stringu
                start_time = f"{date} {time}"

                # Create a record for JIRA API
                record = {
                    'task_id': task_id,
                    'task_description': task_description,
                    'time_spent_seconds': time_spent_seconds,
                    'start_time': start_time
                }
                records.append(record)

    return records

def add_worklog_to_jira(task_id, task_description, time_spent_seconds, start_time, jira_url, jira_username, jira_token, timezone_str, dry_run, visibility=None):
    url = f"{jira_url}/rest/api/3/issue/{task_id}/worklog"
    auth = HTTPBasicAuth(jira_username, jira_token)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    # Convert the start time to the format required by Jira and apply the timezone
    local_tz = pytz.timezone(timezone_str)
    start_time_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M")
    start_time_aware = local_tz.localize(start_time_dt)
    start_time_formatted = start_time_aware.strftime("%Y-%m-%dT%H:%M:%S.000%z")

    payload = {
        "comment": {
            "content": [
                {
                    "content": [
                        {
                            "text": task_description,
                            "type": "text"
                        }
                    ],
                    "type": "paragraph"
                }
            ],
            "type": "doc",
            "version": 1
        },
        "started": start_time_formatted,
        "timeSpentSeconds": time_spent_seconds
    }

    if visibility:
        payload["visibility"] = {
            "type": "group",
            "identifier": visibility
        }

    if dry_run:
        print(f"[DRY RUN] Would add worklog to {task_id} with {time_spent_seconds} seconds on {start_time_formatted} with description '{task_description}'")
        return

    response = requests.post(url, data=json.dumps(payload), headers=headers, auth=auth)

    if response.status_code == 201:
        print(f"Worklog added to {task_id}")
    elif response.status_code == 400:
        print(f"Failed to add worklog to {task_id}: Bad Request (400) - {response.json().get('message', 'No additional information provided')}")
    elif response.status_code == 401:
        print(f"Failed to add worklog to {task_id}: Unauthorized (401) - Check your authentication credentials.")
    elif response.status_code == 404:
        print(f"Failed to add worklog to {task_id}: Not Found (404) - Issue not found or insufficient permissions.")
    elif response.status_code == 413:
        print(f"Failed to add worklog to {task_id}: Request Entity Too Large (413) - Worklog limit exceeded.")
    else:
        print(f"Failed to add worklog to {task_id}: {response.status_code} - {response.text}")

def main():
    # Argument parser setup
    parser = argparse.ArgumentParser(description="Process CSV file and add worklogs to JIRA.")
    parser.add_argument('file_path', type=str, help="Path to the CSV file")
    parser.add_argument('--dry-run', action='store_true', help="If set, no changes will be made to JIRA, only outputs the actions.")
    parser.add_argument('--visibility', type=str, help="Optional visibility identifier for the worklog.")
    args = parser.parse_args()

    # Load environment variables from .env file if it exists
    load_dotenv()

    # Load Jira credentials and timezone from environment variables
    jira_url = os.getenv('JIRA_URL')
    jira_username = os.getenv('JIRA_USERNAME')
    jira_token = os.getenv('JIRA_API_TOKEN')
    timezone_str = os.getenv('TIMEZONE', 'GMT')

    # Load column names from environment variables
    column_names = {
        'description': os.getenv('COLUMN_DESCRIPTION', 'Popis'),
        'duration': os.getenv('COLUMN_DURATION', 'Doba trvání'),
        'date': os.getenv('COLUMN_DATE', 'Datum'),
        'time': os.getenv('COLUMN_TIME', 'Od')
    }

    # Load regex for task ID and description parsing from environment variables
    task_regex = os.getenv('TASK_REGEX', r'([A-Z]+-\d+)(:?\s+)(.*)')

    if not jira_url or not jira_username or not jira_token:
        print("Missing JIRA credentials. Please set them in environment variables or .env file.")
        return

    # Process the CSV file
    records = process_csv(args.file_path, column_names, task_regex)

    # Iterate over the records and add worklogs
    for record in records:
        add_worklog_to_jira(
            task_id=record['task_id'],
            task_description=record['task_description'],
            time_spent_seconds=record['time_spent_seconds'],
            start_time=record['start_time'],
            jira_url=jira_url,
            jira_username=jira_username,
            jira_token=jira_token,
            timezone_str=timezone_str,
            dry_run=args.dry_run,
            visibility=args.visibility
        )

if __name__ == "__main__":
    main()
