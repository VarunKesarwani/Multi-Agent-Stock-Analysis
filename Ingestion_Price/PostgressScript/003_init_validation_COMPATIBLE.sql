SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_name IN ('company_master', 'company_market', 'equity_bhavcopy', 'fo_bhavcopy')
ORDER BY table_name, ordinal_position;