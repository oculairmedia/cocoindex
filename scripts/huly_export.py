#!/usr/bin/env python3
"""
Huly to JSON export script for CocoIndex ingestion.

Reads Huly project data via REST API and writes JSON files for processing.
Required env vars:
  HULY_API_URL (default: http://192.168.50.90:3457/api)
Optional env:
  HULY_EXPORT_DIR (default: ./huly_export_full)
  EXPORT_LIMIT (default: no limit)

This script does not run automatically. Execute manually when ready, e.g.:
  python scripts/huly_export.py --limit 100
"""

import os
import sys
import json
import time
import argparse
import requests
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime


def getenv_or_default(name: str, default: str) -> str:
    """Get environment variable or return default."""
    return os.getenv(name, default)


def create_api_session(base_url: Optional[str] = None) -> requests.Session:
    """Create HTTP session for Huly REST API calls."""
    base_url = base_url or getenv_or_default("HULY_API_URL", "http://192.168.50.90:3457/api")

    if not base_url:
        raise ValueError("Huly API base URL is not configured. Set HULY_API_URL or pass --url.")

    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "cocoindex-huly-export/1.0"
    })

    # Store base URL for convenience
    session.base_url = base_url.rstrip('/')
    return session


def call_huly_tool(session: requests.Session, tool_name: str, **kwargs) -> Dict[str, Any]:
    """Call a Huly tool via REST API."""
    url = f"{session.base_url}/tools/{tool_name}"

    if kwargs:
        # Use POST for tools with parameters
        data = {"arguments": kwargs}
        response = session.post(url, json=data)
    else:
        # Use GET for simple tools
        response = session.get(url)

    response.raise_for_status()
    result = response.json()

    if not result.get('success', False):
        error_msg = result.get('error', {}).get('message', 'Unknown error')
        raise Exception(f"Huly API error: {error_msg}")

    return result['data']['result']


def export_projects(session: requests.Session, out_dir: Path) -> List[Dict[str, Any]]:
    """Export all projects from Huly."""
    print("📁 Exporting projects...")

    try:
        result = call_huly_tool(session, "huly_list_projects")

        # Parse the text response to extract projects
        content_text = result['content'][0]['text']
        projects = parse_projects_from_text(content_text)

        # Save each project as a separate JSON file
        for project in projects:
            filename = f"project_{project['identifier']}.json"
            filepath = out_dir / filename

            project_data = {
                "type": "project",
                "id": project['identifier'],
                "name": project['name'],
                "description": project['description'],
                "issues_count": project.get('issues', 0),
                "status": project.get('status', 'active'),
                "created_at": datetime.utcnow().isoformat(),
                "exported_at": datetime.utcnow().isoformat(),
                "raw_data": project
            }

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(project_data, f, indent=2, ensure_ascii=False)

        print(f"✅ Exported {len(projects)} projects")
        return projects

    except Exception as e:
        print(f"❌ Error exporting projects: {e}")
        return []


