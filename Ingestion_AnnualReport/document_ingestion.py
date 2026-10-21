"""Compatibility entry point for document ingestion."""
from src.ingestion.loader import annual_chunks, education_chunks, iter_documents, run_ingestion, main

if __name__ == "__main__":
    main()
