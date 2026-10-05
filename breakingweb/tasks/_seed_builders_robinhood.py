"""Composable seed builder framework for the Robinhood environment.

Provides :class:`RobinhoodSeedContext` (the mutable accumulator threaded through
every builder step) and a registry of reusable builder functions that generate
deterministic financial test data for benchmark tasks.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable

from breakingweb.backend.models.robinhood import (
    DividendEntry,
    EarningsEvent,
    Greeks,
    HistoricalPrice,
    LinkedBank,
    Notification,
    OptionsContract,
    OptionsLeg,
    OptionsOrder,
    OptionsPosition,
    Order,
    Position,
    PriceAlert,
    RealizedGainLoss,
    RecurringExecution,
    RecurringInvestment,
    Referral,
    SecurityEntry,
    Stock,
    TaxDocument,
    TaxLot,
    Transaction,
    Transfer,
    Watchlist,
)


# ---------------------------------------------------------------------------
# ResolvedActor (shared shape with Gmail)
# ---------------------------------------------------------------------------

@dataclass
class ResolvedActor:
    """A named person with a deterministically-generated email address."""

    name: str
    email: str
    first_name: str


# ---------------------------------------------------------------------------
# ETF symbol set
# ---------------------------------------------------------------------------

_ETF_SYMBOLS: set[str] = {
    "SPY", "QQQ", "VTI", "VXUS", "BND", "SCHD", "VOO", "IWM", "GLD", "TLT",
    "XLK", "SMH", "VEA", "VTIP",
}

# ---------------------------------------------------------------------------
# Hardcoded stock universe (~80 real US stocks + ETFs)
# ---------------------------------------------------------------------------

_STOCK_SEED_DATA: list[dict[str, Any]] = [
    # ── Technology ──────────────────────────────────────────────────────
    {"symbol": "AAPL", "name": "Apple Inc.", "sector": "Technology", "industry": "Consumer Electronics",
     "about": "Apple Inc. designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories worldwide.",
     "base_price": 189.0, "pe": 28.5, "eps": 6.64, "div_yield": 0.55, "market_cap": 2900e9},
    {"symbol": "MSFT", "name": "Microsoft Corporation", "sector": "Technology", "industry": "Software",
     "about": "Microsoft develops and supports software, services, devices, and solutions worldwide.",
     "base_price": 412.0, "pe": 35.2, "eps": 11.70, "div_yield": 0.72, "market_cap": 3100e9},
    {"symbol": "GOOGL", "name": "Alphabet Inc.", "sector": "Technology", "industry": "Internet Services",
     "about": "Alphabet provides online advertising services in the United States, Europe, and internationally.",
     "base_price": 171.0, "pe": 24.8, "eps": 6.90, "div_yield": 0.0, "market_cap": 2100e9},
    {"symbol": "AMZN", "name": "Amazon.com, Inc.", "sector": "Technology", "industry": "E-Commerce",
     "about": "Amazon engages in the retail sale of consumer products, advertising, and cloud computing services.",
     "base_price": 185.0, "pe": 58.0, "eps": 3.19, "div_yield": 0.0, "market_cap": 1900e9},
    {"symbol": "NVDA", "name": "NVIDIA Corporation", "sector": "Technology", "industry": "Semiconductors",
     "about": "NVIDIA provides graphics and compute networking solutions.",
     "base_price": 875.0, "pe": 65.0, "eps": 13.46, "div_yield": 0.02, "market_cap": 2200e9},
    {"symbol": "META", "name": "Meta Platforms, Inc.", "sector": "Technology", "industry": "Social Media",
     "about": "Meta builds technologies that help people connect, find communities, and grow businesses.",
     "base_price": 505.0, "pe": 27.0, "eps": 18.70, "div_yield": 0.40, "market_cap": 1300e9},
    {"symbol": "AMD", "name": "Advanced Micro Devices, Inc.", "sector": "Technology", "industry": "Semiconductors",
     "about": "AMD operates as a semiconductor company offering x86 microprocessors and GPUs.",
     "base_price": 160.0, "pe": 45.0, "eps": 3.56, "div_yield": 0.0, "market_cap": 260e9},
    {"symbol": "INTC", "name": "Intel Corporation", "sector": "Technology", "industry": "Semiconductors",
     "about": "Intel designs and manufactures computing and related products worldwide.",
     "base_price": 43.0, "pe": 28.0, "eps": 1.54, "div_yield": 1.15, "market_cap": 180e9},
    {"symbol": "CRM", "name": "Salesforce, Inc.", "sector": "Technology", "industry": "Software",
     "about": "Salesforce provides customer relationship management technology worldwide.",
     "base_price": 270.0, "pe": 55.0, "eps": 4.91, "div_yield": 0.60, "market_cap": 260e9},
    {"symbol": "ADBE", "name": "Adobe Inc.", "sector": "Technology", "industry": "Software",
     "about": "Adobe operates as a diversified software company worldwide.",
     "base_price": 550.0, "pe": 42.0, "eps": 13.10, "div_yield": 0.0, "market_cap": 245e9},
    {"symbol": "ORCL", "name": "Oracle Corporation", "sector": "Technology", "industry": "Software",
     "about": "Oracle provides products and services that address enterprise information technology environments.",
     "base_price": 125.0, "pe": 32.0, "eps": 3.91, "div_yield": 1.28, "market_cap": 340e9},
    {"symbol": "CSCO", "name": "Cisco Systems, Inc.", "sector": "Technology", "industry": "Networking",
     "about": "Cisco designs and sells networking equipment, software, and services.",
     "base_price": 52.0, "pe": 15.0, "eps": 3.47, "div_yield": 2.92, "market_cap": 215e9},
    {"symbol": "IBM", "name": "International Business Machines Corporation", "sector": "Technology", "industry": "IT Services",
     "about": "IBM provides integrated solutions and products in cloud, AI, and consulting.",
     "base_price": 168.0, "pe": 22.0, "eps": 7.64, "div_yield": 3.96, "market_cap": 152e9},
    {"symbol": "QCOM", "name": "Qualcomm Incorporated", "sector": "Technology", "industry": "Semiconductors",
     "about": "Qualcomm develops semiconductor products for wireless technology.",
     "base_price": 160.0, "pe": 22.0, "eps": 7.27, "div_yield": 2.0, "market_cap": 178e9},
    {"symbol": "TXN", "name": "Texas Instruments Incorporated", "sector": "Technology", "industry": "Semiconductors",
     "about": "Texas Instruments designs, manufactures, and sells semiconductors worldwide.",
     "base_price": 170.0, "pe": 28.0, "eps": 6.07, "div_yield": 2.94, "market_cap": 155e9},
    {"symbol": "AVGO", "name": "Broadcom Inc.", "sector": "Technology", "industry": "Semiconductors",
     "about": "Broadcom designs, develops, and supplies semiconductor and infrastructure software solutions.",
     "base_price": 1350.0, "pe": 38.0, "eps": 35.53, "div_yield": 1.55, "market_cap": 630e9},
    {"symbol": "ANET", "name": "Arista Networks, Inc.", "sector": "Technology", "industry": "Networking",
     "about": "Arista Networks develops cloud networking solutions for data center and campus environments.",
     "base_price": 280.0, "pe": 40.0, "eps": 7.00, "div_yield": 0.0, "market_cap": 88e9},
    {"symbol": "PANW", "name": "Palo Alto Networks, Inc.", "sector": "Technology", "industry": "Cybersecurity",
     "about": "Palo Alto Networks provides cybersecurity solutions worldwide.",
     "base_price": 310.0, "pe": 48.0, "eps": 6.46, "div_yield": 0.0, "market_cap": 100e9},
    {"symbol": "NOW", "name": "ServiceNow, Inc.", "sector": "Technology", "industry": "Software",
     "about": "ServiceNow provides enterprise cloud computing solutions for digital workflows.",
     "base_price": 740.0, "pe": 65.0, "eps": 11.38, "div_yield": 0.0, "market_cap": 152e9},
    {"symbol": "SNOW", "name": "Snowflake Inc.", "sector": "Technology", "industry": "Cloud Computing",
     "about": "Snowflake provides a cloud-based data platform in the United States and internationally.",
     "base_price": 195.0, "pe": 0.0, "eps": -0.60, "div_yield": 0.0, "market_cap": 64e9},

    # ── Consumer Cyclical ──────────────────────────────────────────────
    {"symbol": "TSLA", "name": "Tesla, Inc.", "sector": "Consumer Cyclical", "industry": "Auto Manufacturers",
     "about": "Tesla designs, develops, manufactures, sells, and leases electric vehicles and energy generation and storage systems.",
     "base_price": 248.0, "pe": 62.0, "eps": 4.0, "div_yield": 0.0, "market_cap": 790e9},
    {"symbol": "NKE", "name": "NIKE, Inc.", "sector": "Consumer Cyclical", "industry": "Footwear & Accessories",
     "about": "NIKE designs, develops, markets, and sells athletic footwear, apparel, and equipment.",
     "base_price": 98.0, "pe": 28.0, "eps": 3.50, "div_yield": 1.40, "market_cap": 148e9},
    {"symbol": "SBUX", "name": "Starbucks Corporation", "sector": "Consumer Cyclical", "industry": "Restaurants",
     "about": "Starbucks operates as a roaster, marketer, and retailer of specialty coffee worldwide.",
     "base_price": 95.0, "pe": 24.0, "eps": 3.96, "div_yield": 2.30, "market_cap": 108e9},
    {"symbol": "DIS", "name": "The Walt Disney Company", "sector": "Consumer Cyclical", "industry": "Entertainment",
     "about": "Disney operates entertainment businesses including theme parks, studios, and streaming services.",
     "base_price": 112.0, "pe": 35.0, "eps": 3.20, "div_yield": 0.0, "market_cap": 205e9},
    {"symbol": "HD", "name": "The Home Depot, Inc.", "sector": "Consumer Cyclical", "industry": "Home Improvement",
     "about": "Home Depot operates as a home improvement retailer selling building materials and services.",
     "base_price": 370.0, "pe": 24.0, "eps": 15.42, "div_yield": 2.35, "market_cap": 365e9},
    {"symbol": "MCD", "name": "McDonald's Corporation", "sector": "Consumer Cyclical", "industry": "Restaurants",
     "about": "McDonald's operates and franchises restaurants globally serving a varied menu.",
     "base_price": 290.0, "pe": 25.0, "eps": 11.60, "div_yield": 2.20, "market_cap": 210e9},

    # ── Consumer Defensive ─────────────────────────────────────────────
    {"symbol": "KO", "name": "The Coca-Cola Company", "sector": "Consumer Defensive", "industry": "Beverages",
     "about": "Coca-Cola manufactures, markets, and distributes nonalcoholic beverages worldwide.",
     "base_price": 60.0, "pe": 23.0, "eps": 2.61, "div_yield": 3.10, "market_cap": 260e9},
    {"symbol": "PEP", "name": "PepsiCo, Inc.", "sector": "Consumer Defensive", "industry": "Beverages",
     "about": "PepsiCo manufactures, markets, and distributes beverages and convenient foods worldwide.",
     "base_price": 172.0, "pe": 24.0, "eps": 7.17, "div_yield": 2.80, "market_cap": 237e9},
    {"symbol": "PG", "name": "The Procter & Gamble Company", "sector": "Consumer Defensive", "industry": "Household Products",
     "about": "Procter & Gamble provides branded consumer packaged goods worldwide.",
     "base_price": 160.0, "pe": 26.0, "eps": 6.15, "div_yield": 2.45, "market_cap": 380e9},
    {"symbol": "WMT", "name": "Walmart Inc.", "sector": "Consumer Defensive", "industry": "Discount Stores",
     "about": "Walmart operates retail, wholesale, and e-commerce businesses worldwide.",
     "base_price": 165.0, "pe": 28.0, "eps": 5.89, "div_yield": 1.40, "market_cap": 445e9},
    {"symbol": "COST", "name": "Costco Wholesale Corporation", "sector": "Consumer Defensive", "industry": "Discount Stores",
     "about": "Costco operates membership-only warehouse clubs worldwide.",
     "base_price": 720.0, "pe": 47.0, "eps": 15.32, "div_yield": 0.58, "market_cap": 320e9},

    # ── Healthcare ─────────────────────────────────────────────────────
    {"symbol": "JNJ", "name": "Johnson & Johnson", "sector": "Healthcare", "industry": "Pharmaceuticals",
     "about": "Johnson & Johnson researches, develops, manufactures, and sells health care products worldwide.",
     "base_price": 158.0, "pe": 15.0, "eps": 10.53, "div_yield": 2.95, "market_cap": 380e9},
    {"symbol": "UNH", "name": "UnitedHealth Group Incorporated", "sector": "Healthcare", "industry": "Health Plans",
     "about": "UnitedHealth Group operates as a diversified health care company in the United States.",
     "base_price": 525.0, "pe": 22.0, "eps": 23.86, "div_yield": 1.35, "market_cap": 490e9},
    {"symbol": "PFE", "name": "Pfizer Inc.", "sector": "Healthcare", "industry": "Pharmaceuticals",
     "about": "Pfizer discovers, develops, manufactures, markets, and sells biopharmaceutical products worldwide.",
     "base_price": 28.0, "pe": 12.0, "eps": 2.33, "div_yield": 5.80, "market_cap": 158e9},
    {"symbol": "ABBV", "name": "AbbVie Inc.", "sector": "Healthcare", "industry": "Pharmaceuticals",
     "about": "AbbVie discovers, develops, manufactures, and sells pharmaceuticals worldwide.",
     "base_price": 165.0, "pe": 14.0, "eps": 11.79, "div_yield": 3.70, "market_cap": 290e9},
    {"symbol": "MRK", "name": "Merck & Co., Inc.", "sector": "Healthcare", "industry": "Pharmaceuticals",
     "about": "Merck operates as a global health care company offering pharmaceutical and vaccine products.",
     "base_price": 120.0, "pe": 16.0, "eps": 7.50, "div_yield": 2.55, "market_cap": 305e9},
    {"symbol": "LLY", "name": "Eli Lilly and Company", "sector": "Healthcare", "industry": "Pharmaceuticals",
     "about": "Eli Lilly discovers, develops, and markets pharmaceutical products worldwide.",
     "base_price": 780.0, "pe": 105.0, "eps": 7.43, "div_yield": 0.65, "market_cap": 740e9},
    {"symbol": "TMO", "name": "Thermo Fisher Scientific Inc.", "sector": "Healthcare", "industry": "Diagnostics & Research",
     "about": "Thermo Fisher Scientific provides life sciences solutions, analytical instruments, and laboratory products.",
     "base_price": 570.0, "pe": 32.0, "eps": 17.81, "div_yield": 0.24, "market_cap": 220e9},
    {"symbol": "ABT", "name": "Abbott Laboratories", "sector": "Healthcare", "industry": "Medical Devices",
     "about": "Abbott discovers, develops, manufactures, and sells health care products worldwide.",
     "base_price": 110.0, "pe": 22.0, "eps": 5.00, "div_yield": 1.90, "market_cap": 190e9},
    {"symbol": "BMY", "name": "Bristol-Myers Squibb Company", "sector": "Healthcare", "industry": "Pharmaceuticals",
     "about": "Bristol-Myers Squibb discovers, develops, and delivers medicines for serious diseases.",
     "base_price": 52.0, "pe": 8.0, "eps": 6.50, "div_yield": 4.50, "market_cap": 105e9},
    {"symbol": "AMGN", "name": "Amgen Inc.", "sector": "Healthcare", "industry": "Biotechnology",
     "about": "Amgen discovers, develops, manufactures, and delivers human therapeutics worldwide.",
     "base_price": 280.0, "pe": 20.0, "eps": 14.00, "div_yield": 3.15, "market_cap": 150e9},
    {"symbol": "GILD", "name": "Gilead Sciences, Inc.", "sector": "Healthcare", "industry": "Biotechnology",
     "about": "Gilead Sciences discovers, develops, and commercializes medicines for life-threatening diseases.",
     "base_price": 82.0, "pe": 13.0, "eps": 6.31, "div_yield": 3.72, "market_cap": 102e9},
    {"symbol": "VRTX", "name": "Vertex Pharmaceuticals Incorporated", "sector": "Healthcare", "industry": "Biotechnology",
     "about": "Vertex Pharmaceuticals develops and commercializes therapies for treating cystic fibrosis.",
     "base_price": 410.0, "pe": 28.0, "eps": 14.64, "div_yield": 0.0, "market_cap": 105e9},
    {"symbol": "ISRG", "name": "Intuitive Surgical, Inc.", "sector": "Healthcare", "industry": "Medical Instruments",
     "about": "Intuitive Surgical develops, manufactures, and markets robotic-assisted surgical systems.",
     "base_price": 370.0, "pe": 65.0, "eps": 5.69, "div_yield": 0.0, "market_cap": 130e9},
    {"symbol": "MDT", "name": "Medtronic plc", "sector": "Healthcare", "industry": "Medical Devices",
     "about": "Medtronic develops and manufactures device-based medical therapies worldwide.",
     "base_price": 82.0, "pe": 16.0, "eps": 5.13, "div_yield": 3.35, "market_cap": 110e9},

    # ── Financial ──────────────────────────────────────────────────────
    {"symbol": "JPM", "name": "JPMorgan Chase & Co.", "sector": "Financial", "industry": "Banks",
     "about": "JPMorgan Chase operates as a financial services company providing investment banking and financial transaction services.",
     "base_price": 195.0, "pe": 11.0, "eps": 17.73, "div_yield": 2.20, "market_cap": 565e9},
    {"symbol": "BAC", "name": "Bank of America Corporation", "sector": "Financial", "industry": "Banks",
     "about": "Bank of America provides banking and financial products and services worldwide.",
     "base_price": 34.0, "pe": 10.0, "eps": 3.40, "div_yield": 2.75, "market_cap": 270e9},
    {"symbol": "WFC", "name": "Wells Fargo & Company", "sector": "Financial", "industry": "Banks",
     "about": "Wells Fargo provides banking, investment, and mortgage products and services.",
     "base_price": 48.0, "pe": 11.0, "eps": 4.36, "div_yield": 2.70, "market_cap": 178e9},
    {"symbol": "GS", "name": "The Goldman Sachs Group, Inc.", "sector": "Financial", "industry": "Investment Banking",
     "about": "Goldman Sachs operates as a global investment banking and securities firm.",
     "base_price": 420.0, "pe": 14.0, "eps": 30.00, "div_yield": 2.40, "market_cap": 142e9},
    {"symbol": "MS", "name": "Morgan Stanley", "sector": "Financial", "industry": "Investment Banking",
     "about": "Morgan Stanley provides financial advisory and securities services worldwide.",
     "base_price": 92.0, "pe": 15.0, "eps": 6.13, "div_yield": 3.40, "market_cap": 150e9},
    {"symbol": "BLK", "name": "BlackRock, Inc.", "sector": "Financial", "industry": "Asset Management",
     "about": "BlackRock provides investment management, risk management, and advisory services worldwide.",
     "base_price": 810.0, "pe": 22.0, "eps": 36.82, "div_yield": 2.50, "market_cap": 120e9},
    {"symbol": "SCHW", "name": "The Charles Schwab Corporation", "sector": "Financial", "industry": "Brokerage",
     "about": "Charles Schwab provides wealth management, securities brokerage, and financial advisory services.",
     "base_price": 68.0, "pe": 22.0, "eps": 3.09, "div_yield": 1.45, "market_cap": 125e9},
    {"symbol": "AXP", "name": "American Express Company", "sector": "Financial", "industry": "Credit Services",
     "about": "American Express operates as a globally integrated payments company.",
     "base_price": 220.0, "pe": 18.0, "eps": 12.22, "div_yield": 1.20, "market_cap": 165e9},
    {"symbol": "V", "name": "Visa Inc.", "sector": "Financial", "industry": "Credit Services",
     "about": "Visa operates a global digital payments network facilitating fund transfers.",
     "base_price": 280.0, "pe": 30.0, "eps": 9.33, "div_yield": 0.75, "market_cap": 570e9},
    {"symbol": "MA", "name": "Mastercard Incorporated", "sector": "Financial", "industry": "Credit Services",
     "about": "Mastercard provides transaction processing and related payment services worldwide.",
     "base_price": 450.0, "pe": 35.0, "eps": 12.86, "div_yield": 0.55, "market_cap": 430e9},

    # ── Energy ─────────────────────────────────────────────────────────
    {"symbol": "XOM", "name": "Exxon Mobil Corporation", "sector": "Energy", "industry": "Oil & Gas",
     "about": "Exxon Mobil explores, produces, and sells crude oil, natural gas, and petroleum products.",
     "base_price": 105.0, "pe": 12.0, "eps": 8.75, "div_yield": 3.50, "market_cap": 440e9},
    {"symbol": "CVX", "name": "Chevron Corporation", "sector": "Energy", "industry": "Oil & Gas",
     "about": "Chevron engages in integrated energy and chemicals operations worldwide.",
     "base_price": 155.0, "pe": 12.0, "eps": 12.92, "div_yield": 3.90, "market_cap": 295e9},
    {"symbol": "COP", "name": "ConocoPhillips", "sector": "Energy", "industry": "Oil & Gas E&P",
     "about": "ConocoPhillips explores for, produces, transports, and markets crude oil and natural gas.",
     "base_price": 115.0, "pe": 11.0, "eps": 10.45, "div_yield": 1.80, "market_cap": 140e9},
    {"symbol": "SLB", "name": "Schlumberger Limited", "sector": "Energy", "industry": "Oil & Gas Services",
     "about": "Schlumberger provides technology and services to the energy industry worldwide.",
     "base_price": 52.0, "pe": 17.0, "eps": 3.06, "div_yield": 1.85, "market_cap": 75e9},
    {"symbol": "EOG", "name": "EOG Resources, Inc.", "sector": "Energy", "industry": "Oil & Gas E&P",
     "about": "EOG Resources explores, develops, produces, and markets crude oil and natural gas.",
     "base_price": 120.0, "pe": 10.0, "eps": 12.00, "div_yield": 2.50, "market_cap": 70e9},

    # ── Industrial ─────────────────────────────────────────────────────
    {"symbol": "CAT", "name": "Caterpillar Inc.", "sector": "Industrial", "industry": "Farm & Construction Machinery",
     "about": "Caterpillar manufactures construction and mining equipment, engines, and turbines.",
     "base_price": 310.0, "pe": 16.0, "eps": 19.38, "div_yield": 1.70, "market_cap": 158e9},
    {"symbol": "BA", "name": "The Boeing Company", "sector": "Industrial", "industry": "Aerospace & Defense",
     "about": "Boeing designs, develops, manufactures, and services commercial jetliners and defense products.",
     "base_price": 215.0, "pe": 0.0, "eps": -4.50, "div_yield": 0.0, "market_cap": 130e9},
    {"symbol": "HON", "name": "Honeywell International Inc.", "sector": "Industrial", "industry": "Conglomerates",
     "about": "Honeywell operates as a diversified technology and manufacturing company worldwide.",
     "base_price": 205.0, "pe": 23.0, "eps": 8.91, "div_yield": 2.05, "market_cap": 135e9},
    {"symbol": "UPS", "name": "United Parcel Service, Inc.", "sector": "Industrial", "industry": "Logistics",
     "about": "UPS provides letter and package delivery, transportation, and logistics services worldwide.",
     "base_price": 155.0, "pe": 16.0, "eps": 9.69, "div_yield": 4.20, "market_cap": 132e9},
    {"symbol": "GE", "name": "GE Aerospace", "sector": "Industrial", "industry": "Aerospace & Defense",
     "about": "GE Aerospace designs and produces commercial and military aircraft engines and systems.",
     "base_price": 160.0, "pe": 35.0, "eps": 4.57, "div_yield": 0.25, "market_cap": 175e9},
    {"symbol": "RTX", "name": "RTX Corporation", "sector": "Industrial", "industry": "Aerospace & Defense",
     "about": "RTX provides systems and services for the commercial, military, and government customers worldwide.",
     "base_price": 95.0, "pe": 18.0, "eps": 5.28, "div_yield": 2.35, "market_cap": 140e9},
    {"symbol": "LMT", "name": "Lockheed Martin Corporation", "sector": "Industrial", "industry": "Aerospace & Defense",
     "about": "Lockheed Martin researches, designs, develops, and manufactures advanced technology products for defense.",
     "base_price": 460.0, "pe": 17.0, "eps": 27.06, "div_yield": 2.65, "market_cap": 112e9},
    {"symbol": "DE", "name": "Deere & Company", "sector": "Industrial", "industry": "Farm & Construction Machinery",
     "about": "Deere & Company manufactures and distributes equipment for agriculture, construction, and forestry.",
     "base_price": 390.0, "pe": 13.0, "eps": 30.00, "div_yield": 1.35, "market_cap": 115e9},

    # ── ETFs ───────────────────────────────────────────────────────────
    {"symbol": "SPY", "name": "SPDR S&P 500 ETF Trust", "sector": "ETF", "industry": "Large Blend",
     "about": "SPY tracks the S&P 500 Index, providing broad exposure to large-cap U.S. equities.",
     "base_price": 475.0, "pe": 0.0, "eps": 0.0, "div_yield": 1.35, "market_cap": 480e9},
    {"symbol": "QQQ", "name": "Invesco QQQ Trust", "sector": "ETF", "industry": "Large Growth",
     "about": "QQQ tracks the Nasdaq-100 Index, focusing on non-financial large-cap stocks.",
     "base_price": 410.0, "pe": 0.0, "eps": 0.0, "div_yield": 0.55, "market_cap": 220e9},
    {"symbol": "VTI", "name": "Vanguard Total Stock Market ETF", "sector": "ETF", "industry": "Total Market",
     "about": "VTI tracks the CRSP US Total Market Index, covering the entire U.S. equity market.",
     "base_price": 245.0, "pe": 0.0, "eps": 0.0, "div_yield": 1.40, "market_cap": 380e9},
    {"symbol": "VXUS", "name": "Vanguard Total International Stock ETF", "sector": "ETF", "industry": "International",
     "about": "VXUS tracks the FTSE Global All Cap ex US Index for international equity exposure.",
     "base_price": 58.0, "pe": 0.0, "eps": 0.0, "div_yield": 3.10, "market_cap": 70e9},
    {"symbol": "BND", "name": "Vanguard Total Bond Market ETF", "sector": "ETF", "industry": "Bonds",
     "about": "BND tracks the Bloomberg U.S. Aggregate Float Adjusted Index for broad bond exposure.",
     "base_price": 73.0, "pe": 0.0, "eps": 0.0, "div_yield": 3.60, "market_cap": 110e9},
    {"symbol": "SCHD", "name": "Schwab U.S. Dividend Equity ETF", "sector": "ETF", "industry": "Dividend",
     "about": "SCHD tracks the Dow Jones U.S. Dividend 100 Index, focusing on high-dividend U.S. stocks.",
     "base_price": 78.0, "pe": 0.0, "eps": 0.0, "div_yield": 3.45, "market_cap": 55e9},
    {"symbol": "VOO", "name": "Vanguard S&P 500 ETF", "sector": "ETF", "industry": "Large Blend",
     "about": "VOO tracks the S&P 500 Index with low expense ratio for broad large-cap exposure.",
     "base_price": 437.0, "pe": 0.0, "eps": 0.0, "div_yield": 1.35, "market_cap": 430e9},
    {"symbol": "IWM", "name": "iShares Russell 2000 ETF", "sector": "ETF", "industry": "Small Blend",
     "about": "IWM tracks the Russell 2000 Index, providing exposure to U.S. small-cap stocks.",
     "base_price": 205.0, "pe": 0.0, "eps": 0.0, "div_yield": 1.30, "market_cap": 65e9},
    {"symbol": "GLD", "name": "SPDR Gold Shares", "sector": "ETF", "industry": "Commodities",
     "about": "GLD tracks the price of gold bullion held in London vaults.",
     "base_price": 195.0, "pe": 0.0, "eps": 0.0, "div_yield": 0.0, "market_cap": 60e9},
    {"symbol": "TLT", "name": "iShares 20+ Year Treasury Bond ETF", "sector": "ETF", "industry": "Long-Term Bonds",
     "about": "TLT tracks an index of U.S. Treasury bonds with remaining maturities greater than twenty years.",
     "base_price": 95.0, "pe": 0.0, "eps": 0.0, "div_yield": 3.80, "market_cap": 40e9},
    {"symbol": "XLK", "name": "Technology Select Sector SPDR Fund", "sector": "ETF", "industry": "Sector Technology",
     "about": "XLK tracks the Technology Select Sector Index, providing concentrated exposure to U.S. large-cap technology stocks.",
     "base_price": 205.0, "pe": 0.0, "eps": 0.0, "div_yield": 0.65, "market_cap": 65e9},
    {"symbol": "SMH", "name": "VanEck Semiconductor ETF", "sector": "ETF", "industry": "Sector Semiconductors",
     "about": "SMH tracks the MVIS US Listed Semiconductor 25 Index, providing exposure to the largest U.S. semiconductor companies.",
     "base_price": 230.0, "pe": 0.0, "eps": 0.0, "div_yield": 0.55, "market_cap": 22e9},
    {"symbol": "VEA", "name": "Vanguard FTSE Developed Markets ETF", "sector": "ETF", "industry": "International",
     "about": "VEA tracks the FTSE Developed All Cap ex US Index, providing exposure to large- mid- and small-cap stocks in developed markets outside the U.S.",
     "base_price": 48.0, "pe": 0.0, "eps": 0.0, "div_yield": 3.10, "market_cap": 105e9},
    {"symbol": "VTIP", "name": "Vanguard Short-Term Inflation-Protected Securities ETF", "sector": "ETF", "industry": "Inflation-Protected Bonds",
     "about": "VTIP tracks an index of U.S. Treasury inflation-protected securities with maturities of less than five years.",
     "base_price": 49.0, "pe": 0.0, "eps": 0.0, "div_yield": 3.50, "market_cap": 14e9},

    # ── Additional Consumer Cyclical / Defensive ───────────────────────
    {"symbol": "LOW", "name": "Lowe's Companies, Inc.", "sector": "Consumer Cyclical", "industry": "Home Improvement",
     "about": "Lowe's operates as a home improvement retailer in the United States.",
     "base_price": 250.0, "pe": 20.0, "eps": 12.50, "div_yield": 1.80, "market_cap": 145e9},
    {"symbol": "TGT", "name": "Target Corporation", "sector": "Consumer Defensive", "industry": "Discount Stores",
     "about": "Target operates as a general merchandise retailer in the United States.",
     "base_price": 145.0, "pe": 16.0, "eps": 9.06, "div_yield": 3.00, "market_cap": 67e9},

    # ── Additional (referenced by task YAMLs) ─────────────────────────
    {"symbol": "NFLX", "name": "Netflix, Inc.", "sector": "Technology", "industry": "Entertainment",
     "about": "Netflix provides entertainment services and is one of the world's leading streaming platforms.",
     "base_price": 620.0, "pe": 45.0, "eps": 13.78, "div_yield": 0.0, "market_cap": 270e9},
    {"symbol": "T", "name": "AT&T Inc.", "sector": "Technology", "industry": "Telecom Services",
     "about": "AT&T provides telecommunications, media, and technology services worldwide.",
     "base_price": 17.50, "pe": 8.0, "eps": 2.19, "div_yield": 6.30, "market_cap": 125e9},
    {"symbol": "VZ", "name": "Verizon Communications Inc.", "sector": "Technology", "industry": "Telecom Services",
     "about": "Verizon provides communications, technology, and entertainment products and services.",
     "base_price": 40.0, "pe": 9.5, "eps": 4.21, "div_yield": 6.50, "market_cap": 168e9},
    {"symbol": "MO", "name": "Altria Group, Inc.", "sector": "Consumer Defensive", "industry": "Tobacco",
     "about": "Altria produces and sells smokeable and oral tobacco products in the United States.",
     "base_price": 45.0, "pe": 9.0, "eps": 5.00, "div_yield": 8.50, "market_cap": 80e9},
    {"symbol": "PM", "name": "Philip Morris International Inc.", "sector": "Consumer Defensive", "industry": "Tobacco",
     "about": "Philip Morris manufactures and sells cigarettes and smoke-free products internationally.",
     "base_price": 95.0, "pe": 17.0, "eps": 5.59, "div_yield": 5.40, "market_cap": 148e9},
    {"symbol": "SQ", "name": "Block, Inc.", "sector": "Financial", "industry": "Software",
     "about": "Block provides financial services and digital payments through its Square and Cash App ecosystems.",
     "base_price": 68.0, "pe": 55.0, "eps": 1.24, "div_yield": 0.0, "market_cap": 41e9},
    {"symbol": "PLTR", "name": "Palantir Technologies Inc.", "sector": "Technology", "industry": "Software",
     "about": "Palantir builds and deploys software platforms for the intelligence community and commercial enterprises.",
     "base_price": 22.0, "pe": 200.0, "eps": 0.11, "div_yield": 0.0, "market_cap": 48e9},
    {"symbol": "GME", "name": "GameStop Corp.", "sector": "Consumer Cyclical", "industry": "Specialty Retail",
     "about": "GameStop operates as a specialty retailer of games, entertainment products, and technology.",
     "base_price": 15.0, "pe": 0.0, "eps": -0.35, "div_yield": 0.0, "market_cap": 4.5e9},
    {"symbol": "AMC", "name": "AMC Entertainment Holdings, Inc.", "sector": "Consumer Cyclical", "industry": "Entertainment",
     "about": "AMC is the world's largest movie theater chain, operating theatres across the US and internationally.",
     "base_price": 5.50, "pe": 0.0, "eps": -1.20, "div_yield": 0.0, "market_cap": 2.5e9},
]


# ---------------------------------------------------------------------------
# RobinhoodSeedContext
# ---------------------------------------------------------------------------

class RobinhoodSeedContext:
    """Mutable accumulator threaded through every Robinhood seed builder step.

    Exposes shared helpers so builders can operate against one deterministic
    state interface.
    """

    def __init__(
        self,
        seed: int,
        rng: random.Random,
        fake: Any,
        now: datetime,
        base: dict[str, Any],
    ) -> None:
        self.seed = seed
        self.rng = rng
        self.fake = fake
        self.now = now
        self.base = base
        self.actors: dict[str, ResolvedActor] = {}
        self.outputs: dict[str, Any] = {}
        self.counters: dict[str, int] = {}

        self.owner_name: str = base.get("owner_name", "Alex Thompson")
        self.owner_email: str = base.get("owner_email", "alex.thompson@thornton.com")

    # -- ID generation -----------------------------------------------------

    def next_id(self, prefix: str) -> str:
        """Return a monotonically increasing id like ``pos_1``."""
        self.counters[prefix] = self.counters.get(prefix, 0) + 1
        return f"{prefix}_{self.counters[prefix]}"

    # -- Name / email helpers ----------------------------------------------

    def email_for_name(self, name: str, domain: str | None = None) -> str:
        local = "".join(
            ch.lower() for ch in name if ch.isalnum() or ch == " "
        ).replace(" ", ".")
        local = ".".join(part for part in local.split(".") if part) or "contact"
        domain = domain or f"{self.fake.domain_word()}.com"
        return f"{local}@{domain}"

    @staticmethod
    def first_name(name: str) -> str:
        return name.split()[0]

    # -- Actor resolution --------------------------------------------------

    def resolve_actor(
        self,
        key: str,
        domain: str = "baseline.co",
        is_vip: bool = False,
        name: str | None = None,
    ) -> ResolvedActor:
        """Generate a deterministic actor and cache it under *key*."""
        if key in self.actors:
            return self.actors[key]
        name = name or self.fake.name()
        actor = ResolvedActor(
            name=name,
            email=self.email_for_name(name, domain=domain),
            first_name=self.first_name(name),
        )
        self.actors[key] = actor
        return actor

    def get_actor(self, key: str) -> ResolvedActor:
        """Return a previously resolved actor (raises KeyError if missing)."""
        return self.actors[key]

    # -- Stock helpers -----------------------------------------------------

    def get_stock_data(self, symbol: str) -> dict[str, Any] | None:
        """Look up a stock from _STOCK_SEED_DATA by symbol."""
        for sd in _STOCK_SEED_DATA:
            if sd["symbol"] == symbol:
                return sd
        return None

    def get_stock_from_base(self, symbol: str) -> Stock | None:
        """Look up a Stock already loaded into ctx.base['stocks']."""
        for s in self.base.get("stocks", []):
            if s.symbol == symbol:
                return s
        return None

    def pick_symbols(self, count: int, from_base: bool = True) -> list[str]:
        """Pick *count* random symbols from the stock universe in base."""
        stocks = self.base.get("stocks", [])
        if not stocks:
            return []
        syms = [s.symbol for s in stocks]
        self.rng.shuffle(syms)
        return syms[:min(count, len(syms))]


# ---------------------------------------------------------------------------
# Builder registry
# ---------------------------------------------------------------------------

BuilderFn = Callable[["RobinhoodSeedContext", dict[str, Any]], dict[str, Any]]

ROBINHOOD_BUILDER_REGISTRY: dict[str, BuilderFn] = {}


def _register(name: str) -> Callable[[BuilderFn], BuilderFn]:
    def decorator(fn: BuilderFn) -> BuilderFn:
        ROBINHOOD_BUILDER_REGISTRY[name] = fn
        return fn
    return decorator


# ---------------------------------------------------------------------------
# 1. stock_universe
# ---------------------------------------------------------------------------

@_register("stock_universe")
def build_stock_universe(ctx: RobinhoodSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Generate a realistic stock universe from hardcoded seed data.

    Params
    ------
    count : int            -- how many stocks to include (default 30)
    must_include : list    -- symbols that MUST be present
    """
    count = params.get("count", 30)
    must_include = set(params.get("must_include", []))

    # Select stocks: must_include first, then random fill
    available = list(_STOCK_SEED_DATA)
    selected = [s for s in available if s["symbol"] in must_include]
    remaining = [s for s in available if s["symbol"] not in must_include]
    ctx.rng.shuffle(remaining)
    selected.extend(remaining[: max(0, count - len(selected))])

    if "stocks" not in ctx.base:
        ctx.base["stocks"] = []

    outputs: dict[str, Any] = {}
    for sd in selected:
        # Deterministic price perturbation
        pct_change = ctx.rng.uniform(-0.08, 0.08)
        price = Decimal(str(round(sd["base_price"] * (1 + pct_change), 2)))
        prev_close = Decimal(str(round(float(price) * (1 + ctx.rng.uniform(-0.03, 0.03)), 2)))
        day_change = price - prev_close

        # Generate 90 days historical
        historical: list[HistoricalPrice] = []
        p = float(sd["base_price"])
        for i in range(90, 0, -1):
            p *= (1 + ctx.rng.uniform(-0.025, 0.025))
            historical.append(HistoricalPrice(
                date=(ctx.now - timedelta(days=i)).date(),
                close=Decimal(str(round(p, 2))),
            ))

        # 52-week range from historical + extended
        closes = [float(h.close) for h in historical]
        high_52 = Decimal(str(round(max(closes) * ctx.rng.uniform(1.0, 1.15), 2)))
        low_52 = Decimal(str(round(min(closes) * ctx.rng.uniform(0.85, 1.0), 2)))

        stock = Stock(
            symbol=sd["symbol"],
            name=sd["name"],
            asset_type="etf" if sd["symbol"] in _ETF_SYMBOLS else "stock",
            price=price,
            previous_close=prev_close,
            day_change=day_change,
            day_change_pct=Decimal(str(round(float(day_change / prev_close * 100), 2))),
            bid=price - Decimal("0.01"),
            ask=price + Decimal("0.01"),
            bid_size=ctx.rng.randint(100, 5000),
            ask_size=ctx.rng.randint(100, 5000),
            volume=ctx.rng.randint(1_000_000, 80_000_000),
            avg_volume=ctx.rng.randint(5_000_000, 60_000_000),
            market_cap=Decimal(str(int(sd["market_cap"]))),
            pe_ratio=Decimal(str(sd["pe"])) if sd["pe"] is not None and sd["pe"] != 0 else None,
            eps=Decimal(str(sd["eps"])) if sd["eps"] is not None else None,
            dividend_yield=Decimal(str(sd["div_yield"])) if sd["div_yield"] is not None else None,
            fifty_two_week_high=high_52,
            fifty_two_week_low=low_52,
            sector=sd["sector"],
            industry=sd["industry"],
            about=sd["about"],
            historical_prices=historical,
        )
        ctx.base["stocks"].append(stock)
        outputs[f"stock_price_{stock.symbol}"] = stock.price

    return outputs


