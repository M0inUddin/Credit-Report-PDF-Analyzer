import fitz  # PyMuPDF
from datetime import datetime
from helpers.cleaner import (
    clean_text,
    extract_original_amount,
    parse_date,
    compute_months_diff,
    extract_credit_limit,
)
import re


def check_prior_bankruptcy(text):
    """
    Returns True if a bankruptcy is found, otherwise False.
    For example, searching for lines that say 'Bankruptcy', 'Bankruptcies: 1', etc.
    """
    # Very simplistic approach:
    if "bankruptcy" in text.lower():
        return True
    return False


def get_negative_tradelines_for_redemption(negative_tradelines):
    """
    Return how many negative tradelines have a status date older than 2 years,
    etc. This is where you'd code your 70% threshold logic.
    """
    two_years_ago = datetime.now().date().replace(year=datetime.now().year - 2)
    older_than_2yrs = [
        t
        for t in negative_tradelines
        if t["status_date"] and t["status_date"] < two_years_ago
    ]
    return (
        len(older_than_2yrs) / len(negative_tradelines) if negative_tradelines else 0.0
    )


def print_detailed_report(score, grade, details):
    """
    Print a detailed report including which creditors were accepted, rejected, or skipped.
    """
    print("=== CREDIT REPORT ANALYSIS ===")
    print(f"Final Score: {score}")
    print(f"Final Grade: {grade}")
    print(
        f"Base Score: {details['base_score_start']} (Bankruptcy: {details['has_bankruptcy']})"
    )
    print(f"Positive Tradelines: {details['positive_count']}")
    print(f"Negative Tradelines: {details['negative_count']}")

    if details["redemption_applied"]:
        print("\n=== REDEMPTION SCENARIO ===")
        print(
            f"Percentage of negative tradelines older than 2 years: {details['pct_neg_older_2yr']:.2%}"
        )
        print(
            f"Positive tradelines after redemption: {details['redemption_result']['positive_count']}"
        )
        print(
            f"Negative tradelines after redemption: {details['redemption_result']['negative_count']}"
        )
        print(f"Score after redemption: {details['redemption_result']['final_score']}")

    print("\n=== ACCEPTED TRADELINES ===")
    for i, tradeline in enumerate(details["accepted_tradelines"], 1):
        print(
            f"{i}. {tradeline['account_name']} (Account #: {tradeline.get('account_number', 'N/A')})"
        )
        print(f"   Type: {tradeline.get('account_type', 'N/A')}")
        print(
            f"   Status: {tradeline.get('account_condition', 'N/A')} / {tradeline.get('payment_status', 'N/A')}"
        )
        print(f"   Credit Limit: ${tradeline.get('credit_limit', 'N/A')}")
        print(f"   Original Amount: {tradeline.get('original_amount', 'N/A')}")
        print(f"   Responsibility: {tradeline.get('responsibility', 'N/A')}")
        print(f"   Months Reviewed: {tradeline.get('months_reviewed', 'N/A')}")
        print(f"   Is Mortgage: {tradeline.get('is_mortgage', False)}")

    print("\n=== REJECTED TRADELINES ===")
    for i, tradeline in enumerate(details["rejected_tradelines"], 1):
        print(
            f"{i}. {tradeline['account_name']} (Account #: {tradeline.get('account_number', 'N/A')})"
        )
        print(f"   Type: {tradeline.get('account_type', 'N/A')}")
        print(
            f"   Status: {tradeline.get('account_condition', 'N/A')} / {tradeline.get('payment_status', 'N/A')}"
        )
        print(f"   Credit Limit: ${tradeline.get('credit_limit', 'N/A')}")
        print(f"   Original Amount: {tradeline.get('original_amount', 'N/A')}")
        print(f"   Responsibility: {tradeline.get('responsibility', 'N/A')}")
        print(f"   Months Reviewed: {tradeline.get('months_reviewed', 'N/A')}")
        print(f"   Is Mortgage: {tradeline.get('is_mortgage', False)}")
        print(
            f"   Reason for rejection: {' / '.join(reason for reason in tradeline['evaluation']['reasons'] if 'negative' in reason.lower())}"
        )

    print("\n=== SKIPPED TRADELINES ===")
    for i, tradeline in enumerate(details["skipped_tradelines"], 1):
        print(
            f"{i}. {tradeline['account_name']} (Account #: {tradeline.get('account_number', 'N/A')})"
        )
        print(f"   Type: {tradeline.get('account_type', 'N/A')}")
        print(
            f"   Status: {tradeline.get('account_condition', 'N/A')} / {tradeline.get('payment_status', 'N/A')}"
        )
        print(f"   Credit Limit: ${tradeline.get('credit_limit', 'N/A')}")
        print(f"   Original Amount: {tradeline.get('original_amount', 'N/A')}")
        print(f"   Responsibility: {tradeline.get('responsibility', 'N/A')}")
        print(f"   Months Reviewed: {tradeline.get('months_reviewed', 'N/A')}")
        print(f"   Is Mortgage: {tradeline.get('is_mortgage', False)}")
        print(
            f"   Reason for skipping: {' / '.join(tradeline['evaluation']['reasons'][-2:])}"
        )

    print("\n=== DETAILED EVALUATION ===")
    print(f"Total tradelines analyzed: {len(details['all_tradelines'])}")
    print(f"Tradelines accepted: {len(details['accepted_tradelines'])}")
    print(f"Tradelines rejected: {len(details['rejected_tradelines'])}")
    print(f"Tradelines skipped: {len(details['skipped_tradelines'])}")


