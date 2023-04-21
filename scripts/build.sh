#!/bin/bash
# Basic build script using PyInstaller for Windows

# Ensure we are in the project root
cd "$(dirname "$0")/.."

# Clean previous builds
rm -rf dist/ build/

echo "Building PromptBuilder executable for Windows..."

# Run PyInstaller using the spec file *within the Poetry environment*
poetry run pyinstaller scripts/freeze.spec

# Check if build was successful
if [ $? -eq 0 ]; then
  echo "Build successful! Executable is in the dist/PromptBuilder directory."
else
  echo "Build failed."
  exit 1
fi

# Optional: Create a zip archive for Windows
echo "Creating archive..."
cd dist/
# Assuming 7-Zip is installed and in PATH, or use powershell Compress-Archive
if command -v 7z &> /dev/null; then
    7z a ../PromptBuilder_Windows.zip PromptBuilder/
    echo "Created PromptBuilder_Windows.zip using 7z"
elif command -v powershell &> /dev/null; then
    powershell -Command "Compress-Archive -Path PromptBuilder -DestinationPath ../PromptBuilder_Windows.zip -Force"
    echo "Created PromptBuilder_Windows.zip using PowerShell"
else
    echo "Could not find 7z or PowerShell to create archive."
fi
cd ..

echo "Build process finished."