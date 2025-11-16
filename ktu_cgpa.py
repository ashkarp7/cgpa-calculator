import PyPDF2
import re

class KTUCGPACalculator:
    def extract_sgpa_credits_from_pdf(self, pdf_path):
        pdf_reader = PyPDF2.PdfReader(pdf_path)
        text = ""
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text

        sgpa = self._extract_sgpa(text)
        credits = self._extract_credits(text)
        semester_info = self._extract_semester_info(text)

        return sgpa, credits, semester_info

    def _extract_sgpa(self, text):
        patterns = [
            r"SGPA[:\s]*([0-9]+\.?[0-9]*)",
            r"SGPA\s+([0-9]+\.[0-9]+)",
            r"([0-9]+\.[0-9]+)"
        ]

        for pat in patterns:
            sgpa_match = re.search(pat, text, re.IGNORECASE)
            if sgpa_match:
                try:
                    sgpa = float(sgpa_match.group(1))
                    if 4.0 <= sgpa <= 10.0:
                        return sgpa
                except (ValueError, IndexError):
                    continue
        return None

    def _extract_credits(self, text):
        patterns = [
            r"Total Credits[:\s]*([0-9]+)",
            r"Total Credits Earned[:\s]*([0-9]+)",
            r"Total Credits in the Semester[:\s]*([0-9]+)"
        ]
        for pat in patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                return float(match.group(1))
        return None

    def _extract_semester_info(self, text):
        info = {}
        patterns = [
            r"\b(S[1-8])\b",
            r"Semester\s*([A-Z0-9]+)",    
            r"Semester Grade.*?([A-Z0-9]+)", 
            r"Semester\s+(\w+)\s+([A-Z0-9]+)",
            r"Semester[:\s]*\n?(\S+)" 
        ]
        
        for pat in patterns:
            sem_match = re.search(pat, text, re.IGNORECASE)
            if sem_match:
                if len(sem_match.groups()) > 1:
                    info["semester"] = sem_match.group(2).strip()
                else:
                    info["semester"] = sem_match.group(1).strip()
                break
        
        date_match = re.search(r"([A-Za-z]+)\s+(\d{4})", text)
        if date_match:
            info["month"] = date_match.group(1)
            info["year"] = date_match.group(2)
        return info