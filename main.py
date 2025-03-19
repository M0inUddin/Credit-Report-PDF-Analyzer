import os
from helpers.report import print_detailed_report, score_credit_report

# Main directory containing PDF files
pdf_files_path = "docs"
# Get all PDF files in the directory
pdf_files_path = [
    f"{pdf_files_path}/{file}"
    for file in os.listdir(pdf_files_path)
    if file.endswith(".pdf")
]
for pdf_file_path in pdf_files_path:
    score, grade, details = score_credit_report(pdf_file_path)
    print_detailed_report(score, grade, details)
