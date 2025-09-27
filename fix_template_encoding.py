# fix_template_encoding.py
from pathlib import Path

template_path = Path("recap_template.html")

# Read with multiple encoding attempts
content = None
for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
    try:
        with open(template_path, 'r', encoding=encoding) as f:
            content = f.read()
        print(f"Successfully read template with {encoding} encoding")
        break
    except UnicodeDecodeError:
        continue

if content:
    # Save as UTF-8
    with open(template_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Template saved as UTF-8: {template_path}")
else:
    print("Could not read template file")