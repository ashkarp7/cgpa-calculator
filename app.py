# app.py (UI-improved, progress indicator, cleaned table)
import streamlit as st
from ktu_cgpa import KTUCGPACalculator
import os
import json
import hashlib
from datetime import datetime
from pathlib import Path
from PyPDF2 import PdfReader
import tempfile
import pandas as pd
import io

# -------------------------
# Config & constants
# -------------------------
st.set_page_config(page_title="CGPA Calculator", layout="centered")
DATA_FILE = Path("records.json")  # local persistent store of processed file hashes/records

# Ensure data file exists
if not DATA_FILE.exists():
    DATA_FILE.write_text("[]")

# -------------------------
# Helper functions
# -------------------------
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

# -------------------------
# Small CSS for nicer UI
# -------------------------
st.markdown(
    """
    <style>
    :root {
      --accent: #0ea5a4;
      --card-bg: #0f172a;
      --muted: #9ca3af;
      --panel: #0b1220;
    }
    .app-header {
      background: linear-gradient(90deg, rgba(6,95,70,1) 0%, rgba(8,60,90,1) 100%);
      padding: 18px;
      border-radius: 10px;
      color: white;
      margin-bottom: 20px;
    }
    .app-sub {
      color: var(--muted);
      margin-top: 6px;
      margin-bottom: 14px;
    }
    .card {
      background: rgba(255,255,255,0.03);
      padding: 14px;
      border-radius: 10px;
      border: 1px solid rgba(255,255,255,0.03);
      margin-bottom: 12px;
    }
    .muted {
      color: var(--muted);
    }
    .small {
      font-size: 0.9rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Header
st.markdown('<div class="app-header"><h1 style="margin:0">CGPA Calculator — KTU Helper</h1><div class="app-sub">Upload KTU grade card PDFs. Each uploaded grade card must contain your Register No (identifier).</div></div>', unsafe_allow_html=True)

# -------------------------
# Inputs
# -------------------------
col1, col2 = st.columns([3,2])
with col1:
    user_identifier = st.text_input("Register No / Identifier (required)", "").strip()
with col2:
    # compact file uploader
    uploaded_files = st.file_uploader("Choose PDF grade card(s)", accept_multiple_files=True, type=["pdf"])

process_clicked = st.button("Process uploads", key="process_btn")

# Load existing hashes
existing_records = load_records()
existing_hashes = {r.get("file_hash") for r in existing_records if r.get("file_hash")}

# Info card for current user history
with st.expander("Your previous uploads (local history)", expanded=False):
    if existing_records:
        df_hist = pd.DataFrame(existing_records)
        # show only selected fields in history
        if not df_hist.empty:
            hist_df = df_hist[["file_name", "user_identifier", "semester", "month_year", "sgpa", "credits"]].copy()
            if "sgpa" in hist_df.columns:
                hist_df["sgpa"] = hist_df["sgpa"].apply(lambda x: f"{x:.2f}" if x is not None else "")
            st.dataframe(hist_df.sort_values(by="file_name").reset_index(drop=True))
    else:
        st.write("No previously processed records found.")

# -------------------------
# Processing logic
# -------------------------
if process_clicked:
    if not user_identifier:
        st.error("Identifier is required. Enter your Register No / Identifier.")
    elif not uploaded_files:
        st.warning("No files selected.")
    else:
        calc = KTUCGPACalculator()
        all_results = []
        rejected = []
        batch_hashes = set()
        total_files = len(uploaded_files)

        # progress bar + spinner
        progress_bar = st.progress(0)
        status_text = st.empty()
        with st.spinner("Processing files..."):
            for idx, f in enumerate(uploaded_files, start=1):
                status_text.info(f"Processing {idx}/{total_files}: {f.name}")
                try:
                    raw_bytes = f.read()
                    file_hash = compute_file_hash_bytes(raw_bytes)

                    # Duplicate checks
                    if file_hash in existing_hashes or file_hash in batch_hashes:
                        rejected.append((f.name, "Duplicate file (already used)"))
                        progress_bar.progress(idx / total_files)
                        continue

                    # Identifier validation using PDF text extraction
                    text = extract_text_from_pdf_bytes(raw_bytes)
                    if not text or user_identifier.lower() not in text.lower():
                        rejected.append((f.name, "Identifier not found in PDF text"))
                        progress_bar.progress(idx / total_files)
                        continue

                    # Save temp file, extract values
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

                    record = {
                        "file_name": f.name,
                        "file_hash": file_hash,
                        "user_identifier": user_identifier,
                        "sgpa": sgpa_num,
                        "credits": credits_num,
                        "semester": semester,
                        "month_year": month_year,
                        "saved_at": datetime.utcnow().isoformat()
                    }

                    # persist and accumulate
                    save_record(record)
                    existing_hashes.add(file_hash)
                    batch_hashes.add(file_hash)
                    all_results.append(record)

                except Exception as e:
                    rejected.append((f.name, f"Processing error: {e}"))
                finally:
                    progress_bar.progress(idx / total_files)

            status_text.empty()

        # After processing, show summary
        processed_count = len(all_results)
        rejected_count = len(rejected)
        duplicate_count = sum(1 for r in rejected if "Duplicate" in r[1])

        # Summary card
        st.markdown("<div class='card small'><strong>Summary</strong></div>", unsafe_allow_html=True)
        st.write(f"Processed: **{processed_count}**  |  Rejected: **{rejected_count}**  |  Duplicates: **{duplicate_count}**")

        # Show rejected details (if any) in a compact list
        if rejected:
            with st.expander(f"Rejected files ({len(rejected)})", expanded=True):
                for name, reason in rejected:
                    st.write(f"- **{name}** — {reason}")

        # Display results table (cleaned)
        if all_results:
            df = pd.DataFrame(all_results)
            # Format SGPA to always show two decimals (but keep computation on numeric values)
            df["sgpa_display"] = df["sgpa"].apply(lambda x: f"{x:.2f}" if pd.notnull(x) else "")
            # Build display table without file_hash and saved_at
            display_df = df[["file_name", "user_identifier", "semester", "month_year", "sgpa_display", "credits"]].copy()
            display_df = display_df.rename(columns={"sgpa_display": "sgpa", "file_name":"File", "user_identifier":"Identifier", "semester":"Semester", "month_year":"Exam", "credits":"Credits"})
            st.subheader("Newly Processed Results")
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

            # Download CSV button for newly processed results
            csv_buf = io.StringIO()
            csv_df = display_df.copy()
            csv_df.to_csv(csv_buf, index=False)
            csv_bytes = csv_buf.getvalue().encode("utf-8")
            st.download_button("Download results as CSV", data=csv_bytes, file_name="cgpa_results.csv", mime="text/csv")

        else:
            st.info("No new files were processed.")

# If not processing: show help/instructions
if not process_clicked:
    st.markdown(
        """
        <div class="card small">
        <strong>How to use</strong>
        <ol>
        <li>Enter your Register No / Identifier in the box above.</li>
        <li>Upload one or more KTU grade card PDFs (these must contain your identifier).</li>
        <li>Click <em>Process uploads</em>. A progress bar and status will show.</li>
        <li>Processed results will appear below with SGPA formatted to two decimals.</li>
        </ol>
        </div>
        """,
        unsafe_allow_html=True
    )
