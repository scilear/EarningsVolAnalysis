# NVDA Earnings Volatility Analysis - Quick Start Guide

## Overview
This project analyzes NVIDIA (NVDA) earnings volatility to help inform options trading strategies around earnings announcements.

## What This Project Does
- Analyzes historical earnings volatility patterns
- Calculates implied volatility and option Greeks
- Simulates potential price scenarios
- Generates actionable trading recommendations
- Creates visual reports and HTML documentation

## Key Components

### Data Layer
- **Data Loader**: Fetches historical price data, earnings dates, and options chains
- **Data Filters**: Cleans and prepares data for analysis
- **Cache System**: Stores processed data to avoid redundant API calls

### Analytics Engine
- **BSM Module**: Black-Scholes-Merton option pricing calculations
- **Volatility Analysis**: Implied move, event volatility, and skew calculations
- **Historical Analysis**: Past volatility patterns and trends
- **Gamma Analysis**: Options sensitivity to price changes

### Strategy Engine
- **Payoff Calculator**: Evaluates potential profit/loss scenarios
- **Scoring System**: Ranks trading strategies by risk/return metrics
- **Monte Carlo Simulator**: Generates thousands of price scenarios

### Reporting
- **HTML Reports**: Interactive visualizations and analysis summaries
- **Figures Directory**: All generated charts and plots
- **Console Output**: Real-time progress and results

## Main Data Flow

1. **Data Loading**: Fetch historical prices, earnings dates, and options data
2. **Data Processing**: Clean, filter, and cache data for reuse
3. **Volatility Analysis**: Calculate implied moves, historical volatility, and skew
4. **Scenario Simulation**: Generate potential price paths using Monte Carlo methods
5. **Strategy Evaluation**: Score different trading strategies based on simulated outcomes
6. **Report Generation**: Create HTML reports with visualizations and recommendations

## How to Run

```bash
# From project root
python nvda_earnings_vol/main.py
```

### Configuration
- Edit `config.py` for date ranges, symbols, and analysis parameters
- Adjust settings in `nvda_earnings_vol/config.py` for different analysis scenarios

## Output Locations

- **Reports**: `reports/` directory (HTML files)
- **Figures**: `reports/figures/` directory (charts and plots)
- **Cache**: `cache/` directory (stored data files)
- **Logs**: Console output and log files

## Key Files

- `main.py`: Entry point and main orchestration
- `config.py`: Configuration settings
- `data/` directory: Data loading and filtering
- `analytics/` directory: Volatility and pricing calculations
- `strategies/` directory: Trading strategy logic
- `reports/` directory: Report generation
- `tests/` directory: Test suite

## Dependencies
- Python 3.x
- pandas, numpy, scipy for data analysis
- yfinance for market data
- plotly for visualizations
- pytest for testing

## Getting Help

- Run with `--help` flag for command-line options
- Check the `tests/` directory for usage examples
- Review the generated HTML reports for analysis results

## Next Steps

1. Run the analysis to see current results
2. Explore the HTML reports in the `reports/` directory
3. Adjust configuration settings for different analysis scenarios
4. Review the test suite to understand functionality
5. Modify strategies or add new analysis modules as needed