def export_project_issues(session: requests.Session, project_id: str, out_dir: Path, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Export issues for a specific project."""
    print(f"📋 Exporting issues for project {project_id}...")

    try:
        kwargs = {"project_identifier": project_id}
        if limit:
            kwargs["limit"] = limit

        result = call_huly_tool(session, "huly_list_issues", **kwargs)

        # Parse the text response to extract issues
        content_text = result['content'][0]['text']
        issues = parse_issues_from_text(content_text, project_id)

        # Save each issue as a separate JSON file
        for issue in issues:
            filename = f"issue_{issue['identifier']}.json"
            filepath = out_dir / filename

            issue_data = {
                "type": "issue",
                "id": issue['identifier'],
                "project_id": project_id,
                "title": issue['title'],
                "description": issue.get('description', ''),
                "status": issue.get('status', 'unknown'),
                "priority": issue.get('priority', 'medium'),
                "component": issue.get('component'),
                "milestone": issue.get('milestone'),
                "created_at": datetime.utcnow().isoformat(),
                "exported_at": datetime.utcnow().isoformat(),
                "raw_data": issue
            }

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(issue_data, f, indent=2, ensure_ascii=False)

        print(f"✅ Exported {len(issues)} issues for {project_id}")
        return issues

    except Exception as e:
        print(f"❌ Error exporting issues for {project_id}: {e}")
        return []


def export_project_components(session: requests.Session, project_id: str, out_dir: Path) -> List[Dict[str, Any]]:
    """Export components for a specific project."""
    print(f"🔧 Exporting components for project {project_id}...")

    try:
        result = call_huly_tool(session, "huly_list_components", project_identifier=project_id)

        # Parse the text response to extract components
        content_text = result['content'][0]['text']
        components = parse_components_from_text(content_text, project_id)

        # Save each component as a separate JSON file
        for component in components:
            filename = f"component_{project_id}_{component['label']}.json"
            filepath = out_dir / filename

            component_data = {
                "type": "component",
                "id": f"{project_id}-{component['label']}",
                "project_id": project_id,
                "label": component['label'],
                "description": component.get('description', ''),
                "created_at": datetime.utcnow().isoformat(),
                "exported_at": datetime.utcnow().isoformat(),
                "raw_data": component
            }

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(component_data, f, indent=2, ensure_ascii=False)

        print(f"✅ Exported {len(components)} components for {project_id}")
        return components

    except Exception as e:
        print(f"❌ Error exporting components for {project_id}: {e}")
        return []


def export_project_milestones(session: requests.Session, project_id: str, out_dir: Path) -> List[Dict[str, Any]]:
    """Export milestones for a specific project."""
    print(f"🎯 Exporting milestones for project {project_id}...")

    try:
        result = call_huly_tool(session, "huly_list_milestones", project_identifier=project_id)

        # Parse the text response to extract milestones
        content_text = result['content'][0]['text']
        milestones = parse_milestones_from_text(content_text, project_id)

        # Save each milestone as a separate JSON file
        for milestone in milestones:
            filename = f"milestone_{project_id}_{milestone['label']}.json"
            filepath = out_dir / filename

            milestone_data = {
                "type": "milestone",
                "id": f"{project_id}-{milestone['label']}",
                "project_id": project_id,
                "label": milestone['label'],
                "description": milestone.get('description', ''),
                "target_date": milestone.get('target_date'),
                "status": milestone.get('status', 'planned'),
                "created_at": datetime.utcnow().isoformat(),
                "exported_at": datetime.utcnow().isoformat(),
                "raw_data": milestone
            }

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(milestone_data, f, indent=2, ensure_ascii=False)

        print(f"✅ Exported {len(milestones)} milestones for {project_id}")
        return milestones

    except Exception as e:
        print(f"❌ Error exporting milestones for {project_id}: {e}")
        return []


def parse_projects_from_text(text: str) -> List[Dict[str, Any]]:
    """Parse project information from Huly API text response."""
    projects = []
    lines = text.split('\n')

    current_project = None
    for line in lines:
        line = line.strip()

        # Project header: 📁 Project Name (CODE)
        if line.startswith('📁 ') and '(' in line and line.endswith(')'):
            if current_project:
                projects.append(current_project)

            # Extract name and identifier
            parts = line[2:].rsplit('(', 1)
            name = parts[0].strip()
            identifier = parts[1].rstrip(')').strip()

            current_project = {
                "name": name,
                "identifier": identifier,
                "description": "",
                "issues": 0,
                "status": "active"
            }

        # Description line
        elif line.startswith('Description: ') and current_project:
            current_project["description"] = line[13:].strip()

        # Issues count
        elif line.startswith('Issues: ') and current_project:
            try:
                current_project["issues"] = int(line[8:].split()[0])
            except:
                current_project["issues"] = 0

        # Status
        elif line.startswith('Status: ') and current_project:
            current_project["status"] = line[8:].strip().lower()

    # Add the last project
    if current_project:
        projects.append(current_project)

    return projects


def parse_issues_from_text(text: str, project_id: str) -> List[Dict[str, Any]]:
    """Parse issue information from Huly API text response."""
    issues = []
    lines = text.split('\n')

    current_issue = None
    for line in lines:
        line = line.strip()

        # Issue header: 📋 **PROJ-123**: Issue Title
        if line.startswith('📋 **') and '**:' in line:
            if current_issue:
                issues.append(current_issue)

            # Extract identifier and title
            parts = line.split('**:', 1)
            identifier = parts[0][5:].strip()  # Remove "📋 **"
            title = parts[1].strip() if len(parts) > 1 else ""

            current_issue = {
                "identifier": identifier,
                "title": title,
                "description": "",
                "status": "unknown",
                "priority": "medium",
                "component": None,
                "milestone": None
            }

        # Status line
        elif line.startswith('Status: ') and current_issue:
            current_issue["status"] = line[8:].strip().lower()

        # Priority line
        elif line.startswith('Priority: ') and current_issue:
            current_issue["priority"] = line[10:].strip().lower()

        # Description line
        elif line.startswith('Description: ') and current_issue:
            current_issue["description"] = line[13:].strip()

    # Add the last issue
    if current_issue:
        issues.append(current_issue)

    return issues


def parse_components_from_text(text: str, project_id: str) -> List[Dict[str, Any]]:
    """Parse component information from Huly API text response."""
    components = []
    lines = text.split('\n')

    for line in lines:
        line = line.strip()

        # Component line format may vary, adapt as needed
        if line and not line.startswith('📁') and not line.startswith('Found'):
            components.append({
                "label": line,
                "description": f"Component in {project_id}"
            })

    return components


def parse_milestones_from_text(text: str, project_id: str) -> List[Dict[str, Any]]:
    """Parse milestone information from Huly API text response."""
    milestones = []
    lines = text.split('\n')

    for line in lines:
        line = line.strip()

        # Milestone line format may vary, adapt as needed
        if line and not line.startswith('📁') and not line.startswith('Found'):
            milestones.append({
                "label": line,
                "description": f"Milestone in {project_id}",
                "status": "planned"
            })

    return milestones


def main():
    """Main export function."""
    parser = argparse.ArgumentParser(description="Export Huly data to JSON files")
    parser.add_argument("--limit", type=int, help="Limit number of issues per project")
    parser.add_argument("--out", default=os.getenv("HULY_EXPORT_DIR", "huly_export_full"), help="Output directory")
    parser.add_argument("--projects-only", action="store_true", help="Export only projects")
    parser.add_argument("--url", help="Override Huly API base URL (defaults to HULY_API_URL env)")

    args = parser.parse_args()

    api_url = args.url or getenv_or_default("HULY_API_URL", "http://192.168.50.90:3457/api")
    if not api_url:
        print("❌ Huly API URL not provided. Set HULY_API_URL or pass --url.")
        sys.exit(1)

    # Create output directory
    out_dir = Path(args.out)
    out_dir.mkdir(exist_ok=True)

    print(f"🚀 Starting Huly export to {out_dir}")
    print(f"API URL: {api_url}")

    try:
        # Create API session
        session = create_api_session(api_url)

        # Test API connectivity
        health_response = session.get(f"{session.base_url}/health")
        if health_response.ok:
            print("✅ Huly API connection successful")
        else:
            print("⚠️ API health check returned non-200 status")

        # Export projects
        projects = export_projects(session, out_dir)

        if not args.projects_only and projects:
            # Export data for each project
            for project in projects:
                project_id = project['identifier']
                print(f"\n🔄 Processing project {project_id}...")

                # Export issues
                export_project_issues(session, project_id, out_dir, args.limit)

                # Export components
                export_project_components(session, project_id, out_dir)

                # Export milestones
                export_project_milestones(session, project_id, out_dir)

                # Add small delay to be respectful to the API
                time.sleep(0.5)

        print(f"\n✅ Export completed successfully!")
        print(f"📁 Files written to: {out_dir.absolute()}")

    except Exception as e:
        print(f"❌ Export failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()