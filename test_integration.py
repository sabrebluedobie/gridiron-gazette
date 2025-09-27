#!/usr/bin/env python3
"""
Test Integration Script for Gridiron Gazette
Tests all components to ensure they work together
"""

import os
import sys
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def test_imports():
    """Test that all required modules can be imported."""
    print("\n" + "="*60)
    print("TESTING MODULE IMPORTS")
    print("="*60)
    
    modules_ok = True
    
    # Test core modules
    try:
        import gazette_data
        print("✅ gazette_data imported")
    except ImportError as e:
        print(f"❌ gazette_data import failed: {e}")
        modules_ok = False
    
    try:
        from storymaker import StoryMaker, clean_markdown_for_docx, SABRE_PROMPT
        print("✅ storymaker imported (with markdown cleaning)")
        print(f"   Sabre persona: {SABRE_PROMPT['persona'][:50]}...")
    except ImportError as e:
        print(f"❌ storymaker import failed: {e}")
        modules_ok = False
    
    try:
        import weekly_recap
        print("✅ weekly_recap imported")
    except ImportError as e:
        print(f"❌ weekly_recap import failed: {e}")
        modules_ok = False
    
    try:
        from logo_resolver import LogoResolver
        print("✅ logo_resolver imported")
    except ImportError:
        print("⚠️  logo_resolver not available (optional)")
    
    try:
        from llm_openai import chat as openai_llm
        print("✅ OpenAI LLM available")
    except ImportError:
        print("⚠️  OpenAI LLM not available (will use fallbacks)")
    
    return modules_ok


def test_markdown_cleaning():
    """Test markdown cleaning functionality."""
    print("\n" + "="*60)
    print("TESTING MARKDOWN CLEANING")
    print("="*60)
    
    from storymaker import clean_markdown_for_docx
    
    test_cases = [
        ("**Top Play**: The big moment", "Top Play: The big moment"),
        ("The team **dominated** with *precision*", "The team dominated with precision"),
        ("### Game Summary", "Game Summary"),
        ("`Code text` should be clean", "Code text should be clean"),
    ]
    
    all_passed = True
    for input_text, expected in test_cases:
        result = clean_markdown_for_docx(input_text)
        if result == expected:
            print(f"✅ '{input_text[:30]}...' → '{result[:30]}...'")
        else:
            print(f"❌ Failed: '{input_text}'")
            print(f"   Expected: '{expected}'")
            print(f"   Got: '{result}'")
            all_passed = False
    
    return all_passed


def test_sabre_voice():
    """Test that Sabre's voice is properly configured."""
    print("\n" + "="*60)
    print("TESTING SABRE VOICE CONFIGURATION")
    print("="*60)
    
    from storymaker import SABRE_PROMPT, SABRE_SIGNOFF, StoryMaker, MatchupData
    
    # Check prompt configuration
    print("Sabre Configuration:")
    print(f"  Role: {SABRE_PROMPT['role']}")
    print(f"  Tone: {SABRE_PROMPT['tone']}")
    print(f"  Style: {SABRE_PROMPT['style']}")
    print(f"  Signoff: {SABRE_SIGNOFF}")
    
    # Test fallback generation
    maker = StoryMaker(llm=None)  # No LLM, use fallback
    
    test_data = MatchupData(
        league_name="Test League",
        week=3,
        team_a="Thunder Hawks",
        team_b="Lightning Bolts",
        score_a=125.5,
        score_b=98.3,
        winner="Thunder Hawks",
        margin=27.2
    )
    
    # Generate fallback recap
    recap = maker.generate_recap(test_data, clean_markdown=True)
    
    # Check for Sabre's signoff
    if SABRE_SIGNOFF in recap:
        print(f"\n✅ Sabre signoff present in recap")
    else:
        print(f"\n❌ Sabre signoff missing from recap")
        return False
    
    # Check for markdown (should be cleaned)
    if "**" in recap or "__" in recap:
        print("❌ Markdown found in recap (should be cleaned)")
        return False
    else:
        print("✅ No markdown in recap")
    
    print(f"\nSample recap (first 200 chars):")
    print(f"  {recap[:200]}...")
    
    return True


