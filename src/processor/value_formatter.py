"""
Value formatter for SEC financial data.
"""

from typing import Optional, Dict, Any


class ValueFormatter:
    """Formatter for financial values and display text."""

    def __init__(self, currency: str = "USD", scale_millions: bool = True):
        """
        Initialize value formatter.

        Args:
            currency: Expected currency (default: USD)
            scale_millions: Whether to scale currency values to millions
        """
        self.currency = currency
        self.scale_millions = scale_millions

    def format_cell_value(self, raw_value: Optional[float], unit: Optional[str],
                         decimals: Optional[int], concept: Optional[str] = None) -> str:
        """
        Format a single cell value according to its type and unit.

        Args:
            raw_value: Raw numeric value
            unit: Unit of measurement
            decimals: Number of decimal places
            concept: Concept identifier for type detection

        Returns:
            Formatted string value
        """
        if raw_value is None:
            return "—"  # Em dash for missing values

        try:
            # Determine value type based on unit and concept
            value_type = self._determine_value_type(unit, concept)

            if value_type == "currency":
                return self._format_currency(raw_value, decimals)
            elif value_type == "shares":
                return self._format_shares(raw_value)
            elif value_type == "eps":
                return self._format_eps(raw_value)
            elif value_type == "percentage":
                return self._format_percentage(raw_value, decimals)
            elif value_type == "ratio":
                return self._format_ratio(raw_value, decimals)
            else:
                return self._format_generic_number(raw_value, decimals)

        except (ValueError, TypeError):
            # If formatting fails, return raw value as string
            return str(raw_value) if raw_value is not None else "—"

    def _determine_value_type(self, unit: Optional[str], concept: Optional[str]) -> str:
        """
        Determine the type of value based on unit and concept.

        Args:
            unit: Unit string from XBRL
            concept: Concept identifier

        Returns:
            Value type string
        """
        if not unit and not concept:
            return "generic"

        unit_lower = (unit or "").lower()
        concept_lower = (concept or "").lower()

        # Currency values
        if any(curr in unit_lower for curr in ["usd", "eur", "cad", "gbp"]):
            return "currency"

        # Share counts
        if any(term in unit_lower for term in ["shares", "share"]):
            return "shares"

        # EPS values
        if any(term in concept_lower for term in ["earningsper", "eps", "pershare"]):
            return "eps"

        # Percentages
        if any(term in unit_lower for term in ["percent", "%"]):
            return "percentage"

        # Ratios (no unit, decimal concept)
        if not unit and any(term in concept_lower for term in ["ratio", "rate", "margin"]):
            return "ratio"

        return "generic"

    def _format_currency(self, value: float, decimals: Optional[int]) -> str:
        """
        Format currency values.

        Args:
            value: Raw currency value
            decimals: Decimal places

        Returns:
            Formatted currency string
        """
        if self.scale_millions:
            # Scale to millions
            scaled_value = value / 1_000_000

            # Handle negatives with parentheses
            if scaled_value < 0:
                return f"({abs(scaled_value):,.1f})"
            else:
                return f"{scaled_value:,.1f}"
        else:
            # Use raw value with thousands separators
            if value < 0:
                return f"({abs(value):,.0f})"
            else:
                return f"{value:,.0f}"

    def _format_shares(self, value: float) -> str:
        """
        Format share counts (in millions, no decimals).

        Args:
            value: Raw share count

        Returns:
            Formatted share string
        """
        # Convert to millions
        millions = value / 1_000_000

        if millions < 0:
            return f"({abs(millions):,.0f})"
        else:
            return f"{millions:,.0f}"

    def _format_eps(self, value: float) -> str:
        """
        Format EPS values (2 decimal places).

        Args:
            value: Raw EPS value

        Returns:
            Formatted EPS string
        """
        if value < 0:
            return f"({abs(value):.2f})"
        else:
            return f"{value:.2f}"

    def _format_percentage(self, value: float, decimals: Optional[int]) -> str:
        """
        Format percentage values.

        Args:
            value: Raw percentage value
            decimals: Decimal places

        Returns:
            Formatted percentage string
        """
        decimal_places = min(decimals or 1, 3)  # Max 3 decimal places

        if value < 0:
            return f"({abs(value):.{decimal_places}f}%)"
        else:
            return f"{value:.{decimal_places}f}%"

    def _format_ratio(self, value: float, decimals: Optional[int]) -> str:
        """
        Format ratio values.

        Args:
            value: Raw ratio value
            decimals: Decimal places

        Returns:
            Formatted ratio string
        """
        decimal_places = min(decimals or 2, 4)  # Max 4 decimal places

        if value < 0:
            return f"({abs(value):.{decimal_places}f})"
        else:
            return f"{value:.{decimal_places}f}"

    def _format_generic_number(self, value: float, decimals: Optional[int]) -> str:
        """
        Format generic numeric values.

        Args:
            value: Raw numeric value
            decimals: Decimal places

        Returns:
            Formatted number string
        """
        # Use provided decimals or default based on value magnitude
        if decimals is not None:
            decimal_places = min(decimals, 6)  # Max 6 decimal places
        else:
            # Auto-determine decimals based on value
            if abs(value) >= 1000:
                decimal_places = 0
            elif abs(value) >= 1:
                decimal_places = 2
            else:
                decimal_places = 4

        # Format with thousands separators for large values
        if abs(value) >= 1000:
            if value < 0:
                return f"({abs(value):,.{decimal_places}f})"
            else:
                return f"{value:,.{decimal_places}f}"
        else:
            if value < 0:
                return f"({abs(value):.{decimal_places}f})"
            else:
                return f"{value:.{decimal_places}f}"

    def clean_label(self, label: str) -> str:
        """
        Clean up row labels for display.

        Args:
            label: Raw label string

        Returns:
            Cleaned label string
        """
        if not label:
            return ""

        # Remove excessive whitespace
        cleaned = re.sub(r'\s+', ' ', label.strip())

        # Remove common prefixes that aren't needed for display
        prefixes_to_remove = [
            "us-gaap:",
            "dei:",
            "ifrs-full:",
        ]

        for prefix in prefixes_to_remove:
            if cleaned.lower().startswith(prefix):
                cleaned = cleaned[len(prefix):]
                break

        return cleaned

    def format_period_label(self, period_label: str) -> str:
        """
        Format period labels for column headers.

        Args:
            period_label: Raw period label

        Returns:
            Formatted period label
        """
        if not period_label:
            return ""

        # Extract year if it's a long date string
        year_match = re.search(r'20\d{2}', period_label)
        if year_match:
            return year_match.group(0)

        return period_label
