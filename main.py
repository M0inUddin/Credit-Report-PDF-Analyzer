import os
import re
import argparse
from datetime import datetime, timedelta
import PyPDF2


def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file."""
    text = ""
    try:
        with open(pdf_path, "rb") as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                text += page.extract_text()
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
    return text


def parse_date(date_str):
    """Parse date string into datetime object."""
    try:
        # Try to parse MM/YYYY format
        if "/" in date_str:
            month, year = date_str.split("/")
            return datetime(int(year), int(month), 1)
        # Try to parse MM/DD/YYYY format
        elif re.match(r"\d{2}/\d{2}/\d{4}", date_str):
            return datetime.strptime(date_str, "%m/%d/%Y")
        else:
            return None
    except:
        return None


def calculate_credit_score(text):
    """Calculate credit score based on the defined rules."""
    score = 0

    # Check for bankruptcy
    has_bankruptcy = False
    if re.search(r"Bankruptcy", text, re.IGNORECASE):
        has_bankruptcy = True
        score = -1

    # Extract tradelines
    tradelines = extract_tradelines(text)

    # Current date (for calculations)
    current_date = datetime.now()

    # Lists to track positive and negative tradelines
    positive_tradelines = []
    negative_tradelines = []

    for tradeline in tradelines:
        # Skip if tradeline is included in bankruptcy
        if has_bankruptcy and "discharged through Bankruptcy" in tradeline.get(
            "Account Condition", ""
        ):
            continue

        # Check for positive tradelines
        if (
            tradeline.get("Responsibility", "") == "Individual"
            and tradeline.get("Account Condition", "") == "Open"
            and tradeline.get("Payment Status", "") == "Current"
            and float(
                tradeline.get("Credit Limit", "0").replace("$", "").replace(",", "")
                or 0
            )
            > 1000
            and int(tradeline.get("Months Reviewed", "0") or 0) >= 12
            and tradeline.get("Account Type", "")
            not in ["AUT Auto Loan", "Auto Lease", "Education Loan", "Medical"]
            and not tradeline.get("SELFREPORTED", False)
        ):

            positive_tradelines.append(tradeline)
            score += 1

        # Check for negative tradelines
        if (
            tradeline.get("Account Condition", "") == "Unpaid balance reported as loss"
            or "Seriously past due" in tradeline.get("Payment Status", "")
            and tradeline.get("Account Type", "") not in ["Education Loan", "Medical"]
        ):

            negative_tradelines.append(tradeline)
            score -= 1

    # Check for redemption scenario
    if negative_tradelines:
        old_tradelines = 0
        for tradeline in negative_tradelines:
            status_date = parse_date(tradeline.get("Status Date", ""))
            if (
                status_date and (current_date - status_date).days > 730
            ):  # 2 years in days
                old_tradelines += 1

        # If 70% of negative tradelines are older than 2 years
        if old_tradelines / len(negative_tradelines) >= 0.7:
            # Recalculate score counting only tradelines within last 3 years
            score = 0
            if has_bankruptcy:
                score = -1

            for tradeline in positive_tradelines:
                status_date = parse_date(tradeline.get("Status Date", ""))
                if (
                    status_date and (current_date - status_date).days <= 1095
                ):  # 3 years in days
                    score += 1

            for tradeline in negative_tradelines:
                status_date = parse_date(tradeline.get("Status Date", ""))
                if (
                    status_date and (current_date - status_date).days <= 1095
                ):  # 3 years in days
                    score -= 1

    # Calculate final grade
    final_grade = determine_final_grade(score, positive_tradelines)

    return {
        "score": score,
        "final_grade": final_grade,
        "positive_tradelines": len(positive_tradelines),
        "negative_tradelines": len(negative_tradelines),
        "has_bankruptcy": has_bankruptcy,
    }


def determine_final_grade(score, positive_tradelines):
    """Determine final grade based on score and rules."""
    if score < 0:
        return 5
    elif score == 0:
        return 4
    elif score <= 2:
        return 3
    elif score <= 4:
        # Check if score is 4 and one positive tradeline is an open mortgage
        if score == 4 and any(
            tradeline.get("Account Type", "").lower() == "mortgage"
            and tradeline.get("Account Condition", "").lower() == "open"
            for tradeline in positive_tradelines
        ):
            return 1
        return 2
    else:  # score >= 5
        return 1


def extract_tradelines(text):
    """Extract tradeline information from the text."""
    tradelines = []

    # Use regex to find tradeline sections
    # This is a simplified approach - real implementation would need more robust parsing
    tradeline_pattern = r"([A-Z\s/]+)\s*/\s*(\d+)\s*/\s*([A-Z\-\s]+)\s*\nOpen\s*Date\s*(?:Credit\s*Limit|Original\s*Amount)\s*(?:High\s*Balance|Charge\s*Off\s*Amount)?\s*Status\s*Date\s*Past\s*Due\s*Last\s*Paid\s*Date\s*(?:Scheduled\s*Payment\s*)?\s*Balance\s*Date\s*Current\s*Balance\s*\n(.*?)\nAccount\s*Condition:\s*(.*?)\s*Account\s*#:\s*(.*?)\nPayment\s*Status:\s*(.*?)\s*Responsibility:\s*(.*?)\nAccount\s*Type:\s*(.*?)\s*Account\s*Terms:\s*(.*?)\n"

    matches = re.finditer(tradeline_pattern, text, re.DOTALL)

    for match in matches:
        try:
            creditor = match.group(1).strip()
            account_number = match.group(6).strip()
            account_condition = match.group(5).strip()
            payment_status = match.group(7).strip()
            responsibility = match.group(8).strip()
            account_type = match.group(9).strip()

            # Extract details from the data line
            data_line = match.group(4).strip()
            data_parts = data_line.split()

            open_date = data_parts[0] if len(data_parts) > 0 else ""

            # Try to extract credit limit or original amount
            credit_limit = ""
            for part in data_parts:
                if part.startswith("$"):
                    credit_limit = part
                    break

            # Try to extract status date
            status_date = ""
            for i, part in enumerate(data_parts):
                if "/" in part and i > 1:
                    status_date = part
                    break

            # Try to extract months reviewed
            months_reviewed = ""
            months_pattern = r"Months\s*Reviewed:\s*(\d+)"
            months_match = re.search(
                months_pattern, text[match.end() : match.end() + 200]
            )
            if months_match:
                months_reviewed = months_match.group(1)

            tradeline = {
                "Creditor": creditor,
                "Account Number": account_number,
                "Account Condition": account_condition,
                "Payment Status": payment_status,
                "Responsibility": responsibility,
                "Account Type": account_type,
                "Open Date": open_date,
                "Credit Limit": credit_limit,
                "Status Date": status_date,
                "Months Reviewed": months_reviewed,
            }

            tradelines.append(tradeline)
        except Exception as e:
            print(f"Error parsing tradeline: {e}")

    return tradelines


def main():
    parser = argparse.ArgumentParser(description="Credit Report PDF Analyzer")
    parser.add_argument("pdf_path", help="Path to the credit report PDF")
    parser.add_argument("--output", help="Path to output file (optional)")
    args = parser.parse_args()

    if not os.path.exists(args.pdf_path):
        print(f"Error: File {args.pdf_path} not found.")
        return

    # Extract text from PDF
    text = extract_text_from_pdf(args.pdf_path)

    # Calculate credit score
    result = calculate_credit_score(text)

    # Format output
    output = f"""
Credit Report Analysis
=====================
PDF File: {os.path.basename(args.pdf_path)}
Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Results:
- Raw Score: {result['score']}
- Final Grade: {result['final_grade']}
- Positive Tradelines: {result['positive_tradelines']}
- Negative Tradelines: {result['negative_tradelines']}
- Bankruptcy: {'Yes' if result['has_bankruptcy'] else 'No'}

Grade Interpretation:
1 = Excellent
2 = Good
3 = Fair
4 = Poor
5 = Very Poor
"""

    # Print output
    print(output)

    # Save to file if specified
    if args.output:
        try:
            with open(args.output, "w") as f:
                f.write(output)
            print(f"Analysis saved to {args.output}")
        except Exception as e:
            print(f"Error saving output to file: {e}")


if __name__ == "__main__":
    main()
