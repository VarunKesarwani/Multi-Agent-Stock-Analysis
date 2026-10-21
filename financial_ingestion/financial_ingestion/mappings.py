"""Small reviewed mapping set, intentionally exact and source-specific.
No fuzzy financial concept matching. Extending this file changes its digest.
"""
from .contract import digest
NS = 'http://www.bseindia.com/xbrl/fin/2020-03-31/in-bse-fin'

def seed_definitions():
    rows = []
    def add(source, statement, label, metric, unit, kind='DURATION'):
        rows.append(dict(source=source, statement=statement, source_label=label,
                         metric=metric, unit=unit, period_kind=kind, approved=True,
                         review_note='Explicit v1 mapping; no fuzzy matching', mapping_version='1.0.0'))
    for s in ('profit_loss','quarterly_results'):
        for label, metric in [('Sales','revenue'),('Expenses','expenses'),('Operating Profit','operating_profit'),('Other Income','other_income'),('Interest','interest_expense'),('Depreciation','depreciation'),('Profit before tax','profit_before_tax'),('Net Profit','net_profit')]:
            add('SCREENER',s,label,metric,'INR')
        for label, metric in [('OPM %','operating_margin'),('Tax %','reported_tax_percent'),('Dividend Payout %','dividend_payout')]:
            add('SCREENER',s,label,metric,'PERCENT')
        add('SCREENER',s,'EPS in Rs','eps','INR_PER_SHARE')
    for label, metric in [('Equity Capital','equity_capital'),('Reserves','reserves'),('Borrowings','borrowings'),('Other Liabilities','other_liabilities'),('Total Liabilities','total_liabilities'),('Fixed Assets','fixed_assets'),('CWIP','capital_work_in_progress'),('Investments','investments'),('Other Assets','other_assets'),('Total Assets','total_assets')]:
        add('SCREENER','balance_sheet',label,metric,'INR','INSTANT')
    for label,metric in [('Cash from Operating Activity','operating_cash_flow'),('Cash from Investing Activity','investing_cash_flow'),('Cash from Financing Activity','financing_cash_flow'),('Net Cash Flow','net_cash_flow')]:
        add('SCREENER','cash_flows',label,metric,'INR')
    for label,metric,unit in [('Debtor Days','debtor_days','DAYS'),('Inventory Days','inventory_days','DAYS'),('Days Payable','days_payable','DAYS'),('Cash Conversion Cycle','cash_conversion_cycle','DAYS'),('Working Capital Days','working_capital_days','DAYS'),('ROCE %','roce','PERCENT')]:
        add('SCREENER','ratios_table',label,metric,unit)
    for label,metric in [('Promoters','promoter_holding'),('FIIs','fii_holding'),('DIIs','dii_holding'),('Government','government_holding'),('Public','public_holding'),('Others','other_holding')]:
        add('SCREENER','shareholding',label,metric,'PERCENT','INSTANT')
    add('SCREENER','shareholding','No. of Shareholders','shareholder_count','COUNT','INSTANT')
    for label,metric in [('RevenueFromOperations','revenue'),('OtherIncome','other_income'),('ProfitBeforeTax','profit_before_tax'),('ProfitLossForPeriod','net_profit'),('SegmentProfitLossBeforeTaxAndFinanceCosts','segment_profit_before_tax_and_finance_costs')]:
        add('NSE_XBRL','profit_loss',f'{{{NS}}}{label}',metric,'INR')
    return rows

class MetricDefinitions:
    def __init__(self, rows=None):
        self.rows = rows if rows is not None else seed_definitions()
        keys = [(r['source'], r['statement'], r['source_label']) for r in self.rows]
        if len(keys) != len(set(keys)): raise ValueError('Duplicate mapping')
        self.rows = sorted(self.rows, key=lambda r: (r["source"], r["statement"], r["source_label"]))
        self.version = digest(self.rows)
    def find(self, source, label, statement=None):
        matches = [r for r in self.rows if r.get('approved') is True and r['source']==source and r['source_label']==label and (statement is None or r['statement']==statement)]
        return matches[0] if len(matches)==1 else None
