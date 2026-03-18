"""SEC EDGAR connector implementation."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

import aiohttp
import structlog

from connectors.base_connector import BaseConnector, RawEvent

log = structlog.get_logger(__name__)

TICKER_TO_CIK: dict[str, str] = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "GOOGL": "0001652044",
    "AMZN": "0001018724",
    "NVDA": "0001045810",
    "META": "0001326801",
    "TSLA": "0001318605",
    "JPM": "0000019617",
}

SEC_HEADERS = {
    "User-Agent": "YourCompany contact@company.com",
    "Accept": "application/json",
}


class SECConnector(BaseConnector):
    """Fetch SEC filings for configured tickers and filing forms.

    Parameters
    ----------
    source_id : str
        Source identifier from configuration.
    filing_types : list[str]
        Filing forms to include, such as ["10-Q", "8-K"].
    tickers : list[str]
        Ticker symbols to query.
    lookback_hours : int, default=2
        Lookback window in hours for filings.
    """

    def __init__(
        self,
        source_id: str,
        filing_types: list[str],
        tickers: list[str],
        lookback_hours: int = 2,
    ) -> None:
        self._source_id = source_id
        self._filing_types = {value.upper() for value in filing_types}
        self._tickers = [ticker.upper() for ticker in tickers]
        self._lookback_hours = lookback_hours
        super().__init__()

    @property
    def source_id(self) -> str:
        """Return connector source identifier."""
        return self._source_id

    async def _fetch_raw(self) -> AsyncIterator[RawEvent]:
        """Fetch and emit filings across all configured tickers."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self._lookback_hours)
        semaphore = asyncio.Semaphore(5)

        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout, headers=SEC_HEADERS) as session:
            tasks = [
                self._fetch_ticker_filings(
                    session=session,
                    semaphore=semaphore,
                    ticker=ticker,
                    cutoff=cutoff,
                )
                for ticker in self._tickers
            ]
            results = await asyncio.gather(*tasks)

        for records in results:
            for event in records:
                yield event

    async def _fetch_ticker_filings(
        self,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        ticker: str,
        cutoff: datetime,
    ) -> list[RawEvent]:
        """Fetch recent filings for a single ticker."""
        async with semaphore:
            cik = TICKER_TO_CIK.get(ticker)
            if cik is None:
                cik = await self._lookup_cik(session, ticker)
                if cik is None:
                    log.warning("sec.ticker_cik_not_found", ticker=ticker)
                    await asyncio.sleep(0.15)
                    return []

            cik_padded = str(int(cik)).zfill(10)
            url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"

            try:
                async with session.get(url) as response:
                    if response.status != 200:
                        log.warning(
                            "sec.submissions_request_failed",
                            ticker=ticker,
                            cik=cik_padded,
                            status=response.status,
                        )
                        return []
                    data = await response.json()
            finally:
                # SEC guidance: no more than 10 requests/sec.
                await asyncio.sleep(0.15)

            recent = (data.get("filings") or {}).get("recent") or {}
            forms = recent.get("form") or []
            filing_dates = recent.get("filingDate") or []
            accession_numbers = recent.get("accessionNumber") or []

            events: list[RawEvent] = []
            for form, filing_date, accession in zip(forms, filing_dates, accession_numbers):
                form_upper = str(form).upper()
                if form_upper not in self._filing_types:
                    continue

                filed_dt = self._parse_filing_date(filing_date)
                if filed_dt < cutoff:
                    break

                accession_str = str(accession)
                accession_nodash = accession_str.replace("-", "")
                sec_url = (
                    f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                    f"{accession_nodash}/{accession_str}-index.html"
                )

                events.append(
                    RawEvent(
                        id=f"{ticker}:{accession_str}",
                        title=f"{ticker} filed {form_upper}",
                        body=(
                            f"SEC filing detected for {ticker}. Form {form_upper} filed on "
                            f"{filed_dt.date().isoformat()}."
                        ),
                        source_url=sec_url,
                        source=self.source_id,
                        source_type="sec",
                        published=filed_dt,
                        raw_payload={
                            "ticker": ticker,
                            "form": form_upper,
                            "filingDate": filing_date,
                            "accessionNumber": accession_str,
                        },
                        metadata={
                            "ticker": ticker,
                            "cik": cik_padded,
                            "form_type": form_upper,
                            "accession_number": accession_str,
                        },
                    )
                )

            return events

    async def _lookup_cik(self, session: aiohttp.ClientSession, ticker: str) -> str | None:
        """Resolve ticker to CIK using SEC company_tickers lookup."""
        url = "https://www.sec.gov/files/company_tickers.json"
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    return None
                payload = await response.json()
        finally:
            await asyncio.sleep(0.15)

        target = ticker.upper()
        values = payload.values() if isinstance(payload, dict) else payload
        for item in values:
            if not isinstance(item, dict):
                continue
            if str(item.get("ticker", "")).upper() == target:
                cik_str = item.get("cik_str")
                if cik_str is None:
                    return None
                return str(cik_str).zfill(10)

        return None

    async def health_check(self) -> bool:
        """Return True when Apple's submissions endpoint returns HTTP 200."""
        timeout = aiohttp.ClientTimeout(total=10)
        url = "https://data.sec.gov/submissions/CIK0000320193.json"
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=SEC_HEADERS) as session:
                async with session.get(url) as response:
                    return response.status == 200
        except aiohttp.ClientError:
            return False

    @staticmethod
    def _parse_filing_date(value: Any) -> datetime:
        """Parse SEC filingDate values to timezone-aware UTC datetime."""
        if not value:
            return datetime.now(timezone.utc)

        text = str(value)
        for candidate in (text, f"{text}T00:00:00+00:00"):
            try:
                parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    return parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
            except ValueError:
                continue

        return datetime.now(timezone.utc)
