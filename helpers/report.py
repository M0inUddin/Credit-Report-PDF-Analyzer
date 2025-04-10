import fitz  # PyMuPDF
from datetime import datetime
from helpers.cleaner import (
    clean_text,
    extract_original_amount,
    extract_status_date,
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


def get_negative_tradelines_for_redemption(all_tradelines):
    """
    Check the percentage of negative tradelines that are older than 2 years.

    Returns:
    - Percentage of negative tradelines that are older than 2 years
    """
    two_years_ago = datetime.now().date().replace(year=datetime.now().year - 2)

    # Identify negative tradelines
    negative_tradelines = [t for t in all_tradelines if t["evaluation"]["is_negative"]]
    if not negative_tradelines:
        return 0.0

    # Old negative tradelines
    old_negative_tradelines = [
        t
        for t in negative_tradelines
        if t["status_date"]
        and parse_date(t["status_date"]) is not None
        and parse_date(t["status_date"]) < two_years_ago  # type: ignore
    ]

    # Calculate percentage
    pct_old_negative = len(old_negative_tradelines) / len(negative_tradelines)

    return pct_old_negative


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
        print(f"   Status Date: {tradeline.get('status_date', 'N/A')}")
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
        print(f"   Status Date: {tradeline.get('status_date', 'N/A')}")
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
        print(f"   Status Date: {tradeline.get('status_date', 'N/A')}")
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
        # Check for open mortgage exception
        has_open_mortgage = any(
            t.get("is_mortgage", False) and t["evaluation"]["is_positive"]
            for t in positive_tradelines
        )
        return 1 if (final_score == 4 and has_open_mortgage) else 2
    else:  # final_score >= 5
        return 1


def evaluate_tradeline(t, report_date, has_bankruptcy):
    """
    Evaluate a single tradeline under the new ruleset:

    1. If there's a known bankruptcy and the account condition includes
       'included in bankruptcy' or 'discharged through Bankruptcy', we skip it.
    2. Check for 'Mortgage Exception': if the account is a Conventional or FHA
       Real Estate Loan with Original Amount > 30000, is open, current, then it counts +1
       (ignoring responsibility).
    3. Otherwise, for normal +1:
       - Must be open/current
       - Must have 'Responsibility: Individual'
         (unless it's a mortgage which we already handle above)
       - Must have credit limit/original amount >= 1000
       - Must have 12+ months
       - Must not be auto, self-reported, medical, or edu
    4. For -1:
       - Condition/payment status has "unpaid balance reported as loss", or
         "seriously past due", or
         condition: "Legally paid in full for less than full balance" & status: "unpaid balance reported as loss", or
         condition: "Open" & status: "60 days past due" or "90 days past due" or "120 days past due" or "150 days past due" or "180 days past due"
       - Exclude medical or edu from negative scoring
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
        cond in (t.get("account_condition", "") or "").lower()
        for cond in [
            "discharged through bankruptcy",
            "included in bankruptcy",
            "debt included in or discharged through bankruptcy",
        ]
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

    # Account type normalization
    account_type = (t.get("account_type", "") or "").lower()

    # Determine if medical or education loan
    is_medical_or_edu = (
        t.get("is_medical_or_edu", False)
        or "education loan" in account_type
        or "student loan" in account_type
        or "medical" in account_type
    )
    t["is_medical_or_edu"] = is_medical_or_edu

    # Determine mortgage type
    is_mortgage = "real estate loan" in account_type or "mortgage" in account_type
    is_conventional_fha = (
        "conventional real estate loan" in account_type
        or "fha real estate loan" in account_type
    )
    t["is_mortgage"] = is_mortgage
    t["is_conventional_fha"] = is_conventional_fha

    # Check if auto loan/lease or selfreported
    is_auto = "auto loan" in account_type or "auto lease" in account_type
    is_selfreported = "selfreported" in account_type

    # Check account condition and payment status
    account_condition = (t.get("account_condition", "") or "").lower()
    payment_status = (t.get("payment_status", "") or "").lower()

    is_open = "open" in account_condition
    # FIX #3: Check if status is "current" but exclude "current/was X past due"
    is_current = "current" in payment_status and not any(
        f"current/was {days} days past due" in payment_status
        for days in ["30", "60", "90", "120", "150", "180"]
    )

    # Credit limit and original amount checks
    # FIX #2: Ensure we consistently use >= 1000, not > 1000
    credit_limit = t.get("credit_limit", 0) or 0
    original_amount = t.get("original_amount", 0) or 0

    # Check months maintained (for non-mortgage tradelines)
    months_reviewed = t.get("months_reviewed")
    open_date = t.get("open_date")
    has_12_months = False

    if months_reviewed is not None:
        has_12_months = months_reviewed >= 12
    elif open_date:
        months_on_file = compute_months_diff(open_date, report_date)
        has_12_months = months_on_file >= 12

    # Check responsibility (only for non-mortgage tradelines)
    responsibility = (t.get("responsibility", "") or "").lower()
    is_individual = "individual" in responsibility

    # EVALUATE POSITIVE TRADELINES - NORMAL CRITERIA
    if not is_conventional_fha:
        # Regular positive tradeline criteria
        if (
            is_open
            and is_current
            and (credit_limit >= 1000 or original_amount >= 1000)
            and has_12_months
            and is_individual
            and not is_medical_or_edu
            and not is_auto
            and not is_selfreported
        ):

            t["evaluation"].update(
                {
                    "status": "accepted",
                    "is_positive": True,
                    "reasons": ["ACCEPTED as positive tradeline - meets all criteria"],
                }
            )
            t["evaluation"]["reasons"].append(
                f"Open: {is_open}, Current: {is_current}, Amount OK: {credit_limit >= 1000 or original_amount >= 1000}"
            )
            t["evaluation"]["reasons"].append(
                f"12+ months: {has_12_months}, Individual: {is_individual}"
            )
        else:
            t["evaluation"]["reasons"].append("Does not meet all positive criteria")

    # EVALUATE POSITIVE TRADELINES - MORTGAGE EXCEPTION
    elif is_conventional_fha:
        # Special mortgage criteria
        if is_open and is_current and original_amount > 30000:

            t["evaluation"].update(
                {
                    "status": "accepted",
                    "is_positive": True,
                    "reasons": ["ACCEPTED as positive mortgage tradeline"],
                }
            )
            t["evaluation"]["reasons"].append(
                f"Open: {is_open}, Current: {is_current}, Original amount: ${original_amount} > $30,000"
            )
        else:
            t["evaluation"]["reasons"].append("Does not meet mortgage criteria")

    # EVALUATE NEGATIVE TRADELINES
    # Skip medical and educational for negative evaluation
    if not is_medical_or_edu:
        is_negative = False

        # Check for specific negative conditions
        if (
            "unpaid balance reported as loss" in account_condition
            or "unpaid balance reported as loss" in payment_status
        ):
            is_negative = True
            t["evaluation"]["reasons"].append(
                "Negative: Unpaid balance reported as loss"
            )

        # FIX #4: Ensure we're properly catching "Seriously Past Due"
        if "seriously past due" in payment_status.lower():
            is_negative = True
            t["evaluation"]["reasons"].append("Negative: Seriously past due")

        if (
            "legally paid in full for less than full balance" in account_condition
            and "unpaid balance reported as loss" in payment_status
        ):
            is_negative = True
            t["evaluation"]["reasons"].append(
                "Negative: Legally paid for less than full balance with unpaid balance"
            )

        # FIX #1 and #3: Check for past due days but exclude "current/was X past due" pattern
        past_due_days = ["60", "90", "120", "150", "180"]

        # Check if account is past due and NOT "paid/zero balance"
        if not "paid/zero balance" in account_condition:
            for days in past_due_days:
                # Match specific pattern like "60 days past due" but not "current/was 60 days past due"
                pattern = f"{days} days past due"
                if (
                    pattern in payment_status
                    and not f"current/was {pattern}" in payment_status.lower()
                ):
                    is_negative = True
                    t["evaluation"]["reasons"].append(
                        f"Negative: Account {days} days past due"
                    )
                    break

        if is_negative:
            t["evaluation"].update(
                {
                    "status": "rejected",
                    "is_negative": True,
                }
            )

    # Handle skipped tradelines (neither positive nor negative)
    if not (t["evaluation"]["is_positive"] or t["evaluation"]["is_negative"]):
        t["evaluation"].update(
            {
                "status": "skipped",
                "is_skipped": True,
                "reasons": ["Does not meet criteria for positive or negative scoring"],
            }
        )

        # Add more specific skip reasons
        if is_medical_or_edu:
            t["evaluation"]["reasons"].append(
                "Medical or Educational account type excluded"
            )
        if is_auto:
            t["evaluation"]["reasons"].append(
                "Auto loan/lease excluded from positive scoring"
            )
        if is_selfreported:
            t["evaluation"]["reasons"].append(
                "SELFREPORTED tradeline excluded from positive scoring"
            )

    return t


def score_credit_report(pdf_path):
    """
    Main function to open the PDF, parse data, apply scoring logic,
    and return (final_score, final_grade, extras).
    """
    doc = fitz.open(pdf_path)

    # Use today's date as the "report date"
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

    # Parse and evaluate tradelines
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

    # Default redemption result
    redemption_result = {
        "final_score": raw_score,
        "positive_count": len(pos_tradelines),
        "negative_count": len(neg_tradelines),
    }

    # Redemption scenario check (Exception #1)
    redemption_applied = False

    # Get percentage of negative tradelines older than 2 years
    pct_old_negative = get_negative_tradelines_for_redemption(all_tradelines)

    # Check if 70% or more of negative tradelines are older than 2 years
    if pct_old_negative >= 0.7 and neg_tradelines:
        # For redemption, exclude negative tradelines older than 3 years
        three_years_ago = datetime.now().date().replace(year=datetime.now().year - 3)
        filtered_tradelines = []

        for tradeline in all_tradelines:
            if tradeline["evaluation"]["is_negative"]:
                # If negative, check if it's older than 3 years
                status_dt = parse_date(tradeline["status_date"])
                if status_dt and status_dt < three_years_ago:
                    # This negative tradeline is old (>3 years); exclude it
                    continue
                else:
                    # Keep newer negative tradelines
                    filtered_tradelines.append(tradeline)
            else:
                # Keep all non-negative tradelines
                filtered_tradelines.append(tradeline)

        # Recalculate positive/negative counts with filtered list
        redemption_pos = sum(
            t["evaluation"]["is_positive"] for t in filtered_tradelines
        )
        redemption_neg = sum(
            t["evaluation"]["is_negative"] for t in filtered_tradelines
        )
        redemption_score = base_score + redemption_pos - redemption_neg

        # Update results only if redemption scenario yields a better score
        if redemption_score > raw_score:
            raw_score = redemption_score
            pos_tradelines = [
                t for t in filtered_tradelines if t["evaluation"]["is_positive"]
            ]
            neg_tradelines = [
                t for t in filtered_tradelines if t["evaluation"]["is_negative"]
            ]
            redemption_applied = True

            redemption_result = {
                "final_score": redemption_score,
                "positive_count": redemption_pos,
                "negative_count": redemption_neg,
            }

    # Calculate final grade
    final_grade = grade_report(raw_score, pos_tradelines)

    # Prepare extras for reporting
    extras = {
        "positive_count": len(pos_tradelines),
        "negative_count": len(neg_tradelines),
        "base_score_start": base_score,
        "has_bankruptcy": has_bankruptcy,
        "pct_neg_older_2yr": pct_old_negative,
        "redemption_applied": redemption_applied,
        "redemption_result": redemption_result,
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
        # mstat = re.search(r"Status\s*Date\s*([\d/]+)", chunk)
        mstat = extract_status_date(lines)
        if mstat is not None:
            tline["status_date"] = mstat

        yield tline
