from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yfinance as yf
from deep_research_agent.tools.base import ToolDefinition, ToolRegistry

def register_finance_tools(
    registry: ToolRegistry,
    workspace_root: Path,
) -> None:
    def yfinance_stock_info(arguments: dict[str, Any]) -> dict[str, Any]:
        symbol = arguments["symbol"]
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        # Archive search
        finance_dir = workspace_root / "research" / "finance"
        finance_dir.mkdir(parents=True, exist_ok=True)
        file_path = finance_dir / f"{symbol}_info.json"
        file_path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        
        # Return only essential info for context efficiency
        essential = {
            "symbol": symbol,
            "shortName": info.get("shortName"),
            "longBusinessSummary": info.get("longBusinessSummary", "")[:500],
            "currentPrice": info.get("currentPrice"),
            "marketCap": info.get("marketCap"),
            "trailingPE": info.get("trailingPE"),
        }
        
        return {
            "symbol": symbol,
            "info": essential,
            "archive_path": str(file_path.relative_to(workspace_root)),
            "system_note": f"Full stock info for {symbol} archived at {file_path.relative_to(workspace_root)}."
        }

    def yfinance_stock_history(arguments: dict[str, Any]) -> dict[str, Any]:
        symbol = arguments["symbol"]
        period = arguments.get("period", "1mo")
        interval = arguments.get("interval", "1d")
        
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval)
        
        # Convert to list of dicts
        history_data = hist.reset_index().to_dict(orient="records")
        # Handle Timestamp objects
        for row in history_data:
            for k, v in row.items():
                if hasattr(v, "isoformat"):
                    row[k] = v.isoformat()

        # Archive search
        finance_dir = workspace_root / "research" / "finance"
        finance_dir.mkdir(parents=True, exist_ok=True)
        file_path = finance_dir / f"{symbol}_history_{period}.json"
        file_path.write_text(json.dumps(history_data, ensure_ascii=False, indent=2), encoding="utf-8")
        
        return {
            "symbol": symbol,
            "period": period,
            "data_count": len(history_data),
            "latest_close": history_data[-1]["Close"] if history_data else None,
            "archive_path": str(file_path.relative_to(workspace_root)),
            "system_note": f"Full history data for {symbol} archived at {file_path.relative_to(workspace_root)}."
        }

    registry.register(
        ToolDefinition(
            name="yfinance_stock_info",
            description="Get real-time stock information and business summary using yfinance.",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol (e.g. AAPL, MSFT)"},
                },
                "required": ["symbol"],
            },
            handler=yfinance_stock_info,
        )
    )
    registry.register(
        ToolDefinition(
            name="yfinance_stock_history",
            description="Get historical stock price data using yfinance.",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "period": {"type": "string", "enum": ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"], "default": "1mo"},
                    "interval": {"type": "string", "enum": ["1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"], "default": "1d"},
                },
                "required": ["symbol"],
            },
            handler=yfinance_stock_history,
        )
    )
