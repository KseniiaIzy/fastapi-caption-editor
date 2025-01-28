from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
import os
import zipfile
import datetime
import re
from collections import Counter
from io import BytesIO

app = FastAPI()

from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="FastAPI Caption Editor",
        version="1.0",
        description="API for processing captions",
        routes=app.routes,
    )
    openapi_schema["servers"] = [
        {"url": "https://fastapi-caption-editor.onrender.com", "description": "Render Deployment"}
    ]
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Setup directories
output_dir = "output_captions"
os.makedirs(output_dir, exist_ok=True)

# Processing Rules
processing_rules = [
    ("branches that are growing upwards", "upward growing branches"),
    ("tree with green leaves and green flowers and grass", "tree with green leaves, flowers and grass"),
]

# Extract filename and description
def extract_file_and_description(line):
    match = re.match(r"^(.*\.txt):\s*(.+)", line)
    if match:
        return match.group(1), match.group(2)
    raise ValueError(f"Invalid line format: {line}")

# Identify the most common trigger token
def identify_trigger_token(lines):
    tokens = [line.split(",")[0].strip() for _, line in lines if "," in line]
    return Counter(tokens).most_common(1)[0][0]

# Handle trigger token
def process_trigger_token(description, standard_trigger):
    if not description.startswith(standard_trigger):
        return f"{standard_trigger}, {description}", f"Added missing trigger token: '{standard_trigger}'"
    return description, None

# Simplify description
def simplify_object_description(description):
    logs = []
    original_description = description

    # Rule 1: Condense subordinate clauses
    if re.search(r"\b(that are|that is|that has|which are|which is|which has)\b", description):
        description = re.sub(r"\b(that are|that is|that has|which are|which is|which has)\b", "", description)
        logs.append("Condensed subordinate clauses.")

    # Rule 2: Remove auxiliary verbs
    if re.search(r"\b(is|are|was|were|has|have|had|does|do|did)\b", description):
        description = re.sub(r"\b(is|are|was|were|has|have|had|does|do|did)\b", "", description)
        logs.append("Removed auxiliary verbs.")

    # Rule 3: Simplify repetitive phrases
    if re.search(r"\b(\w+)\s\1\b", description):
        description = re.sub(r"\b(\w+)\s\1\b", r"\1", description)
        logs.append("Simplified repetitive phrases.")

    # Final clean-up
    description = " ".join(description.split())
    if description != original_description:
        logs.append("Ensured clarity and grammatical correctness.")
    
    return description.strip(), logs

# Handle articles
def handle_articles(description):
    logs = []
    required_phrases = {
        "on the left", "on the right", "at the top", "at the bottom",
        "in the center", "on the horizon", "from the ground", "at the base",
        "in the middle", "on the surface", "in the shadow", "at the tip",
    }

    # Add articles in required phrases
    for phrase in required_phrases:
        short_variant = phrase.replace("the ", "")
        if short_variant in description:
            description = description.replace(short_variant, phrase)
            logs.append(f"Added article in fixed expression: '{short_variant}' → '{phrase}'.")

    return description, logs

# Process captions
def process_captions(lines):
    processed_data = []

    # Parse lines into filenames and descriptions
    parsed_lines = [extract_file_and_description(line) for line in lines if line.strip()]

    # Identify the most common trigger token
    standard_trigger = identify_trigger_token(parsed_lines)

    for file_name, description in parsed_lines:
        original_description = description.strip()
        logs_for_description = []

        # Process trigger token
        description, trigger_log = process_trigger_token(description, standard_trigger)
        if trigger_log:
            logs_for_description.append(trigger_log)

        # Handle articles
        description, article_logs = handle_articles(description)
        logs_for_description.extend(article_logs)

        # Simplify object description
        description, simplification_logs = simplify_object_description(description)
        logs_for_description.extend(simplification_logs)

        # Finalize description
        description = " ".join(description.split())

        # Log changes or note no changes made
        if description == original_description:
            logs_for_description.append("No changes made.")
        else:
            processed_data.append({
                "file_name": file_name.strip(),
                "original": original_description,
                "corrected": description.strip(),
                "logs": logs_for_description
            })

    return processed_data

@app.post("/process_captions")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only .txt files are supported.")
    
    lines = file.file.read().decode("utf-8").splitlines()

    try:
        processed_data = process_captions(lines)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Save results and logs to a ZIP file
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zipf:
        # Write each processed description to a file
        for data in processed_data:
            file_path = os.path.join(output_dir, data["file_name"])
            with open(file_path, "w") as f:
                f.write(data["corrected"])
            zipf.write(file_path, data["file_name"])

        # Generate consolidated log file
        log_file_path = os.path.join(output_dir, "updated_captions.txt")
        with open(log_file_path, "w") as log_file:
            for data in processed_data:
                log_file.write(f"File: {data['file_name']}\n")
                log_file.write(f"Original: {data['original']}\n")
                log_file.write(f"Edited: {data['corrected']}\n")
                log_file.write(f"Log: {'; '.join(data['logs'])}\n\n")
        zipf.write(log_file_path, "updated_captions.txt")

@app.get("/")
def test_root():
    return {"status": "API is working!"}

    zip_buffer.seek(0)
    return FileResponse(zip_buffer, filename="processed_captions.zip", media_type="application/zip")
