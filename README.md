# Credit-Report-PDF-Analyzer

A Python utility for automated credit report analysis and scoring.

## Overview

This tool processes PDF credit reports and applies predefined rules to calculate credit score grades. It automates the evaluation of credit reports by extracting relevant information from PDF documents and generating standardized credit assessments.

## Features

- PDF credit report parsing
- Automated credit score calculation
- Rule-based grade assessment
- Credit report analysis
- Interactive web-based interface for analysis

## Purpose

Designed to streamline the credit evaluation process by providing consistent and objective credit score grading based on standardized rules and criteria.
This Python script analyzes credit report PDFs and calculates a credit score grade based on the rules.

## Usage

### Command-Line Interface

```bash
# Clone the repository
git clone https://github.com/M0inUddin/Credit-Report-PDF-Analyzer.git

# Navigate to the project directory
cd Credit-Report-PDF-Analyzer

# Install required dependencies
pip install -r requirements.txt

# Run the analyzer
python main.py
```

### Web-Based Interface

The project also includes a web-based interface powered by Gradio for analyzing credit reports interactively.

```bash
# Run the Gradio interface
python ui.py
```

1. Open the provided link in your browser after running the script.
2. Upload a credit report PDF file.
3. Click the "Analyze Report" button to view the results.

## Requirements

- Python 3.11+
- Other dependencies listed in requirements.txt

## Web Interface Features

- **File Upload**: Upload PDF credit reports for analysis.
- **Summary Display**: View a quick summary of the credit score and grade.
- **Detailed Report**: Access a detailed breakdown of the credit analysis.
- **Interactive Visuals**: Color-coded grade and score representations for better understanding.

## Understanding Results

- **Grade 1**: Excellent credit profile
- **Grade 2**: Good credit profile
- **Grade 3**: Fair credit profile
- **Grade 4**: Poor credit profile
- **Grade 5**: Very poor credit profile