# ---------------------------------------------------------------------------
# 2. portfolio_basic
# ---------------------------------------------------------------------------

@_register("portfolio_basic")
def build_portfolio_basic(ctx: RobinhoodSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create positions from explicit params with single tax lots.

    Params
    ------
    stocks : list[str]        -- symbols
    quantities : list[str]    -- share quantities (as strings for Decimal)
    cost_bases : list[str]    -- cost basis per share (as strings for Decimal)
    """
    symbols = params["stocks"]
    quantities = params["quantities"]
    cost_bases = params["cost_bases"]

    if "positions" not in ctx.base:
        ctx.base["positions"] = []

    position_ids: list[str] = []
    created_positions: list[Position] = []
    total_value = Decimal("0")

    for sym, qty_s, cost_s in zip(symbols, quantities, cost_bases):
        qty = Decimal(str(qty_s))
        cost = Decimal(str(cost_s))
        stock = ctx.get_stock_from_base(sym)
        current_price = stock.price if stock else cost
        total = current_price * qty
        total_return = (current_price - cost) * qty
        total_return_pct = Decimal(str(round(float((current_price - cost) / cost * 100), 2))) if cost else Decimal("0")
        day_change_pct = stock.day_change_pct if stock else Decimal("0")

        pos_id = ctx.next_id("pos")
        acquired = (ctx.now - timedelta(days=ctx.rng.randint(30, 365))).date()

        pos = Position(
            id=pos_id,
            symbol=sym,
            name=stock.name if stock else sym,
            asset_type=stock.asset_type if stock else "stock",
            quantity=qty,
            avg_cost_basis=cost,
            current_price=current_price,
            day_change_pct=day_change_pct,
            total_return=total_return,
            total_return_pct=total_return_pct,
            lots=[TaxLot(shares=qty, cost_per_share=cost, acquired_date=acquired)],
        )
        ctx.base["positions"].append(pos)
        created_positions.append(pos)
        position_ids.append(pos_id)
        total_value += total

        if "transactions" not in ctx.base:
            ctx.base["transactions"] = []
        acquired_dt = datetime(acquired.year, acquired.month, acquired.day, tzinfo=timezone.utc)
        ctx.base["transactions"].append(Transaction(
            id=ctx.next_id("txn"),
            type="buy",
            symbol=sym,
            quantity=qty,
            amount=qty * cost,
            description=f"Bought {qty} shares of {sym} @ ${cost:.2f}",
            timestamp=acquired_dt,
        ))

    ctx.base["portfolio_value"] = ctx.base.get("portfolio_value", Decimal("0")) + total_value
    best_symbol = max(created_positions, key=lambda position: position.total_return_pct).symbol if created_positions else None
    worst_symbol = min(created_positions, key=lambda position: position.total_return_pct).symbol if created_positions else None
    largest_position_symbol = max(created_positions, key=lambda position: position.current_price * position.quantity).symbol if created_positions else None
    tech_candidates = [
        position for position in created_positions
        if ctx.get_stock_from_base(position.symbol) and ctx.get_stock_from_base(position.symbol).sector == "Technology"
    ]
    largest_tech_symbol = max(tech_candidates, key=lambda position: position.current_price * position.quantity).symbol if tech_candidates else None
    lowest_dividend_income_symbol = None
    dividend_candidates = [
        position for position in created_positions
        if ctx.get_stock_from_base(position.symbol) and ctx.get_stock_from_base(position.symbol).dividend_yield
    ]
    if dividend_candidates:
        lowest_dividend_income_symbol = min(
            dividend_candidates,
            key=lambda position: (ctx.get_stock_from_base(position.symbol).dividend_yield or Decimal("0")) * position.current_price * position.quantity,
        ).symbol
    return {
        "position_ids": position_ids,
        "best_symbol": best_symbol,
        "worst_symbol": worst_symbol,
        "largest_position_symbol": largest_position_symbol,
        "largest_tech_symbol": largest_tech_symbol,
        "lowest_dividend_income_symbol": lowest_dividend_income_symbol,
    }


# ---------------------------------------------------------------------------
# 3. portfolio_diverse
# ---------------------------------------------------------------------------

@_register("portfolio_diverse")
def build_portfolio_diverse(ctx: RobinhoodSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Generate 8-15 positions across sectors with multi-lot tax history.

    Params
    ------
    count : int             -- number of positions (default 10)
    sectors : list[str]     -- limit to these sectors (default all)
    include_etfs : bool     -- include ETF positions (default True)
    include_losers : bool   -- ensure some positions are at a loss (default True)
    """
    count = params.get("position_count", params.get("count", 10))
    sectors = params.get("sectors", None)
    include_etfs = params.get("include_etfs", True)
    include_losers = params.get("include_losers", True)
    growth_focused = params.get("growth_focused", False)
    loser_count = params.get("loser_count")
    large_position_stock = params.get("large_position_stock", params.get("concentrated_stock"))
    multi_lot = params.get("multi_lot", True)
    mixed_quantities = params.get("mixed_quantities", False)
    total_value_target = params.get("total_value_target")
    gain_forced_symbols = set(params.get("gain_forced_symbols", []))
    # today_loser_count: number of positions whose underlying stock should be forced
    # to be down >5% intraday (day_change_pct in [-10, -6]). Used by tasks that
    # filter on "down today" rather than lifetime total return.
    today_loser_count = params.get("today_loser_count")

    stocks = list(ctx.base.get("stocks", []))
    if sectors:
        sector_set = set(sectors)
        stocks = [s for s in stocks if s.sector in sector_set]
    if not include_etfs:
        stocks = [s for s in stocks if s.asset_type != "etf"]

    if growth_focused:
        stocks.sort(key=lambda stock: (float(stock.dividend_yield or Decimal("0")), stock.symbol))
    else:
        ctx.rng.shuffle(stocks)

    picked: list[Stock] = []
    if large_position_stock:
        large_stock = next((stock for stock in stocks if stock.symbol == large_position_stock), None)
        if large_stock is not None:
            picked.append(large_stock)
            stocks = [stock for stock in stocks if stock.symbol != large_position_stock]
    picked.extend(stocks[: max(0, min(count, len(stocks)) - len(picked))])

    if "positions" not in ctx.base:
        ctx.base["positions"] = []

    if loser_count is None:
        loss_indexes = {idx for idx in range(len(picked)) if include_losers and idx % 3 == 0 and picked[idx].symbol not in gain_forced_symbols}
    else:
        eligible = [i for i in range(len(picked)) if picked[i].symbol not in gain_forced_symbols]
        loss_indexes = set(eligible[:min(int(loser_count), len(eligible))]) if include_losers else set()

    # Force a subset of underlying stocks to be down >5% today so positions on
    # them satisfy "down more than 5% today" filters at the agent layer.
    today_loser_indexes: set[int] = set()
    if today_loser_count is not None:
        eligible_today = [i for i in range(len(picked)) if picked[i].symbol not in gain_forced_symbols]
        today_loser_indexes = set(eligible_today[:min(int(today_loser_count), len(eligible_today))])
        for idx in today_loser_indexes:
            stock = picked[idx]
            forced_pct = Decimal(str(round(ctx.rng.uniform(-10.0, -6.0), 2)))
            new_prev_close = Decimal(str(round(float(stock.price) / (1 + float(forced_pct) / 100.0), 2)))
            stock.previous_close = new_prev_close
            stock.day_change = stock.price - new_prev_close
            stock.day_change_pct = forced_pct

    position_ids: list[str] = []
    created_positions: list[Position] = []
    total_value = Decimal("0")

    for idx, stock in enumerate(picked):
        # 2-4 lots per position
        num_lots = ctx.rng.randint(2, 4) if multi_lot else 1
        lots: list[TaxLot] = []
        total_shares = Decimal("0")
        total_cost = Decimal("0")

        for lot_i in range(num_lots):
            if mixed_quantities:
                if idx % 2 == 0:
                    share_lo, share_hi = 35, 80
                else:
                    share_lo, share_hi = 5, 20
            else:
                share_lo, share_hi = 5, (180 if stock.symbol == large_position_stock else 100)
            shares = Decimal(str(ctx.rng.randint(share_lo, share_hi)))
            # Vary cost basis; make some losers
            if idx in loss_indexes:
                cost_mult = ctx.rng.uniform(1.05, 1.30)  # above current = loss
            else:
                cost_mult = ctx.rng.uniform(0.60, 0.98)  # below current = gain
            cost_per = Decimal(str(round(float(stock.price) * cost_mult, 2)))
            # Baseline portfolio lots predate the wash-sale window; tasks that
            # need recent purchases add them explicitly via transaction_ledger.
            days_ago = ctx.rng.randint(31 + lot_i * 60, 120 + lot_i * 120)
            lots.append(TaxLot(
                shares=shares,
                cost_per_share=cost_per,
                acquired_date=(ctx.now - timedelta(days=days_ago)).date(),
            ))
            total_shares += shares
            total_cost += cost_per * shares

        avg_cost = Decimal(str(round(float(total_cost / total_shares), 2)))
        market_val = stock.price * total_shares
        total_return = market_val - total_cost
        total_return_pct = Decimal(str(round(float(total_return / total_cost * 100), 2))) if total_cost else Decimal("0")

        pos_id = ctx.next_id("pos")
        pos = Position(
            id=pos_id,
            symbol=stock.symbol,
            name=stock.name,
            asset_type=stock.asset_type,
            quantity=total_shares,
            avg_cost_basis=avg_cost,
            current_price=stock.price,
            day_change_pct=stock.day_change_pct,
            total_return=total_return,
            total_return_pct=total_return_pct,
            lots=lots,
        )
        ctx.base["positions"].append(pos)
        created_positions.append(pos)
        position_ids.append(pos_id)
        total_value += market_val

    if total_value_target and total_value > Decimal("0"):
        target_value = Decimal(str(total_value_target))
        scale = target_value / total_value
        total_value = Decimal("0")
        for position in created_positions:
            scaled_quantity = (position.quantity * scale).quantize(Decimal("0.000001"))
            if scaled_quantity <= Decimal("0"):
                scaled_quantity = Decimal("0.000001")
            lot_scale = scaled_quantity / position.quantity if position.quantity else Decimal("0")
            for lot in position.lots:
                lot.shares = (lot.shares * lot_scale).quantize(Decimal("0.000001"))
            position.quantity = sum((lot.shares for lot in position.lots), Decimal("0"))
            total_cost = sum((lot.shares * lot.cost_per_share for lot in position.lots), Decimal("0"))
            position.avg_cost_basis = Decimal(str(round(float(total_cost / position.quantity), 2))) if position.quantity else Decimal("0")
            market_val = position.current_price * position.quantity
            position.total_return = market_val - total_cost
            position.total_return_pct = Decimal(str(round(float(position.total_return / total_cost * 100), 2))) if total_cost else Decimal("0")
            total_value += market_val

    if "transactions" not in ctx.base:
        ctx.base["transactions"] = []
    for pos in created_positions:
        for lot in pos.lots:
            acquired_dt = datetime(lot.acquired_date.year, lot.acquired_date.month, lot.acquired_date.day, tzinfo=timezone.utc)
            ctx.base["transactions"].append(Transaction(
                id=ctx.next_id("txn"),
                type="buy",
                symbol=pos.symbol,
                quantity=lot.shares,
                amount=lot.shares * lot.cost_per_share,
                description=f"Bought {float(lot.shares):.0f} shares of {pos.symbol} @ ${lot.cost_per_share:.2f}",
                timestamp=acquired_dt,
            ))

    ctx.base["portfolio_value"] = ctx.base.get("portfolio_value", Decimal("0")) + total_value
    loss_symbols = sorted(position.symbol for position in created_positions if position.total_return < 0)
    gain_symbols = sorted(position.symbol for position in created_positions if position.total_return >= 0)
    today_loss_symbols = sorted(
        position.symbol for position in created_positions if position.day_change_pct < Decimal("-5")
    )
    largest_position_symbol = max(created_positions, key=lambda position: position.current_price * position.quantity).symbol if created_positions else None
    tech_candidates = [
        position for position in created_positions
        if ctx.get_stock_from_base(position.symbol) and ctx.get_stock_from_base(position.symbol).sector == "Technology"
    ]
    largest_tech_symbol = max(tech_candidates, key=lambda position: position.current_price * position.quantity).symbol if tech_candidates else None
    best_symbol = max(created_positions, key=lambda position: position.total_return_pct).symbol if created_positions else None
    worst_symbol = min(created_positions, key=lambda position: position.total_return_pct).symbol if created_positions else None
    smallest_return_impact_symbol = min(created_positions, key=lambda position: abs(position.total_return)).symbol if created_positions else None
    hundred_share_symbols = sorted(position.symbol for position in created_positions if position.quantity >= Decimal("100"))
    sub_hundred_share_symbols = sorted(position.symbol for position in created_positions if position.quantity < Decimal("100"))
    dividend_candidates = [
        position for position in created_positions
        if ctx.get_stock_from_base(position.symbol) and ctx.get_stock_from_base(position.symbol).dividend_yield
    ]
    lowest_dividend_income_symbol = None
    if dividend_candidates:
        lowest_dividend_income_symbol = min(
            dividend_candidates,
            key=lambda position: (ctx.get_stock_from_base(position.symbol).dividend_yield or Decimal("0")) * position.current_price * position.quantity,
        ).symbol
    return {
        "position_ids": position_ids,
        "loss_symbols": loss_symbols,
        "today_loss_symbols": today_loss_symbols,
        "gain_symbols": gain_symbols,
        "best_symbol": best_symbol,
        "worst_symbol": worst_symbol,
        "largest_position_symbol": largest_position_symbol,
        "largest_tech_symbol": largest_tech_symbol,
        "smallest_return_impact_symbol": smallest_return_impact_symbol,
        "lowest_dividend_income_symbol": lowest_dividend_income_symbol,
        "hundred_share_symbols": hundred_share_symbols,
        "sub_hundred_share_symbols": sub_hundred_share_symbols,
        "portfolio_value": str(total_value),
    }


# ---------------------------------------------------------------------------
# 4. pending_orders
# ---------------------------------------------------------------------------

@_register("pending_orders")
def build_pending_orders(ctx: RobinhoodSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create N pending orders.

    Params
    ------
    count : int                 -- number of orders (default 3)
    order_types : list[str]     -- types to choose from (default ["limit", "stop"])
    symbols : list[str]         -- symbols to use (default picks from universe)
    force_side : str | None     -- if set ("buy" or "sell"), all orders use this side
    """
    count = params.get("count", 3)
    order_types = params.get("order_types", ["limit", "stop"])
    symbols = params.get("symbols", None) or ctx.pick_symbols(count)
    force_side = params.get("force_side")
    include_suspicious_window = params.get("include_suspicious_window", False)
    suspicious_timestamp = params.get("suspicious_timestamp")
    suspicious_order_count = int(params.get("suspicious_order_count", 1))
    far_below_count = int(params.get("far_below_count", 0))

    if "orders" not in ctx.base:
        ctx.base["orders"] = []

    order_ids: list[str] = []
    suspicious_order_ids: list[str] = []
    suspicious_symbols: list[str] = []
    for i in range(count):
        sym = symbols[i % len(symbols)]
        stock = ctx.get_stock_from_base(sym)
        otype = ctx.rng.choice(order_types)
        side = force_side if force_side else ctx.rng.choice(["buy", "sell"])
        qty = Decimal(str(ctx.rng.randint(1, 50)))
        price = float(stock.price) if stock else 100.0

        # Force first far_below_count orders to be limit buys far below market
        if i < far_below_count:
            otype = "limit"
            side = "buy"

        limit_price = None
        stop_price = None
        if otype == "limit":
            if side == "buy":
                if i < far_below_count:
                    limit_price = Decimal(str(round(price * ctx.rng.uniform(0.80, 0.88), 2)))
                else:
                    limit_price = Decimal(str(round(price * ctx.rng.uniform(0.92, 0.99), 2)))
            else:
                limit_price = Decimal(str(round(price * ctx.rng.uniform(1.01, 1.08), 2)))
        elif otype == "stop":
            if side == "sell":
                stop_price = Decimal(str(round(price * ctx.rng.uniform(0.90, 0.97), 2)))
            else:
                stop_price = Decimal(str(round(price * ctx.rng.uniform(1.03, 1.10), 2)))
        elif otype == "stop_limit":
            stop_price = Decimal(str(round(price * ctx.rng.uniform(0.90, 0.97), 2)))
            limit_price = Decimal(str(round(float(stop_price) * 0.99, 2)))

        order_id = ctx.next_id("ord")
        if include_suspicious_window and suspicious_timestamp is not None and i < suspicious_order_count:
            created = suspicious_timestamp + timedelta(minutes=ctx.rng.randint(-20, 20))
        else:
            created = ctx.now - timedelta(hours=ctx.rng.randint(1, 48))
        order = Order(
            id=order_id,
            symbol=sym,
            side=side,
            order_type=otype,
            quantity=qty,
            filled_quantity=Decimal("0"),
            limit_price=limit_price,
            stop_price=stop_price,
            time_in_force=ctx.rng.choice(["gfd", "gtc"]),
            status="pending",
            created_at=created,
        )
        ctx.base["orders"].append(order)
        order_ids.append(order_id)
        if include_suspicious_window and suspicious_timestamp is not None and i < suspicious_order_count:
            suspicious_order_ids.append(order_id)
            suspicious_symbols.append(sym)

    return {
        "order_ids": order_ids,
        "suspicious_order_ids": suspicious_order_ids,
        "suspicious_symbols": sorted(set(suspicious_symbols)),
    }


# ---------------------------------------------------------------------------
# 5. filled_orders
# ---------------------------------------------------------------------------

@_register("filled_orders")
def build_filled_orders(ctx: RobinhoodSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create historical filled orders.

    Params
    ------
    count : int                  -- number of orders (default 5)
    age_range_days : [lo, hi]    -- days ago range (default [1, 30])
    symbols : list[str]          -- symbols to use (default picks from universe)
    """
    count = params.get("count", 5)
    lo, hi = params.get("age_range_days", [1, 30])
    symbols = params.get("symbols", None) or ctx.pick_symbols(count)
    order_types = params.get("order_types", ["market"])
    high_slippage_count = int(params.get("high_slippage_count", 0))

    if "orders" not in ctx.base:
        ctx.base["orders"] = []

    order_ids: list[str] = []
    high_slippage_symbols: list[str] = []
    for i in range(count):
        sym = symbols[i % len(symbols)]
        stock = ctx.get_stock_from_base(sym)
        side = ctx.rng.choice(["buy", "sell"])
        order_type = ctx.rng.choice(order_types)
        qty = Decimal(str(ctx.rng.randint(1, 100)))
        price = float(stock.price) if stock else 100.0
        days_ago = ctx.rng.randint(lo, hi)
        created = ctx.now - timedelta(days=days_ago, hours=ctx.rng.randint(0, 8))
        filled = created + timedelta(seconds=ctx.rng.randint(1, 120))

        limit_price = None
        if order_type == "limit":
            limit_price = Decimal(str(round(price * ctx.rng.uniform(0.99, 1.01), 2)))
            if i < high_slippage_count:
                fill_multiplier = 1.04 if side == "buy" else 0.96
                fill_price = Decimal(str(round(float(limit_price) * fill_multiplier, 2)))
                high_slippage_symbols.append(sym)
            else:
                fill_price = Decimal(str(round(price * ctx.rng.uniform(0.985, 1.015), 2)))
        else:
            fill_price = Decimal(str(round(price * ctx.rng.uniform(0.97, 1.03), 2)))

        order_id = ctx.next_id("ord")
        order = Order(
            id=order_id,
            symbol=sym,
            side=side,
            order_type=order_type,
            quantity=qty,
            filled_quantity=qty,
            filled_price=fill_price,
            limit_price=limit_price,
            status="filled",
            created_at=created,
            filled_at=filled,
        )
        ctx.base["orders"].append(order)
        order_ids.append(order_id)

    return {"order_ids": order_ids, "high_slippage_symbols": sorted(set(high_slippage_symbols))}


# ---------------------------------------------------------------------------
# 6. watchlist
# ---------------------------------------------------------------------------

@_register("watchlist")
def build_watchlist(ctx: RobinhoodSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create a named watchlist.

    Params
    ------
    name : str             -- watchlist name
    symbols : list[str]    -- symbols to include
    """
    name = params.get("name", "My Watchlist")
    symbols = params.get("symbols", [])

    if "watchlists" not in ctx.base:
        ctx.base["watchlists"] = []

    wl_id = ctx.next_id("wl")
    wl = Watchlist(
        id=wl_id,
        name=name,
        symbols=list(symbols),
        created_at=ctx.now - timedelta(days=ctx.rng.randint(1, 90)),
    )
    ctx.base["watchlists"].append(wl)

    # Screen symbols against criteria: P/E < 25, div yield > 2%, price within 10% of 52-week high
    passing_symbols: list[str] = []
    failing_all_symbols: list[str] = []
    for sym in symbols:
        stock = ctx.get_stock_from_base(sym)
        if not stock:
            failing_all_symbols.append(sym)
            continue
        pe_ok = stock.pe_ratio is not None and stock.pe_ratio < Decimal("25")
        div_ok = stock.dividend_yield is not None and stock.dividend_yield > Decimal("2")
        high_ok = stock.fifty_two_week_high > 0 and (
            stock.price >= stock.fifty_two_week_high * Decimal("0.9")
        )
        if pe_ok and div_ok and high_ok:
            passing_symbols.append(sym)
        elif not pe_ok and not div_ok and not high_ok:
            failing_all_symbols.append(sym)

    return {
        "watchlist_id": wl_id,
        "passing_symbols": sorted(passing_symbols),
        "failing_all_symbols": sorted(failing_all_symbols),
        "initial_watchlist_count": len(symbols),
    }


# ---------------------------------------------------------------------------
# 7. linked_banks
# ---------------------------------------------------------------------------

@_register("linked_banks")
def build_linked_banks(ctx: RobinhoodSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create linked bank accounts. First bank is default.

    Params
    ------
    banks : list[dict]   -- [{name, type, last_four}, ...]
    """
    banks_spec = params.get("banks", [
        {"name": "Chase Checking", "type": "checking", "last_four": "4521"},
    ])

    if "linked_banks" not in ctx.base:
        ctx.base["linked_banks"] = []

    bank_ids: list[str] = []
    for idx, b in enumerate(banks_spec):
        bank_id = ctx.next_id("bank")
        bank = LinkedBank(
            id=bank_id,
            bank_name=b["name"],
            account_type=b.get("type", "checking"),
            last_four=b["last_four"],
            status="verified",
            is_default=(idx == 0),
        )
        ctx.base["linked_banks"].append(bank)
        bank_ids.append(bank_id)

    return {"bank_ids": bank_ids}


# ---------------------------------------------------------------------------
# 8. options_chain
# ---------------------------------------------------------------------------

@_register("options_chain")
def build_options_chain(ctx: RobinhoodSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Generate a full options chain for a symbol.

    Params
    ------
    symbol : str                    -- underlying symbol
    expirations_count : int         -- number of expiration dates (default 4)
    strikes_per_expiration : int    -- strikes per expiration (default 10)
    """
    symbol = params["symbol"]
    exp_count = params.get("expirations_count", 4)
    strikes_per = params.get("strikes_per_expiration", 10)

    stock = ctx.get_stock_from_base(symbol)
    base_price = float(stock.price) if stock else 100.0

    if "options_chains" not in ctx.base:
        ctx.base["options_chains"] = {}

    contracts: list[OptionsContract] = []

    for exp_i in range(exp_count):
        days_out = 7 + exp_i * 14  # weekly increments
        exp_date = (ctx.now + timedelta(days=days_out)).date()
        dte = days_out / 365.0

        # Generate strikes centered around current price
        strike_step = max(1.0, round(base_price * 0.025, 0))
        center_strike = round(base_price / strike_step) * strike_step
        half = (strikes_per - 1) // 2

        for s_i in range(-half, half + 1):
            strike = Decimal(str(round(center_strike + s_i * strike_step, 2)))
            for opt_type in ("call", "put"):
                # Simplified Black-Scholes-ish pricing
                moneyness = float(strike) / base_price
                iv = Decimal(str(round(ctx.rng.uniform(0.20, 0.60), 4)))
                float_iv = float(iv)

                if opt_type == "call":
                    intrinsic = max(0.0, base_price - float(strike))
                    delta = Decimal(str(round(max(0.05, min(0.95, 1.0 - moneyness + 0.5)), 4)))
                else:
                    intrinsic = max(0.0, float(strike) - base_price)
                    delta = Decimal(str(round(max(-0.95, min(-0.05, -moneyness + 0.5)), 4)))

                time_value = base_price * float_iv * math.sqrt(dte) * 0.4
                premium = round(intrinsic + time_value, 2)
                premium = max(premium, 0.01)

                gamma = Decimal(str(round(ctx.rng.uniform(0.001, 0.05), 4)))
                theta = Decimal(str(round(-ctx.rng.uniform(0.01, 0.15), 4)))
                vega = Decimal(str(round(ctx.rng.uniform(0.05, 0.30), 4)))

                contract_id = ctx.next_id("opt")
                last_price = Decimal(str(round(premium * ctx.rng.uniform(0.95, 1.05), 2)))
                bid = Decimal(str(round(premium * 0.95, 2)))
                ask = Decimal(str(round(premium * 1.05, 2)))

                contracts.append(OptionsContract(
                    contract_id=contract_id,
                    underlying=symbol,
                    option_type=opt_type,
                    strike=strike,
                    expiration=exp_date,
                    bid=bid,
                    ask=ask,
                    last_price=last_price,
                    volume=ctx.rng.randint(10, 5000),
                    open_interest=ctx.rng.randint(100, 50000),
                    implied_volatility=iv,
                    greeks=Greeks(delta=delta, gamma=gamma, theta=theta, vega=vega),
                ))

    ctx.base["options_chains"][symbol] = contracts
    return {"contract_count": len(contracts)}


# ---------------------------------------------------------------------------
# 9. options_positions
# ---------------------------------------------------------------------------

@_register("options_positions")
def build_options_positions(ctx: RobinhoodSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create open options positions.

    Params
    ------
    count : int            -- number of positions (default 3)
    strategies : list[str] -- strategies to pick from (default ["single"])
    symbols : list[str]    -- underlying symbols (default picks from universe)
    """
    count = params.get("count", 3)
    strategies = params.get("strategies", ["single"])
    symbols = [params["symbol"]] if params.get("symbol") else (params.get("symbols", None) or ctx.pick_symbols(count))
    near_expiry_count = params.get("near_expiry_count", count if "near_expiry_days" in params else 0)
    near_expiry_days = params.get("near_expiry_days", 5)
    forced_option_type = params.get("option_type")
    forced_position_side = params.get("position_side")
    forced_in_the_money = params.get("in_the_money")
    position_type = params.get("position_type")

    if "options_positions" not in ctx.base:
        ctx.base["options_positions"] = []

    pos_ids: list[str] = []
    for i in range(count):
        sym = symbols[i % len(symbols)]
        stock = ctx.get_stock_from_base(sym)
        base_price = float(stock.price) if stock else 100.0
        if forced_option_type:
            opt_type = forced_option_type
        elif position_type == "covered_call":
            opt_type = "call"
        else:
            opt_type = ctx.rng.choice(["call", "put"])

        if forced_position_side:
            position_side = forced_position_side
        elif position_type == "covered_call":
            position_side = "short"
        else:
            position_side = ctx.rng.choice(["long", "short"])

        if forced_in_the_money is True:
            strike_mult = ctx.rng.uniform(0.92, 0.98) if opt_type == "call" else ctx.rng.uniform(1.02, 1.08)
        elif forced_in_the_money is False:
            strike_mult = ctx.rng.uniform(1.02, 1.08) if opt_type == "call" else ctx.rng.uniform(0.92, 0.98)
        else:
            strike_mult = ctx.rng.uniform(0.90, 1.10)
        strike = Decimal(str(round(base_price * strike_mult, 2)))
        exp_date = (ctx.now + timedelta(days=near_expiry_days if i < near_expiry_count else ctx.rng.randint(7, 60))).date()
        qty = 1 if position_type == "covered_call" else ctx.rng.randint(1, 10)
        avg_cost = Decimal(str(round(base_price * 0.03 * ctx.rng.uniform(0.5, 2.0), 2)))
        if position_side == "long":
            current_mult = ctx.rng.uniform(0.6, 1.5)
        else:
            current_mult = ctx.rng.uniform(0.5, 1.2)
        current_premium = Decimal(str(round(float(avg_cost) * current_mult, 2)))

        pos_id = ctx.next_id("opos")
        opos = OptionsPosition(
            id=pos_id,
            contract_id=ctx.next_id("opt"),
            underlying_symbol=sym,
            position_side=position_side,
            option_type=opt_type,
            strike_price=strike,
            expiration_date=exp_date,
            quantity=qty,
            avg_cost=avg_cost,
            current_premium=current_premium,
            greeks=Greeks(
                delta=Decimal(str(round(ctx.rng.uniform(-0.8, 0.8), 4))),
                gamma=Decimal(str(round(ctx.rng.uniform(0.001, 0.05), 4))),
                theta=Decimal(str(round(-ctx.rng.uniform(0.01, 0.15), 4))),
                vega=Decimal(str(round(ctx.rng.uniform(0.05, 0.30), 4))),
            ),
            status="open",
        )
        ctx.base["options_positions"].append(opos)
        pos_ids.append(pos_id)

    return {"options_position_ids": pos_ids}


# ---------------------------------------------------------------------------
# 10. complex_options_book
# ---------------------------------------------------------------------------

@_register("complex_options_book")
def build_complex_options_book(ctx: RobinhoodSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create multi-leg options positions near expiration.

    Params
    ------
    positions_count : int      -- number of positions (default 2)
    days_to_expiry : int       -- days until expiration (default 5)
    """
    positions_count = params.get("positions_count", 2)
    days_to_expiry = params.get("days_to_expiry", 5)

    if "options_orders" not in ctx.base:
        ctx.base["options_orders"] = []
    if "options_positions" not in ctx.base:
        ctx.base["options_positions"] = []
    if "options_chains" not in ctx.base:
        ctx.base["options_chains"] = {}

    order_ids: list[str] = []
    position_ids: list[str] = []
    action_symbols: list[str] = []
    no_action_symbols: list[str] = []
    profitable_long_symbols: list[str] = []
    short_itm_symbols: list[str] = []
    exp_date = (ctx.now + timedelta(days=days_to_expiry)).date()

    symbols = params.get("symbols", None) or ctx.pick_symbols(positions_count)
    categories = ["profitable_long", "losing_long", "short_itm", "short_otm"]

    for idx in range(positions_count):
        sym = symbols[idx % len(symbols)] if symbols else "AAPL"
        stock = ctx.get_stock_from_base(sym)
        base_price = float(stock.price) if stock else 100.0
        category = categories[idx % len(categories)]
        if category == "profitable_long":
            option_type = "call"
            position_side = "long"
            strike = Decimal(str(round(base_price * 0.96, 2)))
            avg_cost = Decimal(str(round(base_price * 0.025, 2)))
            current_premium = Decimal(str(round(float(avg_cost) * 1.35, 2)))
            action_symbols.append(sym)
            profitable_long_symbols.append(sym)
        elif category == "losing_long":
            option_type = "put"
            position_side = "long"
            strike = Decimal(str(round(base_price * 0.90, 2)))
            avg_cost = Decimal(str(round(base_price * 0.03, 2)))
            current_premium = Decimal(str(round(float(avg_cost) * 0.65, 2)))
            no_action_symbols.append(sym)
        elif category == "short_itm":
            option_type = "call"
            position_side = "short"
            strike = Decimal(str(round(base_price * 0.95, 2)))
            avg_cost = Decimal(str(round(base_price * 0.03, 2)))
            current_premium = Decimal(str(round(float(avg_cost) * 1.25, 2)))
            action_symbols.append(sym)
            short_itm_symbols.append(sym)
        else:
            option_type = "put"
            position_side = "short"
            strike = Decimal(str(round(base_price * 0.85, 2)))
            avg_cost = Decimal(str(round(base_price * 0.03, 2)))
            current_premium = Decimal(str(round(float(avg_cost) * 0.55, 2)))
            no_action_symbols.append(sym)

        pos_id = ctx.next_id("opos")
        contract_id = ctx.next_id("opt")
        position_greeks = Greeks(
            delta=Decimal(str(round(ctx.rng.uniform(-0.8, 0.8), 4))),
            gamma=Decimal(str(round(ctx.rng.uniform(0.001, 0.05), 4))),
            theta=Decimal(str(round(-ctx.rng.uniform(0.01, 0.15), 4))),
            vega=Decimal(str(round(ctx.rng.uniform(0.05, 0.30), 4))),
        )
        position = OptionsPosition(
            id=pos_id,
            contract_id=contract_id,
            underlying_symbol=sym,
            position_side=position_side,
            option_type=option_type,
            strike_price=strike,
            expiration_date=exp_date,
            quantity=1,
            avg_cost=avg_cost,
            current_premium=current_premium,
            greeks=position_greeks,
            status="open",
        )
        ctx.base["options_positions"].append(position)
        position_ids.append(pos_id)

        # Register the position's contract in the symbol's chain so the
        # OptionsTrade page can resolve it from contract_id and pre-fill the
        # close/roll form. Without this, Sell/Buy-to-Close lands on an empty
        # form and the user can't submit.
        ctx.base["options_chains"].setdefault(sym, []).append(OptionsContract(
            contract_id=contract_id,
            underlying=sym,
            option_type=option_type,
            strike=strike,
            expiration=exp_date,
            bid=Decimal(str(round(float(current_premium) * 0.95, 2))),
            ask=Decimal(str(round(float(current_premium) * 1.05, 2))),
            last_price=current_premium,
            volume=ctx.rng.randint(10, 5000),
            open_interest=ctx.rng.randint(100, 50000),
            implied_volatility=Decimal(str(round(ctx.rng.uniform(0.20, 0.60), 4))),
            greeks=position_greeks,
        ))

        legs = [
            OptionsLeg(
                underlying_symbol=sym,
                side="buy" if position_side == "long" else "sell",
                option_type=option_type,
                strike=strike,
                expiration=exp_date,
                quantity=1,
                premium=avg_cost,
            )
        ]

        order_id = ctx.next_id("oord")
        created_at = ctx.now - timedelta(days=ctx.rng.randint(1, 10))
        oord = OptionsOrder(
            id=order_id,
            strategy="single",
            legs=legs,
            status="filled",
            created_at=created_at,
            filled_at=created_at + timedelta(seconds=ctx.rng.randint(30, 300)),
        )
        ctx.base["options_orders"].append(oord)
        order_ids.append(order_id)

    return {
        "options_order_ids": order_ids,
        "options_position_ids": position_ids,
        "action_symbols": sorted(set(action_symbols)),
        "no_action_symbols": sorted(set(no_action_symbols)),
        "profitable_long_symbols": sorted(set(profitable_long_symbols)),
        "short_itm_symbols": sorted(set(short_itm_symbols)),
    }


# ---------------------------------------------------------------------------
# 11. recurring_investments
# ---------------------------------------------------------------------------

@_register("recurring_investments")
def build_recurring_investments(ctx: RobinhoodSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create active recurring investments with execution history.

    Params
    ------
    count : int                -- number of recurring investments (default 3)
    symbols : list[str]        -- symbols (default picks from universe)
    frequencies : list[str]    -- frequencies to choose from (default ["weekly", "monthly"])
    """
    count = params.get("count", 3)
    symbols = params.get("symbols", None) or ctx.pick_symbols(count)
    frequencies = params.get("frequencies", ["weekly", "monthly"])
    include_history = params.get("include_history", True)
    overpaying_count = int(params.get("overpaying_count", 0))
    overdue_count = int(params.get("overdue_count", 0))

    if "recurring_investments" not in ctx.base:
        ctx.base["recurring_investments"] = []

    ri_ids: list[str] = []
    overpaying_symbols: list[str] = []
    overdue_symbols: list[str] = []
    for i in range(count):
        sym = symbols[i % len(symbols)]
        freq = ctx.rng.choice(frequencies)
        amount = Decimal(str(ctx.rng.choice([10, 25, 50, 100, 250, 500])))

        # Generate 4-8 past executions
        history: list[RecurringExecution] = []
        num_executions = ctx.rng.randint(4, 8)
        stock = ctx.get_stock_from_base(sym)
        for ex_i in range(num_executions):
            days_ago = (num_executions - ex_i) * (7 if freq == "weekly" else 30)
            if stock and i < overpaying_count:
                exec_price = float(stock.price) * ctx.rng.uniform(1.08, 1.25)
            else:
                exec_price = float(stock.price) * ctx.rng.uniform(0.85, 1.02) if stock else 100.0
            exec_price_d = Decimal(str(round(exec_price, 2)))
            shares = Decimal(str(round(float(amount) / exec_price, 6)))
            history.append(RecurringExecution(
                date=(ctx.now - timedelta(days=days_ago)).date(),
                amount=amount,
                shares_bought=shares,
                price=exec_price_d,
            ))

        # Next execution
        if i < overdue_count:
            if freq == "weekly":
                next_date = (ctx.now - timedelta(days=ctx.rng.randint(1, 7))).date()
            elif freq == "biweekly":
                next_date = (ctx.now - timedelta(days=ctx.rng.randint(1, 14))).date()
            elif freq == "daily":
                next_date = (ctx.now - timedelta(days=1)).date()
            else:  # monthly
                next_date = (ctx.now - timedelta(days=ctx.rng.randint(1, 30))).date()
        elif freq == "weekly":
            next_date = (ctx.now + timedelta(days=ctx.rng.randint(1, 7))).date()
        elif freq == "biweekly":
            next_date = (ctx.now + timedelta(days=ctx.rng.randint(1, 14))).date()
        elif freq == "daily":
            next_date = (ctx.now + timedelta(days=1)).date()
        else:  # monthly
            next_date = (ctx.now + timedelta(days=ctx.rng.randint(1, 30))).date()

        ri_id = ctx.next_id("ri")
        ri = RecurringInvestment(
            id=ri_id,
            symbol=sym,
            amount=amount,
            frequency=freq,
            next_execution_date=next_date,
            status="active",
            history=history if include_history else [],
        )
        ctx.base["recurring_investments"].append(ri)
        ri_ids.append(ri_id)
        if stock and i < overpaying_count:
            overpaying_symbols.append(sym)
        if i < overdue_count:
            overdue_symbols.append(sym)

    active_symbols = [investment.symbol for investment in ctx.base["recurring_investments"]]
    duplicate_symbols = sorted({
        symbol for symbol in active_symbols
        if active_symbols.count(symbol) > 1
    })
    combined_amounts = {
        symbol: str(sum(
            (investment.amount for investment in ctx.base["recurring_investments"] if investment.symbol == symbol),
            Decimal("0"),
        ))
        for symbol in duplicate_symbols
    }
    total_active_before = len([
        ri for ri in ctx.base["recurring_investments"] if ri.status == "active"
    ])
    return {
        "recurring_investment_ids": ri_ids,
        "overpaying_symbols": sorted(set(overpaying_symbols)),
        "overdue_symbols": sorted(set(overdue_symbols)),
        "duplicate_symbols": duplicate_symbols,
        "combined_amounts": combined_amounts,
        "total_active_before": total_active_before,
    }


# ---------------------------------------------------------------------------
# 12. transfers_history
# ---------------------------------------------------------------------------

@_register("transfers_history")
def build_transfers_history(ctx: RobinhoodSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create deposit/withdrawal history.

    Params
    ------
    count : int                  -- number of transfers (default 5)
    age_range_days : [lo, hi]    -- days ago range (default [1, 90])
    include_pending : bool       -- include pending transfers (default False)
    """
    count = params.get("count", 5)
    lo, hi = params.get("age_range_days", [1, max(30, int(params.get("months", 3)) * 30)])
    include_pending = params.get("include_old_pending", params.get("include_pending", False))

    if "transfers" not in ctx.base:
        ctx.base["transfers"] = []

    # Need a bank
    banks = ctx.base.get("linked_banks", [])
    if not banks:
        build_linked_banks(ctx, {"banks": [{"name": "Chase Checking", "type": "checking", "last_four": "4521"}]})
        banks = ctx.base["linked_banks"]

    transfer_ids: list[str] = []
    for i in range(count):
        direction = ctx.rng.choice(["deposit", "withdrawal"])
        amount = Decimal(str(ctx.rng.choice([100, 250, 500, 1000, 2500, 5000])))
        days_ago = ctx.rng.randint(lo, hi)
        initiated = ctx.now - timedelta(days=days_ago)

        if include_pending and i == 0:
            status = "pending"
            completed_at = None
            initiated = ctx.now - timedelta(days=max(days_ago, 8))
        else:
            status = "completed"
            completed_at = initiated + timedelta(days=ctx.rng.randint(1, 3))

        xfer_id = ctx.next_id("xfer")
        xfer = Transfer(
            id=xfer_id,
            direction=direction,
            amount=amount,
            status=status,
            bank_account_id=banks[0].id,
            initiated_at=initiated,
            completed_at=completed_at,
            expected_date=(initiated + timedelta(days=3)).date(),
        )
        ctx.base["transfers"].append(xfer)
        transfer_ids.append(xfer_id)

    return {"transfer_ids": transfer_ids}


# ---------------------------------------------------------------------------
# 13. transaction_ledger
# ---------------------------------------------------------------------------

@_register("transaction_ledger")
def build_transaction_ledger(ctx: RobinhoodSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create a full buy/sell/dividend transaction history.

    Params
    ------
    months : int              -- how many months of history (default 3)
    symbols : list[str]       -- symbols (default picks from universe)
    include_dividends : bool  -- include dividend transactions (default True)
    """
    months = params.get("months", 3)
    symbols = params.get("symbols", None) or ctx.pick_symbols(5)
    include_dividends = params.get("include_dividends", True)
    include_recent_buys = params.get("include_recent_buys", False)
    recent_buy_symbols = params.get("recent_buy_symbols")
    recent_buy_count = params.get("recent_buy_count")
    quantity_mismatch_stock = params.get("quantity_mismatch_stock")
    if quantity_mismatch_stock is None and params.get("include_discrepancy"):
        quantity_mismatch_stock = next((position.symbol for position in ctx.base.get("positions", [])), None)

    if "transactions" not in ctx.base:
        ctx.base["transactions"] = []

    txn_ids: list[str] = []
    for month_i in range(months):
        for sym in symbols:
            stock = ctx.get_stock_from_base(sym)
            base_price = float(stock.price) if stock else 100.0

            # 1-3 buy/sell per month per symbol
            num_trades = ctx.rng.randint(1, 3)
            for _ in range(num_trades):
                side = ctx.rng.choice(["buy", "sell"])
                qty = Decimal(str(ctx.rng.randint(1, 50)))
                price = Decimal(str(round(base_price * ctx.rng.uniform(0.90, 1.10), 2)))
                amount = qty * price
                days_ago = month_i * 30 + ctx.rng.randint(0, 29)
                ts = ctx.now - timedelta(days=days_ago, hours=ctx.rng.randint(9, 16))

                txn_id = ctx.next_id("txn")
                ctx.base["transactions"].append(Transaction(
                    id=txn_id,
                    type=side,
                    symbol=sym,
                    quantity=qty,
                    amount=amount,
                    description=f"Market {side} {qty} shares of {sym} @ ${price}",
                    timestamp=ts,
                ))
                txn_ids.append(txn_id)

            # Optional dividend
            if include_dividends and stock and stock.dividend_yield and ctx.rng.random() < 0.4:
                div_amount = Decimal(str(round(base_price * float(stock.dividend_yield) / 400, 2)))
                days_ago = month_i * 30 + ctx.rng.randint(15, 28)
                ts = ctx.now - timedelta(days=days_ago)
                txn_id = ctx.next_id("txn")
                ctx.base["transactions"].append(Transaction(
                    id=txn_id,
                    type="dividend",
                    symbol=sym,
                    quantity=None,
                    amount=div_amount,
                    description=f"Dividend payment from {sym}",
                    timestamp=ts,
                ))
                txn_ids.append(txn_id)

    recent_buy_symbols_used: list[str] = []
    if include_recent_buys:
        candidate_symbols = recent_buy_symbols or [
            position.symbol for position in ctx.base.get("positions", [])
        ] or list(symbols[:3])
        if recent_buy_count is not None:
            candidate_symbols = list(candidate_symbols)[: int(recent_buy_count)]
        for idx, sym in enumerate(candidate_symbols):
            stock = ctx.get_stock_from_base(sym)
            base_price = float(stock.price) if stock else 100.0
            qty = Decimal(str(3 + idx))
            price = Decimal(str(round(base_price * 1.01, 2)))
            txn_id = ctx.next_id("txn")
            ctx.base["transactions"].append(Transaction(
                id=txn_id,
                type="buy",
                symbol=sym,
                quantity=qty,
                amount=qty * price,
                description=f"Bought {qty} shares of {sym} @ ${price}",
                timestamp=ctx.now - timedelta(days=idx + 3),
            ))
            txn_ids.append(txn_id)
            recent_buy_symbols_used.append(sym)

    mismatch_symbol = quantity_mismatch_stock
    if mismatch_symbol:
        stock = ctx.get_stock_from_base(mismatch_symbol)
        base_price = float(stock.price) if stock else 100.0
        qty = Decimal("7")
        price = Decimal(str(round(base_price * 1.02, 2)))
        txn_id = ctx.next_id("txn")
        ctx.base["transactions"].append(Transaction(
            id=txn_id,
            type="buy",
            symbol=mismatch_symbol,
            quantity=qty,
            amount=qty * price,
            description=f"Bought {qty} shares of {mismatch_symbol} @ ${price}",
            timestamp=ctx.now - timedelta(days=14),
        ))
        txn_ids.append(txn_id)

    return {
        "transaction_ids": txn_ids,
        "mismatch_symbol": mismatch_symbol,
        "recent_buy_symbols": sorted(set(recent_buy_symbols_used)),
    }


# ---------------------------------------------------------------------------
# 14. tax_documents
# ---------------------------------------------------------------------------

@_register("tax_documents")
def build_tax_documents(ctx: RobinhoodSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create 1099 tax documents with realized gains/losses.

    Params
    ------
    year : int                  -- tax year (default current year - 1)
    include_wash_sales : bool   -- include wash sale entries (default False)
    gains_count : int           -- number of realized gain/loss entries (default 8)
    """
    year = params.get("year", ctx.now.year - 1)
    include_wash_sales = params.get("include_wash_sales", False)
    gains_count = params.get("gains_count", 8)
    include_gains = params.get("include_gains", False)
    short_term_gains = params.get("short_term_gains")
    long_term_gains = params.get("long_term_gains")
    discrepancy_count = int(params.get("discrepancy_count", 0))

    if "tax_documents" not in ctx.base:
        ctx.base["tax_documents"] = []

    sell_symbols = [txn.symbol for txn in ctx.base.get("transactions", []) if txn.type == "sell" and txn.symbol]
    requested_symbols = list(params.get("symbols", []) or [])
    symbol_pool = list(dict.fromkeys(requested_symbols + sell_symbols))
    if len(symbol_pool) < gains_count:
        symbol_pool.extend(sym for sym in ctx.pick_symbols(gains_count) if sym not in symbol_pool)
    symbols = symbol_pool[:gains_count]

    transaction_cost_bases: dict[str, Decimal] = {}
    for symbol in symbols:
        purchase_total = sum(
            (
                txn.amount
                for txn in ctx.base.get("transactions", [])
                if txn.type == "buy" and txn.symbol == symbol
            ),
            Decimal("0"),
        )
        if purchase_total == Decimal("0"):
            purchase_total = Decimal(str(round(ctx.rng.uniform(500, 10000), 2)))
        transaction_cost_bases[symbol] = purchase_total

    gains: list[RealizedGainLoss] = []
    discrepancy_symbols: list[str] = []
    reported_cost_bases: dict[str, str] = {}
    transaction_cost_basis_map: dict[str, str] = {}
    for i in range(gains_count):
        sym = symbols[i % len(symbols)]
        buy_date = date(year, ctx.rng.randint(1, 6), ctx.rng.randint(1, 28))
        sell_date = date(year, ctx.rng.randint(7, 12), ctx.rng.randint(1, 28))
        cost_basis = transaction_cost_bases[sym]
        if i < discrepancy_count:
            discrepancy_symbols.append(sym)
            cost_basis += Decimal(str((i + 1) * 125))
        gain_pct = ctx.rng.uniform(-0.30, 0.50)
        holding_days = (sell_date - buy_date).days
        if include_gains:
            gain_pct = abs(gain_pct) + 0.05
        holding_period = "long" if holding_days > 365 else "short"
        if short_term_gains is not None and i == 0:
            holding_period = "short"
            sell_date = min(date(year, 12, 28), buy_date + timedelta(days=120))
            target_gain = Decimal(str(short_term_gains))
            proceeds = cost_basis + target_gain
        elif long_term_gains is not None and i == 1:
            holding_period = "long"
            sell_date = max(sell_date, buy_date + timedelta(days=370))
            if sell_date.year != year:
                sell_date = date(year, 12, 28)
                buy_date = min(buy_date, date(year - 1, 1, 5))
            target_gain = Decimal(str(long_term_gains))
            proceeds = cost_basis + target_gain
        else:
            proceeds = Decimal(str(round(float(cost_basis) * (1 + gain_pct), 2)))
        gain_loss = proceeds - cost_basis
        is_wash = include_wash_sales and i % 4 == 0

        gains.append(RealizedGainLoss(
            symbol=sym,
            buy_date=buy_date,
            sell_date=sell_date,
            proceeds=proceeds,
            cost_basis=cost_basis,
            gain_loss=gain_loss,
            wash_sale=is_wash,
            holding_period=holding_period,
        ))
        reported_cost_bases[sym] = f"{cost_basis:.2f}"
        transaction_cost_basis_map[sym] = f"{transaction_cost_bases[sym]:.2f}"

    doc_id = ctx.next_id("taxdoc")
    doc = TaxDocument(
        id=doc_id,
        type="1099_B" if params.get("include_1099b") else "1099_CONSOLIDATED",
        tax_year=year,
        available_date=date(year + 1, 2, 15),
        realized_gains=gains,
    )
    ctx.base["tax_documents"].append(doc)
    return {
        "tax_document_id": doc_id,
        "discrepancy_symbols": sorted(set(discrepancy_symbols)),
        "reported_cost_bases": reported_cost_bases,
        "transaction_cost_bases": transaction_cost_basis_map,
    }


# ---------------------------------------------------------------------------
# 15. price_alerts
# ---------------------------------------------------------------------------

@_register("price_alerts")
def build_price_alerts(ctx: RobinhoodSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create active and optionally triggered price alerts.

    Params
    ------
    count : int                -- number of alerts (default 5)
    include_triggered : bool   -- include some triggered alerts (default False)
    """
    count = params.get("count", 5)
    include_triggered = params.get("include_triggered", False)
    include_stale = params.get("include_stale", False)
    stale_symbol = params.get("stale_symbol")

    if "price_alerts" not in ctx.base:
        ctx.base["price_alerts"] = []

    symbols = ctx.pick_symbols(count)
    alert_ids: list[str] = []

    for i in range(count):
        sym = stale_symbol if include_stale and i == 0 and stale_symbol else symbols[i % len(symbols)]
        stock = ctx.get_stock_from_base(sym)
        base_price = float(stock.price) if stock else 100.0
        condition = ctx.rng.choice(["above", "below"])

        if condition == "above":
            target = Decimal(str(round(base_price * ctx.rng.uniform(1.05, 1.20), 2)))
        else:
            target = Decimal(str(round(base_price * ctx.rng.uniform(0.80, 0.95), 2)))

        triggered = include_triggered and i % 3 == 0
        alert_id = ctx.next_id("alert")
        alert = PriceAlert(
            id=alert_id,
            symbol=sym,
            condition=condition,
            target_price=target,
            status="triggered" if triggered else "active",
            created_at=ctx.now - timedelta(days=ctx.rng.randint(1, 30)),
            triggered_at=(ctx.now - timedelta(hours=ctx.rng.randint(1, 48))) if triggered else None,
        )
        ctx.base["price_alerts"].append(alert)
        alert_ids.append(alert_id)

    return {"alert_ids": alert_ids}


# ---------------------------------------------------------------------------
# 16. notifications
# ---------------------------------------------------------------------------

_NOTIFICATION_TEMPLATES: dict[str, list[dict[str, str]]] = {
    "order_fill": [
        {"title": "Order Filled: {sym}", "message": "Your market buy order for {qty} shares of {sym} was filled at ${price}."},
    ],
    "price_alert": [
        {"title": "Price Alert: {sym}", "message": "{sym} has crossed your target price of ${price}."},
    ],
    "dividend": [
        {"title": "Dividend Received: {sym}", "message": "You received a ${price} dividend payment from {sym}."},
    ],
    "earnings": [
        {"title": "Upcoming Earnings: {sym}", "message": "{sym} reports earnings {detail}. Check the latest estimates."},
    ],
    "transfer_complete": [
        {"title": "Transfer Complete", "message": "Your ${price} deposit has been completed and is available for trading."},
    ],
    "security_alert": [
        {"title": "New Login Detected", "message": "A new login was detected from {detail}. If this wasn't you, secure your account."},
    ],
    "corporate_action": [
        {"title": "Corporate Action: {sym}", "message": "{sym} has an upcoming corporate action. Review the notice before market open."},
    ],
}


@_register("notifications")
def build_notifications(ctx: RobinhoodSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create a mix of notification types.

    Params
    ------
    count : int            -- total notifications (default 10)
    types : list[str]      -- types to include (default all available)
    unread_ratio : float   -- fraction unread (default 0.4)
    """
    count = params.get("count", 10)
    types = params.get("types", list(_NOTIFICATION_TEMPLATES.keys()))
    unread_ratio = params.get("unread_ratio", 0.4)
    include_corporate_actions = params.get("include_corporate_actions", False)

    if "notifications" not in ctx.base:
        ctx.base["notifications"] = []

    # When notifications are exclusively order_fill, mirror the symbols of
    # actually-filled orders so the agent can cross-reference notifications
    # against order history (otherwise random universe symbols look like fills
    # for stocks the user never traded).
    filled_symbols = [
        o.symbol for o in ctx.base.get("orders", []) if getattr(o, "status", None) == "filled"
    ]
    if filled_symbols and set(types) == {"order_fill"}:
        symbols = [filled_symbols[i % len(filled_symbols)] for i in range(count)]
    else:
        symbols = ctx.pick_symbols(count)
    if include_corporate_actions and "corporate_action" not in types:
        types = list(types) + ["corporate_action"]
    notif_ids: list[str] = []
    unread_count = round(count * unread_ratio)

    for i in range(count):
        ntype = ctx.rng.choice(types)
        sym = symbols[i % len(symbols)] if symbols else "AAPL"
        templates = _NOTIFICATION_TEMPLATES.get(ntype, _NOTIFICATION_TEMPLATES["order_fill"])
        template = ctx.rng.choice(templates)

        price = str(round(ctx.rng.uniform(10, 500), 2))
        qty = str(ctx.rng.randint(1, 100))
        detail = "tomorrow after market close" if ntype == "earnings" else "Chrome on macOS"

        title = template["title"].format(sym=sym, qty=qty, price=price, detail=detail)
        message = template["message"].format(sym=sym, qty=qty, price=price, detail=detail)
        is_read = i >= unread_count  # first N are unread
        ts = ctx.now - timedelta(hours=ctx.rng.randint(1, 72 * (i + 1)))

        notif_id = ctx.next_id("notif")
        notif = Notification(
            id=notif_id,
            type=ntype,
            title=title,
            message=message,
            timestamp=ts,
            is_read=is_read,
        )
        ctx.base["notifications"].append(notif)
        notif_ids.append(notif_id)

    return {"notification_ids": notif_ids}


# ---------------------------------------------------------------------------
# 17. earnings_calendar
# ---------------------------------------------------------------------------

@_register("earnings_calendar")
def build_earnings_calendar(ctx: RobinhoodSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create upcoming earnings events.

    Params
    ------
    symbols : list[str]    -- symbols with earnings (default picks from universe)
    days_ahead : int       -- how far ahead to schedule (default 30)
    """
    include_symbols = params.get("include_symbols", None)
    from_portfolio = params.get("from_portfolio", False)
    days_ahead = params.get("days_ahead", 30)
    if from_portfolio and not params.get("symbols"):
        # Restrict earnings to symbols the user actually holds so portfolio
        # earnings filters resolve to a non-empty set.
        portfolio_symbols = sorted({p.symbol for p in ctx.base.get("positions", [])})
        symbols = portfolio_symbols if portfolio_symbols else ctx.pick_symbols(5)
    else:
        symbols = params.get("symbols", None) or include_symbols or ctx.pick_symbols(5)

    if "earnings_events" not in ctx.base:
        ctx.base["earnings_events"] = []

    include_set = set(include_symbols) if include_symbols else set()

    for sym in symbols:
        stock = ctx.get_stock_from_base(sym)
        eps_est = None
        if stock and stock.eps:
            eps_est = Decimal(str(round(float(stock.eps) * ctx.rng.uniform(0.95, 1.10), 2)))

        # Ensure include_symbols land in the near future (for pause eligibility).
        # Honor an explicit small ``days_ahead`` if the caller asked for tighter
        # bounds (e.g. tasks that say "earnings tomorrow" use days_ahead=1) —
        # previously this branch always used randint(1, 3) which contradicted
        # the prompt for tomorrow-only tasks.
        if sym in include_set:
            include_upper = max(1, min(3, days_ahead))
            event_date = (ctx.now + timedelta(days=ctx.rng.randint(1, include_upper))).date()
        else:
            event_date = (ctx.now + timedelta(days=ctx.rng.randint(1, days_ahead))).date()
        time = ctx.rng.choice(["before_market", "after_market"])
        revenue_est = Decimal(str(round(ctx.rng.uniform(1e9, 50e9), 0))) if ctx.rng.random() > 0.3 else None

        ctx.base["earnings_events"].append(EarningsEvent(
            symbol=sym,
            date=event_date,
            time=time,
            eps_estimate=eps_est,
            revenue_estimate=revenue_est,
        ))

    # Identify symbols with earnings within 3 days
    three_day_cutoff = (ctx.now + timedelta(days=3)).date()
    earnings_symbols = sorted(
        e.symbol for e in ctx.base["earnings_events"]
        if e.date <= three_day_cutoff
    )

    # should_pause = earnings symbols that also have active recurring investments
    ri_symbols = {
        ri.symbol for ri in ctx.base.get("recurring_investments", [])
        if ri.status == "active"
    }
    # Also include overpaying symbols from recurring_investments builder
    overpaying = set(ctx.outputs.get("overpaying_symbols", []))
    earnings_with_ri = {sym for sym in earnings_symbols if sym in ri_symbols}
    should_pause_symbols = sorted(overpaying | earnings_with_ri)

    return {
        "earnings_symbols": earnings_symbols,
        "should_pause_symbols": should_pause_symbols,
    }


# ---------------------------------------------------------------------------
# 18. dividend_schedule
# ---------------------------------------------------------------------------

@_register("dividend_schedule")
def build_dividend_schedule(ctx: RobinhoodSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create a dividend payment schedule.

    Params
    ------
    symbols : list[str]         -- dividend-paying symbols (default auto-detect)
    include_history : bool      -- include past paid dividends (default True)
    """
    symbols = params.get("symbols", None)
    include_history = params.get("include_history", True)
    quarters = params.get("quarters", 1)

    if "dividend_schedule" not in ctx.base:
        ctx.base["dividend_schedule"] = []

    # Auto-detect dividend payers from universe
    if symbols is None:
        symbols = [
            s.symbol for s in ctx.base.get("stocks", [])
            if s.dividend_yield and float(s.dividend_yield) > 0
        ][:8]

    for sym in symbols:
        stock = ctx.get_stock_from_base(sym)
        div_yield = float(stock.dividend_yield) if stock and stock.dividend_yield else 2.0
        price = float(stock.price) if stock else 100.0
        amount_per_share = Decimal(str(round(price * div_yield / 400, 4)))
        shares_held = Decimal(str(ctx.rng.randint(10, 200)))
        estimated_total = Decimal(str(round(float(amount_per_share * shares_held), 2)))

        # Upcoming dividend
        ex_date = (ctx.now + timedelta(days=ctx.rng.randint(5, 45))).date()
        pay_date = ex_date + timedelta(days=ctx.rng.randint(14, 30))
        ctx.base["dividend_schedule"].append(DividendEntry(
            symbol=sym,
            ex_date=ex_date,
            pay_date=pay_date,
            amount_per_share=amount_per_share,
            estimated_total=estimated_total,
            status="upcoming",
        ))

        # Historical dividend
        if include_history:
            for quarter_idx in range(max(1, quarters)):
                past_ex = (ctx.now - timedelta(days=90 * (quarter_idx + 1) + ctx.rng.randint(0, 20))).date()
                past_pay = past_ex + timedelta(days=20)
                ctx.base["dividend_schedule"].append(DividendEntry(
                    symbol=sym,
                    ex_date=past_ex,
                    pay_date=past_pay,
                    amount_per_share=amount_per_share,
                    estimated_total=estimated_total,
                    status="paid",
                ))

    # Compute yield-on-cost for each position that pays dividends
    positions = ctx.base.get("positions", [])
    low_yield_symbols: list[str] = []
    best_yield_symbol: str | None = None
    best_yoc = Decimal("-1")
    for pos in positions:
        stock = ctx.get_stock_from_base(pos.symbol)
        if not stock or not stock.dividend_yield:
            continue
        annual_div_per_share = stock.price * stock.dividend_yield / Decimal("100")
        if pos.avg_cost_basis and pos.avg_cost_basis > 0:
            yoc = annual_div_per_share / pos.avg_cost_basis * Decimal("100")
        else:
            continue
        if yoc < Decimal("1"):
            low_yield_symbols.append(pos.symbol)
        if yoc > best_yoc:
            best_yoc = yoc
            best_yield_symbol = pos.symbol

    return {
        "low_yield_symbols": sorted(low_yield_symbols),
        "best_yield_symbol": best_yield_symbol,
    }


# ---------------------------------------------------------------------------
# 19. security_log
# ---------------------------------------------------------------------------

@_register("security_log")
def build_security_log(ctx: RobinhoodSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create login / security event history.

    Params
    ------
    count : int                  -- number of entries (default 8)
    include_suspicious : bool    -- include suspicious login entries (default False)
    """
    count = params.get("count", 8)
    include_suspicious = params.get("include_suspicious", False)

    if "security_log" not in ctx.base:
        ctx.base["security_log"] = []

    devices = ["Chrome on macOS", "Safari on iPhone", "Chrome on Windows", "Firefox on Linux"]
    locations = ["New York, NY", "San Francisco, CA", "Chicago, IL", "Austin, TX", "Seattle, WA"]
    suspicious_locations = ["Moscow, Russia", "Lagos, Nigeria", "Unknown VPN"]
    suspicious_timestamp = None
    suspicious_location = None
    suspicious_device = None

    for i in range(count):
        ts = ctx.now - timedelta(days=ctx.rng.randint(0, 60), hours=ctx.rng.randint(0, 23))

        if include_suspicious and i == count - 1:
            # Last entry is suspicious
            device = ctx.rng.choice(["Tor Browser on Unknown", "Chrome on Windows"])
            ip = f"{ctx.rng.randint(1,255)}.{ctx.rng.randint(0,255)}.{ctx.rng.randint(0,255)}.{ctx.rng.randint(0,255)}"
            location = ctx.rng.choice(suspicious_locations)
            suspicious_timestamp = ts
            suspicious_location = location
            suspicious_device = device
        else:
            device = ctx.rng.choice(devices)
            ip = f"192.168.{ctx.rng.randint(0,255)}.{ctx.rng.randint(1,254)}"
            location = ctx.rng.choice(locations)

        ctx.base["security_log"].append(SecurityEntry(
            event="login",
            device=device,
            ip_address=ip,
            location=location,
            timestamp=ts,
        ))

    return {
        "suspicious_timestamp": suspicious_timestamp,
        "suspicious_location": suspicious_location,
        "suspicious_device": suspicious_device,
    }


# ---------------------------------------------------------------------------
# 20. margin_account
# ---------------------------------------------------------------------------

@_register("margin_account")
def build_margin_account(ctx: RobinhoodSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Set up margin account state.

    Params
    ------
    margin_used : str          -- amount of margin currently used (Decimal string, default "0")
    maintenance_pct : float    -- maintenance margin percentage (default 0.25)
    """
    utilization_pct = params.get("utilization_pct")
    if params.get("near_maintenance") and utilization_pct is None and "margin_used" not in params:
        utilization_pct = 45
    if utilization_pct is not None and "margin_used" not in params:
        portfolio_value = ctx.base.get("portfolio_value", Decimal("0"))
        margin_used = Decimal(str(round(float(portfolio_value) * float(utilization_pct) / 100, 2)))
    else:
        margin_used = Decimal(str(params.get("margin_used", "0")))
    maintenance_pct = params.get("maintenance_pct", 0.25)

    ctx.base["account_type"] = "margin"
    ctx.base["gold_subscription"] = True

    portfolio_value = ctx.base.get("portfolio_value", Decimal("0"))
    ctx.base["buying_power"] = ctx.base.get("cash_balance", Decimal("0")) + margin_used
    ctx.base["margin_maintenance"] = Decimal(str(round(float(portfolio_value) * maintenance_pct, 2)))

    # Find position with smallest absolute total return (least impact to sell)
    positions = ctx.base.get("positions", [])
    smallest_impact_symbol = None
    if positions:
        smallest_impact_symbol = min(
            positions, key=lambda p: abs(p.total_return)
        ).symbol

    return {
        "margin_used": str(margin_used),
        "maintenance_pct": maintenance_pct,
        "smallest_impact_symbol": smallest_impact_symbol,
    }