def grade_report(final_score, positive_tradelines):
    """
    Apply the final grade mapping logic:
     - Score < 0 => grade = 5
     - Score == 0 => grade = 4
     - Score in [1,2] => grade = 3
     - Score in [3,4] => grade = 2  (unless it's exactly 4 and at least one of
                                     those 4 is an open mortgage => bump grade=1)
     - Score >= 5 => grade = 1
    """
    if final_score < 0:
        return 5
    elif final_score == 0:
        return 4
    elif final_score in (1, 2):
        return 3
    elif final_score in (3, 4):
        has_open_mortgage = any(
            t.get("is_mortgage", False) for t in positive_tradelines
        )
        return 1 if (final_score == 4 and has_open_mortgage) else 2
    else:
        return 1


def evaluate_tradeline(t, report_date, has_bankruptcy):
    """
    Helper function to evaluate a single tradeline for positive/negative scoring.
    """
    # Initialize evaluation details
    t["evaluation"] = {
        "status": "pending",
        "is_bankruptcy_related": False,
        "is_positive": False,
        "is_negative": False,
        "is_skipped": False,
        "reasons": [],
    }

    # Skip if discharged through bankruptcy
    if has_bankruptcy and any(
        cond in t.get("account_condition", "").lower()
        for cond in ["discharged through bankruptcy", "included in bankruptcy"]
    ):
        t["evaluation"].update(
            {
                "status": "skipped",
                "is_skipped": True,
                "is_bankruptcy_related": True,
                "reasons": ["Excluded due to bankruptcy discharge"],
            }
        )
        return t

    # Determine mortgage type
    account_type = t.get("account_type", "") or ""
    account_type = account_type.lower()
    is_conventional_fha = (
        "conventional real estate loan" in account_type
        or "fha real estate loan" in account_type
    )
    is_mortgage = "mortgage" in account_type or "real estate" in account_type
    t["is_mortgage"] = is_conventional_fha or is_mortgage

    # Check if open and current
    is_open = (t.get("account_condition") or "").lower().startswith("open")
    is_current = (t.get("payment_status", "") or "").lower().startswith("current")
    is_open_current = is_open and is_current

    # Check months on file - removed for mortgages
    open_date = t.get("open_date")
    months_on_file = None
    if not is_conventional_fha:
        months_on_file = t.get("months_reviewed") or (
            compute_months_diff(open_date, report_date) if open_date else None
        )

    # Check credit limit/original amount
    credit_limit = t.get("credit_limit", 0) or 0
    original_amount = t.get("original_amount", 0) or 0
    if is_conventional_fha:
        limit_ok = original_amount > 30000
        t["evaluation"]["reasons"].append(
            f"Conventional/FHA mortgage {'meets' if limit_ok else 'fails'} $30k original amount"
        )
    else:
        limit_ok = credit_limit > 1000 or original_amount > 1000

    # Removed responsibility check for mortgages
    meets_responsibility = not is_conventional_fha and (
        t.get("responsibility", "") or ""
    ).lower().startswith("individual")

    # Exclude certain account types
    skip_positive = any(
        [
            t.get("is_medical_or_edu", False),
            "auto loan" in account_type,
            "auto lease" in account_type,
            "selfreported" in account_type,
        ]
    )

    # Determine positive status
    if is_conventional_fha:
        # For conventional or FHA loans, only check if open, current, and meets original amount
        if is_open_current and limit_ok:
            t["evaluation"].update(
                {
                    "status": "accepted",
                    "is_positive": True,
                    "reasons": ["ACCEPTED as positive mortgage tradeline"],
                }
            )
        else:
            t["evaluation"]["reasons"].append("Does not meet mortgage criteria")
    else:
        # For other account types, keep existing criteria
        if (
            is_open_current
            and meets_responsibility
            and limit_ok
            and months_on_file
            and months_on_file >= 12
            and not skip_positive
        ):
            t["evaluation"].update(
                {
                    "status": "accepted",
                    "is_positive": True,
                    "reasons": ["ACCEPTED as positive tradeline"],
                }
            )
        else:
            t["evaluation"]["reasons"].append("Does not meet positive criteria")

    # Determine negative status
    cond_status = (t.get("account_condition", "") or "").lower()
    payment_status = (t.get("payment_status", "") or "").lower()
    if (
        "unpaid balance reported as loss" in cond_status
        or "seriously past due" in payment_status
    ) and not t.get("is_medical_or_edu"):
        t["evaluation"].update(
            {
                "status": "rejected",
                "is_negative": True,
                "reasons": ["Negative status detected"],
            }
        )

    # Handle skipped tradelines
    if not (t["evaluation"]["is_positive"] or t["evaluation"]["is_negative"]):
        t["evaluation"].update(
            {
                "status": "skipped",
                "is_skipped": True,
                "reasons": ["Does not meet criteria for positive or negative"],
            }
        )

    return t


