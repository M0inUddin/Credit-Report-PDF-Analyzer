import gradio as gr
import tempfile
import os
from helpers.report import score_credit_report, print_detailed_report
import io
from contextlib import redirect_stdout


def process_credit_report(pdf_file):
    """
    Process the uploaded PDF credit report and return the analysis results.
    """
    if pdf_file is None:
        return "Please upload a PDF file.", "", "", ""

    # Save the uploaded file to a temporary location
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
        # In Gradio, file uploads come as file-like objects with a name
        # We need to handle this appropriately
        if hasattr(pdf_file, "name"):
            # This is a file path from Gradio's File component
            temp_path = pdf_file.name
        else:
            # Fall back to writing the content (though this shouldn't happen with the fix)
            temp_path = temp_pdf.name
            with open(pdf_file, "rb") as f:
                temp_pdf.write(f.read())

    try:
        # Score and grade the credit report
        score, grade, details = score_credit_report(temp_path)

        # Capture the output of print_detailed_report in a string
        output = io.StringIO()
        with redirect_stdout(output):
            print_detailed_report(score, grade, details)

        # Get the detailed report as text
        detailed_report = output.getvalue()

        # Create a summary for the quick results
        summary = f"Final Score: {score}\nFinal Grade: {grade}\n"
        summary += f"Positive Tradelines: {details['positive_count']}\n"
        summary += f"Negative Tradelines: {details['negative_count']}\n"

        if details["redemption_applied"]:
            summary += f"Redemption Scenario Applied: Yes\n"
            summary += f"Score after redemption: {details['redemption_result']['final_score']}\n"

        # Return both the summary and detailed report
        return (
            summary,
            detailed_report,
            create_grade_html(grade),
            create_score_html(score),
        )

    except Exception as e:
        return f"Error processing file: {str(e)}", "", "", ""

    finally:
        # Only clean up the temp file if we created one
        if (
            "temp_path" in locals()
            and os.path.exists(temp_path)
            and hasattr(pdf_file, "name") is False
        ):
            os.unlink(temp_path)


def create_grade_html(grade):
    """
    Create HTML representation of the grade with appropriate color coding.
    """
    grade_colors = {
        1: "#4CAF50",  # Green
        2: "#8BC34A",  # Light Green
        3: "#FFC107",  # Amber
        4: "#FF9800",  # Orange
        5: "#F44336",  # Red
    }

    color = grade_colors.get(grade, "#607D8B")  # Default to gray

    html = f"""
    <div style="display: flex; justify-content: center; align-items: center;">
        <div style="background-color: {color}; width: 120px; height: 120px; border-radius: 60px; 
                    display: flex; justify-content: center; align-items: center;">
            <span style="color: white; font-size: 60px; font-weight: bold;">{grade}</span>
        </div>
    </div>
    <div style="text-align: center; margin-top: 10px; font-weight: bold;">GRADE</div>
    """
    return html


def create_score_html(score):
    """
    Create HTML representation of the score with appropriate color coding.
    """
    # Determine color based on score
    if score < 0:
        color = "#F44336"  # Red
    elif score == 0:
        color = "#FF9800"  # Orange
    elif score in [1, 2]:
        color = "#FFC107"  # Amber
    elif score in [3, 4]:
        color = "#8BC34A"  # Light Green
    else:
        color = "#4CAF50"  # Green

    html = f"""
    <div style="display: flex; justify-content: center; align-items: center;">
        <div style="background-color: {color}; width: 120px; height: 120px; border-radius: 60px; 
                    display: flex; justify-content: center; align-items: center;">
            <span style="color: white; font-size: 60px; font-weight: bold;">{score}</span>
        </div>
    </div>
    <div style="text-align: center; margin-top: 10px; font-weight: bold;">SCORE</div>
    """
    return html


# Create the Gradio interface
with gr.Blocks(title="Credit Report Analysis", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# Credit Report Analysis")
    gr.Markdown("Upload a credit report PDF file to analyze its creditworthiness.")

    with gr.Row():
        with gr.Column():
            # Use the specific file_types parameter to ensure we get PDF files
            input_pdf = gr.File(label="Upload Credit Report PDF", file_types=[".pdf"])
            analyze_btn = gr.Button("Analyze Report", variant="primary")

        with gr.Column():
            with gr.Row():
                score_display = gr.HTML(label="Score")
                grade_display = gr.HTML(label="Grade")

            summary_output = gr.Textbox(label="Summary", lines=6, interactive=False)

    detailed_output = gr.Textbox(
        label="Detailed Report", lines=20, max_lines=40, interactive=False
    )

    analyze_btn.click(
        fn=process_credit_report,
        inputs=[input_pdf],
        outputs=[summary_output, detailed_output, grade_display, score_display],
    )

    gr.Markdown(
        """
    ## How to Use
    1. Upload a credit report PDF file
    2. Click the "Analyze Report" button
    3. Review the summary and detailed analysis
    
    ## Understanding Results
    - **Grade 1:** Excellent credit profile
    - **Grade 2:** Good credit profile
    - **Grade 3:** Fair credit profile
    - **Grade 4:** Poor credit profile
    - **Grade 5:** Very poor credit profile
    """
    )

# Launch the app
if __name__ == "__main__":
    demo.launch()
