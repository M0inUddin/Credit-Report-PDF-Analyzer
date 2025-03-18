import re
from typing import List, Dict, Any

# If PyPDF2 isn't installed, run "pip install PyPDF2"
try:
    import PyPDF2
except ImportError:
    raise ImportError("PyPDF2 is required. Please install via: pip install PyPDF2")


def extract_pdf_text(pdf_path: str) -> str:
    """
    Extracts all text from the specified PDF file and returns it as a single string.
    Includes basic error handling in case the file is unreadable or doesn't exist.
    """
    try:
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            text_content = []
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                text_content.append(page.extract_text())
        return "\n".join(text_content)
    except FileNotFoundError:
        raise FileNotFoundError(f"PDF file not found at path: {pdf_path}")
    except Exception as e:
        raise RuntimeError(f"Error reading PDF file: {e}")


def parse_tradelines(pdf_text: str) -> List[Dict[str, Any]]:
    """
    Parse the PDF text to extract tradeline information.
    This approach looks for blocks that begin with '*  ' (a hallmark of new tradelines in the sample),
    and then tries to gather key fields (Open Date, Account Condition, Payment Status, etc.)

    Returns a list of dictionaries, each representing one tradeline.
    """
    tradelines = []
    lines = pdf_text.splitlines()
    current_tl = {}

    # Helper function to store the current tradeline and reset
    def store_current_tl():
        nonlocal current_tl
        if current_tl:
            tradelines.append(current_tl)
        current_tl = {}

    # Regex patterns for extracting specific fields
    # Adjust as needed depending on your PDF layout
    re_open_date = re.compile(r"Open\s*Date:\s*(\d{2}/\d{2}/\d{4})")
    re_original_amount = re.compile(r"Original\s*Amount:\s*\$?([\d,]+)")
    re_credit_limit = re.compile(r"Credit\s*Limit:\s*\$?([\d,]+)")
    re_account_condition = re.compile(r"Account\s*Condition:\s*(.*)", re.IGNORECASE)
    re_payment_status = re.compile(r"Payment\s*Status:\s*(.*)", re.IGNORECASE)
    re_account_type = re.compile(r"Account\s*Type:\s*(.*)", re.IGNORECASE)
    re_responsibility = re.compile(r"Responsibility:\s*(.*)", re.IGNORECASE)
    re_months_reviewed = re.compile(r"Months\s*Review\S*:\s*(\d+)", re.IGNORECASE)
    re_high_balance = re.compile(r"High\s*Balance\s*:\s*\$?([\d,]+)")

    for i, line in enumerate(lines):
        line_stripped = line.strip()

        # 1) If we see a line starting with "*  ", that indicates a new tradeline block
        if line_stripped.startswith("* "):
            # Store any existing tradeline data before starting a new one
            store_current_tl()
            # Start a new blank tradeline
            current_tl = {
                "open_date": None,
                "original_amount": None,
                "credit_limit": 0.0,
                "account_condition": "",
                "payment_status": "",
                "account_type": "",
                "responsibility": "",
                "months_open": 0,  # We'll approximate from Months Reviewed or status dates
                "high_balance": 0.0,  # Added to help infer credit limit if not explicitly stated
            }

        # Check if we're looking at a tradeline header (usually contains institution name)
        elif "/" in line_stripped and len(current_tl) == 0:
            # This might be the start of a tradeline without the "*" marker
            current_tl = {
                "open_date": None,
                "original_amount": None,
                "credit_limit": 0.0,
                "account_condition": "",
                "payment_status": "",
                "account_type": "",
                "responsibility": "",
                "months_open": 0,
                "high_balance": 0.0,
            }

        # 2) Attempt to extract known fields from the current line
        # Open Date
        open_date_match = re_open_date.search(line)
        if open_date_match:
            current_tl["open_date"] = open_date_match.group(1)

        # Original Amount
        orig_amt_match = re_original_amount.search(line)
        if orig_amt_match:
            # Remove commas and convert to float
            amt_str = orig_amt_match.group(1).replace(",", "")
            try:
                current_tl["original_amount"] = float(amt_str)
            except ValueError:
                current_tl["original_amount"] = None

        # Credit Limit
        limit_match = re_credit_limit.search(line)
        if limit_match:
            limit_str = limit_match.group(1).replace(",", "")
            try:
                current_tl["credit_limit"] = float(limit_str)
            except ValueError:
                current_tl["credit_limit"] = 0.0

        # High Balance (can be used to infer credit limit if not explicitly stated)
        high_balance_match = re_high_balance.search(line)
        if high_balance_match:
            bal_str = high_balance_match.group(1).replace(",", "")
            try:
                current_tl["high_balance"] = float(bal_str)
            except ValueError:
                current_tl["high_balance"] = 0.0

        # Account Condition
        cond_match = re_account_condition.search(line)
        if cond_match:
            current_tl["account_condition"] = cond_match.group(1).strip().lower()

        # Payment Status
        status_match = re_payment_status.search(line)
        if status_match:
            current_tl["payment_status"] = status_match.group(1).strip().lower()

        # Account Type
        type_match = re_account_type.search(line)
        if type_match:
            current_tl["account_type"] = type_match.group(1).strip().lower()

        # Responsibility
        resp_match = re_responsibility.search(line)
        if resp_match:
            current_tl["responsibility"] = resp_match.group(1).strip().lower()

        # Months Reviewed
        months_match = re_months_reviewed.search(line)
        if months_match:
            try:
                current_tl["months_open"] = int(months_match.group(1))
            except ValueError:
                current_tl["months_open"] = 0

    # Store the last tradeline in the list if present
    store_current_tl()

    return tradelines


