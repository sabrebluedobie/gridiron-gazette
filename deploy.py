#!/usr/bin/env python3
"""
Cross-platform deployment script for Gridiron Gazette fixes
Works on Windows, Mac, and Linux
"""

import sys
import platform
import subprocess
from pathlib import Path

def detect_environment():
    """Detect the current environment"""
    system = platform.system()
    print(f"🖥️  Platform: {system}")
    print(f"🐍 Python: {sys.version}")
    
    # Check if we're in a git repo
    git_dir = Path(".git")
    if git_dir.exists():
        print("📁 Git repository: ✅")
    else:
        print("📁 Git repository: ❌ (not in git repo)")
    
    # Check if we're in virtual environment
    venv_active = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    print(f"🔧 Virtual environment: {'✅' if venv_active else '❌'}")
    
    return system, git_dir.exists(), venv_active

def run_command(command, description):
    """Run a command with proper error handling"""
    print(f"\n🔄 {description}...")
    print(f"   Command: {' '.join(command) if isinstance(command, list) else command}")
    
    try:
        if isinstance(command, str):
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
        else:
            result = subprocess.run(command, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ {description} - SUCCESS")
            if result.stdout.strip():
                print(f"   Output: {result.stdout.strip()}")
            return True
        else:
            print(f"❌ {description} - FAILED")
            if result.stderr.strip():
                print(f"   Error: {result.stderr.strip()}")
            return False
    except Exception as e:
        print(f"💥 {description} - EXCEPTION: {e}")
        return False

def check_required_files():
    """Check if all required files exist"""
    print("\n📋 Checking required files...")
    
    required_files = [
        "gazette_data.py",
        "build_gazette.py", 
        "team_logos.json",
        "requirements.txt"
    ]
    
    missing_files = []
    for file in required_files:
        path = Path(file)
        if path.exists():
            size = path.stat().st_size
            print(f"   ✅ {file} ({size:,} bytes)")
        else:
            print(f"   ❌ {file} - MISSING")
            missing_files.append(file)
    
    if missing_files:
        print(f"\n⚠️  Missing files: {missing_files}")
        return False
    
    print("✅ All required files present")
    return True

def backup_files():
    """Create backups of important files"""
    print("\n💾 Creating backups...")
    
    files_to_backup = ["gazette_data.py", "build_gazette.py"]
    backup_dir = Path("backups")
    backup_dir.mkdir(exist_ok=True)
    
    for file in files_to_backup:
        source = Path(file)
        if source.exists():
            # Add timestamp to backup name
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{source.stem}_{timestamp}{source.suffix}"
            backup_path = backup_dir / backup_name
            
            try:
                backup_path.write_bytes(source.read_bytes())
                print(f"   ✅ {file} → {backup_path}")
            except Exception as e:
                print(f"   ❌ Failed to backup {file}: {e}")
        else:
            print(f"   ⚠️  {file} not found, skipping backup")

def install_requirements():
    """Install/upgrade requirements"""
    print("\n📦 Installing requirements...")
    
    requirements_file = Path("requirements.txt")
    if not requirements_file.exists():
        print("   ⚠️  requirements.txt not found, skipping")
        return True
    
    commands = [
        [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]
    ]
    
    for command in commands:
        if not run_command(command, f"Install {command[-1]}"):
            return False
    
    return True

def test_imports():
    """Test if all required imports work"""
    print("\n🧪 Testing imports...")
    
    imports_to_test = [
        ("requests", "HTTP requests"),
        ("docxtpl", "Document templates"),
        ("PIL", "Image processing"),
        ("openai", "OpenAI API")
    ]
    
    failed_imports = []
    for module, description in imports_to_test:
        try:
            __import__(module)
            print(f"   ✅ {module} ({description})")
        except ImportError:
            print(f"   ❌ {module} ({description}) - NOT AVAILABLE")
            failed_imports.append(module)
    
    if failed_imports:
        print(f"\n⚠️  Missing packages: {failed_imports}")
        print("   Run: pip install -r requirements.txt")
        return False
    
    return True

def main():
    """Main deployment function"""
    print("🚀 Gridiron Gazette Cross-Platform Deployment")
    print("=" * 50)
    
    # Step 1: Environment check
    system, is_git_repo, has_venv = detect_environment()
    
    if not has_venv:
        print("\n⚠️  Warning: Not in a virtual environment")
        print("   Consider activating your venv first")
    
    # Step 2: Check files
    if not check_required_files():
        print("\n❌ Pre-deployment checks failed")
        return 1
    
    # Step 3: Create backups
    backup_files()
    
    # Step 4: Install requirements
    if not install_requirements():
        print("\n❌ Failed to install requirements")
        return 1
    
    # Step 5: Test imports
    if not test_imports():
        print("\n❌ Import tests failed")
        return 1
    
    # Step 6: Run logo fix
    logo_fix_result = run_command(
        [sys.executable, "fix_logo_cross_platform.py"],
        "Logo fix"
    )
    
    # Step 7: Test build (dry run)
    test_build_result = run_command(
        [sys.executable, "build_gazette.py", 
         "--league-id", "887998", 
         "--year", "2025", 
         "--week", "1", 
         "--dry-run"],
        "Test build (dry run)"
    )
    
    # Step 8: Git operations (if in git repo)
    if is_git_repo:
        print("\n📝 Git operations...")
        
        # Check git status
        run_command(["git", "status", "--porcelain"], "Check git status")
        
        # Add files
        run_command(["git", "add", "."], "Stage changes")
        
        # Show what will be committed
        run_command(["git", "diff", "--cached", "--name-only"], "Show staged files")
        
        print("\n💡 Ready to commit! Run:")
        print("   git commit -m 'Deploy production fixes for ESPN auth and logos'")
        print("   git push")
    
    # Final summary
    print(f"\n{'='*50}")
    print("🎯 Deployment Summary:")
    print(f"   Logo fix: {'✅' if logo_fix_result else '❌'}")
    print(f"   Test build: {'✅' if test_build_result else '❌'}")
    
    if logo_fix_result and test_build_result:
        print("\n🎉 Deployment ready! Your system should work on both platforms.")
        print("\n📋 Next steps:")
        print("   1. Commit and push changes")
        print("   2. Run GitHub Action to test")
        print("   3. Check output artifacts")
        return 0
    else:
        print("\n❌ Deployment has issues. Check the errors above.")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)