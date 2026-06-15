import glob

for file in glob.glob('*.py'):
    if file == 'fix_quotes.py': continue
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace escaped quotes with proper python docstrings
    content = content.replace('\\"\\"\\"', '"""')
    
    with open(file, 'w', encoding='utf-8') as f:
        f.write(content)
