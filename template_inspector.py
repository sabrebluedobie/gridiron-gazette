#!/usr/bin/env python3
"""
Template Variable Inspector - Extracts variable names from docx template
"""
import zipfile
import xml.etree.ElementTree as ET
import re
from pathlib import Path

def extract_template_variables(template_path: str):
    """Extract all Jinja2/docxtpl variables from a .docx template"""
    
    if not Path(template_path).exists():
        print(f"❌ Template not found: {template_path}")
        return []
    
    variables = set()
    
    try:
        with zipfile.ZipFile(template_path, 'r') as docx:
            # Check document.xml for main content variables
            if 'word/document.xml' in docx.namelist():
                with docx.open('word/document.xml') as f:
                    content = f.read().decode('utf-8')
                    
                    # Find all Jinja2 variables {{ variable_name }}
                    jinja_vars = re.findall(r'\{\{\s*([^}]+)\s*\}\}', content)
                    for var in jinja_vars:
                        var = var.strip()
                        # Clean up any filters or expressions  
                        var = var.split('|')[0].split('.')[0].strip()
                        if var and not var.startswith('_'):
                            variables.add(var)
            
            # Check headers/footers
            for part in ['word/header1.xml', 'word/header2.xml', 'word/footer1.xml', 'word/footer2.xml']:
                if part in docx.namelist():
                    with docx.open(part) as f:
                        content = f.read().decode('utf-8')
                        jinja_vars = re.findall(r'\{\{\s*([^}]+)\s*\}\}', content)
                        for var in jinja_vars:
                            var = var.strip().split('|')[0].split('.')[0].strip()
                            if var and not var.startswith('_'):
                                variables.add(var)
    
    except Exception as e:
        print(f"❌ Error reading template: {e}")
        return []
    
    return sorted(list(variables))

def analyze_variables(variables):
    """Analyze and categorize the template variables"""
    
    categories = {
        'spotlight': [],
        'awards': [],
        'matchup': [],
        'team': [],
        'score': [],
        'other': []
    }
    
    for var in variables:
        var_lower = var.lower()
        
        if any(x in var_lower for x in ['spotlight', 'bust', 'key', 'defense', 'def']):
            categories['spotlight'].append(var)
        elif any(x in var_lower for x in ['cupcake', 'kitty', 'topscore', 'award']):
            categories['awards'].append(var)
        elif any(x in var_lower for x in ['matchup', 'home', 'away', 'vs']):
            categories['matchup'].append(var)
        elif any(x in var_lower for x in ['team', 'name']):
            categories['team'].append(var)
        elif any(x in var_lower for x in ['score', 'points', 'pts']):
            categories['score'].append(var)
        else:
            categories['other'].append(var)
    
    return categories

def main():
    template_path = "recap_template.docx"
    
    print("🔍 TEMPLATE VARIABLE INSPECTOR")
    print("=" * 50)
    print(f"Analyzing: {template_path}")
    print()
    
    variables = extract_template_variables(template_path)
    
    if not variables:
        print("❌ No variables found or template unreadable")
        return
    
    print(f"📊 Found {len(variables)} template variables:")
    print("-" * 30)
    
    categories = analyze_variables(variables)
    
    for category, vars_list in categories.items():
        if vars_list:
            print(f"\n📂 {category.upper()} Variables ({len(vars_list)}):")
            for var in vars_list:
                print(f"  {{{{ {var} }}}}")
    
    # Specific analysis for Stats Spotlight issue
    print(f"\n🎯 STATS SPOTLIGHT Analysis:")
    print("-" * 30)
    spotlight_vars = categories['spotlight']
    
    if spotlight_vars:
        print("✅ Template DOES expect spotlight variables:")
        for var in spotlight_vars:
            print(f"  {{{{ {var} }}}}")
        print("\n💡 Make sure your code generates these EXACT variable names!")
    else:
        print("❌ No explicit spotlight variables found")
        print("🤔 Template might use generic variables or different naming")
        
        # Check for potential alternatives
        potential_spotlight = [v for v in variables if any(x in v.lower() for x in 
                             ['home', 'away', 'top', 'scorer', 'best', 'worst', 'play'])]
        if potential_spotlight:
            print("\n🔍 Potential spotlight-related variables:")
            for var in potential_spotlight:
                print(f"  {{{{ {var} }}}}")
    
    # Awards analysis  
    print(f"\n🏆 AWARDS Analysis:")
    print("-" * 20)
    awards_vars = categories['awards']
    
    if awards_vars:
        print("✅ Template expects these award variables:")
        for var in awards_vars:
            print(f"  {{{{ {var} }}}}")
    else:
        print("❌ No explicit award variables found")
        potential_awards = [v for v in variables if any(x in v.lower() for x in 
                          ['low', 'high', 'worst', 'best', 'gap', 'blow'])]
        if potential_awards:
            print("\n🔍 Potential award-related variables:")
            for var in potential_awards:
                print(f"  {{{{ {var} }}}}")
    
    print(f"\n📋 ALL VARIABLES (for copy/paste):")
    print("-" * 25)
    for var in variables:
        print(f"{{{{ {var} }}}}")

if __name__ == "__main__":
    main()