#!/bin/bash
# setup.sh - Initialize SECDataExtractor_v3 development environment

set -e  # Exit on any error

echo "🔧 Setting up SECDataExtractor_v3 environment..."

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 is not installed or not in PATH"
    echo "   Please install Python 3.8 or higher"
    exit 1
fi

# Display Python version
echo "🐍 Using Python version: $(python3 --version)"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo "   ✅ Virtual environment created at ./venv"
else
    echo "📦 Virtual environment already exists at ./venv"
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Verify we're in the virtual environment
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo "❌ Error: Failed to activate virtual environment"
    exit 1
fi

echo "   ✅ Virtual environment activated: $VIRTUAL_ENV"

# Upgrade pip to latest version
echo "⬆️  Upgrading pip..."
python -m pip install --upgrade pip --quiet

# Install requirements
if [ -f "requirements.txt" ]; then
    echo "📥 Installing dependencies from requirements.txt..."
    pip install -r requirements.txt
    echo "   ✅ Dependencies installed successfully"
else
    echo "⚠️  Warning: requirements.txt not found, skipping dependency installation"
fi

# Create output directories
echo "📁 Creating output directories..."
mkdir -p downloads
mkdir -p output
mkdir -p temp
echo "   ✅ Directories created: downloads/, output/, temp/"

# Display summary
echo ""
echo "✅ Setup complete!"
echo ""
echo "📋 Next steps:"
echo "   1. Activate the virtual environment: source venv/bin/activate"
echo "   2. Test the download module: python download_filings.py --help"
echo "   3. Download a sample filing: python download_filings.py --ticker AAPL --form 10-K --count 1"
echo ""
echo "💡 Tips:"
echo "   • Always run 'source venv/bin/activate' before using the project"
echo "   • Use 'deactivate' to exit the virtual environment"
echo "   • Re-run this script anytime to refresh the environment"
echo ""
echo "🔗 Integration with main pipeline:"
echo "   1. Download: python download_filings.py --ticker AAPL --form 10-K"
echo "   2. Process: python render_viewer_to_xlsx.py --filing downloads/AAPL/... --out output.xlsx"
echo ""

# Check if we should stay in the virtual environment
if [[ "${1-}" == "--activate" ]]; then
    echo "🔄 Keeping virtual environment active for this shell session..."
    exec "$SHELL"
else
    echo "💡 Run 'source venv/bin/activate' to activate the virtual environment manually"
fi