from datetime import datetime
import re


def clean_text(text):
    """Clean unwanted characters like non-breaking spaces and excessive spaces."""
    return text.replace("\xa0", " ").strip()


def parse_date(date_str):
    """Parse dates of the form MM/YYYY. Returns a datetime.date or None."""
    try:
        return datetime.strptime(date_str.strip(), "%m/%Y").date()
    except:
        return None


def compute_months_diff(d1, d2):
    """
    Returns the number of full months between two date objects.
    """
    return (d2.year - d1.year) * 12 + (d2.month - d1.month)


def extract_credit_limit(lines):
    """
    Extracts the Credit Limit from a list of lines.
    This function looks for the first dollar amount in the lines after finding "Credit Limit".
    """
    # Check if "Credit" and "Limit" appear in the same line
    credit_limit_index = -1

    # If not found, check for consecutive lines
    if credit_limit_index == -1:
        for i in range(len(lines) - 1):
            if "Credit" in lines[i] and "Limit" in lines[i + 1]:
                credit_limit_index = i + 1
                break

    # If we found "Credit Limit", search for the first dollar amount after that
    if credit_limit_index != -1:
        for i in range(credit_limit_index + 1, len(lines)):
            # Clean the line for non-breaking spaces
            cleaned_line = lines[i].replace("\xa0", " ").strip()

            # Match any dollar amount like "$300", "$500.75", etc.
            match = re.search(r"\$([\d,]+(?:\.\d{2})?|\d+)", cleaned_line)
            if match:
                # Return the first matched amount as the Credit Limit
                return int(
                    match.group(1).replace(",", "")
                )  # Remove commas and convert to integer

    # If no Credit Limit found, return None
    return None


def extract_original_amount(lines):
    """
    Extracts the Original Amount from a list of lines.
    This function looks for the first dollar amount in the lines after finding "Original Amount".
    """
    # Check if "Original" and "Amount" appear in the same line
    original_amount_index = -1

    # If not found, check for consecutive lines
    if original_amount_index == -1:
        for i in range(len(lines) - 1):
            if "Original" in lines[i] and "Amount" in lines[i + 1]:
                original_amount_index = i + 1
                break

    # If we found "Original Amount", search for the first dollar amount after that
    if original_amount_index != -1:
        for i in range(original_amount_index + 1, len(lines)):
            # Clean the line for non-breaking spaces
            cleaned_line = lines[i].replace("\xa0", " ").strip()

            # Match any dollar amount like "$300", "$500.75", etc.
            match = re.search(r"\$([\d,]+(?:\.\d{2})?|\d+)", cleaned_line)
            if match:
                # Return the first matched amount as the Original Amount
                return int(
                    match.group(1).replace(",", "")
                )  # Remove commas and convert to integer

    # If no Original Amount found, return None
    return None


def extract_status_date(lines):
    """
    Extracts the Status Date from a list of lines.
    This function looks for the second date in the lines after finding "Status Date".
    """
    # Check if "Status" and "Date" appear in the same line
    status_date_index = -1

    # If not found, check for consecutive lines
    if status_date_index == -1:
        for i in range(len(lines) - 1):
            if "Status" in lines[i] and "Date" in lines[i + 1]:
                status_date_index = i + 1
                break

    # If we found "Status Date", search for the second date after that
    if status_date_index != -1:
        for i in range(status_date_index + 1, len(lines)):
            # Clean the line for non-breaking spaces
            cleaned_line = lines[i].replace("\xa0", " ").strip()
            # Match dates in format MM/DD/YYYY
            match = re.search(r"(\d{2}/\d{2}/\d{4})", cleaned_line)
            if match:
                # Return the matched date string
                continue
            # Match dates in format MM/YYYY
            match = re.search(r"(\d{2}/\d{4})", cleaned_line)
            if match:
                # Return the matched date string
                return match.group(1)

    # If no Status Date found, return None
    return None