def test_logo_paths():
    """Test that logo paths can be resolved."""
    print("\n" + "="*60)
    print("TESTING LOGO RESOLUTION")
    print("="*60)
    
    # Check for Browns logo specifically
    browns_paths = [
        "./logos/team_logos/brownseakc.png",
        "./logos/league_logos/brownseakc.png",
        "./logos/brownseakc.png",
    ]
    
    browns_found = False
    for path in browns_paths:
        if os.path.exists(path):
            print(f"✅ Browns logo found at: {path}")
            browns_found = True
            break
    
    if not browns_found:
        print("⚠️  Browns logo (brownseakc.png) not found")
        print("   Expected locations:")
        for path in browns_paths:
            print(f"     - {path}")
    
    # Try logo resolver if available
    try:
        from logo_resolver import LogoResolver
        resolver = LogoResolver()
        
        test_teams = ["Thunder Hawks", "Lightning Bolts", "Browns", "BrownsEAKC"]
        print("\nTesting logo resolution for sample teams:")
        
        for team in test_teams:
            logo = resolver.resolve_team_logo(team) or resolver.resolve_league_logo(team)
            if logo:
                print(f"  ✅ {team}: {logo}")
            else:
                print(f"  ⚠️  {team}: No logo found")
    except ImportError:
        print("\n⚠️  Logo resolver not available for testing")
    
    return True  # Don't fail on missing logos


def test_environment():
    """Test environment variables."""
    print("\n" + "="*60)
    print("TESTING ENVIRONMENT VARIABLES")
    print("="*60)
    
    required_vars = ["ESPN_S2", "SWID", "LEAGUE_ID", "YEAR"]
    optional_vars = ["OPENAI_API_KEY", "TEAM_LOGOS_FILE"]
    
    all_required = True
    
    print("Required variables:")
    for var in required_vars:
        value = os.getenv(var)
        if value:
            # Mask sensitive values
            if var in ["ESPN_S2", "SWID"]:
                display = f"{value[:10]}..." if len(value) > 10 else "***"
            else:
                display = value
            print(f"  ✅ {var}: {display}")
        else:
            print(f"  ❌ {var}: Not set")
            all_required = False
    
    print("\nOptional variables:")
    for var in optional_vars:
        value = os.getenv(var)
        if value:
            if var == "OPENAI_API_KEY":
                display = f"{value[:10]}..." if len(value) > 10 else "***"
            else:
                display = value
            print(f"  ✅ {var}: {display}")
        else:
            print(f"  ⚠️  {var}: Not set")
    
    return all_required


def test_template():
    """Test that the template file exists."""
    print("\n" + "="*60)
    print("TESTING TEMPLATE FILE")
    print("="*60)
    
    template_path = "recap_template.docx"
    
    if os.path.exists(template_path):
        print(f"✅ Template found: {template_path}")
        
        # Check file size
        size = os.path.getsize(template_path)
        print(f"   File size: {size:,} bytes")
        
        if size < 1000:
            print("   ⚠️  Template seems very small")
        
        return True
    else:
        print(f"❌ Template not found: {template_path}")
        print("   This file is required for generating the gazette")
        return False


def run_all_tests():
    """Run all integration tests."""
    print("\n" + "="*60)
    print("GRIDIRON GAZETTE INTEGRATION TEST")
    print("="*60)
    
    results = {
        "Imports": test_imports(),
        "Environment": test_environment(),
        "Template": test_template(),
        "Markdown Cleaning": test_markdown_cleaning(),
        "Sabre Voice": test_sabre_voice(),
        "Logo Paths": test_logo_paths(),
    }
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    all_passed = True
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")
        if not passed:
            all_passed = False
    
    print("="*60)
    
    if all_passed:
        print("\n🎉 All tests passed! Your Gridiron Gazette is ready to run.")
        print("\nNext step: Run your gazette with:")
        print("  python build_gazette.py --week 3 --verbose")
    else:
        print("\n⚠️  Some tests failed. Please check the issues above.")
        print("\nCritical issues to fix:")
        if not results["Imports"]:
            print("  - Module import errors (check file names and content)")
        if not results["Environment"]:
            print("  - Set required environment variables")
        if not results["Template"]:
            print("  - Add recap_template.docx file")
    
    return all_passed


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)