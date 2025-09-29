"""
JSON extractor for parsing iXBRL viewer data from HTML.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from xml.etree import ElementTree as ET
from lxml import html


logger = logging.getLogger(__name__)


class ViewerDataExtractor:
    """Extracts JSON data from iXBRL viewer HTML files."""

    def __init__(self):
        pass

    def extract_viewer_data(
        self, viewer_html_path: str, meta_links_candidates: Optional[List[Path]] = None
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

        meta_links_path: Optional[Path] = None

        try:
            # Read HTML content
            with open(html_file, "r", encoding="utf-8", errors="ignore") as f:
                html_content = f.read()

            # Extract JSON data from script tags
            json_data = self._find_viewer_json(html_content)

            if not json_data:
                raise ValueError("No viewer JSON data found in HTML file")

            # Attempt to load supplemental metadata (MetaLinks)
            meta_links, meta_links_path = self._load_meta_links(
                html_file, extra_candidates=meta_links_candidates or []
            )
            if meta_links:
                json_data["meta_links"] = meta_links

                role_map = self._build_role_map(meta_links, html_file.name)
                if role_map:
                    json_data["role_map"] = role_map

                concept_labels = self._build_concept_label_map(
                    meta_links, html_file.name, html_file
                )
                if concept_labels:
                    json_data["concept_labels"] = concept_labels

            context_file_candidates: List[Path] = []
            if meta_links and meta_links_path:
                instance_data = meta_links.get("instance") or {}
                base_dir = meta_links_path.parent
                inline_names: Set[str] = set()
                for entry in instance_data.values():
                    inline_payload = (
                        entry.get("dts", {}).get("inline", {}).get("local") or []
                    )
                    for inline_name in inline_payload:
                        inline_names.add(inline_name)

                for inline_name in inline_names:
                    stem = Path(inline_name).stem
                    candidate = base_dir / f"{stem}_htm.xml"
                    if candidate.exists():
                        context_file_candidates.append(candidate)

                if not context_file_candidates:
                    context_file_candidates.extend(base_dir.glob("*_htm.xml"))

            visible_signatures = self._extract_visible_fact_signatures(
                html_content, html_file, context_file_candidates
            )
            if visible_signatures:
                json_data["visible_fact_signatures"] = visible_signatures

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
            r"var\s+viewer_data\s*=\s*(\{.*?\});",
            # Pattern 2: window.viewer = {...}
            r"window\.viewer\s*=\s*(\{.*?\});",
            # Pattern 3: iXBRLViewer.load({...})
            r"iXBRLViewer\.load\s*\(\s*(\{.*?\})\s*\)",
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
                        logger.debug(
                            f"Found viewer data using pattern: {pattern[:50]}..."
                        )
                        return data

                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    logger.debug(f"Error parsing potential JSON: {e}")
                    continue

        # If no patterns worked, try a more aggressive approach
        return self._extract_json_aggressive(html_content)

    def _load_meta_links(
        self, html_file: Path, extra_candidates: List[Path]
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Path]]:
        """Load MetaLinks.json located near the viewer HTML or provided candidates."""
        candidates = [html_file.with_name("MetaLinks.json")]

        # Some viewers are generated into temp folders. Try parent directory as fallback.
        if html_file.parent != html_file.parent.parent:
            candidates.append(html_file.parent.parent / "MetaLinks.json")

        candidates.extend(extra_candidates)

        for candidate in candidates:
            if not candidate or not candidate.exists():
                continue

            try:
                with candidate.open("r", encoding="utf-8") as fp:
                    logger.info("Using MetaLinks from %s", candidate)
                    return json.load(fp), candidate
            except Exception as exc:
                logger.warning(
                    "Failed to parse MetaLinks.json at %s: %s", candidate, exc
                )
        logger.info(
            "No MetaLinks companion found for %s; using viewer JSON alone",
            html_file.name,
        )
        return None, None

    def _build_role_map(
        self, meta_links: Dict[str, Any], instance_name: str
    ) -> Optional[Dict[str, Dict[str, Dict[str, Any]]]]:
        """Build role metadata map keyed by URI and long name for easy lookup.

        Args:
            meta_links: Parsed MetaLinks JSON data
            instance_name: File name of the viewer HTML (used to locate report block)

        Returns:
            Mapping from role URI to role metadata or None if unavailable
        """
        instance_data = meta_links.get("instance") or {}

        # Prefer an entry matching the viewer HTML name; fall back to first
        report_block = instance_data.get(instance_name)
        if not report_block:
            if instance_data:
                report_block = next(iter(instance_data.values()))
            else:
                return None

        reports = report_block.get("report")
        if not isinstance(reports, dict):
            return None

        by_uri: Dict[str, Dict[str, Any]] = {}
        by_long_name: Dict[str, Dict[str, Any]] = {}
        by_normalized_name: Dict[str, Dict[str, Any]] = {}
        for role_id, payload in reports.items():
            role_uri = payload.get("role")
            if not role_uri:
                continue

            try:
                order = payload.get("order")
                order_value = float(order) if order is not None else None
            except (TypeError, ValueError):
                order_value = None

            normalized = {
                "r_id": role_id,
                "groupType": payload.get("groupType"),
                "subGroupType": payload.get("subGroupType"),
                "longName": payload.get("longName"),
                "shortName": payload.get("shortName"),
                "order": order_value,
                "isDefault": payload.get("isDefault"),
            }
            by_uri[role_uri] = normalized
            long_name = payload.get("longName")
            if isinstance(long_name, str):
                lower_name = long_name.lower()
                by_long_name[lower_name] = normalized
                if " - " in lower_name:
                    _, _, tail = lower_name.partition(" - ")
                    by_normalized_name[tail] = normalized

        if not (by_uri or by_long_name or by_normalized_name):
            return None

        return {
            "by_uri": by_uri,
            "by_long_name": by_long_name,
            "by_normalized_name": by_normalized_name,
        }

    def _build_concept_label_map(
        self,
        meta_links: Dict[str, Any],
        instance_name: str,
        viewer_path: Path,
    ) -> Optional[Dict[str, Dict[str, str]]]:
        """Build concept label map keyed by concept QName."""
        instance_data = meta_links.get("instance") or {}
        instance_entry = instance_data.get(instance_name)
        if not instance_entry and instance_data:
            instance_entry = next(iter(instance_data.values()))

        if not instance_entry:
            return None

        tag_block = instance_entry.get("tag")
        concept_labels: Dict[str, Dict[str, str]] = {}

        if isinstance(tag_block, dict):
            for raw_name, payload in tag_block.items():
                if not isinstance(payload, dict):
                    continue

                concept_qname = raw_name.replace("_", ":", 1)
                lang_info = payload.get("lang") or {}
                role_entries: Dict[str, str] = {}

                for lang_data in lang_info.values():
                    roles = lang_data.get("role") or {}
                    for role_name, role_value in roles.items():
                        if isinstance(role_value, str) and role_value.strip():
                            role_entries.setdefault(role_name, role_value)

                if role_entries:
                    concept_labels[concept_qname] = role_entries

        # Fall back to the label linkbase when MetaLinks omits concept captions
        fallback_labels = self._load_label_linkbase_labels(
            viewer_path,
            instance_entry.get("dts", {}).get("labelLink", {}).get("local") or [],
        )

        for concept_qname, roles in fallback_labels.items():
            target = concept_labels.setdefault(concept_qname, {})
            for role, text in roles.items():
                target.setdefault(role, text)

        return concept_labels or None

    def _extract_visible_fact_signatures(
        self,
        html_content: str,
        html_file: Path,
        context_file_candidates: Optional[Iterable[Path]] = None,
    ) -> Optional[Dict[str, List[List[Any]]]]:
        """Scan the inline HTML for visible facts grouped by statement heading."""

        try:
            document = html.fromstring(html_content.encode("utf-8"))
        except Exception as exc:
            logger.debug("Failed to parse HTML for visible fact extraction: %s", exc)
            return None

        ns = {
            "ix": "http://www.xbrl.org/2013/inlineXBRL",
            "xbrli": "http://www.xbrl.org/2003/instance",
            "xbrldi": "http://xbrl.org/2006/xbrldi",
        }

        context_dims: Dict[str, Tuple[Tuple[str, str], ...]] = {}

        def ingest_contexts(context_elements: Iterable[ET.Element]) -> None:
            for ctx in context_elements:
                ctx_id = ctx.get("id")
                if not ctx_id:
                    continue

                dims: List[Tuple[str, str]] = []
                segment = ctx.find(
                    "{http://www.xbrl.org/2003/instance}entity/{http://www.xbrl.org/2003/instance}segment"
                )
                if segment is not None:
                    for member in segment.findall(
                        "{http://xbrl.org/2006/xbrldi}explicitMember"
                    ):
                        axis = member.get("dimension") or ""
                        member_value = (member.text or "").strip()
                        if not axis or not member_value:
                            continue
                        dims.append(
                            (self._local_name(axis), self._local_name(member_value))
                        )

                dims_tuple = tuple(
                    sorted((axis.lower(), member.lower()) for axis, member in dims)
                )
                context_dims[ctx_id] = dims_tuple

        context_sources: List[Path] = []
        default_context_file = html_file.with_name(f"{html_file.stem}_htm.xml")
        if default_context_file.exists():
            context_sources.append(default_context_file)

        for candidate in context_file_candidates or []:
            if candidate not in context_sources and candidate.exists():
                context_sources.append(candidate)

        for context_file in context_sources:
            try:
                context_tree = ET.parse(context_file)
                ingest_contexts(
                    context_tree.getroot().findall(
                        ".//{http://www.xbrl.org/2003/instance}context"
                    )
                )
            except Exception as exc:
                logger.debug(
                    "Failed to parse context metadata from %s: %s", context_file, exc
                )

        if not context_dims:
            inline_contexts = document.xpath(
                "//ix:header//xbrli:context", namespaces=ns
            )
            if inline_contexts:
                logger.debug(
                    "Using inline header contexts for %s (no sidecar XML found)",
                    html_file.name,
                )
                ingest_contexts(inline_contexts)

        visible: Dict[str, Set[Tuple[str, Tuple[Tuple[str, str], ...]]]] = {}
        processed_tables: Set[int] = set()

        def resolve_heading(
            node: ET.Element,
        ) -> Optional[Tuple[ET.Element, str]]:
            """Return the element whose text should be treated as the heading and its key."""

            raw_label = " ".join(node.itertext()).strip()
            heading_key = self._normalise_statement_label(raw_label)
            if heading_key:
                return node, heading_key

            # Workiva filings insert empty anchor divs ahead of the visible heading.
            max_hops = 6
            sibling = node.getnext()
            hops = 0
            while sibling is not None and hops < max_hops:
                if not isinstance(sibling.tag, str):
                    sibling = sibling.getnext()
                    hops += 1
                    continue

                if sibling.tag.lower() == "table":
                    break

                sibling_label = " ".join(sibling.itertext()).strip()
                sibling_key = self._normalise_statement_label(sibling_label)
                if sibling_key:
                    return sibling, sibling_key

                sibling = sibling.getnext()
                hops += 1

            return None

        for element in document.xpath("//*[@id]"):
            if not isinstance(element.tag, str):
                continue

            heading_data = resolve_heading(element)
            if not heading_data:
                continue

            heading_element, key = heading_data

            table_nodes = heading_element.xpath("following::table[1]")
            if not table_nodes:
                continue
            table = table_nodes[0]

            table_identity = id(table)
            if table_identity in processed_tables:
                continue
            processed_tables.add(table_identity)

            signature_set = visible.setdefault(key, set())
            for ix_node in table.iter():
                tag = ix_node.tag.lower() if isinstance(ix_node.tag, str) else ""
                if tag not in {"ix:nonfraction", "ix:nonnumeric"}:
                    continue

                if any(
                    isinstance(ancestor.tag, str)
                    and ancestor.tag.lower().endswith("hidden")
                    for ancestor in ix_node.iterancestors()
                ):
                    continue

                concept_name = ix_node.get("name")
                context_ref = ix_node.get("contextref")
                if not concept_name or not context_ref:
                    continue

                raw_dims = context_dims.get(context_ref, [])
                dims_tuple = tuple(
                    sorted(
                        (
                            self._local_name(axis).lower(),
                            self._local_name(member).lower(),
                        )
                        for axis, member in raw_dims
                        if axis and member
                    )
                )
                signature_set.add((self._local_name(concept_name).lower(), dims_tuple))

        if not visible:
            return None

        serialised: Dict[str, List[List[Any]]] = {}
        for key, entries in visible.items():
            serialised[key] = [
                [concept, [[axis, member] for axis, member in dims]]
                for concept, dims in sorted(entries)
            ]

        return serialised

    @staticmethod
    def _normalise_statement_label(label: Optional[str]) -> Optional[str]:
        if not label:
            return None
        cleaned = re.sub(r"\s+", " ", label).strip().lower()
        if len(cleaned) > 120:
            return None
        cleaned = cleaned.replace("–", "-")
        if cleaned.startswith("note ") or cleaned.startswith("notes "):
            return None
        if cleaned.startswith("item "):
            return None
        if "balance sheet" not in cleaned and not re.search(
            r"\bstatements?\s+of\b", cleaned
        ):
            return None
        cleaned = re.sub(r"^statement\s*-\s*", "", cleaned)
        cleaned = cleaned.strip()
        return cleaned or None

    @staticmethod
    def _local_name(value: Optional[str]) -> str:
        if not value:
            return ""
        return value.split(":", 1)[-1]

    def _load_label_linkbase_labels(
        self, viewer_path: Path, label_names: Iterable[str]
    ) -> Dict[str, Dict[str, str]]:
        """Parse label linkbase files to recover concept captions."""

        search_dir = viewer_path.parent
        candidates = []

        for name in label_names:
            candidate = search_dir / name
            if candidate.exists():
                candidates.append(candidate)

        if not candidates:
            candidates = sorted(search_dir.glob("*_lab.xml"))

        label_map: Dict[str, Dict[str, str]] = {}
        if not candidates:
            return label_map

        ns = {
            "link": "http://www.xbrl.org/2003/linkbase",
            "xlink": "http://www.w3.org/1999/xlink",
            "xml": "http://www.w3.org/XML/1998/namespace",
        }

        for label_path in candidates:
            try:
                tree = ET.parse(label_path)
            except Exception as exc:
                logger.debug("Failed parsing label linkbase %s: %s", label_path, exc)
                continue

            root = tree.getroot()
            locator_targets: Dict[str, str] = {}
            for locator in root.findall(".//link:loc", ns):
                label_attr = locator.get(f"{{{ns['xlink']}}}label")
                href = locator.get(f"{{{ns['xlink']}}}href")
                if not label_attr or not href:
                    continue
                fragment = href.split("#", 1)[-1]
                concept_qname = self._normalise_qname(fragment)
                if concept_qname:
                    locator_targets[label_attr] = concept_qname

            label_texts: Dict[str, Dict[str, str]] = {}
            for resource in root.findall(".//link:label", ns):
                resource_label = resource.get(f"{{{ns['xlink']}}}label")
                role = resource.get(f"{{{ns['xlink']}}}role")
                lang = (resource.get(f"{{{ns['xml']}}}lang") or "").lower()
                text = (resource.text or "").strip()
                if not resource_label or not role or not text:
                    continue
                if lang and lang not in {"en", "en-us"}:
                    continue
                short_role = self._normalise_role_name(role)
                label_texts.setdefault(resource_label, {})[short_role] = text

            for arc in root.findall(".//link:labelArc", ns):
                from_label = arc.get(f"{{{ns['xlink']}}}from")
                to_label = arc.get(f"{{{ns['xlink']}}}to")
                if not from_label or not to_label:
                    continue
                concept_qname = locator_targets.get(from_label)
                if not concept_qname:
                    continue
                roles = label_texts.get(to_label)
                if not roles:
                    continue
                target = label_map.setdefault(concept_qname, {})
                for role, text_value in roles.items():
                    target.setdefault(role, text_value)

        return label_map

    @staticmethod
    def _normalise_qname(identifier: Optional[str]) -> Optional[str]:
        """Convert linkbase identifiers to QName strings."""

        if not identifier:
            return None
        if ":" in identifier:
            return identifier
        if "_" in identifier:
            prefix, _, local = identifier.partition("_")
            if prefix and local:
                return f"{prefix}:{local}"
        return identifier

    @staticmethod
    def _normalise_role_name(role: Optional[str]) -> str:
        """Collapse role URIs to their short token."""

        if not role:
            return ""
        token = role.rsplit("/", 1)[-1]
        token = token.rsplit("#", 1)[-1]
        return token

    def _clean_json_string(self, json_str: str) -> str:
        """
        Clean up JSON string for parsing.

        Args:
            json_str: Raw JSON string

        Returns:
            Cleaned JSON string
        """
        # Remove trailing semicolon
        json_str = json_str.rstrip(";")

        # Remove any trailing JavaScript code
        json_str = re.sub(r"\s*[;}]\s*$", "", json_str)

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
        required_keys = ["facts", "concepts", "sourceReports"]

        # Must have at least some required keys
        if not any(key in data for key in required_keys):
            return False

        # Check for newer Arelle format with sourceReports
        if "sourceReports" in data:
            if (
                isinstance(data["sourceReports"], list)
                and len(data["sourceReports"]) > 0
            ):
                # Check if first source report has the expected structure
                first_report = data["sourceReports"][0]
                if isinstance(first_report, dict) and "targetReports" in first_report:
                    return True

        # Check for older format
        if "facts" in data and isinstance(data["facts"], dict):
            return True

        if "concepts" in data and isinstance(data["concepts"], dict):
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
                '{"facts"',
            ]

            for indicator in json_start_indicators:
                pos = html_content.find(indicator)
                if pos != -1:
                    logger.debug(
                        f"Found JSON indicator '{indicator}' at position {pos}"
                    )

                    # Extract complete JSON object from this position
                    json_str = self._extract_complete_json(html_content, pos)

                    if json_str:
                        try:
                            data = json.loads(json_str)
                            if self._validate_viewer_data(data):
                                logger.debug(
                                    "Successfully parsed JSON from aggressive extraction"
                                )
                                return data
                        except json.JSONDecodeError as e:
                            logger.debug(
                                f"JSON parsing failed for indicator '{indicator}': {e}"
                            )
                            continue

            # If indicators don't work, try script-based approach
            script_pattern = r"<script[^>]*>(.*?)</script>"
            scripts = re.findall(
                script_pattern, html_content, re.DOTALL | re.IGNORECASE
            )

            for script_content in scripts:
                # Look for any large JSON object starting with {
                brace_positions = [
                    m.start() for m in re.finditer(r"\{", script_content)
                ]

                # Try the largest potential JSON objects first
                for pos in sorted(
                    brace_positions, key=lambda p: len(script_content) - p, reverse=True
                )[:5]:
                    try:
                        json_str = self._extract_complete_json(script_content, pos)

                        if json_str and len(json_str) > 10000:  # Only try large objects
                            data = json.loads(json_str)
                            if self._validate_viewer_data(data):
                                return data

                    except Exception:
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
        if text[start_pos] != "{":
            return None

        brace_count = 0
        in_string = False
        escape_next = False

        for i, char in enumerate(text[start_pos:], start_pos):
            if escape_next:
                escape_next = False
                continue

            if char == "\\" and in_string:
                escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                continue

            if not in_string:
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1

                    if brace_count == 0:
                        return text[start_pos : i + 1]

        return None