def score_credit_report(pdf_path):
    """
    Main function to open the PDF, parse data, apply your logic,
    and return (final_score, final_grade, extras).
    """
    doc = fitz.open(pdf_path)

    # (Optional) you might have a 'report_date' that you parse from the first page text
    # For demonstration, we pick today's date as the "report date"
    report_date = datetime.now().date()

    # Extract full text
    full_text = ""
    for page in doc:
        full_text += page.get_text("text")  # type: ignore
    doc.close()

    # Check for prior bankruptcy (Exception #2)
    has_bankruptcy = check_prior_bankruptcy(full_text)

    # If there is a bankruptcy, score starts at -1, else 0
    base_score = -1 if has_bankruptcy else 0
    report_date = datetime.now().date()

    # Parse tradelines
    all_tradelines = [
        evaluate_tradeline(t, report_date, has_bankruptcy)
        for t in get_tradelines(full_text)
    ]

    # Categorize tradelines
    pos_tradelines = [t for t in all_tradelines if t["evaluation"]["is_positive"]]
    neg_tradelines = [t for t in all_tradelines if t["evaluation"]["is_negative"]]
    skipped_tradelines = [t for t in all_tradelines if t["evaluation"]["is_skipped"]]

    # Calculate raw score
    raw_score = base_score + len(pos_tradelines) - len(neg_tradelines)

    # Redemption scenario check
    redemption_applied = False
    pct_older = get_negative_tradelines_for_redemption(neg_tradelines)
    if pct_older >= 0.7 and neg_tradelines:
        three_years_ago = datetime.now().date().replace(year=datetime.now().year - 3)
        recent_tradelines = [
            t
            for t in all_tradelines
            if not t["status_date"] or t["status_date"] >= three_years_ago
        ]

        # Re-evaluate recent tradelines
        redemption_tradelines = [
            evaluate_tradeline(t, report_date, has_bankruptcy)
            for t in recent_tradelines
        ]
        redemption_pos = sum(
            t["evaluation"]["is_positive"] for t in redemption_tradelines
        )
        redemption_neg = sum(
            t["evaluation"]["is_negative"] for t in redemption_tradelines
        )
        redemption_score = base_score + redemption_pos - redemption_neg

        if redemption_score > raw_score:
            raw_score = redemption_score
            pos_tradelines = [
                t for t in redemption_tradelines if t["evaluation"]["is_positive"]
            ]
            neg_tradelines = [
                t for t in redemption_tradelines if t["evaluation"]["is_negative"]
            ]
            redemption_applied = True

    # Final grade
    final_grade = grade_report(raw_score, pos_tradelines)

    # Prepare extras
    extras = {
        "positive_count": len(pos_tradelines),
        "negative_count": len(neg_tradelines),
        "base_score_start": base_score,
        "has_bankruptcy": has_bankruptcy,
        "pct_neg_older_2yr": pct_older,
        "redemption_applied": redemption_applied,
        "accepted_tradelines": pos_tradelines,
        "rejected_tradelines": neg_tradelines,
        "skipped_tradelines": skipped_tradelines,
        "all_tradelines": all_tradelines,
    }

    return raw_score, final_grade, extras


