from pathlib import Path
import py_compile

base = Path(__file__).resolve().parent
files = [p for p in base.glob('*.py') if not p.name.startswith('.')]
files.append(base / 'tests' / 'test_transformers.py')
for file in files:
    if file.exists():
        py_compile.compile(str(file), doraise=True)
        print(f'Compiled {file.name}')
