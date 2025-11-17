# app.py (with identifier-check + duplicate-prevention + formatted SGPA)
import streamlit as st
from ktu_cgpa import KTUCGPACalculator
import os
import json
import hashlib
from datetime import datetime
from pathlib import Path
from PyPDF2 import PdfReader
import tempfile

# Config
st.set_page_config(page_title="CGPA Calculator", layout="centered")
st.title("CGPA Calculator — KTU Helper")
st.write("Upload KTU grade card PDF(s). Enter your Register No (identifier) — each uploaded grade card must contain it.")

DATA_FILE = Path("records.json")  # local persistent store of processed file hashes/records

# Ensure data file exists
if not DATA_FILE.exists():
    DATA_FILE.write_text("[]")

def load_records():
    try:
        return json.loads(DATA_FILE.read_text())
    except Exception:
        return []

def save_record(rec):
    records = load_records()
    records.append(rec)
    DATA_FILE.write_text(json.dumps(records, indent=2))

def compute_file_hash_bytes(content_bytes: bytes) -> str:
    h = hashlib.sha256()
    h.update(content_bytes)
    return h.hexdigest()

def extract_text_from_pdf_bytes(content_bytes: bytes) -> str:
    # write temp file and use PyPDF2 to read text
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(content_bytes)
        tmp_path = tmp.name
    try:
        reader = PdfReader(tmp_path)
        text_parts = []
        for p in reader.pages:
            try:
                t = p.extract_text()
                if t:
                    text_parts.append(t)
            except Exception:
                continue
        return "\n".join(text_parts)
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

# UI: identifier is required now
user_identifier = st.text_input("Register No / Identifier (required)", "").strip()
if not user_identifier:
    st.info("Enter your Register No / Identifier before uploading files.")
uploaded_files = st.file_uploader("Choose PDF grade card(s)", accept_multiple_files=True, type=["pdf"])

process_clicked = st.button("Process uploads")

# Load existing hashes
existing_records = load_records()
existing_hashes = {r.get("file_hash") for r in existing_records if r.get("file_hash")}

if process_clicked:
    if not user_identifier:
        st.error("Identifier is required. Enter your Register No / Identifier.")
    elif not uploaded_files:
        st.warning("No files selected.")
    else:
        calc = KTUCGPACalculator()
        all_results = []
        batch_hashes = set()  # to prevent duplicates inside same upload batch
        rejected = []

        for f in uploaded_files:
            try:
                raw_bytes = f.read()
                # 1) compute hash and check duplicates
                file_hash = compute_file_hash_bytes(raw_bytes)
                if file_hash in existing_hashes or file_hash in batch_hashes:
                    rejected.append((f.name, "Duplicate file (already used)"))
                    continue

                # 2) extract text and verify identifier present (case-insensitive)
                text = extract_text_from_pdf_bytes(raw_bytes)
                if not text or user_identifier.lower() not in text.lower():
                    rejected.append((f.name, "Identifier not found in PDF text"))
                    continue

                # 3) save temp file and call ktu extractor
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(raw_bytes)
                    tmp_path = tmp.name
                try:
                    sgpa, credits, sem_info = calc.extract_sgpa_credits_from_pdf(tmp_path)
                finally:
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass

                sgpa_num = float(sgpa) if sgpa is not None else None
                credits_num = float(credits) if credits is not None else None
                semester = sem_info.get("semester", "Unknown") if isinstance(sem_info, dict) else "Unknown"
                month_year = f"{sem_info.get('month','')} {sem_info.get('year','')}".strip() if isinstance(sem_info, dict) else ""

                # Build record and store
                record = {
                    "file_name": f.name,
                    "file_hash": file_hash,
                    "user_identifier": user_identifier,
                    "sgpa": sgpa_num,
                    "credits": credits_num,
                    "semester": semester,
                    "month_year": month_year,
                    "saved_at": datetime.utcnow().isoformat()  # local record timestamp
                }
                save_record(record)
                existing_hashes.add(file_hash)
                batch_hashes.add(file_hash)
                all_results.append(record)
                st.success(f"Processed {f.name} — SGPA: {sgpa_num if sgpa_num is not None else 'N/A'} Credits: {credits_num if credits_num is not None else 'N/A'}")

            except Exception as e:
                rejected.append((f.name, f"Processing error: {e}"))

        # Show rejected info
        if rejected:
            st.error("Some files were rejected:")
            for name, reason in rejected:
                st.write(f"- **{name}** — {reason}")

        # Show results table and compute CGPA (format SGPA to 2 decimals)
        if all_results:
            import pandas as pd
            df = pd.DataFrame(all_results)
            # format sgpa display
            df["sgpa_display"] = df["sgpa"].apply(lambda x: f"{x:.2f}" if x is not None else "")
            display_df = df.drop(columns=["sgpa"]).rename(columns={"sgpa_display": "sgpa"})
            st.subheader("Extraction Results")
            st.dataframe(display_df.reset_index(drop=True))

            # compute weighted CGPA
            total_weighted = 0.0
            total_credits = 0.0
            for r in all_results:
                if r["sgpa"] is not None and r["credits"] is not None:
                    total_weighted += r["sgpa"] * r["credits"]
                    total_credits += r["credits"]
            if total_credits > 0:
                cum_cgpa = round(total_weighted / total_credits, 2)
                st.success(f"Cumulative CGPA (weighted): {cum_cgpa:.2f}")
            else:
                st.info("Not enough credit/SGPA data to compute cumulative CGPA.")
        else:
            st.info("No new files were processed.")
