# app.py (updated)
import streamlit as st
from ktu_cgpa import KTUCGPACalculator
import os
from datetime import datetime

st.set_page_config(page_title="CGPA Calculator", layout="centered")

st.title("CGPA Calculator — KTU Helper")
st.write("Upload KTU grade card PDF(s). The app will extract SGPA & credits and compute CGPA locally.")

# Simple identifier (optional, since you removed login)
user_identifier = st.text_input("Enter an identifier (email or roll no) to tag saved records (optional):", "")

uploaded_files = st.file_uploader("Choose PDF grade card(s)", accept_multiple_files=True, type=["pdf"])

if st.button("Process uploads") and uploaded_files:
    calc = KTUCGPACalculator()
    all_results = []
    for f in uploaded_files:
        temp_path = f"temp_{f.name}"
        with open(temp_path, "wb") as out:
            out.write(f.getbuffer())

        try:
            sgpa, credits, sem_info = calc.extract_sgpa_credits_from_pdf(temp_path)
            # Keep numeric versions for calculation
            sgpa_num = float(sgpa) if sgpa is not None else None
            credits_num = float(credits) if credits is not None else None

            semester = sem_info.get("semester", "Unknown") if isinstance(sem_info, dict) else "Unknown"
            month_year = f"{sem_info.get('month','')} {sem_info.get('year','')}".strip() if isinstance(sem_info, dict) else ""

            record = {
                "file_name": f.name,
                "sgpa": sgpa_num,
                "credits": credits_num,
                "semester": semester,
                "month_year": month_year,
                "user": user_identifier or "anonymous"
            }
            all_results.append(record)

            st.success(f"Extracted from {f.name}: SGPA={sgpa_num if sgpa_num is not None else 'N/A'} Credits={credits_num if credits_num is not None else 'N/A'} Semester={semester}")

        except Exception as e:
            st.error(f"Failed to extract from {f.name}: {e}")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # Display table and compute cumulative CGPA
    if all_results:
        import pandas as pd
        df = pd.DataFrame(all_results)

        # Format SGPA to always show two decimals (but keep computation on numeric values)
        if "sgpa" in df.columns:
            df["sgpa_display"] = df["sgpa"].apply(lambda x: f"{x:.2f}" if pd.notnull(x) else "")
        else:
            df["sgpa_display"] = ""

        # Optionally hide the raw numeric sgpa column and show sgpa_display instead
        display_df = df.copy()
        if "sgpa" in display_df.columns:
            display_df = display_df.drop(columns=["sgpa"])
        display_df = display_df.rename(columns={"sgpa_display": "sgpa"})

        st.subheader("Extraction Results")
        st.dataframe(display_df.reset_index(drop=True))

        # Compute cumulative CGPA using weighted average where credits exist
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
            st.info("Not enough credit data to compute cumulative CGPA.")
else:
    if not uploaded_files:
        st.info("No files selected yet. Upload one or more KTU grade card PDFs to begin.")
