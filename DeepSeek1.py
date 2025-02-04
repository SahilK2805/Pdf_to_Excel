from flask import Flask, render_template, request, send_file
import os
import pdfplumber
import pandas as pd
import re
import json
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()
API_KEY = os.getenv("AIzaSyAkwYbAyAmR7CoteNfIrkv29eHVTIvk7oY")  
# Configure Gemini
genai.configure(api_key=API_KEY)

# Initialize Flask app
app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Initialize the Gemini model
try:
    model = genai.GenerativeModel("gemini-1.5-flash")
    print("Gemini Model Initialized")
except Exception as e:
    print(f"Error initializing Gemini model: {e}")
    model = None

# Extract text from PDF
def extract_pdf_text(pdf_path):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            return "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())
    except Exception as e:
        print(f"Error extracting text: {e}")
        return None

# Process with Gemini
def process_with_gemini(raw_text):
    try:
        prompt = f"""
        The following is the text extracted from a PDF that contains multiple invoices and multiple items within those invoices. Extract and format the data into a structured JSON array where each item in the array represents a separate item in the invoice. Ensure every field has accurate data and is not left blank. If data is missing, infer it logically from nearby text. Extract numerical fields correctly and format all dates as DD-MM-YYYY.
        {json.dumps({
            "SR.No": "(Start from 1 and increment sequentially for each item, no duplicates)",
            "Invoice No": "(Ensure consistency across invoices, extract exactly as in PDF)",
            "Invoice Date": "(Convert to DD-MM-YYYY format)",
            "SB No": "(Extract as shown in PDF, verify it matches other invoice fields)",
            "SB Date": "(Format as DD-MM-YYYY)",
            "LEO Date": "(Ensure this is accurate and formatted correctly)",
            "Description": "(Extract full description, avoid truncation)",
            "Quantity": "(Ensure numeric accuracy)",
            "UQC": "(Extract correct unit quantity code, validate against description)",
            "Port Code": "(Extract and cross-check with Port of Export)",
            "Port of Export": "(Match closest location related to export)",
            "PMV": "(Extract numeric value, verify against FOB (INR))",
            "FOB (INR)": "(Ensure correct currency and numeric format)",
            "DBK Amount": "(Extract and cross-check with duty-related values)",
            "% of Air DBK": "(Extract as a percentage, verify against Air Duty Drawback Amount)",
            "Air Scroll No": "(Locate Air Scroll details and match with Air DBK info)",
            "Air Scroll Date": "(Match date from Air Scroll entry, format as DD-MM-YYYY)",
            "Export Incentive Scheme": "(Ensure it is captured correctly and matches related financial fields)",
            "Item SNO": "(Ensure unique numbering per item)",
            "Invoice SNO": "(Match this field to the correct invoice)",
            "DBK SNO": "(Cross-check with DBK Amount and validate uniqueness)",
            "QTY/WT": "(Extract and ensure numeric accuracy)",
            "Rate": "(Extract and verify currency format)",
            "Invoice Value": "(Ensure correct total calculation)",
            "FOB Value": "(Cross-check with FOB (INR) for consistency)"
     
        }, indent=4)}
        Ensure numerical values are extracted correctly, and if a field is missing, infer it logically from the text. Here is the text:
        {raw_text}
        """
        response = model.generate_content(prompt)
        
        print("Raw response from Gemini:")
        print(response.text)

        try:
            structured_data = json.loads(response.text)
            
            # Ensure SR.No is sequential and correct
            for index, item in enumerate(structured_data, start=1):
                item["SR.No"] = index
            
            return structured_data
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON directly. Trying regex... Error: {e}")
            match = re.search(r"```json\n(.*?)\n```", response.text, re.DOTALL)
            if match:
                json_content = match.group(1)
                structured_data = json.loads(json_content)
                for index, item in enumerate(structured_data, start=1):
                    item["SR.No"] = index
                return structured_data
            else:
                print("No JSON found in the response.")
                return None
    except Exception as e:
        print(f"Error processing with Gemini: {e}")
        return None

# Generate Excel
def generate_excel(data, output_path):
    try:
        df = pd.DataFrame(data)
        df.to_excel(output_path, index=False, engine="openpyxl")
    except Exception as e:
        print(f"Error generating Excel: {e}")

# Flask Routes
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload():
    if "pdf" not in request.files:
        return "No file uploaded", 400
    pdf_file = request.files["pdf"]
    if pdf_file.filename == "":
        return "No file selected", 400

    pdf_path = os.path.join(app.config["UPLOAD_FOLDER"], pdf_file.filename)
    pdf_file.save(pdf_path)

    raw_text = extract_pdf_text(pdf_path)
    if not raw_text:
        return "Failed to extract text from PDF", 500

    structured_data = process_with_gemini(raw_text)
    if not structured_data:
        return "Failed to process PDF with Gemini", 500

    output_path = os.path.join(OUTPUT_FOLDER, "output.xlsx")
    generate_excel(structured_data, output_path)
    
    return send_file(output_path, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)