def get_tradelines(text):
    """
    Given the extracted text of a credit report, attempt to parse
    individual tradelines with relevant info. Yields dicts containing
    fields like:
      {
         'account_name': 'CAPITAL ONE / 1270246 / BC...',
         'account_type': 'Credit Card' (or something parsed),
         'account_condition': 'Open' / 'Paid/zero balance' / ...
         'payment_status': 'Current' / 'Seriously past due' / 'Unpaid balance reported as loss' / ...
         'months_reviewed': int or None,
         'credit_limit': numeric or None,
         'responsibility': 'Individual' / 'Joint Account' / 'Authorized User' / ...
         'open_date': date object or None,
         'status_date': date object or None,
         'is_medical_or_edu': True/False
         # etc...
      }
    """
    # Split by star lines or a pattern that tends to start new tradelines.
    # In the sample text, each tradeline starts with "* " or some pattern:
    lines = [line.strip() for line in text.split("\n")]
    tradeline_chunks = []
    current_chunk = []
    # Regex to detect tradeline start (e.g., "Creditor / 1234567 / BC - Bank Credit Cards")
    tl_pattern = re.compile(r"^(?:\* )?.*\/.*\/.* - ")

    for line in lines:
        if tl_pattern.match(line):
            if current_chunk:
                tradeline_chunks.append("\n".join(current_chunk))
            current_chunk = [line]
        else:
            if current_chunk:
                current_chunk.append(line)
    if current_chunk:
        tradeline_chunks.append("\n".join(current_chunk))

    for chunk in tradeline_chunks:
        lines = chunk.strip().splitlines()
        if not lines:
            continue

        first_line = lines[0]

        # Heuristic: if it doesn't look like an account line, skip
        if "/" not in first_line or "-" not in first_line:
            continue

        # We'll build a dictionary of fields:
        tline = {
            "account_name": first_line,
            "account_type": None,
            "account_condition": None,
            "payment_status": None,
            "months_reviewed": None,
            "credit_limit": None,
            "original_amount": None,
            "high_balance": None,
            "responsibility": None,
            "open_date": None,
            "status_date": None,
            "is_medical_or_edu": False,
            "account_number": None,
            "raw_text": chunk,  # Store the raw text for debugging
        }

        # Try to parse out "account_type" from the first line if possible
        # e.g. 'Account Type: Real Estate' etc.
        # We'll do a quick match:
        mtype = re.search(r"Account\s*Type:\s*(.*)", chunk)
        if mtype:
            tline["account_type"] = mtype.group(1).split("\n")[0].strip()

        # Extract account number
        account_num = re.search(r"Account #:\s*(\d+)", chunk)
        if account_num:
            tline["account_number"] = account_num.group(1).strip()

        # We'll see if it's obviously a student or medical type
        if "student loan" in chunk.lower() or "education loan" in chunk.lower():
            tline["is_medical_or_edu"] = True
        if "medical" in chunk.lower():
            tline["is_medical_or_edu"] = True

        # For lines inside the chunk, parse key fields:
        # We'll look for "Account Condition: Something"
        mcond = re.search(r"Account\s*Condition:\s*(.*)", chunk)
        if mcond:
            tline["account_condition"] = mcond.group(1).split("\n")[0].strip()

        # Payment Status line
        mstatus = re.search(r"Payment\s*Status:\s*(.*)", chunk)
        if mstatus:
            tline["payment_status"] = mstatus.group(1).split("\n")[0].strip()

        # Months Reviewed line: "Months Reviewed:\n(\d+)"
        # or "Months Review ed:\n(\d+)"
        mmonths = re.search(r"Months\s*(?:Reviewed|Review\s*ed)\s*:\s*(\d+)", chunk)
        if mmonths:
            tline["months_reviewed"] = int(mmonths.group(1))

        # Look for "Credit Limit" and get the next valid number
        credit_limit_search_result = extract_credit_limit(lines)
        if credit_limit_search_result is not None:
            tline["credit_limit"] = credit_limit_search_result

        # Look for "Original Amount" and get the next valid number
        original_amount_search_result = extract_original_amount(lines)
        if original_amount_search_result is not None:
            tline["original_amount"] = original_amount_search_result

        # Clean and extract High Balance
        high_balance_search = re.search(
            r"High\s*Balance\s*\$([\d,]+)", clean_text("\n".join(lines))
        )
        if high_balance_search:
            tline["high_balance"] = int(high_balance_search.group(1).replace(",", ""))

        # Responsibility line: "Responsibility:\nIndividual" or "Joint Account"
        mresp = re.search(r"Responsibility:\s*(.*)", chunk)
        if mresp:
            tline["responsibility"] = mresp.group(1).split("\n")[0].strip()

        # "Open Date" + date
        # e.g. "Open\nDate\n08/09/2019"
        mopen = re.search(r"Open\s*Date\s*([\d/]+)", chunk)
        if mopen:
            od = parse_date(mopen.group(1))
            tline["open_date"] = od

        # "Status Date" + date
        mstat = re.search(r"Status\s*Date\s*([\d/]+)", chunk)
        if mstat:
            sd = parse_date(mstat.group(1))
            tline["status_date"] = sd

        yield tline
