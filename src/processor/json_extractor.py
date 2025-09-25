"""
JSON extractor for parsing iXBRL viewer data from HTML.
"""

import json
import re
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List


logger = logging.getLogger(__name__)


class ViewerDataExtractor:
    """Extracts JSON data from iXBRL viewer HTML files."""

    def __init__(self):
        pass

    def extract_viewer_data(
        self,
        viewer_html_path: str,
        meta_links_candidates: Optional[List[Path]] = None
    ) -> Dict[str, Any]:
        """
        Extract viewer JSON data from HTML file.

        Args:
            viewer_html_path: Path to the iXBRL viewer HTML file

        Returns:
            Dictionary containing parsed viewer data

        Raises:
            ValueError: If JSON data cannot be found or parsed
        """
        html_file = Path(viewer_html_path)

        if not html_file.exists():
            raise FileNotFoundError(f"Viewer HTML file not found: {viewer_html_path}")

        try:
            # Read HTML content
            with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
                html_content = f.read()

            # Extract JSON data from script tags
            json_data = self._find_viewer_json(html_content)

            if not json_data:
                raise ValueError("No viewer JSON data found in HTML file")

            # Attempt to load supplemental metadata (MetaLinks)
            meta_links = self._load_meta_links(
                html_file,
                extra_candidates=meta_links_candidates or []
            )
            if meta_links:
                json_data['meta_links'] = meta_links

                role_map = self._build_role_map(meta_links, html_file.name)
                if role_map:
                    json_data['role_map'] = role_map

            logger.info("Successfully extracted viewer JSON data")
            return json_data

        except Exception as e:
            logger.error(f"Error extracting viewer data from {viewer_html_path}: {e}")
            raise

    def _find_viewer_json(self, html_content: str) -> Optional[Dict[str, Any]]:
        """
        Find and parse viewer JSON from HTML content.

        Args:
            html_content: HTML content string

        Returns:
            Parsed JSON data or None if not found
        """
        # Look for common patterns used by iXBRL viewer
        patterns = [
            # Pattern 1: var viewer_data = {...}
            r'var\s+viewer_data\s*=\s*(\{.*?\});',
            # Pattern 2: window.viewer = {...}
            r'window\.viewer\s*=\s*(\{.*?\});',
            # Pattern 3: iXBRLViewer.load({...})
            r'iXBRLViewer\.load\s*\(\s*(\{.*?\})\s*\)',
            # Pattern 4: Any large JSON object in script tags with facts
            r'<script[^>]*>\s*.*?(\{.*?"facts".*?\})\s*.*?</script>',
            # Pattern 5: Large standalone JSON object with sourceReports (newer Arelle format)
            r'(\{\s*"sourceReports".*?\})',
            # Pattern 6: Large standalone JSON object with concepts
            r'(\{\s*"concepts".*?\})',
        ]

        for pattern in patterns:
            matches = re.finditer(pattern, html_content, re.DOTALL | re.IGNORECASE)

            for match in matches:
                json_str = match.group(1)
                try:
                    # Clean up the JSON string
                    json_str = self._clean_json_string(json_str)

                    # Parse JSON
                    data = json.loads(json_str)

                    # Validate that this looks like viewer data
                    if self._validate_viewer_data(data):
                        logger.debug(f"Found viewer data using pattern: {pattern[:50]}...")
                        return data

                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    logger.debug(f"Error parsing potential JSON: {e}")
                    continue

        # If no patterns worked, try a more aggressive approach
        return self._extract_json_aggressive(html_content)

    def _load_meta_links(
        self,
        html_file: Path,
        extra_candidates: List[Path]
    ) -> Optional[Dict[str, Any]]:
        """Load MetaLinks.json located near the viewer HTML or provided candidates."""
        candidates = [html_file.with_name('MetaLinks.json')]

        # Some viewers are generated into temp folders. Try parent directory as fallback.
        if html_file.parent != html_file.parent.parent:
            candidates.append(html_file.parent.parent / 'MetaLinks.json')

        candidates.extend(extra_candidates)

        for candidate in candidates:
            if not candidate or not candidate.exists():
                continue

            try:
                with candidate.open('r', encoding='utf-8') as fp:
                    logger.debug("Loaded MetaLinks from %s", candidate)
                    return json.load(fp)
            except Exception as exc:
                logger.warning("Failed to parse MetaLinks.json at %s: %s", candidate, exc)

        return None

    def _build_role_map(self, meta_links: Dict[str, Any], instance_name: str) -> Optional[Dict[str, Dict[str, Dict[str, Any]]]]:
        """Build role metadata map keyed by URI and long name for easy lookup.

        Args:
            meta_links: Parsed MetaLinks JSON data
            instance_name: File name of the viewer HTML (used to locate report block)

        Returns:
            Mapping from role URI to role metadata or None if unavailable
        """
        instance_data = meta_links.get('instance') or {}

        # Prefer an entry matching the viewer HTML name; fall back to first
        report_block = instance_data.get(instance_name)
        if not report_block:
            if instance_data:
                report_block = next(iter(instance_data.values()))
            else:
                return None

        reports = report_block.get('report')
        if not isinstance(reports, dict):
            return None

        by_uri: Dict[str, Dict[str, Any]] = {}
        by_long_name: Dict[str, Dict[str, Any]] = {}
        by_normalized_name: Dict[str, Dict[str, Any]] = {}
        for role_id, payload in reports.items():
            role_uri = payload.get('role')
            if not role_uri:
                continue

            try:
                order = payload.get('order')
                order_value = float(order) if order is not None else None
            except (TypeError, ValueError):
                order_value = None

            normalized = {
                'r_id': role_id,
                'groupType': payload.get('groupType'),
                'subGroupType': payload.get('subGroupType'),
                'longName': payload.get('longName'),
                'shortName': payload.get('shortName'),
                'order': order_value,
                'isDefault': payload.get('isDefault'),
            }
            by_uri[role_uri] = normalized
            long_name = payload.get('longName')
            if isinstance(long_name, str):
                lower_name = long_name.lower()
                by_long_name[lower_name] = normalized
                if ' - ' in lower_name:
                    _, _, tail = lower_name.partition(' - ')
                    by_normalized_name[tail] = normalized

        if not (by_uri or by_long_name or by_normalized_name):
            return None

        return {
            'by_uri': by_uri,
            'by_long_name': by_long_name,
            'by_normalized_name': by_normalized_name
        }

    def _clean_json_string(self, json_str: str) -> str:
        """
        Clean up JSON string for parsing.

        Args:
            json_str: Raw JSON string

        Returns:
            Cleaned JSON string
        """
        # Remove trailing semicolon
        json_str = json_str.rstrip(';')

        # Remove any trailing JavaScript code
        json_str = re.sub(r'\s*[;}]\s*$', '', json_str)

        # Handle common JavaScript to JSON issues
        # Replace single quotes with double quotes (but be careful of escaped quotes)
        # This is a simplified approach - more complex cases might need a proper parser
        json_str = re.sub(r"'([^'\\]*(\\.[^'\\]*)*)'", r'"\1"', json_str)

        return json_str

    def _validate_viewer_data(self, data: Dict[str, Any]) -> bool:
        """
        Validate that the data looks like iXBRL viewer data.

        Args:
            data: Parsed JSON data

        Returns:
            True if this looks like viewer data
        """
        # Check for common iXBRL viewer data structures
        required_keys = ['facts', 'concepts', 'sourceReports']

        # Must have at least some required keys
        if not any(key in data for key in required_keys):
            return False

        # Check for newer Arelle format with sourceReports
        if 'sourceReports' in data:
            if isinstance(data['sourceReports'], list) and len(data['sourceReports']) > 0:
                # Check if first source report has the expected structure
                first_report = data['sourceReports'][0]
                if isinstance(first_report, dict) and 'targetReports' in first_report:
                    return True

        # Check for older format
        if 'facts' in data and isinstance(data['facts'], dict):
            return True

        if 'concepts' in data and isinstance(data['concepts'], dict):
            return True

        return False

    def _extract_json_aggressive(self, html_content: str) -> Optional[Dict[str, Any]]:
        """
        More aggressive JSON extraction as a fallback.

        Args:
            html_content: HTML content string

        Returns:
            Parsed JSON data or None if not found
        """
        try:
            # Find all positions where large JSON objects might start
            json_start_indicators = [
                '{\n "sourceReports"',
                '{"sourceReports"',
                '{\n "concepts"',
                '{"concepts"',
                '{\n "facts"',
                '{"facts"'
            ]

            for indicator in json_start_indicators:
                pos = html_content.find(indicator)
                if pos != -1:
                    logger.debug(f"Found JSON indicator '{indicator}' at position {pos}")

                    # Extract complete JSON object from this position
                    json_str = self._extract_complete_json(html_content, pos)

                    if json_str:
                        try:
                            data = json.loads(json_str)
                            if self._validate_viewer_data(data):
                                logger.debug("Successfully parsed JSON from aggressive extraction")
                                return data
                        except json.JSONDecodeError as e:
                            logger.debug(f"JSON parsing failed for indicator '{indicator}': {e}")
                            continue

            # If indicators don't work, try script-based approach
            script_pattern = r'<script[^>]*>(.*?)</script>'
            scripts = re.findall(script_pattern, html_content, re.DOTALL | re.IGNORECASE)

            for script_content in scripts:
                # Look for any large JSON object starting with {
                brace_positions = [m.start() for m in re.finditer(r'\{', script_content)]

                # Try the largest potential JSON objects first
                for pos in sorted(brace_positions, key=lambda p: len(script_content) - p, reverse=True)[:5]:
                    try:
                        json_str = self._extract_complete_json(script_content, pos)

                        if json_str and len(json_str) > 10000:  # Only try large objects
                            data = json.loads(json_str)
                            if self._validate_viewer_data(data):
                                return data

                    except:
                        continue

        except Exception as e:
            logger.debug(f"Aggressive JSON extraction failed: {e}")

        return None

    def _extract_complete_json(self, text: str, start_pos: int) -> Optional[str]:
        """
        Extract complete JSON object starting from a position.

        Args:
            text: Text content
            start_pos: Starting position of JSON object

        Returns:
            Complete JSON string or None
        """
        if text[start_pos] != '{':
            return None

        brace_count = 0
        in_string = False
        escape_next = False

        for i, char in enumerate(text[start_pos:], start_pos):
            if escape_next:
                escape_next = False
                continue

            if char == '\\' and in_string:
                escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                continue

            if not in_string:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1

                    if brace_count == 0:
                        return text[start_pos:i+1]

        return None
