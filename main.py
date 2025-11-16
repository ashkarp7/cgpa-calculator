# main.py (modified)
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import os
from ktu_cgpa import KTUCGPACalculator
from google.cloud import firestore
from datetime import datetime
import tempfile

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Init Firestore client if service account is available
sa_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", None)
db = None
if sa_path and os.path.exists(sa_path):
    try:
        db = firestore.Client.from_service_account_json(sa_path)
        print("Firestore initialized.")
    except Exception as e:
        print("Failed to init Firestore:", e)
else:
    print("No GOOGLE_APPLICATION_CREDENTIALS set or path invalid. Firestore disabled.")

calculator = KTUCGPACalculator()

def _process_temp_file(temp_path):
    sgpa, credits, sem_info = calculator.extract_sgpa_credits_from_pdf(temp_path)
    sem = sem_info.get("semester", "Unknown") if isinstance(sem_info, dict) else "Unknown"
    month_year = f"{sem_info.get('month','')} {sem_info.get('year','')}".strip() if isinstance(sem_info, dict) else ""
    return {
        "sgpa": sgpa,
        "credits": credits,
        "semester": sem,
        "month_year": month_year
    }

@app.post("/extract_single")
async def extract_single(file: UploadFile = File(...), userId: str = Form(None)):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload a PDF.")
    try:
        # save to temp file
        suffix = os.path.splitext(file.filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        result = _process_temp_file(tmp_path)

        # Save to Firestore if configured
        if db is not None:
            try:
                doc = {
                    "userId": userId or "anonymous",
                    "fileName": file.filename,
                    "semester": result["semester"],
                    "sgpa": result["sgpa"],
                    "credits": result["credits"],
                    "month_year": result["month_year"],
                    "createdAt": datetime.utcnow().isoformat()
                }
                db.collection("cgpa_records").add(doc)
            except Exception as e:
                # don't fail the endpoint just because of Firestore issues
                print("Firestore save failed:", e)

        return {"ok": True, "file": file.filename, "result": result}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.post("/extract_multi")
async def extract_multi(files: List[UploadFile] = File(...), userId: str = Form(None)):
    responses = []
    for file in files:
        if file.content_type != "application/pdf":
            responses.append({"file": file.filename, "error": "Invalid file type"})
            continue
        try:
            suffix = os.path.splitext(file.filename)[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                content = await file.read()
                tmp.write(content)
                tmp_path = tmp.name

            result = _process_temp_file(tmp_path)

            # Save to Firestore if enabled
            if db is not None:
                try:
                    doc = {
                        "userId": userId or "anonymous",
                        "fileName": file.filename,
                        "semester": result["semester"],
                        "sgpa": result["sgpa"],
                        "credits": result["credits"],
                        "month_year": result["month_year"],
                        "createdAt": datetime.utcnow().isoformat()
                    }
                    db.collection("cgpa_records").add(doc)
                except Exception as e:
                    print("Firestore save failed:", e)

            responses.append({"file": file.filename, "result": result})
        except Exception as e:
            responses.append({"file": file.filename, "error": str(e)})
        finally:
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                os.remove(tmp_path)

    return {"ok": True, "files": responses}
