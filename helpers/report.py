import fitz  # PyMuPDF
from datetime import datetime
from helpers.cleaner import (
    clean_text,
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
    if negative_tradelines:
        pct_older = len(older_than_2yrs) / len(negative_tradelines)
        return pct_older
    return 0.0


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
        print(f"   Responsibility: {tradeline.get('responsibility', 'N/A')}")
        print(f"   Open Date: {tradeline.get('open_date', 'N/A')}")
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
        print(f"   Responsibility: {tradeline.get('responsibility', 'N/A')}")
        print(f"   Open Date: {tradeline.get('open_date', 'N/A')}")
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
        print(f"   Responsibility: {tradeline.get('responsibility', 'N/A')}")
        print(f"   Open Date: {tradeline.get('open_date', 'N/A')}")
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
    elif final_score in [1, 2]:
        return 3
    elif final_score in [3, 4]:
        # check if final_score == 4 and we have an open mortgage => grade=1
        has_open_mortgage = any(
            t["is_mortgage"] for t in positive_tradelines if t.get("is_mortgage")
        )
        if final_score == 4 and has_open_mortgage:
            return 1
        else:
            return 2
    else:
        return 1


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
        full_text += page.get_text("text")
    doc.close()

    # Check for prior bankruptcy (Exception #2)
    has_bankruptcy = check_prior_bankruptcy(full_text)

    # If there is a bankruptcy, score starts at -1, else 0
    base_score = -1 if has_bankruptcy else 0

    # We parse the tradelines
    positive_count = 0
    negative_count = 0
    positive_tradelines_list = []
    negative_tradelines_list = []
    skipped_tradelines_list = []
    all_tradelines = []

    for t in get_tradelines(full_text):
        # Store the tradeline for later reference
        all_tradelines.append(t)

        # Initialize evaluation details
        t["evaluation"] = {
            "status": "pending",
            "is_bankruptcy_related": False,
            "is_positive": False,
            "is_negative": False,
            "is_skipped": False,
            "reasons": [],
        }

        # ----- Possibly skip if "Debt included in or discharged through Bankruptcy" for prior bankruptcy scenario
        if has_bankruptcy:
            if (
                t.get("account_condition", "")
                .lower()
                .find("discharged through bankruptcy")
                >= 0
                or t.get("account_condition", "").lower().find("included in bankruptcy")
                >= 0
            ):
                # Skip counting entirely
                t["evaluation"]["status"] = "skipped"
                t["evaluation"]["is_skipped"] = True
                t["evaluation"]["is_bankruptcy_related"] = True
                t["evaluation"]["reasons"].append(
                    "Excluded due to bankruptcy discharge"
                )
                skipped_tradelines_list.append(t)
                continue

        # ---------- Step 2: +1 conditions -----------
        # Quick check for mortgage:
        is_mortgage = False
        if t["account_type"]:
            if "real estate" in t["account_type"] or "mortgage" in t["account_type"]:
                is_mortgage = True
                t["evaluation"]["reasons"].append("Identified as mortgage")

        # We'll store this on the tradeline for final grading logic
        t["is_mortgage"] = is_mortgage

        # We'll define a helper to see if the account is open + current
        is_open_and_current = False
        if t is not None:  # Make sure t exists
            account_condition = t.get("account_condition")
            payment_status = t.get("payment_status")

            if isinstance(account_condition, str) and isinstance(payment_status, str):
                if account_condition.lower().startswith(
                    "open"
                ) and payment_status.lower().startswith("current"):
                    is_open_and_current = True
                    t["evaluation"]["reasons"].append("Account is open and current")
                else:
                    t["evaluation"]["reasons"].append(
                        f"Account is not open and current: {account_condition} / {payment_status}"
                    )
            else:
                t["evaluation"]["reasons"].append(
                    f"Account condition or payment status missing: {account_condition} / {payment_status}"
                )
        else:
            print("Error: Tradeline object is None")

        # figure out months on file
        months_on_file = t["months_reviewed"]
        if months_on_file is None and t["open_date"]:
            # fallback: compare open_date with report_date
            months_on_file = compute_months_diff(t["open_date"], report_date)

        if months_on_file is not None:
            t["evaluation"]["reasons"].append(f"Months on file: {months_on_file}")
            if months_on_file >= 12:
                t["evaluation"]["reasons"].append("Meets minimum 12 months requirement")
            else:
                t["evaluation"]["reasons"].append(
                    "Does not meet minimum 12 months requirement"
                )
        else:
            t["evaluation"]["reasons"].append("Unable to determine months on file")

        # Check "credit limit > 1000" requirement
        limit_ok = t["credit_limit"] and (t["credit_limit"] > 1000)
        if t["credit_limit"]:
            t["evaluation"]["reasons"].append(f"Credit limit: ${t['credit_limit']}")
            if limit_ok:
                t["evaluation"]["reasons"].append(
                    "Meets minimum $1000 credit limit requirement"
                )
            else:
                t["evaluation"]["reasons"].append(
                    "Does not meet minimum $1000 credit limit requirement"
                )
        else:
            t["evaluation"]["reasons"].append("No credit limit found")

        # Check if it is auto/lease, student, or medical => skip from positive
        skip_for_positive = False
        if t["is_medical_or_edu"]:
            skip_for_positive = True
            t["evaluation"]["reasons"].append(
                "Medical or educational account - not counted as positive"
            )

        # Also skip if the account_type has "Auto Loan" or "Auto Lease"
        if t["account_type"] and (
            "auto loan" in t["account_type"] or "auto lease" in t["account_type"]
        ):
            skip_for_positive = True
            t["evaluation"]["reasons"].append(
                "Auto loan or lease - not counted as positive"
            )

        # For the mortgage exception: if is_mortgage, we do NOT require responsibility=Individual
        # but for normal accounts, we want responsibility=Individual
        responsibility = t.get("responsibility")
        meets_responsibility = False
        if is_mortgage:
            # Mortgage can be joint or individual, as long as open+current
            meets_responsibility = True
            t["evaluation"]["reasons"].append(
                "Mortgage - responsibility requirement waived"
            )
        else:
            # Non-mortgage must be 'Individual'
            if responsibility and responsibility.lower().startswith("individual"):
                meets_responsibility = True
                t["evaluation"]["reasons"].append("Individual responsibility")
            else:
                t["evaluation"]["reasons"].append(
                    f"Not individual responsibility: {t.get('responsibility', 'N/A')}"
                )
        # Now combine all conditions for +1
        if (
            is_open_and_current
            and meets_responsibility
            and limit_ok
            and months_on_file is not None
            and months_on_file >= 12
            and not skip_for_positive
        ):
            positive_count += 1
            t["evaluation"]["status"] = "accepted"
            t["evaluation"]["is_positive"] = True
            t["evaluation"]["reasons"].append("ACCEPTED as positive tradeline")
            positive_tradelines_list.append(t)
        else:
            t["evaluation"]["reasons"].append("NOT accepted as positive tradeline")

        # ---------- Step 3: -1 conditions -----------
        # -1 for any tradeline that is "Unpaid balance reported as loss" or "Seriously Past Due"
        # except if it's medical or education type, in which case we skip negative.
        negative_flag = False
        cond_lower = t.get("account_condition", "")
        if cond_lower is not None:
            cond_lower = cond_lower.lower()
        else:
            cond_lower = ""

        stat_lower = t.get("payment_status", "")
        if stat_lower is not None:
            stat_lower = stat_lower.lower()
        else:
            stat_lower = ""

        # check for "Unpaid balance reported as loss" or "Seriously Past Due"
        if ("unpaid balance reported as loss" in cond_lower) or (
            "seriously past due" in stat_lower
        ):
            t["evaluation"]["reasons"].append("Negative status detected")
            # skip if medical or edu
            if not t["is_medical_or_edu"]:
                negative_flag = True
                t["evaluation"]["reasons"].append("Counted as negative tradeline")
            else:
                t["evaluation"]["reasons"].append(
                    "Medical/educational account - negative status ignored"
                )

        if negative_flag:
            negative_count += 1
            t["evaluation"]["status"] = "rejected"
            t["evaluation"]["is_negative"] = True
            negative_tradelines_list.append(t)

        # If neither positive nor negative nor skipped due to bankruptcy
        if (
            not t["evaluation"]["is_positive"]
            and not t["evaluation"]["is_negative"]
            and not t["evaluation"]["is_bankruptcy_related"]
        ):
            t["evaluation"]["status"] = "skipped"
            t["evaluation"]["is_skipped"] = True
            t["evaluation"]["reasons"].append(
                "Does not meet criteria for positive or negative"
            )
            skipped_tradelines_list.append(t)

    # Combine into final score:
    raw_score = base_score + positive_count - negative_count

    # Track if redemption scenario was applied
    redemption_applied = False
    redemption_result = {
        "applied": False,
        "positive_count": 0,
        "negative_count": 0,
        "final_score": raw_score,
    }

    # ---------------- EXCEPTION #1: "Redemption Scenario" ----------------
    # If 70% of the negative tradelines have a status date older than 2 years,
    # then re-score ignoring any tradelines older than 3 years.

    pct_older = get_negative_tradelines_for_redemption(negative_tradelines_list)
    if pct_older >= 0.70 and negative_tradelines_list:
        # "When 70% of the -1 tradelines have a status date older than 2 years old,
        #  then we re-compute the report's score but only counting tradelines with
        #  a status date within the last 3 years."

        redemption_applied = True
        redemption_result["applied"] = True

        three_years_ago = datetime.now().date().replace(year=datetime.now().year - 3)

        # We re-run the logic with only 'recent' tradelines (status_date >= 3 years ago).
        # For simplicity, let's define a quick function:

        def in_last_3_years(t):
            sd = t["status_date"]
            if not sd:
                # if no status date found, we might keep it.
                # Or we treat "no date" as not countable. We'll keep it for demonstration
                return True
            return sd >= three_years_ago

        # Re-initialize
        redemption_pos = 0
        redemption_neg = 0
        redemption_pos_tradelines = []
        redemption_neg_tradelines = []

        for t in all_tradelines:
            # Add redemption evaluation to each tradeline
            t["redemption_evaluation"] = {
                "considered": False,
                "reason": "Not considered for redemption scoring",
            }

            # skip bankruptcy condition:
            if has_bankruptcy:
                if (
                    t.get("account_condition", "")
                    .lower()
                    .find("discharged through bankruptcy")
                    >= 0
                    or t.get("account_condition", "")
                    .lower()
                    .find("included in bankruptcy")
                    >= 0
                ):
                    t["redemption_evaluation"]["reason"] = "Excluded due to bankruptcy"
                    continue

            # only count if in last 3 years
            if not in_last_3_years(t):
                t["redemption_evaluation"][
                    "reason"
                ] = "Excluded due to being older than 3 years"
                continue

            t["redemption_evaluation"]["considered"] = True
            t["redemption_evaluation"]["reason"] = "Considered for redemption scoring"

            # check +1 conditions again
            # (the same logic as before, only shortened for demonstration)
            is_open_and_current = t.get("account_condition", "").lower().startswith(
                "open"
            ) and t.get("payment_status", "").lower().startswith("current")

            is_mortgage = False
            if t["account_type"] and (
                "real estate" in t["account_type"] or "mortgage" in t["account_type"]
            ):
                is_mortgage = True
            t["is_mortgage"] = is_mortgage

            # months
            months_on_file = t["months_reviewed"]
            if months_on_file is None and t["open_date"]:
                months_on_file = compute_months_diff(
                    t["open_date"], datetime.now().date()
                )

            limit_ok = t["credit_limit"] and (t["credit_limit"] > 1000)

            skip_for_positive = False
            if t["is_medical_or_edu"]:
                skip_for_positive = True
            if t["account_type"] and (
                "auto loan" in t["account_type"] or "auto lease" in t["account_type"]
            ):
                skip_for_positive = True

            meets_responsibility = False
            if is_mortgage:
                meets_responsibility = True
            else:
                if t.get("responsibility", "").lower().startswith("individual"):
                    meets_responsibility = True

            # +1
            if (
                is_open_and_current
                and meets_responsibility
                and limit_ok
                and months_on_file is not None
                and months_on_file >= 12
                and not skip_for_positive
            ):
                redemption_pos += 1
                t["redemption_evaluation"]["status"] = "positive"
                redemption_pos_tradelines.append(t)

            # -1
            cond_lower = t.get("account_condition", "").lower()
            stat_lower = t.get("payment_status", "").lower()
            if ("unpaid balance reported as loss" in cond_lower) or (
                "seriously past due" in stat_lower
            ):
                if not t["is_medical_or_edu"]:
                    redemption_neg += 1
                    t["redemption_evaluation"]["status"] = "negative"
                    redemption_neg_tradelines.append(t)

        # final redemption score:
        redemption_raw_score = base_score + redemption_pos - redemption_neg
        redemption_result["positive_count"] = redemption_pos
        redemption_result["negative_count"] = redemption_neg
        redemption_result["final_score"] = redemption_raw_score

        # Use the better score between original and redemption
        if redemption_raw_score > raw_score:
            raw_score = redemption_raw_score
            # Update the lists to reflect the redemption scenario results
            positive_tradelines_list = redemption_pos_tradelines
            negative_tradelines_list = redemption_neg_tradelines

    # --------------- Now map raw_score -> final grade ---------------
    final_score = raw_score
    final_grade = grade_report(final_score, positive_tradelines_list)

    # Just for demonstration, we pack some "extra info" into a dictionary:
    extras = {
        "positive_count": positive_count,
        "negative_count": negative_count,
        "base_score_start": base_score,
        "has_bankruptcy": has_bankruptcy,
        "pct_neg_older_2yr": pct_older,
        "redemption_applied": redemption_applied,
        "redemption_result": redemption_result if redemption_applied else None,
        "accepted_tradelines": positive_tradelines_list,
        "rejected_tradelines": negative_tradelines_list,
        "skipped_tradelines": skipped_tradelines_list,
        "all_tradelines": all_tradelines,
    }

    return final_score, final_grade, extras


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
            "high_balance": None,
            "responsibility": None,
            "open_date": None,
            "status_date": None,
            "is_medical_or_edu": False,
            "account_number": None,
            "raw_text": chunk,  # Store the raw text for debugging
        }

        # Try to parse out "account_type" from the first line if possible
        # e.g. 'BC  - Bank Credit Cards', 'EL - Student Loans', etc.
        # We'll do a quick match:
        mtype = re.search(r"/\s*([A-Z]{2,3})\s*-\s*(.*)", first_line)
        if mtype:
            # Example: group(1) = "BC", group(2) = "Bank Credit Cards"
            # or group(1) = "EL", group(2) = "Student Loans"
            tline["account_type"] = mtype.group(2).strip().lower()

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
        mmonths = re.search(r"Months\s*Review ed\S*:\s*(\d+)", chunk)
        if mmonths:
            tline["months_reviewed"] = int(mmonths.group(1))

        # Look for "Credit Limit" and get the next valid number
        credit_limit_search_result = extract_credit_limit(lines)
        if credit_limit_search_result is not None:
            tline["credit_limit"] = credit_limit_search_result

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
