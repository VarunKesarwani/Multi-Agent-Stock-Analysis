"""Tests for NSE F&O bhavcopy source selection and fallback."""

from datetime import date
from unittest.mock import Mock, patch

import config
import fo_ingestion
import utils


def test_udiff_fo_url_is_primary():
    target = date(2026, 9, 24)

    url = utils.resolve_url(config.FO_SOURCES[0].url, target)

    assert url == (
        'https://archives.nseindia.com/content/fo/'
        'BhavCopy_NSE_FO_0_0_0_20260924_F_0000.csv.zip'
    )


@patch('fo_ingestion.transformers.transform_fo')
@patch('fo_ingestion.utils.parse_csv_payload')
@patch('fo_ingestion.utils.download_payload')
@patch('fo_ingestion.utils.generate_trading_dates')
def test_fo_ingestion_falls_back_to_archive(
    mock_dates,
    mock_download,
    mock_parse,
    mock_transform,
):
    target = date(2026, 9, 24)
    mock_dates.return_value = [target]
    mock_download.side_effect = [(403, None), (200, b'csv')]
    mock_parse.return_value = Mock()
    transformed = Mock()
    transformed.empty = False
    mock_transform.return_value = transformed
    db_manager = Mock()

    failed = fo_ingestion.ingest_fo(target, target, db_manager, Mock())

    assert failed == []
    assert mock_download.call_count == 2
    first_url = mock_download.call_args_list[0].args[0]
    second_url = mock_download.call_args_list[1].args[0]
    assert first_url == ('https://archives.nseindia.com/content/fo/'
                         'BhavCopy_NSE_FO_0_0_0_20260924_F_0000.csv.zip')
    assert second_url == ('https://nsearchives.nseindia.com/content/fo/'
                          'BhavCopy_NSE_FO_0_0_0_20260924_F_0000.csv.zip')
    db_manager.upsert_fo_bhavcopy.assert_called_once_with(transformed)


def test_udiff_zip_transforms_futures_and_options():
    import io
    import zipfile
    import transformers

    csv = (
        'TradDt,FinInstrmTp,TckrSymb,XpryDt,StrkPric,OptnTp,OpnPric,'
        'HghPric,LwPric,ClsPric,SttlmPric,TtlTradgVol,TtlTrfVal,OpnIntrst,ChngInOpnIntrst\n'
        '2026-07-20,STF,TCS,2026-07-28,,,100,110,90,105,105,10,200000,100,5\n'
        '2026-07-20,IDO,NIFTY,2026-07-28,25000,CE,100,110,90,105,105,20,300000,200,10\n'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('BhavCopy_NSE_FO_0_0_0_20260720_F_0000.csv', csv)
    result = transformers.transform_fo(utils.parse_csv_payload(buffer.getvalue()))
    assert len(result) == 2
    assert list(result['INSTRUMENT']) == ['FUTSTK', 'OPTIDX']
    assert list(result['OPTION_TYPE']) == ['XX', 'CE']
    assert list(result['STRIKE_PRICE']) == [0, 25000]
    assert list(result['VAL_IN_LAKHS']) == [2, 3]
    assert all(value.date() == date(2026, 7, 20) for value in result['TRADE_DATE'])
