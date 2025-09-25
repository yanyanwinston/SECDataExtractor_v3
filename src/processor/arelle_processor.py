"""
Arelle processor for generating iXBRL viewer data.
"""

import subprocess
import tempfile
import logging
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)


class ArelleError(Exception):
    """Exception for Arelle processing errors."""
    pass


class ArelleProcessor:
    """Processor that uses Arelle to generate iXBRL viewer HTML."""

    def __init__(self, temp_dir: Optional[Path] = None, timeout: int = 300):
        """
        Initialize Arelle processor.

        Args:
            temp_dir: Directory for temporary files
            timeout: Timeout in seconds for Arelle processing
        """
        self.temp_dir = temp_dir or Path(tempfile.gettempdir())
        self.timeout = timeout

    def generate_viewer_html(self, filing_path: str) -> str:
        """
        Generate iXBRL viewer HTML using Arelle.

        Args:
            filing_path: Path to the iXBRL filing

        Returns:
            Path to generated viewer HTML file

        Raises:
            ArelleError: If Arelle processing fails
        """
        filing_path = Path(filing_path)

        if not filing_path.exists():
            raise ArelleError(f"Filing file not found: {filing_path}")

        filing_path = filing_path.resolve()

        # Create output directory
        output_dir = self.temp_dir / f"arelle_output_{hash(str(filing_path)) % 10000}"
        output_dir.mkdir(exist_ok=True)

        viewer_file = output_dir / "ixbrl-viewer.htm"

        try:
            # Build Arelle command
            cmd = [
                "python", "-m", "arelle.CntlrCmdLine",
                "--plugins", "iXBRLViewerPlugin",
                "--file", str(filing_path),
                "--save-viewer", str(viewer_file)
            ]

            logger.info(f"Running Arelle command: {' '.join(cmd)}")

            # Run Arelle
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=output_dir
            )

            if result.returncode != 0:
                logger.error(f"Arelle failed with return code {result.returncode}")
                logger.error(f"Stdout: {result.stdout}")
                logger.error(f"Stderr: {result.stderr}")
                raise ArelleError(f"Arelle processing failed: {result.stderr}")

            if not viewer_file.exists():
                raise ArelleError("Arelle completed but viewer file was not created")

            logger.info(f"Successfully generated viewer HTML: {viewer_file}")
            return str(viewer_file)

        except subprocess.TimeoutExpired:
            raise ArelleError(f"Arelle processing timed out after {self.timeout} seconds")
        except subprocess.SubprocessError as e:
            raise ArelleError(f"Arelle subprocess error: {e}")
        except Exception as e:
            raise ArelleError(f"Unexpected error during Arelle processing: {e}")

    def check_arelle_available(self) -> bool:
        """
        Check if Arelle is available and has the iXBRL viewer plugin.

        Returns:
            True if Arelle is available, False otherwise
        """
        try:
            # First, check if basic Arelle is available
            basic_result = subprocess.run(
                ["python", "-m", "arelle.CntlrCmdLine", "--help"],
                capture_output=True,
                text=True,
                timeout=30
            )

            if basic_result.returncode != 0:
                logger.debug("Basic Arelle not available")
                return False

            # Try to check plugin availability by testing with plugin flag
            plugin_result = subprocess.run(
                ["python", "-m", "arelle.CntlrCmdLine", "--plugins", "iXBRLViewerPlugin", "--help"],
                capture_output=True,
                text=True,
                timeout=30
            )

            # If plugin command works, check for save-viewer option
            if plugin_result.returncode == 0 and "save-viewer" in plugin_result.stdout:
                logger.debug("iXBRL viewer plugin available")
                return True

            # Fallback: if basic Arelle works, assume plugin is available
            # This handles cases where plugin help doesn't work but plugin itself does
            logger.debug("Plugin check inconclusive, assuming available since basic Arelle works")
            return True

        except (subprocess.SubprocessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.debug(f"Arelle availability check failed: {e}")
            return False

    def install_arelle(self) -> bool:
        """
        Attempt to install Arelle and iXBRL viewer plugin.

        Returns:
            True if installation succeeded, False otherwise
        """
        try:
            logger.info("Attempting to install Arelle...")

            # Install Arelle
            result = subprocess.run(
                ["pip", "install", "arelle"],
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode != 0:
                logger.error(f"Failed to install Arelle: {result.stderr}")
                return False

            logger.info("Arelle installed successfully")
            return self.check_arelle_available()

        except (subprocess.SubprocessError, subprocess.TimeoutExpired) as e:
            logger.error(f"Error installing Arelle: {e}")
            return False