def compute_score_and_grade(
    tradelines: List[Dict[str, Any]], bankruptcy_found=False
) -> (int, int):
    """
    Applies the scoring rules:
      1) Score starts at 0 (or -1 if a prior bankruptcy).
      2) +1 for each open, current, individual tradeline with credit_limit > 1000 and >=12 months,
         excluding auto, education, medical, or self-reported types.
      3) -1 for each tradeline with an account condition or payment status of
         "unpaid balance reported as loss" or "seriously past due", excluding medical/educational loans.
      4) Grade mapping:
         - Score < 0 => 5
         - Score = 0 => 4
         - Score = 1 or 2 => 3
         - Score = 3 or 4 => 2 (unless score=4 and there's an open mortgage => 1)
         - Score >= 5 => 1

    Returns (score, grade).
    """

    # 1) Start Score
    score = -1 if bankruptcy_found else 0

    positive_tradelines = []
    negative_tradelines = []

    # Lists for debugging
    positive_info = []
    negative_info = []
    skipped_info = []

    # 2) +1 for positive lines
    #    Must be "open", "current", "responsibility=individual", credit_limit>1000, months_open>=12
    #    Exclude if account_type in [auto, education, medical, lease, etc.]
    excluded_positive = ["auto", "aut", "education", "medic", "lease", "selfreported"]
    for idx, tl in enumerate(tradelines):
        # IMPROVED: More accurate detection of "open" accounts
        is_open = True  # Default assumption
        account_condition = tl["account_condition"].lower()

        # Check if explicitly marked as closed or paid off
        if (
            "paid/zero balance" in account_condition
            or "closed" in account_condition
            or "transferred" in account_condition
            or "paid" in account_condition
        ):
            is_open = False
            skipped_info.append(
                f"TL#{idx}: Not counted as positive - not open (condition: {account_condition})"
            )
            continue

        # "current" means it must have "current" in payment_status
        payment_status = tl["payment_status"].lower()
        has_current_status = "current" in payment_status

        if not has_current_status:
            skipped_info.append(
                f"TL#{idx}: Not counted as positive - not current (status: {payment_status})"
            )
            continue

        # Check responsibility
        if tl["responsibility"] != "individual":
            skipped_info.append(
                f"TL#{idx}: Not counted as positive - not individual responsibility"
            )
            continue

        # Check credit limit
        # IMPROVED: If credit_limit is 0 but high_balance is substantial, use high_balance as fallback
        credit_limit = tl["credit_limit"]
        if credit_limit == 0 and tl["high_balance"] > 1000:
            credit_limit = tl[
                "high_balance"
            ]  # Use high balance as a proxy for credit limit

        if credit_limit <= 1000:
            skipped_info.append(
                f"TL#{idx}: Not counted as positive - credit limit <= $1000 (limit: ${credit_limit})"
            )
            continue

        # Check months open
        if tl["months_open"] < 12:
            skipped_info.append(
                f"TL#{idx}: Not counted as positive - less than 12 months (months: {tl['months_open']})"
            )
            continue

        # Check if account type is excluded
        account_type = tl["account_type"].lower()
        is_excluded_type = any(token in account_type for token in excluded_positive)

        if is_excluded_type:
            skipped_info.append(
                f"TL#{idx}: Not counted as positive - excluded account type: {account_type}"
            )
            continue

        # If we got here, this is a positive tradeline
        score += 1
        positive_tradelines.append(tl)
        positive_info.append(
            f"TL#{idx}: +1 point - Open: {is_open}, Current: {has_current_status}, "
            f"Credit Limit: ${credit_limit}, Months: {tl['months_open']}, "
            f"Type: {account_type}, Condition: {account_condition}"
        )

    # 3) -1 for negative lines
    #    Condition or status: "unpaid balance reported as loss" or "seriously past due"
    #    Exclude medical/education
    excluded_negative = ["education", "medic"]
    negative_triggers = ["unpaid balance reported as loss", "seriously past due"]
    for idx, tl in enumerate(tradelines):
        # If account type includes "education" or "medical", skip
        account_type = tl["account_type"].lower()
        if any(ex in account_type for ex in excluded_negative):
            continue

        # If condition or status is negative
        condition_or_status = tl["account_condition"] + " " + tl["payment_status"]
        if any(trigger in condition_or_status.lower() for trigger in negative_triggers):
            score -= 1
            negative_tradelines.append(tl)
            negative_info.append(
                f"TL#{idx}: -1 point - Negative condition/status: '{condition_or_status}'"
            )

    # 4) Compute final grade
    if score < 0:
        grade = 5
    elif score == 0:
        grade = 4
    elif score in [1, 2]:
        grade = 3
    elif score in [3, 4]:
        # Special check if score==4 AND there's an open mortgage => grade=1
        if score == 4:
            # Check for an open mortgage
            has_open_mortgage = False
            for (
                tl
            ) in (
                positive_tradelines
            ):  # Only check the tradelines that counted positively
                if "mortgage" in tl["account_type"].lower():
                    has_open_mortgage = True
                    break
            if has_open_mortgage:
                grade = 1
            else:
                grade = 2
        else:
            grade = 2
    else:
        # score >= 5
        grade = 1

    # Print debug information
    print("\n=== SCORING DETAILS ===")
    print(
        f"Starting score: {-1 if bankruptcy_found else 0} (Bankruptcy found: {bankruptcy_found})"
    )

    print("\nPOSITIVE TRADELINES:")
    for info in positive_info:
        print(f"  {info}")

    print("\nNEGATIVE TRADELINES:")
    if negative_info:
        for info in negative_info:
            print(f"  {info}")
    else:
        print("  None found")

    print("\nSKIPPED TRADELINES:")
    for info in skipped_info:
        print(f"  {info}")

    print(f"\nFinal score: {score}")
    print(f"Final grade: {grade}")
    print("=" * 30)

    return score, grade


def main():
    # Hard-code the PDF path here, rather than passing arguments
    pdf_file_path = (
        "docs/CHRISTIAN MCCLELLAN_EXP.pdf"  # Example; adjust to your actual file path
    )

    try:
        # Extract text
        pdf_text = extract_pdf_text(pdf_file_path)

        # Detect if there's an indication of bankruptcy
        # For simplicity, search for 'bankruptcy' or 'bankruptcies' in the text
        bankruptcy_found = bool(re.search(r"bankrupt", pdf_text, re.IGNORECASE))

        # Parse out tradelines from the PDF
        tradelines = parse_tradelines(pdf_text)

        # Compute score and grade
        score, grade = compute_score_and_grade(tradelines, bankruptcy_found)

        # Print out results
        print("\n=== CREDIT REPORT SCORING ===")
        print(f"File: {pdf_file_path}")
        print(f"Score: {score}")
        print(f"Grade: {grade}")

    except FileNotFoundError as fnf_err:
        print(fnf_err)
    except RuntimeError as run_err:
        print(f"Runtime error occurred: {run_err}")
    except Exception as e:
        # Catch-all for unexpected errors
        print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    main()
