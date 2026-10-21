"""Legacy command entry point; delegates to the maintained ingestion CLI."""
from main import main

if __name__ == '__main__':
    raise SystemExit(main())
